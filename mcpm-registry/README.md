# MCPM Registry

A simple Node.js/Express-based registry server for MCPM packages.

- Stores package metadata in SQLite.
- Stores package zip files in the `uploads/` directory.
- Provides API endpoints for listing, downloading, and publishing packages.
- Includes a basic web UI.

## Setup

```bash
cd mcpm-registry
npm install
```

## Running

```bash
node server.js
```

The server will typically run on http://localhost:8000.

## API Endpoints

- `GET /api/packages/`: List all available packages.
- `GET /api/packages/:name/:version/download`: Download a package zip file.
- `POST /api/packages/publish`: Publish a new package (expects multipart/form-data with 'package' file and 'metadata' JSON string).
