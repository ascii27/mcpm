"""
List command implementation for MCPM.
"""
import click
import questionary
import json
from pathlib import Path

from mcpm.registry.api import get_registry_packages, get_registry_servers
from mcpm.database.local_db import init_local_db, get_all_installed_package_details
from mcpm.utils.ui_helpers import _display_package_details_interactive
from mcpm.utils.package_helpers import _get_package_data_by_name

def list_items(non_interactive, search=None):
    """
    Fetches and lists packages and servers from the registry.
    In interactive mode (default), shows package details and allows management.
    """
    # Initialize the local database
    init_local_db()
    
    # Get installed packages info
    installed_packages = get_all_installed_package_details()
    installed_packages_info = {pkg["name"]: pkg for pkg in installed_packages}
    
    # Fetch packages from registry
    all_packages_data = get_registry_packages()
    
    # Fetch servers from registry
    servers_data = get_registry_servers()
    
    if non_interactive:
        # Non-interactive mode: just list packages and servers
        click.echo("=== MCP Packages ===")
        if all_packages_data:
            for pkg in all_packages_data:
                pkg_name = pkg.get("name", "Unknown Package Name")
                pkg_version = pkg.get("version", "N/A")
                pkg_description = pkg.get("description", "")
                pkg_author = pkg.get("author", "")

                # Determine installation status
                is_installed = pkg_name in installed_packages_info
                install_status = "🟢 " if is_installed else "- "
                
                # Format display with name, version, status, then details
                line_parts = [f"{install_status}{pkg_name} (v{pkg_version})"]
                
                # Add installed version if different from registry version
                if pkg_name in installed_packages_info:
                    installed_version = installed_packages_info[pkg_name].get('version')
                    if installed_version and installed_version != pkg_version:
                        line_parts.append(f"[Installed: v{installed_version}]")
                
                # Add description if available
                if pkg_description:
                    # Truncate description if too long
                    max_desc_len = 50
                    if len(pkg_description) > max_desc_len:
                        pkg_description = pkg_description[:max_desc_len] + "..."
                    line_parts.append(f"- {pkg_description}")
                
                # Add author if available
                if pkg_author:
                    line_parts.append(f"By: {pkg_author}")
                
                # Join all parts with spaces
                click.echo(" ".join(line_parts))
        else:
            click.echo("No MCP packages found in the registry or registry is unavailable.")
        
        # List local-only packages
        local_only_packages = [pkg for pkg in installed_packages if pkg["name"] not in [p.get("name") for p in (all_packages_data or [])]]
        if local_only_packages:
            click.echo("\n=== Local-only Packages (not in registry) ===")
            for pkg in local_only_packages:
                pkg_name = pkg["name"]
                pkg_version = pkg["version"]
                pkg_path = pkg["install_path"]
                click.echo(f"{pkg_name} (v{pkg_version}) 🟢 : Local only - {pkg_path}")
        
        # List servers
        click.echo("\n=== MCP Servers ===")
        if servers_data:
            for server in servers_data:
                server_reg_name = server.get('registry_name', 'Unknown Server Name')
                description = server.get('description', 'No description')
                
                # Determine installation status
                is_installed = server_reg_name in installed_packages_info
                install_status = "🟢 " if is_installed else "- "
                
                # Build display parts with name, version, status, then details
                display_parts = [f"{install_status}{server_reg_name}"]  
                
                # Add version info
                if is_installed:
                    version = installed_packages_info[server_reg_name].get('version', 'N/A')
                    display_parts.append(f"(v{version})")
                
                # Add description
                display_parts.append(f": {description}")
                    
                click.echo(" ".join(display_parts))
        else:
            click.echo("No MCP servers found in the registry or registry is unavailable.")
        return
    
    # Interactive mode
    while True:
        click.clear()
        click.echo("=== MCP Package Manager ===")
        
        # Prepare choices for questionary
        choices = []
        
        # Add packages from registry
        if all_packages_data:
            # Add search option
            choices.append(questionary.Choice(title="🔍 Search packages...", value="search"))
            
            # Add clear search option if search is active
            if search:
                choices.append(questionary.Choice(title="❌ Clear search", value="clear_search"))
                click.echo(f"Filtering results for: '{search}'")
            
            # Filter packages based on search query if provided
            filtered_packages = all_packages_data
            if search:
                search_lower = search.lower()
                filtered_packages = [
                    pkg for pkg in all_packages_data 
                    if (search_lower in pkg.get("name", "").lower() or 
                        search_lower in pkg.get("description", "").lower() or
                        search_lower in pkg.get("author", "").lower())
                ]
            
            # Add filtered packages to choices
            for pkg in filtered_packages:
                pkg_name = pkg.get("name", "Unknown Package Name")
                pkg_version = pkg.get("version", "N/A")
                pkg_description = pkg.get("description", "")
                pkg_author = pkg.get("author", "")
                
                # Check if installed
                is_installed = pkg_name in installed_packages_info
                
                # Use installed version if available
                display_version = installed_packages_info[pkg_name].get('version', pkg_version) if is_installed else pkg_version
                
                # Build title parts with name, version, then status
                status_icon = "🟢" if is_installed else "-"
                
                # Format title with name, version, status, then description
                title_parts = [
                    f"{pkg_name} (v{display_version})",
                    status_icon
                ]
                
                # Add truncated description if available
                if pkg_description:
                    max_desc_len = 80
                    desc_display = pkg_description[:max_desc_len] + ('...' if len(pkg_description) > max_desc_len else '')
                    title_parts.append(f"- {desc_display}")
                
                # Add author if available
                if pkg_author and pkg_author.strip():
                    title_parts.append(f"(by {pkg_author})")
                
                # Join all parts, filtering out empty strings
                title = " ".join(filter(None, title_parts))
                choices.append(questionary.Choice(title=title, value=pkg_name))
            
            # Show "no results" message if search returned no packages
            if search and not filtered_packages:
                choices.append(questionary.Choice(title="No packages match your search", value="no_results", disabled=True))
        else:
            choices.append(questionary.Choice(title="No packages found in registry", value="no_packages", disabled=True))
        
        # Add local-only packages
        local_only_packages = [pkg for pkg in installed_packages if pkg["name"] not in [p.get("name") for p in (all_packages_data or [])]]
        if local_only_packages:
            choices.append(questionary.Choice(title="=== Local-only Packages ===", value="local_header", disabled=True))
            
            # Filter local packages based on search query if provided
            filtered_local_packages = local_only_packages
            if search:
                search_lower = search.lower()
                filtered_local_packages = [
                    pkg for pkg in local_only_packages 
                    if search_lower in pkg["name"].lower()
                ]
            
            # Add filtered local packages to choices
            for pkg_dict in filtered_local_packages:
                pkg_name = pkg_dict.get('name', 'N/A')
                pkg_version = pkg_dict.get('version', 'N/A')
                pkg_path = pkg_dict.get('install_path', 'N/A')
                
                # Format title with name, version, status, then details
                title_parts = [
                    f"{pkg_name} (v{pkg_version})",
                    "🟢",
                    "- Local only"
                ]
                
                # No author information for local-only packages
                
                # Join all parts, filtering out empty strings
                title = " ".join(filter(None, title_parts))
                choices.append(questionary.Choice(title=title, value=pkg_name))
            
            # Show search results for local packages if search was performed
            if search and not filtered_local_packages and local_only_packages:
                choices.append(questionary.Choice(title="No local packages match your search", value="no_local_results", disabled=True))
        
        # Add exit option
        choices.append(questionary.Choice(title="Exit MCPM", value="exit"))
        
        # Show selection menu
        selection = questionary.select(
            "Select a package to view details:",
            choices=choices
        ).ask()
        
        if not selection:
            # User cancelled (Ctrl+C)
            return
        
        if selection == "search":
            # User wants to search
            search_query = questionary.text("Enter search term:").ask()
            if search_query:
                search = search_query
            continue
        
        if selection == "clear_search":
            # Clear the search filter
            search = None
            continue
        
        if selection == "exit":
            # Exit the application
            return
        
        if selection in ["no_packages", "no_results", "no_local_results", "local_header"]:
            # These are just informational headers, not selectable items
            continue
        
        # User selected a package, show details
        ctx = click.get_current_context()
        result = _display_package_details_interactive(selection, all_packages_data, installed_packages_info, ctx)
        
        if result == "exit_mcpm":
            return
        elif result == "state_changed":
            # Refresh installed packages info
            installed_packages = get_all_installed_package_details()
            installed_packages_info = {pkg["name"]: pkg for pkg in installed_packages}
        elif result == "back_to_list":
            # Just continue the loop
            pass
