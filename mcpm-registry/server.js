// mcpm-registry/server.js
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const cors = require('cors');

const app = express();
const port = process.env.PORT || 8000; // Default port 8000

// --- Configuration ---
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const DB_PATH = path.join(__dirname, 'db', 'registry.db');
const PUBLIC_DIR = path.join(__dirname, 'public');

// Default config command for new servers
const DEFAULT_CONFIG_COMMAND = JSON.stringify({
    mcpServers: {
      "{server_name}": { // Placeholder for the actual server name
        command: "some_command", // Example command
        args: ["arg1", "arg2"], // Example args
        // Add other necessary config like env vars if needed
      }
    }
  }, null, 2); // Pretty print JSON with 2 spaces

// Ensure upload directory exists
fs.mkdirSync(UPLOAD_DIR, { recursive: true });
fs.mkdirSync(path.dirname(DB_PATH), { recursive: true }); // Ensure db dir exists

// --- Database Setup ---
const db = new sqlite3.Database(DB_PATH, (err) => {
    if (err) {
        console.error("Error opening database", err.message);
    } else {
        console.log("Connected to the SQLite database.");
        db.serialize(() => { // Use serialize to ensure table creation happens in order
            // Create packages table if it doesn't exist
            db.run(`CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                description TEXT,
                entrypoint TEXT,
                author TEXT,
                license TEXT,
                filename TEXT NOT NULL, -- Name of the stored zip file
                upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, version) -- Prevent duplicate package versions
            )`, (err) => {
                if (err) {
                    console.error("Error creating packages table", err.message);
                } else {
                    console.log("Packages table ready.");
                }
            });

            // Create servers table if it doesn't exist
            db.run(`CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                github_url TEXT,
                language TEXT,
                config_command TEXT,
                registration_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )`, (err) => {
                if (err) {
                    console.error("Error creating servers table", err.message);
                } else {
                    console.log("Servers table ready.");
                }
            });
        });
    }
});

// --- Middleware ---
app.use(cors()); // Enable CORS for all origins (adjust for production)
app.use(express.json()); // For parsing application/json
app.use(express.urlencoded({ extended: true })); // For parsing application/x-www-form-urlencoded
app.use(express.static(PUBLIC_DIR)); // Serve static files from public/

// --- File Upload Setup (Multer) ---
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        cb(null, UPLOAD_DIR); // Store files in the uploads directory
    },
    filename: function (req, file, cb) {
        // Use a unique filename to avoid collisions, maybe based on package name/version + timestamp?
        // For now, just use the original name; the publish endpoint will rename appropriately if needed
        // or store the mapping in the DB. Let's store the actual filename in DB.
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        const finalFilename = uniqueSuffix + '-' + file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_'); // Sanitize
        cb(null, finalFilename);
    }
});
const upload = multer({
    storage: storage,
    limits: { fileSize: 100 * 1024 * 1024 } // Limit file size (e.g., 100MB)
});

// --- API Routes ---

// GET /api/packages/ - List all packages (latest version of each)
app.get('/api/packages/', (req, res) => {
    // Query to get the latest version for each package name
    const sql = `
        SELECT p1.*
        FROM packages p1
        LEFT JOIN packages p2 ON p1.name = p2.name AND p1.upload_time < p2.upload_time
        WHERE p2.id IS NULL
        ORDER BY p1.name ASC;
    `;
    db.all(sql, [], (err, rows) => {
        if (err) {
            console.error("Error fetching packages:", err.message);
            res.status(500).json({ error: "Internal server error", details: err.message });
        } else {
            // Map to a cleaner format expected by mcpm client (adjust as needed)
            const packageList = rows.map(row => ({
                name: row.name,
                latest_version: row.version,
                description: row.description
            }));
            res.json(packageList);
        }
    });
});

// POST /api/packages/publish - Publish a new package
// Expects multipart/form-data with 'package' (the zip file) and 'metadata' (JSON string)
app.post('/api/packages/publish', upload.single('package'), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: "No package file uploaded." });
    }
    if (!req.body.metadata) {
        // Cleanup uploaded file if metadata is missing
        fs.unlink(req.file.path, (err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Missing package metadata." });
    }

    let metadata;
    try {
        metadata = JSON.parse(req.body.metadata);
    } catch (e) {
        fs.unlink(req.file.path, (err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Invalid metadata JSON.", details: e.message });
    }

    // Validate required metadata fields
    const { name, version, description, entrypoint, author, license } = metadata;
    if (!name || !version) {
        fs.unlink(req.file.path, (err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Metadata must include 'name' and 'version'." });
    }

    const filename = req.file.filename; // The unique filename assigned by multer

    const sql = `INSERT INTO packages (name, version, description, entrypoint, author, license, filename)
                 VALUES (?, ?, ?, ?, ?, ?, ?)`;
    const params = [name, version, description, entrypoint, author, license, filename];

    db.run(sql, params, function(err) { // Use function() to access this.lastID
        if (err) {
            fs.unlink(req.file.path, (unlinkErr) => { // Cleanup file on DB error
                if (unlinkErr) console.error("Error removing upload after DB fail:", unlinkErr.message);
            });
            if (err.message.includes('UNIQUE constraint failed')) {
                console.error(`Publish error: Package ${name} version ${version} already exists.`);
                res.status(409).json({ error: `Package ${name} version ${version} already exists.`, details: err.message });
            } else {
                console.error("Error inserting package metadata:", err.message);
                res.status(500).json({ error: "Failed to save package metadata.", details: err.message });
            }
        } else {
            console.log(`Package ${name} v${version} published successfully. ID: ${this.lastID}, File: ${filename}`);
            res.status(201).json({ message: "Package published successfully.", packageId: this.lastID, name: name, version: version });
        }
    });
});

// GET /api/packages/:name/:version/download - Download a specific package version
app.get('/api/packages/:name/:version/download', (req, res) => {
    const { name } = req.params;
    let version = req.params.version;

    const findAndSendFile = (packageName, packageVersion) => {
        // Find the corresponding filename in the database
        const sql = "SELECT filename FROM packages WHERE name = ? AND version = ?";
        db.get(sql, [packageName, packageVersion], (err, row) => {
            if (err) {
                console.error(`Error finding package ${packageName} v${packageVersion}:`, err.message);
                return res.status(500).json({ error: "Internal server error finding package", details: err.message });
            }
            if (!row) {
                return res.status(404).json({ error: `Package ${packageName} version ${packageVersion} not found.` });
            }

            const filename = row.filename;
            const filePath = path.join(UPLOAD_DIR, filename);

            // Check if file exists before sending
            fs.access(filePath, fs.constants.R_OK, (err) => {
                if (err) {
                    console.error(`File not found or unreadable: ${filePath}`, err);
                    return res.status(404).json({ error: `Package file for ${packageName} version ${packageVersion} not found on server.` });
                }

                // Set headers for file download
                res.setHeader('Content-Disposition', `attachment; filename="${packageName}-${packageVersion}.zip"`);
                res.setHeader('Content-Type', 'application/zip');

                // Stream the file
                const fileStream = fs.createReadStream(filePath);
                fileStream.pipe(res);

                fileStream.on('error', (streamErr) => {
                    console.error(`Error streaming file ${filePath}:`, streamErr);
                    if (!res.headersSent) {
                        res.status(500).json({ error: "Error reading package file." });
                    }
                });

                 fileStream.on('close', () => {
                    console.log(`Sent file ${filePath} for ${packageName} v${packageVersion}`);
                 });
            });
        });
    };

    if (version.toLowerCase() === 'latest') {
        // Query for the latest version based on upload_time
        const latestVersionSql = `SELECT version
                                  FROM packages
                                  WHERE name = ?
                                  ORDER BY upload_time DESC
                                  LIMIT 1`;
        db.get(latestVersionSql, [name], (err, row) => {
            if (err) {
                console.error(`Error finding latest version for package ${name}:`, err.message);
                return res.status(500).json({ error: "Internal server error finding latest version", details: err.message });
            }
            if (!row) {
                return res.status(404).json({ error: `Package ${name} not found.` });
            }
            const latestVersion = row.version;
            console.log(`Request for latest version of ${name}, resolved to ${latestVersion}`);
            findAndSendFile(name, latestVersion);
        });
    } else {
        // Use the specific version provided
        findAndSendFile(name, version);
    }
});

// --- Server Registration Routes (New) ---

// GET /api/servers - List all registered servers
app.get('/api/servers', (req, res) => {
    const sql = "SELECT id, name, github_url, language, config_command, registration_time FROM servers ORDER BY name ASC";
    db.all(sql, [], (err, rows) => {
        if (err) {
            console.error("Error fetching servers:", err.message);
            res.status(500).json({ error: "Internal server error", details: err.message });
        } else {
            res.json(rows);
        }
    });
});

// POST /api/servers - Register a new server
app.post('/api/servers', (req, res) => {
    const { name, github_url, language, config_command } = req.body;

    if (!name) {
        return res.status(400).json({ error: "Server 'name' is required." });
    }
    // Basic validation for language if provided
    const allowedLanguages = ['Python', 'Go', 'Typescript', 'Other', null, undefined, '']; // Allow empty/null or specific values
    if (!allowedLanguages.includes(language)) {
         return res.status(400).json({ error: `Invalid language specified. Allowed: ${allowedLanguages.filter(l => l).join(', ')} or leave empty.` });
    }

    // Use provided config or default if empty/missing
    const final_config_command = (config_command && config_command.trim() !== '')
        ? config_command
        : DEFAULT_CONFIG_COMMAND.replace("{server_name}", name); // Insert name into default

    const sql = `INSERT INTO servers (name, github_url, language, config_command)
                 VALUES (?, ?, ?, ?)`;
    const params = [name, github_url, language, final_config_command];

    db.run(sql, params, function(err) {
        if (err) {
            if (err.message.includes('UNIQUE constraint failed')) {
                console.error(`Registration error: Server name '${name}' already exists.`);
                res.status(409).json({ error: `Server name '${name}' already exists.`, details: err.message });
            } else {
                console.error("Error inserting server registration:", err.message);
                res.status(500).json({ error: "Failed to save server registration.", details: err.message });
            }
        } else {
            console.log(`Server '${name}' registered successfully. ID: ${this.lastID}`);
            res.status(201).json({
                message: "Server registered successfully.",
                serverId: this.lastID,
                name: name,
                github_url: github_url,
                language: language,
                config_command: final_config_command // Return the actual config used
            });
        }
    });
});

// --- Root Route (Serve UI) ---
app.get('/', (req, res) => {
    res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
});

// --- Start Server ---
app.listen(port, () => {
    console.log(`mcpm-registry server listening on port ${port}`);
    console.log(`Serving static files from: ${PUBLIC_DIR}`);
    console.log(`Storing package files in: ${UPLOAD_DIR}`);
    console.log(`Using database at: ${DB_PATH}`);
});

// --- Graceful Shutdown ---
process.on('SIGINT', () => {
    console.log('SIGINT signal received: closing database connection.');
    db.close((err) => {
        if (err) {
            console.error(err.message);
        }
        console.log('Closed the database connection.');
        process.exit(0);
    });
});
