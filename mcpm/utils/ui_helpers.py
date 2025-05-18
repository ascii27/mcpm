"""
Helper functions for interactive UI components.
"""
import click
import webbrowser
import questionary
import json
from pathlib import Path

from mcpm.utils.package_helpers import _get_package_data_by_name
from mcpm.config.constants import INSTALL_DIR

def _display_package_details_interactive(package_name, all_packages_data, installed_packages_info, ctx):
    """
    Displays detailed information for a selected package and allows interactive
    management (install/uninstall, open URLs).
    
    Args:
        package_name: The name of the package to display details for.
        all_packages_data: List of all package data dictionaries from the registry.
        installed_packages_info: Dictionary of installed packages info keyed by name.
        ctx: Click context for invoking other commands.
        
    Returns:
        A status string: 'back_to_list', 'state_changed', 'exit_mcpm', or 'details_refresh'.
    """
    # Get full package data
    pkg_data = _get_package_data_by_name(package_name, all_packages_data)
    
    if not pkg_data:
        # Check if it's a local-only package
        if package_name in installed_packages_info:
            # Display local-only package details
            pkg_path = installed_packages_info[package_name].get('install_path', 'Unknown')
            pkg_version = installed_packages_info[package_name].get('version', 'Unknown')
            installed_date = installed_packages_info[package_name].get('installed_at', 'Unknown')
            
            click.clear()
            click.echo("Package Details:")
            click.echo(f"Name:        {package_name}")
            
            # Check for mcp_package.json to get more details
            metadata_path = Path(pkg_path) / "mcp_package.json"
            description = "No description available"
            author = "Unknown"
            license_info = "Unknown"
            runtime = "Unknown"
            source_url = ""
            homepage = ""
            
            if metadata_path.exists():
                try:
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    
                    # Extract metadata if available
                    if "description" in metadata:
                        description = metadata['description']
                    if "author" in metadata:
                        author = metadata['author']
                    if "license" in metadata:
                        license_info = metadata['license']
                    if "runtime" in metadata:
                        runtime = metadata['runtime']
                    if "source_url" in metadata:
                        source_url = metadata['source_url']
                    if "homepage" in metadata:
                        homepage = metadata['homepage']
                except Exception as e:
                    click.echo(f"Error reading package metadata: {e}", err=True)
            
            click.echo(f"Description: {description}")
            
            vendor_info = author
            if homepage and not homepage.startswith("http"):
                vendor_info += f" ({homepage})"
            click.echo(f"Vendor:      {vendor_info}")
            
            click.echo(f"License:     {license_info}")
            click.echo(f"Runtime:     {runtime}")
            
            if source_url:
                click.echo(f"Source:      {source_url}")
            if homepage and homepage.startswith("http"):
                click.echo(f"Homepage:    {homepage}")
                
            click.echo(f"Status:      Installed (Local only)")
            click.echo(f"Version:     {pkg_version}")
            click.echo(f"Path:        {pkg_path}")
            click.echo(f"Installed:   {installed_date}")
            
            # Management options
            actions = [
                questionary.Choice(title="✅ Uninstall this package", value="uninstall"),
                questionary.Choice(title="⚙️  Configure for IDE", value="configure"),
                questionary.Choice(title="⬅️  Back to list", value="back"),
                questionary.Choice(title="❌ Exit", value="exit")
            ]
            
            action = questionary.select(
                "Select an action:",
                choices=actions
            ).ask()
            
            if action == "uninstall":
                if click.confirm(f"Are you sure you want to uninstall {package_name}?", default=False):
                    from mcpm.commands.uninstall import uninstall_command_func
                    uninstall_command_func(package_name, None)
                    return "state_changed"
            elif action == "configure":
                # Invoke the configure command
                from mcpm.commands.configure import configure_command_func
                configure_command_func()
                return "state_changed"
            elif action == "back":
                return "back_to_list"
            elif action == "exit":
                return "exit_mcpm"
            
            return "details_refresh"
        else:
            click.echo(f"Error: Package {package_name} not found in registry or local database.", err=True)
            return "back_to_list"
    
    # Package exists in registry
    is_installed = package_name in installed_packages_info
    
    # Extract package details
    pkg_name = pkg_data.get("name", "Unknown")
    pkg_version = pkg_data.get("version", "Unknown")
    pkg_description = pkg_data.get("description", "No description available")
    pkg_author = pkg_data.get("author", "Unknown")
    pkg_license = pkg_data.get("license", "Unknown")
    pkg_runtime = pkg_data.get("runtime", "Unknown")
    pkg_source_url = pkg_data.get("source_url", "")
    pkg_homepage = pkg_data.get("homepage", "")
    
    # Display package details
    click.clear()
    click.echo("Package Details:")
    click.echo(f"Name:        {pkg_name}")
    click.echo(f"Description: {pkg_description}")
    
    vendor_info = pkg_author
    if pkg_homepage and not pkg_homepage.startswith("http"):
        vendor_info += f" ({pkg_homepage})"
    click.echo(f"Vendor:      {vendor_info}")
    
    click.echo(f"License:     {pkg_license}")
    click.echo(f"Runtime:     {pkg_runtime}")
    
    if pkg_source_url:
        click.echo(f"Source:      {pkg_source_url}")
    if pkg_homepage and pkg_homepage.startswith("http"):
        click.echo(f"Homepage:    {pkg_homepage}")
    
    click.echo(f"Status:      {'Installed' if is_installed else 'Not installed'}")
    
    if is_installed:
        pkg_path = installed_packages_info[package_name].get('install_path', 'Unknown')
        installed_version = installed_packages_info[package_name].get('version', 'Unknown')
        installed_date = installed_packages_info[package_name].get('installed_at', 'Unknown')
        click.echo(f"Version:     {installed_version}")
        click.echo(f"Path:        {pkg_path}")
        click.echo(f"Installed:   {installed_date}")
    
    # Management options
    actions = []
    
    if is_installed:
        actions.append(questionary.Choice(title="✅ Uninstall this package", value="uninstall"))
        actions.append(questionary.Choice(title="⚙️  Configure for IDE", value="configure"))
    else:
        actions.append(questionary.Choice(title="✅ Install this package", value="install"))
    
    if pkg_source_url:
        actions.append(questionary.Choice(title="🔗 Open source URL", value="source_url"))
    if pkg_homepage and pkg_homepage.startswith("http"):
        actions.append(questionary.Choice(title="🔗 Open homepage", value="homepage"))
    
    actions.extend([
        questionary.Choice(title="⬅️  Back to list", value="back"),
        questionary.Choice(title="❌ Exit", value="exit")
    ])
    
    action = questionary.select(
        "Select an action:",
        choices=actions
    ).ask()
    
    if action == "install":
        from mcpm.commands.install import install_command_func
        install_command_func(package_name, None)
        return "state_changed"
    elif action == "uninstall":
        if click.confirm(f"Are you sure you want to uninstall {package_name}?", default=False):
            from mcpm.commands.uninstall import uninstall_command_func
            uninstall_command_func(package_name, None)
            return "state_changed"
    elif action == "configure":
        # Invoke the configure command
        from mcpm.commands.configure import configure_command_func
        configure_command_func(package_name)
        return "state_changed"
    elif action == "source_url":
        click.echo(f"Opening source URL: {pkg_source_url}")
        webbrowser.open(pkg_source_url)
    elif action == "homepage":
        click.echo(f"Opening homepage: {pkg_homepage}")
        webbrowser.open(pkg_homepage)
    elif action == "back":
        return "back_to_list"
    elif action == "exit":
        return "exit_mcpm"
    
    return "details_refresh"

def _configure_specific_package(package_name, package_path):
    """Helper function to configure a specific package, skipping the package selection step.
    
    Args:
        package_name: The name of the package to configure (install_name from DB).
        package_path: The installation path of the package.
    """
    if not package_path:
        click.echo(f"Error: Could not determine installation path for package '{package_name}'.", err=True)
        return
    
    pkg_install_path = Path(package_path)
    if not pkg_install_path.exists():
        click.echo(f"Error: Package installation directory not found at {pkg_install_path}", err=True)
        return
    
    # Load mcp_package.json to get available IDEs for selection
    mcp_package_json_path = pkg_install_path / "mcp_package.json"
    if not mcp_package_json_path.exists():
        click.echo(f"Error: mcp_package.json not found at {mcp_package_json_path} for package '{package_name}'.", err=True)
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
    
    # Get available IDE configurations
    ide_configs = package_metadata.get('ide_config_commands', {})
    if not ide_configs:
        click.echo(f"No IDE configurations found in {mcp_package_json_path} for package '{package_name}'.", err=True)
        return
    
    # Get list of available IDEs
    available_ides = list(ide_configs.keys())
    if not available_ides:
        click.echo(f"No target IDEs found in the ide_config_commands section for package '{package_name}'.", err=True)
        return
    
    # Let user select target IDE
    ide_choices = [questionary.Choice(title=ide, value=ide) for ide in available_ides]
    target_ide = questionary.select(
        "Select target IDE to configure:",
        choices=ide_choices
    ).ask()
    
    if not target_ide:
        click.echo("IDE selection cancelled.")
        return
    
    # Get the configuration for the selected IDE
    ide_config = ide_configs.get(target_ide)
    if not isinstance(ide_config, dict):
        click.echo(f"Error: Invalid configuration format for IDE '{target_ide}'.", err=True)
        return
    
    # Let user select action (add or remove)
    action_choices = [
        questionary.Choice(title="Add/Update Configuration", value="add"),
        questionary.Choice(title="Remove Configuration", value="remove")
    ]
    action = questionary.select(
        f"Select action for {package_name} in {target_ide}:",
        choices=action_choices
    ).ask()
    
    if not action:
        click.echo("Action selection cancelled.")
        return
    
    # Now we have package_name, target_ide, and action - process the configuration directly
    from mcpm.config.manager import get_target_config_path, update_mcp_config_file_for_configure, remove_server_from_mcp_config
    
    # Get the target configuration file path
    config_path = get_target_config_path(target_ide)
    if not config_path:
        click.echo(f"Error: Unknown target IDE '{target_ide}'.", err=True)
        return
    
    # Get the configuration for the target IDE
    ide_config = ide_configs.get(target_ide)
    
    # Get the install_name from metadata (for config key)
    install_name = package_metadata.get("install_name", package_name)
    
    # Get stored input values for this package
    from mcpm.database.local_db import get_package_input_values
    input_values = get_package_input_values(install_name)
    
    # Process the action
    if action == "add":
        # Update the configuration
        if update_mcp_config_file_for_configure(config_path, install_name, ide_config, pkg_install_path, input_values):
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
