"""
Create command implementation for MCPM.
"""
import click
import json
import os
from pathlib import Path

from mcpm.utils.package_helpers import create_package_archive

def create(output, source):
    """
    Create an MCP server package (zip) from the current directory.
    
    Args:
        output: Output filename for the package zip.
        source: Source directory to package.
    """
    # Validate source directory
    source_path = Path(source).resolve()
    if not source_path.exists() or not source_path.is_dir():
        click.echo(f"Error: Source directory '{source}' does not exist or is not a directory.", err=True)
        return
    
    # Check for mcp_package.json
    metadata_path = source_path / "mcp_package.json"
    if not metadata_path.exists():
        if click.confirm("No mcp_package.json found. Would you like to create one?", default=True):
            # Create a basic mcp_package.json
            package_name = click.prompt("Package name", default=source_path.name)
            package_description = click.prompt("Description", default="")
            package_version = click.prompt("Version", default="0.1.0")
            package_author = click.prompt("Author", default="")
            package_license = click.prompt("License", default="MIT")
            
            # Create a basic metadata file
            metadata = {
                "name": package_name,
                "install_name": package_name,  # Default to package name
                "description": package_description,
                "version": package_version,
                "author": package_author,
                "license": package_license,
                "runtime": "generic",  # Default runtime
                "install_steps": [],
                "uninstall_steps": [],
                "ide_config_commands": {
                    "windsurf": {
                        "command": "echo",
                        "args": ["No command specified"]
                    }
                }
            }
            
            # Ask for IDE configuration
            if click.confirm("Would you like to configure this package for Windsurf?", default=True):
                # Get command type
                command_type = click.prompt(
                    "Command type",
                    type=click.Choice(["docker", "executable", "python", "custom"]),
                    default="docker"
                )
                
                if command_type == "docker":
                    docker_image = click.prompt("Docker image", default=f"mcp/{package_name}")
                    metadata["ide_config_commands"]["windsurf"] = {
                        "command": "docker",
                        "args": [
                            "run",
                            "-i",
                            "--rm",
                            docker_image
                        ]
                    }
                elif command_type == "executable":
                    executable_path = click.prompt("Executable path", default="./server")
                    metadata["ide_config_commands"]["windsurf"] = {
                        "command": executable_path,
                        "args": []
                    }
                elif command_type == "python":
                    script_path = click.prompt("Python script path", default="./server.py")
                    metadata["ide_config_commands"]["windsurf"] = {
                        "command": "python",
                        "args": [
                            script_path
                        ]
                    }
                elif command_type == "custom":
                    command = click.prompt("Command", default="echo")
                    args_str = click.prompt("Arguments (comma-separated)", default="Hello, MCP!")
                    args = [arg.strip() for arg in args_str.split(",")]
                    metadata["ide_config_commands"]["windsurf"] = {
                        "command": command,
                        "args": args
                    }
            
            # Write the metadata file
            try:
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                click.echo(f"Created {metadata_path}")
            except Exception as e:
                click.echo(f"Error creating metadata file: {e}", err=True)
                return
        else:
            click.echo("Cancelled. A mcp_package.json file is required to create a package.", err=True)
            return
    else:
        # Validate existing mcp_package.json
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Check for required fields
            required_fields = ["name", "version"]
            missing_fields = [field for field in required_fields if field not in metadata]
            
            if missing_fields:
                click.echo(f"Error: mcp_package.json is missing required fields: {', '.join(missing_fields)}", err=True)
                return
        except json.JSONDecodeError:
            click.echo("Error: mcp_package.json is not valid JSON.", err=True)
            return
        except Exception as e:
            click.echo(f"Error reading mcp_package.json: {e}", err=True)
            return
    
    # Set default output filename if not provided
    if not output:
        package_name = metadata.get("name", source_path.name)
        package_version = metadata.get("version", "0.1.0")
        output = f"{package_name}-{package_version}.zip"
    
    # Create the package archive
    if create_package_archive(output, source):
        click.echo(f"Package created: {output}")
        
        # Show next steps
        click.echo("\nNext steps:")
        click.echo(f"1. Publish your package: mcpm publish {output}")
        click.echo("2. Install your package: mcpm install <package-name>")
    else:
        click.echo("Failed to create package.", err=True)
