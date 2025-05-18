"""
Install command implementation for MCPM.
"""
import click
import json
from pathlib import Path

from mcpm.registry.api import get_registry_server, download_package
from mcpm.utils.package_helpers import install_package_from_zip
from mcpm.config.manager import get_target_config_path, update_mcp_config_file
from mcpm.database.local_db import init_local_db

def install_command_func(package_name, target):
    """
    Installs a package or configures a server.
    
    Args:
        package_name: Name of the package to install.
        target: Target tool to configure (e.g., 'windsurf').
    """
    # Initialize the local database
    init_local_db()
    
    # Check if this is a server configuration request
    if target:
        # This is a server configuration request
        click.echo(f"Configuring server {package_name} for {target}...")
        
        # Get the target configuration file path
        config_path = get_target_config_path(target)
        if not config_path:
            click.echo(f"Error: Unknown target tool '{target}'.", err=True)
            return
        
        # Fetch server details from registry
        server_data = get_registry_server(package_name)
        if not server_data:
            click.echo(f"Error: Server '{package_name}' not found in registry.", err=True)
            return
        
        # Extract server configuration
        config_command = server_data.get('config_command')
        if not config_command:
            click.echo(f"Error: Server '{package_name}' does not have a configuration command.", err=True)
            return
        
        # Update the target configuration file
        if update_mcp_config_file(config_path, package_name, config_command):
            click.echo(f"Successfully configured server '{package_name}' for {target}.")
        else:
            click.echo(f"Failed to configure server '{package_name}' for {target}.", err=True)
    else:
        # This is a package installation request
        click.echo(f"Installing package {package_name}...")
        
        # Download the package
        zip_path = download_package(package_name)
        if not zip_path:
            click.echo(f"Error: Failed to download package {package_name}.", err=True)
            return
        
        # Install the package
        success, _ = install_package_from_zip(zip_path, package_name)
        if success:
            click.echo(f"Successfully installed package {package_name}.")
        else:
            click.echo(f"Failed to install package {package_name}.", err=True)
