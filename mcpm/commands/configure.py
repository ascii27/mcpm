"""
Configure command implementation for MCPM.
"""
import click
import json
import questionary
from pathlib import Path

from mcpm.config.manager import get_target_config_path, update_mcp_config_file_for_configure, remove_server_from_mcp_config
from mcpm.database.local_db import init_local_db, get_all_installed_package_details
from mcpm.utils.ui_helpers import _configure_specific_package

def configure_command_func(package_name=None, target_ide=None, action=None, non_interactive=False):
    """
    Configures an installed MCP package for a target IDE.
    
    Args:
        package_name: Name of the package to configure (optional).
        target_ide: Target IDE to configure for (e.g., 'windsurf').
        action: Action to perform ('add' or 'remove').
        non_interactive: Whether to run in non-interactive mode.
    """
    # Initialize the local database
    init_local_db()
    
    # Get installed packages
    installed_packages = get_all_installed_package_details()
    
    if not installed_packages:
        click.echo("No packages are installed. Please install a package first.")
        return
    
    # If package_name is provided, find its details
    package_path = None
    if package_name:
        for pkg in installed_packages:
            if pkg["name"] == package_name:
                package_path = pkg["install_path"]
                break
        
        if not package_path:
            click.echo(f"Error: Package '{package_name}' is not installed.", err=True)
            return
    
    # Non-interactive mode
    if non_interactive:
        if not package_name or not target_ide or not action:
            click.echo("Error: In non-interactive mode, you must specify package_name, target_ide, and action.", err=True)
            return
        
        # Process the configuration
        _process_configuration(package_name, package_path, target_ide, action)
        return
    
    # Interactive mode
    if package_name and package_path:
        # If package_name is provided, configure that specific package
        _configure_specific_package(package_name, package_path)
    else:
        # Let user select a package to configure
        pkg_choices = []
        for pkg in installed_packages:
            pkg_name = pkg["name"]
            pkg_version = pkg["version"]
            pkg_path = pkg["install_path"]
            
            # Check if the package has a mcp_package.json with ide_config_commands
            mcp_package_json_path = Path(pkg_path) / "mcp_package.json"
            has_ide_configs = False
            
            if mcp_package_json_path.exists():
                try:
                    with open(mcp_package_json_path, 'r') as f:
                        metadata = json.load(f)
                    has_ide_configs = 'ide_config_commands' in metadata and metadata['ide_config_commands']
                except:
                    pass
            
            # Only add packages that have IDE configurations
            if has_ide_configs:
                pkg_choices.append(questionary.Choice(title=f"{pkg_name} (v{pkg_version})", value=(pkg_name, pkg_path)))
        
        if not pkg_choices:
            click.echo("No installed packages have IDE configurations.")
            return
        
        # Add cancel option
        pkg_choices.append(questionary.Choice(title="Cancel", value=None))
        
        # Let user select a package
        selection = questionary.select(
            "Select a package to configure:",
            choices=pkg_choices
        ).ask()
        
        if not selection:
            click.echo("Configuration cancelled.")
            return
        
        # Configure the selected package
        selected_pkg_name, selected_pkg_path = selection
        _configure_specific_package(selected_pkg_name, selected_pkg_path)

def _process_configuration(package_name, package_path, target_ide, action):
    """
    Process the configuration for a package.
    
    Args:
        package_name: Name of the package to configure.
        package_path: Path to the package installation directory.
        target_ide: Target IDE to configure for.
        action: Action to perform ('add' or 'remove').
    """
    # Get the target configuration file path
    config_path = get_target_config_path(target_ide)
    if not config_path:
        click.echo(f"Error: Unknown target IDE '{target_ide}'.", err=True)
        return
    
    # Load the package's mcp_package.json
    pkg_install_path = Path(package_path)
    mcp_package_json_path = pkg_install_path / "mcp_package.json"
    
    if not mcp_package_json_path.exists():
        click.echo(f"Error: mcp_package.json not found at {mcp_package_json_path}.", err=True)
        return
    
    try:
        with open(mcp_package_json_path, 'r') as f:
            package_metadata = json.load(f)
    except json.JSONDecodeError:
        click.echo(f"Error: Could not parse {mcp_package_json_path}.", err=True)
        return
    except IOError as e:
        click.echo(f"Error reading {mcp_package_json_path}: {e}", err=True)
        return
    
    # Get IDE configurations
    ide_configs = package_metadata.get('ide_config_commands', {})
    if not ide_configs:
        click.echo(f"No IDE configurations found in {mcp_package_json_path}.", err=True)
        return
    
    # Check if the target IDE is supported
    if target_ide not in ide_configs:
        click.echo(f"Error: Target IDE '{target_ide}' not supported by this package.", err=True)
        click.echo(f"Supported IDEs: {', '.join(ide_configs.keys())}")
        return
    
    # Get the configuration for the target IDE
    ide_config = ide_configs.get(target_ide)
    
    # Get the install_name from metadata (for config key)
    install_name = package_metadata.get("install_name", package_name)
    
    # Process the action
    if action == "add":
        # Update the configuration
        if update_mcp_config_file_for_configure(config_path, install_name, ide_config, pkg_install_path):
            click.echo(f"Successfully configured {package_name} for {target_ide}.")
        else:
            click.echo(f"Failed to configure {package_name} for {target_ide}.", err=True)
    elif action == "remove":
        # Remove the configuration
        if remove_server_from_mcp_config(config_path, install_name):
            click.echo(f"Successfully removed {package_name} configuration from {target_ide}.")
        else:
            click.echo(f"Failed to remove {package_name} configuration from {target_ide}.", err=True)
    else:
        click.echo(f"Error: Unknown action '{action}'. Must be 'add' or 'remove'.", err=True)
