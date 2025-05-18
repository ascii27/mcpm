"""
Uninstall command implementation for MCPM.
"""
import click
import json
import shutil
import os
from pathlib import Path

from mcpm.config.constants import INSTALL_DIR
from mcpm.config.manager import get_target_config_path, remove_server_from_mcp_config
from mcpm.database.local_db import init_local_db, get_all_installed_package_details, remove_package_from_local_db

def uninstall_command_func(package_name, target):
    """
    Uninstalls a package or de-configures a server.
    
    Args:
        package_name: Name of the package to uninstall.
        target: Target tool to de-configure (e.g., 'windsurf').
    """
    # Initialize the local database
    init_local_db()
    
    # Check if this is a server de-configuration request
    if target:
        # This is a server de-configuration request
        click.echo(f"De-configuring server {package_name} from {target}...")
        
        # Get the target configuration file path
        config_path = get_target_config_path(target)
        if not config_path:
            click.echo(f"Error: Unknown target tool '{target}'.", err=True)
            return
        
        # Remove the server from the target configuration file
        if remove_server_from_mcp_config(config_path, package_name):
            click.echo(f"Successfully de-configured server '{package_name}' from {target}.")
        else:
            click.echo(f"Failed to de-configure server '{package_name}' from {target}.", err=True)
    else:
        # This is a package uninstallation request
        click.echo(f"Uninstalling package {package_name}...")
        
        # Get installed package details
        installed_packages = get_all_installed_package_details()
        installed_packages_dict = {pkg["name"]: pkg for pkg in installed_packages}
        
        if package_name not in installed_packages_dict:
            click.echo(f"Error: Package '{package_name}' is not installed.", err=True)
            return
        
        package_info = installed_packages_dict[package_name]
        install_path = package_info.get("install_path")
        
        if not install_path:
            click.echo(f"Error: Could not determine installation path for package '{package_name}'.", err=True)
            return
        
        # Read package metadata for uninstall steps
        pkg_path = Path(install_path)
        metadata_path = pkg_path / "mcp_package.json"
        
        # Variables for configuration removal
        config_key_name = package_name  # Default to package_name
        
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                
                # Get the install_name from metadata (for config removal)
                config_key_name = metadata.get("install_name", package_name)
                
                # Run uninstall steps if defined
                uninstall_steps = metadata.get("uninstall_steps", [])
                if uninstall_steps:
                    click.echo(f"Running uninstall steps for {package_name}...")
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(pkg_path)
                        click.echo(f"Changed directory to {pkg_path} for uninstall steps.")
                        for idx, step in enumerate(uninstall_steps, 1):
                            if step.get("type") == "shell" and "command" in step:
                                command = step["command"]
                                click.echo(f"Step {idx}: {command}")
                                if click.confirm(f"Do you want to run this command in {os.getcwd()}?", default=True):
                                    import subprocess
                                    process_result = subprocess.run(command, shell=True, capture_output=True, text=True)
                                    if process_result.stdout:
                                        click.echo(f"Output:\n{process_result.stdout.strip()}")
                                    if process_result.stderr:
                                        click.echo(f"Error output:\n{process_result.stderr.strip()}", err=True)
                                    if process_result.returncode != 0:
                                        click.echo(f"Warning: Command '{command}' exited with code {process_result.returncode}", err=True)
                                else:
                                    click.echo("Skipped this step.")
                            else:
                                click.echo(f"Unknown or unsupported step type: {step}", err=True)
                    except Exception as e:
                        click.echo(f"Error running uninstall steps: {e}", err=True)
                    finally:
                        os.chdir(original_cwd)
                        click.echo(f"Restored directory to {original_cwd}.")
            except Exception as e:
                click.echo(f"Warning: Could not read package metadata: {e}", err=True)
        
        # Remove the package directory
        try:
            shutil.rmtree(pkg_path)
            click.echo(f"Removed package directory: {pkg_path}")
        except Exception as e:
            click.echo(f"Error removing package directory: {e}", err=True)
            return
        
        # Remove from local database
        remove_package_from_local_db(package_name)
        
        # Check if the package was configured for any IDE and offer to remove configurations
        for target_tool in ["windsurf"]:  # Add more tools as needed
            config_path = get_target_config_path(target_tool)
            if config_path and config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config_data = json.load(f)
                    
                    if 'mcpServers' in config_data and config_key_name in config_data['mcpServers']:
                        if click.confirm(f"Package '{package_name}' is configured for {target_tool}. Remove configuration?", default=True):
                            if remove_server_from_mcp_config(config_path, config_key_name):
                                click.echo(f"Successfully removed configuration from {target_tool}.")
                            else:
                                click.echo(f"Failed to remove configuration from {target_tool}.", err=True)
                except Exception as e:
                    click.echo(f"Warning: Could not check/remove IDE configuration: {e}", err=True)
        
        click.echo(f"Successfully uninstalled package {package_name}.")
