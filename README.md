# MCPM - Model Context Protocol Manager

[![GitHub license](https://img.shields.io/github/license/ascii27/mcpm)](https://github.com/ascii27/mcpm/blob/main/LICENSE)

A comprehensive command-line tool for managing Model Context Protocol (MCP) server packages. MCPM provides a familiar package management experience similar to npm or pip, allowing users to discover, install, configure, and publish MCP server packages.

## What is MCP?

The Model Context Protocol (MCP) is a standardized interface for AI models to access external data and functionality. MCP servers act as connectors between AI models and various data sources or APIs, enabling models to perform tasks like retrieving information from databases, executing code, or interacting with external services.

## Features

### Package Management
- ✅ Install MCP server packages from a registry
- ✅ Uninstall packages with cleanup
- ✅ List available packages with filtering options
- ✅ Interactive and non-interactive modes
- ✅ Local database tracking of installed packages

### Configuration Management
- ✅ Configure packages for different IDEs
- ✅ Support for API keys and other input values
- ✅ Variable substitution in configuration files

### Package Development
- ✅ Create MCP server packages (zip format)
- ✅ Publish packages to the registry
- ✅ Support for installation steps and configuration commands

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Installing from Source

```bash
# Clone the repository
git clone https://github.com/ascii27/mcpm.git
cd mcpm

# Install the package in development mode
pip install -e .
```

## Usage

### Basic Commands

```bash
# List available packages (interactive mode)
mcpm list

# List available packages (non-interactive mode)
mcpm list --non-interactive

# Install a package
mcpm install <package_name>

# Uninstall a package
mcpm uninstall <package_name>

# Configure an installed package
mcpm configure [package_name] [--target-ide <ide>] [--action <add|remove>]

# Create a package from the current directory
mcpm create

# Publish a package
mcpm publish <package_file.zip>
```

### Interactive Mode

MCPM offers an interactive mode for easier package discovery and management:

```bash
mcpm list
```

This will display a searchable list of available packages with detailed information and management options.

### Package Installation with Input Values

Some packages may require API keys or other configuration values during installation:

```bash
mcpm install mcp-linear
```

If the package requires input values (like API keys), MCPM will prompt for them and securely store them for later use during configuration.

### Package Configuration

Configure an installed package for a specific IDE:

```bash
mcpm configure mcp-linear --target-ide windsurf --action add
```

Or use interactive mode to select options:

```bash
mcpm configure
```

## Package Structure

An MCP package is a zip file with a specific structure:

```
package-root/
├── mcp_package.json    # Package metadata and configuration
├── server.js           # Main server implementation
└── ... other files
```

### mcp_package.json

The `mcp_package.json` file defines the package metadata, installation steps, and IDE configuration:

```json
{
  "name": "my-mcp-server",
  "install_name": "my-server",
  "version": "1.0.0",
  "description": "An example MCP server",
  "author": "Your Name",
  "license": "MIT",
  "runtime": "node",
  "install_inputs": [
    {
      "name": "api_key",
      "prompt": "Enter your API key:",
      "secret": true
    }
  ],
  "install_steps": [
    {
      "type": "shell",
      "command": "npm install"
    }
  ],
  "ide_config_commands": {
    "windsurf": {
      "command": "node",
      "args": ["server.js"],
      "env": {
        "API_KEY": "${api_key}"
      }
    }
  }
}
```

## Architecture

MCPM is organized into several modules:

- **commands**: Implementation of CLI commands
- **config**: Configuration management
- **database**: Local SQLite database for tracking installed packages
- **registry**: API client for the package registry
- **utils**: Helper functions for package operations and UI

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
