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

---

## Creating a Package for MCPM Registry

To publish a package to the MCPM registry, you need to create a zip file containing your server code and a metadata file called `mcp_package.json` at the root of your package directory.

### Steps to Create a Package

1. **Prepare your server code** in a directory (e.g., `my-mcp-server/`).
2. **Create an `mcp_package.json` file** in the root of your server directory with the following fields:

   - `name` (string, required): The name of your package.
   - `version` (string, required): The version of your package.
   - `description` (string, recommended): A short description of your package.
   - `entrypoint` (string, recommended): The main file to run your server (e.g., `server.py`).
   - `author` (string, recommended): Your name and email.
   - `license` (string, recommended): License type (e.g., MIT).
   - `install_steps` (array, optional): List of install steps to run after installation. Each step should be an object with `type` (currently only `shell` is supported) and `command`.
   - `uninstall_steps` (array, optional): List of uninstall steps to run when the package is removed. Each step should be an object with `type` (currently only `shell` is supported) and `command`.
   - `ide_config_commands` (object, optional): IDE integration commands. Each key is an IDE name (e.g., `vscode`, `pycharm`), and the value is a command block with `command` and `args` fields. Used for automatic IDE configuration when installing with `--target <ide>`.
   - `install_inputs` (array, optional): List of user-supplied values (such as tokens, secrets, or config variables) needed during installation. Each input is an object with:
     - `name` (string): The variable name to reference in steps/configs (e.g., `GITHUB_PERSONAL_ACCESS_TOKEN`).
     - `prompt` (string): The prompt shown to the user during installation.
     - `type` (string, optional): The type of input (default: `string`).
     - `secret` (boolean, optional): If true, input is hidden (for passwords/tokens).

**You can reference these variables in your `install_steps` and `ide_config_commands` using `${VAR_NAME}`. The installer will prompt the user for each value and substitute it into commands/configs.**

#### Example `mcp_package.json` with install_inputs

```json
{
  "name": "my-github-mcp-server",
  "version": "0.1.0",
  "description": "A GitHub MCP server that requires a personal access token.",
  "entrypoint": "server.py",
  "author": "Your Name <your.email@example.com>",
  "license": "MIT",
  "install_inputs": [
    {
      "name": "GITHUB_PERSONAL_ACCESS_TOKEN",
      "prompt": "Enter your GitHub Personal Access Token",
      "type": "string",
      "secret": true
    }
  ],
  "install_steps": [
    { "type": "shell", "command": "docker run -e GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN} ghcr.io/github/github-mcp-server" }
  ],
  "uninstall_steps": [
    { "type": "shell", "command": "echo 'Uninstall complete'" }
  ],
  "ide_config_commands": {
    "windsurf": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

#### Example `mcp_package.json`

#### Example `mcp_package.json`

```json
{
  "name": "my-example-mcp-server",
  "version": "0.1.0",
  "description": "An example MCP server package.",
  "entrypoint": "server.py",
  "author": "Your Name <your.email@example.com>",
  "license": "MIT",
  "install_steps": [
    { "type": "shell", "command": "pip install -r requirements.txt" },
    { "type": "shell", "command": "python setup.py install" }
  ],
  "uninstall_steps": [
    { "type": "shell", "command": "pip uninstall -y some-dependency" },
    { "type": "shell", "command": "echo 'Cleanup complete'" }
  ],
  "ide_config_commands": {
    "vscode": {
      "command": "code",
      "args": ["--install-extension", "my-mcp-server-support"]
    },
    "pycharm": {
      "command": "pycharm",
      "args": ["--install-plugin", "my-mcp-server-support"]
    }
  }
}
```

**IDE Integration:**
- To automatically configure an IDE after installing a package, use the `--target <ide>` flag with the `mcpm install` command (e.g., `mcpm install my-example-mcp-server --target vscode`).
- The CLI will look for a matching entry in `ide_config_commands` and update your IDE's configuration accordingly.

3. **Zip your package directory**, making sure `mcp_package.json` is at the root of the zip file.
   - Example:
     ```bash
     zip -r my-example-mcp-server-0.1.0.zip .
     ```
4. **Publish your package** using the MCPM CLI or the registry web UI.

---
