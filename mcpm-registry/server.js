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
            // Note: We previously dropped the packages table which caused data loss
            // In the future, we should use ALTER TABLE instead of DROP TABLE
            // For now, we'll just create the table if it doesn't exist
            
            // Create packages table with updated schema
            db.run(`CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL, -- The nice looking name
                package_name TEXT NOT NULL, -- Normalized name for installation (lowercase, dashes instead of spaces)
                version TEXT NOT NULL,
                description TEXT,
                entrypoint TEXT,
                author TEXT,
                license TEXT,
                filename TEXT NOT NULL, -- Name of the stored zip file
                upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(package_name, version) -- Prevent duplicate package versions
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
            
            // Create downloads table if it doesn't exist
            db.run(`CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package_name TEXT NOT NULL,
                package_version TEXT NOT NULL,
                download_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )`, (err) => {
                if (err) {
                    console.error("Error creating downloads table", err.message);
                } else {
                    console.log("Downloads table ready.");
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
        LEFT JOIN packages p2 ON p1.package_name = p2.package_name AND p1.upload_time < p2.upload_time
        WHERE p2.id IS NULL
        ORDER BY p1.display_name ASC;
    `;
    db.all(sql, [], (err, rows) => {
        if (err) {
            console.error("Error fetching packages:", err.message);
            res.status(500).json({ error: "Internal server error", details: err.message });
        } else {
            // Format the response with both display_name and package_name
            const packageList = rows.map(row => ({
                name: row.display_name, // Nice looking name for display
                package_name: row.package_name, // Normalized name for installation
                latest_version: row.version,
                description: row.description,
                author: row.author
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
    
    // Set display name (the nice looking one)
    let displayName = name;
    
    // Generate package name (for installation/uninstallation)
    // Package name should be the same as display name but lowercase with spaces replaced by dashes
    let packageName = null;
    
    if (displayName) {
        // Normalize package name: lowercase and replace spaces with dashes
        packageName = displayName.trim().toLowerCase()
            .replace(/[^a-z0-9\-_\s]/g, "") // Remove non-alphanum (except dash/underscore/space)
            .replace(/\s+/g, "-"); // Replace whitespace with dash
    } else {
        // Fallback: use filename if no name provided
        let fallback = req.file.originalname || req.file.filename;
        fallback = fallback.replace(/\.mcpz$/i, ""); // Remove .mcpz extension
        fallback = fallback.replace(/-\d+(?:\.\d+)*$/, ""); // Remove version numbers
        displayName = fallback;
        packageName = fallback.toLowerCase().replace(/[^a-z0-9\-_]/g, "-");
    }
    metadata.display_name = displayName;
    metadata.package_name = packageName;
    if (!displayName || !packageName || !version) {
        fsPromises.unlink(req.file.path).catch((err) => {
            if (err) console.error("Error removing orphaned upload:", err.message);
        });
        return res.status(400).json({ error: "Metadata must include 'name' and 'version'. (Name can be auto-generated from filename if omitted)" });
    }

    const filename = req.file.filename; // The unique filename assigned by multer

    // Update SQL to store both display name and package name
    const sql = `INSERT INTO packages (display_name, package_name, version, description, entrypoint, author, license, filename)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`;
    const params = [displayName, packageName, version, description, entrypoint, author, license, filename];

    db.run(sql, params, function(err) { // Use function() to access this.lastID
        if (err) {
            fsPromises.unlink(req.file.path).catch((err) => {
                if (err) console.error("Error removing upload after DB fail:", err.message);
            });
            if (err.message.includes('UNIQUE constraint failed')) {
                console.error(`Publish error: Package ${displayName} version ${version} already exists.`);
                res.status(409).json({ error: `Package ${displayName} version ${version} already exists.`, details: err.message });
            } else {
                console.error("Error inserting package metadata:", err.message);
                res.status(500).json({ error: "Failed to save package metadata.", details: err.message });
            }
        } else {
            console.log(`Package ${displayName} v${version} published successfully. ID: ${this.lastID}, File: ${filename}`);
            res.status(201).json({ message: "Package published successfully.", packageId: this.lastID, name: displayName, version: version });
        }
    });
});

// GET /api/packages/:name/:version/download - Download a specific package version
app.get('/api/packages/:name/:version/download', (req, res) => {
    const { name } = req.params;
    let version = req.params.version;

    const findAndSendFile = (packageName, packageVersion) => {
        // Try to find by package_name first, then by display_name
        const sql = `SELECT filename, package_name FROM packages WHERE (package_name = ? OR display_name = ?) AND version = ?`;
        db.get(sql, [packageName, packageName, packageVersion], (err, row) => {
            if (err) {
                console.error(`Error finding package ${packageName} v${packageVersion}:`, err.message);
                return res.status(500).json({ error: "Internal server error finding package", details: err.message });
            }
            if (!row) {
                return res.status(404).json({ error: `Package ${packageName} version ${packageVersion} not found.` });
            }

            const filename = row.filename;
            const packageName = row.package_name;
            const filePath = path.join(UPLOAD_DIR, filename);

            // Record the download
            const downloadSql = `INSERT INTO downloads (package_name, package_version) VALUES (?, ?)`;
            db.run(downloadSql, [packageName, packageVersion], (downloadErr) => {
                if (downloadErr) {
                    console.error(`Error recording download for ${packageName} v${packageVersion}:`, downloadErr.message);
                    // Continue with download even if tracking fails
                }
            });

            // Check if file exists before sending
            fsPromises.access(filePath, fs.constants.R_OK).catch((err) => {
                console.error(`File not found or unreadable: ${filePath}`, err);
                return res.status(404).json({ error: `Package file for ${packageName} version ${packageVersion} not found on server.` });
            }).then(() => {
                // Set headers for file download
                res.setHeader('Content-Disposition', `attachment; filename="${packageName}-${packageVersion}.mcpz"`);
                res.setHeader('Content-Type', 'application/octet-stream');

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
        // Query for the latest version based on upload_time, matching by package_name or display_name
        const latestVersionSql = `SELECT version, package_name, display_name
                                  FROM packages
                                  WHERE package_name = ? OR display_name = ?
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
            const resolvedName = row.package_name || row.display_name;
            console.log(`Request for latest version of ${name}, resolved to ${latestVersion} (resolved name: ${resolvedName})`);
            findAndSendFile(resolvedName, latestVersion);
        });
    } else {
        // Use the specific version provided
        findAndSendFile(name, version);
    }
});

// --- GET Package Details ---

// GET /api/packages/:name - Get details for a specific package
app.get('/api/packages/:name', (req, res) => {
    const nameParam = req.params.name;
    
    // Query to get the latest version of the package
    const sql = `
        SELECT p1.*, 
               (SELECT COUNT(*) FROM packages WHERE package_name = p1.package_name) as version_count,
               (SELECT COUNT(*) FROM downloads WHERE package_name = p1.package_name) as download_count
        FROM packages p1
        LEFT JOIN packages p2 ON p1.package_name = p2.package_name AND p1.upload_time < p2.upload_time
        WHERE (p1.package_name = ? OR p1.display_name = ?) AND p2.id IS NULL
    `;
    
    db.get(sql, [nameParam, nameParam], (err, row) => {
        if (err) {
            console.error(`Error fetching package ${nameParam}:`, err.message);
            return res.status(500).json({ error: "Internal server error", details: err.message });
        }
        
        if (!row) {
            return res.status(404).json({ error: `Package ${nameParam} not found.` });
        }
        
        // Format the response
        const packageDetails = {
            name: row.display_name,
            package_name: row.package_name,
            latest_version: row.version,
            description: row.description,
            author: row.author,
            license: row.license,
            entrypoint: row.entrypoint,
            version_count: row.version_count,
            download_count: row.download_count || 0,
            updated_at: row.upload_time
        };
        
        res.json(packageDetails);
    });
});

// GET /api/packages/:name/versions - Get all versions of a package
app.get('/api/packages/:name/versions', (req, res) => {
    const nameParam = req.params.name;
    
    // Query to get all versions of the package
    const sql = `
        SELECT version, upload_time as released_at,
               (SELECT COUNT(*) FROM downloads WHERE package_name = p.package_name AND package_version = p.version) as download_count
        FROM packages p
        WHERE package_name = ? OR display_name = ?
        ORDER BY upload_time DESC
    `;
    
    db.all(sql, [nameParam, nameParam], (err, rows) => {
        if (err) {
            console.error(`Error fetching versions for package ${nameParam}:`, err.message);
            return res.status(500).json({ error: "Internal server error", details: err.message });
        }
        
        if (rows.length === 0) {
            return res.status(404).json({ error: `Package ${nameParam} not found.` });
        }
        
        // Format the response
        const versions = rows.map(row => ({
            version: row.version,
            released_at: row.released_at,
            download_count: row.download_count || 0
        }));
        
        res.json(versions);
    });
});

// --- DELETE Endpoints ---

// Delete a package (all versions) and its files
app.delete('/api/packages/:name', async (req, res) => {
    const nameToDelete = req.params.name;
    console.log(`Attempting to delete package: ${nameToDelete}`);

    // 1. Find all package entries and filenames for this name
    // Check if package exists by name
    const checkSql = `SELECT id, filename FROM packages WHERE display_name = ? OR package_name = ?`;
    
    db.all(checkSql, [nameToDelete, nameToDelete], async (err, rows) => {
        if (err) {
            console.error(`Error checking for package ${nameToDelete}:`, err.message);
            return res.status(500).json({ error: "Internal server error", details: err.message });
        }
        
        if (rows.length === 0) {
            return res.status(404).json({ error: `Package ${nameToDelete} not found.` });
        }
        
        // 2. Delete the files
        const filesToDelete = rows.map(row => row.filename);
        const fileDeletePromises = filesToDelete.map(filename => {
            const filePath = path.join(UPLOAD_DIR, filename);
            return fsPromises.unlink(filePath).catch(err => {
                console.error(`Warning: Could not delete file ${filePath}:`, err.message);
                // Continue with DB deletion even if file deletion fails
                return null;
            });
        });
        
        try {
            await Promise.all(fileDeletePromises);
            console.log(`Deleted ${filesToDelete.length} files for package ${nameToDelete}`);
            
            // 3. Delete from database
            const deleteSql = `DELETE FROM packages WHERE display_name = ? OR package_name = ?`;
            db.run(deleteSql, [nameToDelete, nameToDelete], function(err) {
                if (err) {
                    console.error(`Error deleting package ${nameToDelete} from database:`, err.message);
                    return res.status(500).json({ error: "Failed to delete package from database", details: err.message });
                }
                
                console.log(`Deleted package ${nameToDelete} from database (${this.changes} rows affected)`);
                res.json({ message: `Package ${nameToDelete} deleted successfully.`, deletedVersions: rows.length });
            });
        } catch (error) {
            console.error(`Error during package deletion:`, error);
            res.status(500).json({ error: "Failed to delete package files", details: error.message });
        }
    });
});

// --- Server Endpoints ---

// GET /api/servers/ - List all servers
app.get('/api/servers/', (req, res) => {
    const sql = `SELECT id, display_name, registry_name, github_url, language, registration_time FROM servers ORDER BY display_name ASC`;
    db.all(sql, [], (err, rows) => {
        if (err) {
            console.error("Error fetching servers:", err.message);
            res.status(500).json({ error: "Internal server error", details: err.message });
        } else {
            res.json(rows);
        }
    });
});

// POST /api/servers/ - Register a new server
app.post('/api/servers/', (req, res) => {
    const { display_name, github_url, language, config_command } = req.body;
    
    if (!display_name) {
        return res.status(400).json({ error: "Server display name is required." });
    }
    
    // Generate a registry name (unique identifier) from display name
    const registry_name = generateRegistryName(display_name);
    if (!registry_name) {
        return res.status(400).json({ error: "Could not generate a valid registry name from the display name." });
    }
    
    // Use default config command if none provided
    const serverConfigCommand = config_command || DEFAULT_CONFIG_COMMAND.replace('"{server_name}"', `"${registry_name}"`);
    
    const sql = `INSERT INTO servers (display_name, registry_name, github_url, language, config_command)
                 VALUES (?, ?, ?, ?, ?)`;
    const params = [display_name, registry_name, github_url, language, serverConfigCommand];
    
    db.run(sql, params, function(err) {
        if (err) {
            if (err.message.includes('UNIQUE constraint failed')) {
                return res.status(409).json({ error: `Server with name '${display_name}' or registry name '${registry_name}' already exists.` });
            }
            console.error("Error registering server:", err.message);
            return res.status(500).json({ error: "Failed to register server", details: err.message });
        }
        
        res.status(201).json({
            message: "Server registered successfully.",
            serverId: this.lastID,
            display_name,
            registry_name
        });
    });
});

// GET /api/servers/:name - Get server details by registry name
app.get('/api/servers/:name', (req, res) => {
    const serverName = req.params.name;
    const sql = `SELECT * FROM servers WHERE registry_name = ?`;
    
    db.get(sql, [serverName], (err, row) => {
        if (err) {
            console.error(`Error fetching server ${serverName}:`, err.message);
            return res.status(500).json({ error: "Internal server error", details: err.message });
        }
        
        if (!row) {
            return res.status(404).json({ error: `Server '${serverName}' not found.` });
        }
        
        res.json(row);
    });
});

// PUT /api/servers/:name - Update server details
app.put('/api/servers/:name', (req, res) => {
    const serverName = req.params.name;
    const { display_name, github_url, language, config_command } = req.body;
    
    // First check if server exists
    db.get(`SELECT * FROM servers WHERE registry_name = ?`, [serverName], (err, row) => {
        if (err) {
            console.error(`Error checking server ${serverName}:`, err.message);
            return res.status(500).json({ error: "Internal server error", details: err.message });
        }
        
        if (!row) {
            return res.status(404).json({ error: `Server '${serverName}' not found.` });
        }
        
        // Build update SQL dynamically based on provided fields
        let updates = [];
        let params = [];
        
        if (display_name !== undefined) {
            updates.push('display_name = ?');
            params.push(display_name);
        }
        
        if (github_url !== undefined) {
            updates.push('github_url = ?');
            params.push(github_url);
        }
        
        if (language !== undefined) {
            updates.push('language = ?');
            params.push(language);
        }
        
        if (config_command !== undefined) {
            updates.push('config_command = ?');
            params.push(config_command);
        }
        
        if (updates.length === 0) {
            return res.status(400).json({ error: "No fields to update were provided." });
        }
        
        // Add the WHERE parameter
        params.push(serverName);
        
        const sql = `UPDATE servers SET ${updates.join(', ')} WHERE registry_name = ?`;
        
        db.run(sql, params, function(err) {
            if (err) {
                console.error(`Error updating server ${serverName}:`, err.message);
                return res.status(500).json({ error: "Failed to update server", details: err.message });
            }
            
            if (this.changes === 0) {
                return res.status(404).json({ error: `Server '${serverName}' not found or no changes made.` });
            }
            
            res.json({ message: `Server '${serverName}' updated successfully.` });
        });
    });
});

// DELETE /api/servers/:name - Delete a server
app.delete('/api/servers/:name', (req, res) => {
    const serverName = req.params.name;
    
    db.run(`DELETE FROM servers WHERE registry_name = ?`, [serverName], function(err) {
        if (err) {
            console.error(`Error deleting server ${serverName}:`, err.message);
            return res.status(500).json({ error: "Failed to delete server", details: err.message });
        }
        
        if (this.changes === 0) {
            return res.status(404).json({ error: `Server '${serverName}' not found.` });
        }
        
        res.json({ message: `Server '${serverName}' deleted successfully.` });
    });
});

// --- Server Start ---
app.listen(port, () => {
    console.log(`mcpm-registry server listening on port ${port}`);
    console.log(`Serving static files from: ${PUBLIC_DIR}`);
    console.log(`Storing package files in: ${UPLOAD_DIR}`);
    console.log(`Using database at: ${DB_PATH}`);
});

// Make loadServerForEditing globally accessible for the inline script in edit-server.html
// Needs to be inside the DOMContentLoaded listener where the function is defined.
if (typeof window !== 'undefined') {
    window.loadServerForEditing = loadServerForEditing;
}
