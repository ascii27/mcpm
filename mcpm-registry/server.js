// mcpm-registry/server.js
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const multer = require('multer');
const path = require('path');
const fs = require('fs'); // Import the core fs module for sync operations
const fsPromises = require('fs').promises; // Import promises API separately
const cors = require('cors');

const app = express();
const port = process.env.PORT || 8000; // Default port 8000

// --- Configuration ---
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const DB_DIR = path.join(__dirname, 'db');
const DB_PATH = path.join(DB_DIR, 'registry.db');
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

// Ensure upload and db directories exist
fs.mkdirSync(UPLOAD_DIR, { recursive: true }); // This should now work
fs.mkdirSync(DB_DIR, { recursive: true });

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

            // Servers table (MODIFIED SCHEMA)
            db.run(`DROP TABLE IF EXISTS servers`); // Drop for schema change during dev
            db.run(`CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                registry_name TEXT NOT NULL UNIQUE, -- Generated, unique name for lookup
                github_url TEXT,
                language TEXT,
                config_command TEXT,
                registration_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )`, (createErr) => {
                if (createErr) {
                     console.error("Error creating servers table:", createErr.message);
                 } else {
                    console.log("Servers table created or already exists.");
                 }
            });
        });
    }
});

// --- Helper ---
function generateRegistryName(displayName) {
    if (!displayName) return '';
    // Lowercase, replace spaces with hyphens, remove other problematic chars (basic example)
    return displayName
        .toLowerCase()
        .replace(/\s+/g, '-') // Replace spaces with hyphens
        .replace(/[^a-z0-9\-]/g, ''); // Remove non-alphanumeric/non-hyphen chars
}

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
        LEFT JOIN packages p2 ON p1.install_name = p2.install_name AND p1.upload_time < p2.upload_time
        WHERE p2.id IS NULL
        ORDER BY p1.name ASC;
    `;
    db.all(sql, [], (err, rows) => {
        if (err) {
            console.error("Error fetching packages:", err.message);
            res.status(500).json({ error: "Internal server error", details: err.message });
        } else {
            // Include install_name in the response for each package
            const packageList = rows.map(row => ({
                name: row.name, // Display name
                install_name: row.install_name,
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
        fsPromises.unlink(req.file.path).catch((err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Missing package metadata." });
    }

    let metadata;
    try {
        metadata = JSON.parse(req.body.metadata);
    } catch (e) {
        fsPromises.unlink(req.file.path).catch((err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Invalid metadata JSON.", details: e.message });
    }

    // Validate required metadata fields
    let { name, version, description, entrypoint, author, license } = metadata;
    // Treat 'name' as display name, generate install name
    let displayName = name;
    let installName = null;
    if (displayName) {
        installName = displayName.trim().toLowerCase()
            .replace(/[^a-z0-9\-_\s]/g, "") // Remove non-alphanum (except dash/underscore/space)
            .replace(/\s+/g, "-"); // Replace whitespace with dash
    } else {
        // Fallback: use filename as before
        let fallback = req.file.originalname || req.file.filename;
        fallback = fallback.replace(/\.zip$/i, "");
        fallback = fallback.replace(/-\d+(?:\.\d+)*$/, "");
        displayName = fallback;
        installName = fallback.toLowerCase().replace(/[^a-z0-9\-_]/g, "-");
    }
    metadata.name = displayName;
    metadata.install_name = installName;
    if (!displayName || !installName || !version) {
        fsPromises.unlink(req.file.path).catch((err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Metadata must include 'name' and 'version'. (Name can be auto-generated from filename if omitted)" });
    }

    const filename = req.file.filename; // The unique filename assigned by multer

    // Update SQL to store both display name and install name
    const sql = `INSERT INTO packages (name, install_name, version, description, entrypoint, author, license, filename)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`;
    const params = [displayName, installName, version, description, entrypoint, author, license, filename];

    db.run(sql, params, function(err) { // Use function() to access this.lastID
        if (err) {
            fsPromises.unlink(req.file.path).catch((err) => {
                if (err) console.error("Error removing upload after DB fail:", err.message);
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
        // Try to find by install_name first, then by display name
        const sql = `SELECT filename FROM packages WHERE (install_name = ? OR name = ?) AND version = ?`;
        db.get(sql, [packageName, packageName, packageVersion], (err, row) => {
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
            fsPromises.access(filePath, fs.constants.R_OK).catch((err) => {
                console.error(`File not found or unreadable: ${filePath}`, err);
                return res.status(404).json({ error: `Package file for ${packageName} version ${packageVersion} not found on server.` });
            }).then(() => {
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
        // Query for the latest version based on upload_time, matching by install_name or name
        const latestVersionSql = `SELECT version, install_name, name
                                  FROM packages
                                  WHERE install_name = ? OR name = ?
                                  ORDER BY upload_time DESC
                                  LIMIT 1`;
        db.get(latestVersionSql, [name, name], (err, row) => {
            if (err) {
                console.error(`Error finding latest version for package ${name}:`, err.message);
                return res.status(500).json({ error: "Internal server error finding latest version", details: err.message });
            }
            if (!row) {
                return res.status(404).json({ error: `Package ${name} not found.` });
            }
            const latestVersion = row.version;
            const resolvedName = row.install_name || row.name;
            console.log(`Request for latest version of ${name}, resolved to ${latestVersion} (resolved name: ${resolvedName})`);
            findAndSendFile(resolvedName, latestVersion);
        });
    } else {
        // Use the specific version provided
        findAndSendFile(name, version);
    }
});



// --- DELETE Endpoints ---

// Delete a package (all versions) and its files
app.delete('/api/packages/:name', async (req, res) => {
    const nameToDelete = req.params.name;
    console.log(`Attempting to delete package: ${nameToDelete}`);

    // 1. Find all package entries and filenames for this name
    db.all(`SELECT filename FROM packages WHERE name = ?`, [nameToDelete], async (err, rows) => {
        if (err) {
            console.error("Database error finding package files:", err.message);
            return res.status(500).json({ message: 'Error finding package files', error: err.message });
        }

        if (rows.length === 0) {
            return res.status(404).json({ message: `Package '${nameToDelete}' not found` });
        }

        const filenames = rows.map(row => row.filename);
        console.log(`Found filenames to delete:`, filenames);

        // 2. Delete associated files from uploads directory
        const deleteFilePromises = filenames.map(filename => {
            const filePath = path.join(UPLOAD_DIR, filename);
            console.log(`Attempting to delete file: ${filePath}`);
            return fsPromises.unlink(filePath).catch(fileErr => {
                 // Log error but continue trying to delete others/DB entry
                 console.error(`Error deleting file ${filePath}:`, fileErr.message);
                 // If file not found, it might have been deleted already, which is okay
                 if (fileErr.code !== 'ENOENT') {
                    throw fileErr; // Re-throw other errors
                 }
            });
        });

        try {
            await Promise.all(deleteFilePromises);
            console.log(`Successfully deleted associated files (or they were already gone).`);
        } catch (fileErr) {
             // If any critical file deletion error occurred (other than ENOENT)
             console.error("Critical error during file deletion:", fileErr.message);
             // Decide if you want to stop or proceed with DB deletion
             // Proceeding: return res.status(500).json({ message: 'Error deleting package files', error: fileErr.message });
        }


        // 3. Delete package entries from the database
        db.run(`DELETE FROM packages WHERE name = ?`, [nameToDelete], function(dbErr) {
            if (dbErr) {
                console.error("Database error deleting package entries:", dbErr.message);
                // File deletion might have partially succeeded, this is tricky state
                return res.status(500).json({ message: 'Error deleting package from database after attempting file removal', error: dbErr.message });
            }
            console.log(`Deleted ${this.changes} package entries for '${nameToDelete}' from database.`);
             if (this.changes === 0) {
                 // This case should theoretically not happen if rows were found earlier, but good practice
                 console.warn(`Inconsistency: Found package rows earlier but deleted 0 rows for ${nameToDelete}`);
                 return res.status(404).json({ message: `Package '${nameToDelete}' found initially but couldn't delete from DB` });
             }

            res.status(200).json({ message: `Package '${nameToDelete}' and its associated files deleted successfully` });
        });
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
