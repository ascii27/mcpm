# MCPM - Model Context Protocol Manager

A command-line tool to manage Model Context Protocol (MCP) server packages, similar to npm.

## Features

- Install MCP server packages from a registry.
- Remove installed packages.
- List available packages in the registry.
- Create MCP server packages (zip format).
- Publish packages to the registry.

## Usage

```bash
# Install the tool (after packaging)
pip install .

# List available packages
mcpm list

# Install a package
mcpm install <package_name>

# Remove an installed package
mcpm remove <package_name>

# Create a package from the current directory
mcpm create

# Publish a package
mcpm publish <package_file.zip>
```
