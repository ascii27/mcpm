import click
import os
import requests
import zipfile
import json
import shutil
import sys
import re
from pathlib import Path

# --- Constants ---
# Default installation directory for packages
INSTALL_DIR = Path("~/.mcpm/packages").expanduser()
# Default registry URL (can be overridden by environment variable)
DEFAULT_REGISTRY_URL = "http://localhost:8000/api" # Example default
# Environment variable name for the registry URL
REGISTRY_URL_ENV_VAR = "MCPM_REGISTRY_URL"
# Environment variable for Windsurf config path override
WINDSURF_CONFIG_ENV_VAR = "WINDSURF_MCP_CONFIG_PATH"

# --- Target Tool Configuration ---
DEFAULT_TARGET_CONFIG_PATHS = {
    "windsurf": Path("~/.codeium/windsurf/mcp_config.json"),
    # Add other tools here if needed
    # "claude-desktop": Path("~/.config/claude/mcp_servers.json"),
}

def get_target_config_path(target_tool):
    """Gets the configuration file path for a target tool."""
    if target_tool == "windsurf":
        # Check environment variable override first
        override_path = os.getenv(WINDSURF_CONFIG_ENV_VAR)
        if override_path:
            return Path(override_path).expanduser()
    # Use default path from mapping
    path = DEFAULT_TARGET_CONFIG_PATHS.get(target_tool)
    return path.expanduser() if path else None

# --- Helper functions (get_registry_url, get_registry_server, etc. - Keep existing) ---
def get_registry_url():
    """Gets the registry URL from environment variable or uses default."""
    return os.environ.get(REGISTRY_URL_ENV_VAR, DEFAULT_REGISTRY_URL)

# Helper function to fetch all packages
def get_registry_packages():
    """Fetches the list of available packages (latest versions) from the registry."""
    packages_url = f"{get_registry_url()}/packages/" # Append specific path
    try:
        response = requests.get(packages_url)
        response.raise_for_status() # Raise an exception for bad status codes
        return response.json() # Assuming the registry returns JSON list of packages
    except requests.exceptions.RequestException as e:
        click.echo(f"Error connecting to registry at {get_registry_url()}: {e}", err=True)
        return None

def get_registry_servers():
    """Fetches the list of all registered servers from the registry."""
    servers_url = f"{get_registry_url()}/servers" # Append specific path
    try:
        response = requests.get(servers_url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error fetching server list from registry: {e}", err=True)
        return None
    except json.JSONDecodeError:
        click.echo("Error: Could not decode server list response from registry.", err=True)
        return None

def get_registry_server(server_registry_name):
    """Fetches server details by registry_name from the registry."""
    registry_url = get_registry_url()
    if not registry_url:
        return None  # Error already handled by caller typically

    try:
        server_list_url = f"{registry_url}/servers"
        response = requests.get(server_list_url)
        response.raise_for_status()
        servers = response.json()
        for server in servers:
            # IMPORTANT: Compare against 'registry_name'
            if server.get('registry_name') == server_registry_name:
                return server # Return the full server details dict
        return None # Not found
    except requests.exceptions.RequestException as e:
        click.echo(f"Error contacting registry to check for server '{server_registry_name}': {e}", err=True)
        return None
    except json.JSONDecodeError:
        click.echo(f"Error decoding server list response when checking for '{server_registry_name}'.", err=True)
        return None
    except KeyError:
         click.echo(f"Error: Missing expected key ('registry_name'?) in server response when checking for '{server_registry_name}'.", err=True)
         return None

def download_package(package_name, version="latest"):
    """Downloads a specific package version from the registry."""
    # TODO: Implement version handling
    download_url = f"{get_registry_url()}/packages/{package_name}/{version}/download" # Append specific path
    click.echo(f"Downloading {package_name} ({version}) from {download_url}...")
    try:
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Save the downloaded zip file temporarily
        temp_zip_path = INSTALL_DIR / f"{package_name}_{version}_temp.zip"
        with open(temp_zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        click.echo(f"Downloaded to {temp_zip_path}")
        return temp_zip_path
    except requests.exceptions.RequestException as e:
        click.echo(f"Error downloading package {package_name}: {e}", err=True)
        return None

def install_package_from_zip(zip_path, package_name):
    """Installs a package from a downloaded zip file, supporting install_inputs for user config."""
    target_install_path = INSTALL_DIR / package_name
    try:
        if target_install_path.exists():
            click.echo(f"Package {package_name} already exists. Removing existing version.")
            shutil.rmtree(target_install_path)

        click.echo(f"Installing {package_name} to {target_install_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_install_path)

        os.remove(zip_path)
        click.echo(f"Successfully installed {package_name}.")

        # --- Support install_inputs for user config ---
        metadata_path = target_install_path / "mcp_package.json"
        install_inputs_values = {}
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                install_inputs = metadata.get("install_inputs", [])
                for input_spec in install_inputs:
                    prompt_text = input_spec.get("prompt") or f"Enter value for {input_spec['name']}"
                    input_type = input_spec.get("type", "string")
                    is_secret = input_spec.get("secret", False)
                    value = click.prompt(prompt_text, hide_input=is_secret, type=str if input_type == "string" else None)
                    install_inputs_values[input_spec["name"]] = value
                install_steps = metadata.get("install_steps", [])
                if install_steps:
                    click.echo(f"Running install steps for {package_name}...")
                    for idx, step in enumerate(install_steps, 1):
                        if step.get("type") == "shell" and "command" in step:
                            command = step["command"]
                            # Substitute variables in the command
                            for var, val in install_inputs_values.items():
                                command = command.replace(f"${{{var}}}", val)
                            click.echo(f"Step {idx}: {command}")
                            if click.confirm(f"Do you want to run this command?", default=True):
                                result = os.system(command)
                                if result != 0:
                                    click.echo(f"Warning: Command '{command}' exited with code {result}", err=True)
                            else:
                                click.echo("Skipped this step.")
                        else:
                            click.echo(f"Unknown or unsupported step type: {step}", err=True)
                else:
                    click.echo("No install steps defined in mcp_package.json.")
            except Exception as e:
                click.echo(f"Error reading install_steps from mcp_package.json: {e}", err=True)
        else:
            click.echo("No mcp_package.json found in the installed package directory.")
        return True, install_inputs_values
    except zipfile.BadZipFile:
        click.echo(f"Error: Downloaded file {zip_path} is not a valid zip file.", err=True)
        if os.path.exists(zip_path): os.remove(zip_path)
        return False, {}
    except Exception as e:
        click.echo(f"Error installing package {package_name}: {e}", err=True)
        if os.path.exists(zip_path): os.remove(zip_path)
        return False, {}

def get_installed_packages():
    """Lists locally installed packages."""
    if not INSTALL_DIR.exists():
        return []
    return [d.name for d in INSTALL_DIR.iterdir() if d.is_dir()]

def create_package_archive(output_filename, source_dir='.'):
    """Creates a zip archive of the source directory."""
    source_path = Path(source_dir).resolve()
    exclude_patterns = ['.git', '__pycache__', '*.pyc', '.DS_Store', output_filename, '.venv', 'venv']

    click.echo(f"Creating archive {output_filename} from {source_path}...")
    try:
        with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in source_path.rglob('*'):
                # Calculate relative path for storage inside zip
                relative_path = item.relative_to(source_path)

                # Check against exclude patterns
                if any(part in exclude_patterns for part in relative_path.parts) or \
                   any(item.match(pattern) for pattern in exclude_patterns if '*' in pattern) or \
                   item.name in exclude_patterns:
                    click.echo(f"  Excluding: {relative_path}")
                    continue

                if item.is_file():
                    click.echo(f"  Adding: {relative_path}")
                    zipf.write(item, arcname=relative_path)
                # Add empty directories if needed (often not required if files exist within)
                # elif item.is_dir() and not any(item.iterdir()):
                #    zipf.write(item, arcname=relative_path)

        click.echo(f"Successfully created package: {output_filename}")
        return True
    except Exception as e:
        click.echo(f"Error creating package archive: {e}", err=True)
        # Clean up incomplete zip file if it exists
        if Path(output_filename).exists():
            os.remove(output_filename)
        return False

# --- JSON Update Logic (MODIFIED) ---
def update_mcp_config_file(config_path: Path, server_registry_name: str, server_config_str: str):
    """Reads, updates, and writes the target MCP JSON configuration file.

    Args:
        config_path: Path to the target JSON file (e.g., windsurf mcp_config.json).
        server_registry_name: The unique name used in the registry (e.g., 'my-calculator-server').
            This is currently NOT used as the key in the target file.
        server_config_str: The JSON string fetched from the registry's 'config_command' field.
            Expected format: '{"mcpServers": {"<short_name>": { ... server config ...}}}'.
    """
    try:
        # --- Parse the incoming server config first ---
        try:
            registry_config = json.loads(server_config_str)
            if not isinstance(registry_config, dict) or 'mcpServers' not in registry_config or not isinstance(registry_config['mcpServers'], dict) or len(registry_config['mcpServers']) != 1:
                raise ValueError("Registry config_command must be a JSON object containing exactly one key under 'mcpServers'.")
            
            # Extract the short name and the actual config object
            mcp_servers_dict = registry_config['mcpServers']
            server_short_name = next(iter(mcp_servers_dict)) # Get the first (and only) key
            server_actual_config = mcp_servers_dict[server_short_name]
            
            if not isinstance(server_actual_config, dict):
                 raise ValueError(f"The configuration for '{server_short_name}' within 'mcpServers' must be a JSON object.")

        except json.JSONDecodeError as e:
            click.echo(f"Error: Could not parse the server configuration received from the registry: {e}", err=True)
            click.echo(f"--- Raw config string from registry for '{server_registry_name}' ---")
            click.echo(server_config_str)
            click.echo("----------------------------------------------------------")
            return False
        except (ValueError, TypeError, KeyError, StopIteration) as e:
            click.echo(f"Error: Invalid structure in the server configuration received from the registry: {e}", err=True)
            click.echo(f"Expected structure: {{\"mcpServers\": {{\"<server_short_name>\": {{...}} }} }}")
            click.echo(f"--- Raw config string from registry for '{server_registry_name}' ---")
            click.echo(server_config_str)
            click.echo("----------------------------------------------------------")
            return False

        # --- Read existing target file data ---
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if config_path.exists() and config_path.stat().st_size > 0:
            with open(config_path, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, dict): # Handle non-dict JSON
                        click.echo(f"Warning: Existing config file {config_path} does not contain a JSON object. Initializing structure.", err=True)
                        data = {}
                except json.JSONDecodeError:
                    click.echo(f"Warning: Could not parse existing config file {config_path}. Backing up and creating new.", err=True)
                    backup_path = config_path.with_suffix('.json.bak')
                    try:
                        shutil.copyfile(config_path, backup_path)
                        click.echo(f"Backed up existing config to {backup_path}")
                    except Exception as backup_e:
                        click.echo(f"Warning: Failed to back up existing config file: {backup_e}", err=True)
                    data = {}

        # Ensure 'mcpServers' key exists in the target data
        if 'mcpServers' not in data or not isinstance(data.get('mcpServers'), dict):
            click.echo(f"Initializing 'mcpServers' object in {config_path}.")
            data['mcpServers'] = {}

        # --- Update the target data --- 
        # Use the extracted short name and config object
        target_key = server_short_name
        click.echo(f"Adding/Updating configuration for server '{target_key}' in {config_path}...")
        data['mcpServers'][target_key] = server_actual_config

        # --- Write updated data back to file ---
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2) # Use indent=2 for pretty printing
            f.write('\n') # Add trailing newline for POSIX compatibility

        click.echo(f"Successfully updated {config_path} for server '{target_key}'.")
        return True

    except IOError as e:
        click.echo(f"Error writing to config file {config_path}: {e}", err=True)
        return False
    except Exception as e:
        # Log the full exception for debugging unexpected errors
        import traceback
        click.echo(f"An unexpected error occurred while updating {config_path}:", err=True)
        click.echo(traceback.format_exc(), err=True)
        return False

# --- NEW Helper: Remove server from config ---
def remove_server_from_mcp_config(config_path: Path, server_short_name: str):
    """Reads a target MCP JSON configuration file, removes a server entry, and writes it back.

    Args:
        config_path: Path to the target JSON configuration file.
        server_short_name: The key name of the server to remove within the 'mcpServers' object.

    Returns:
        True if successful or server was already absent, False on error.
    """
    if not config_path.exists():
        click.echo(f"Info: Target config file {config_path} does not exist. Nothing to remove.")
        return True # Nothing to do, consider it success

    try:
        data = {}
        with open(config_path, 'r') as f:
            try:
                data = json.load(f)
                if not isinstance(data, dict):
                    click.echo(f"Warning: Config file {config_path} is not a JSON object. Cannot remove server entry.", err=True)
                    return False
            except json.JSONDecodeError:
                click.echo(f"Warning: Could not parse config file {config_path}. Cannot remove server entry.", err=True)
                return False # Don't overwrite potentially corrupt file

        if 'mcpServers' not in data or not isinstance(data.get('mcpServers'), dict):
            click.echo(f"Info: 'mcpServers' object not found in {config_path}. Nothing to remove.")
            return True # Server effectively absent

        if server_short_name in data['mcpServers']:
            click.echo(f"Removing server '{server_short_name}' from {config_path}...")
            del data['mcpServers'][server_short_name]

            # Write updated data back
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
            click.echo(f"Successfully removed '{server_short_name}' from {config_path}.")
        else:
            click.echo(f"Info: Server '{server_short_name}' not found in {config_path}. Nothing to remove.")
            
        return True

    except IOError as e:
        click.echo(f"Error accessing config file {config_path}: {e}", err=True)
        return False
    except Exception as e:
        import traceback
        click.echo(f"An unexpected error occurred while removing server from {config_path}:", err=True)
        click.echo(traceback.format_exc(), err=True)
        return False

# --- CLI Commands ---

@click.group()
def cli():
    """Model Context Protocol Manager (MCPM)"""
    pass

@cli.command("list", help="List registered packages and servers.")
def list_items():
    """Fetches and lists both packages and servers from the registry."""
    click.echo("Fetching data from registry...")

    all_items = []

    # Fetch Servers
    servers = get_registry_servers()
    if servers:
        for server in servers:
            all_items.append({
                'type': 'Server',
                'display_name': server.get('display_name', 'Unknown Server'), # The user-friendly name
                'registry_name': server.get('registry_name', 'N/A'), # The name used for install
                'language': server.get('language', 'N/A')
            })
    elif servers is None: # Handle fetch error
         click.echo("Warning: Could not retrieve server list.", err=True)

    # Fetch Packages
    packages = get_registry_packages()
    if packages:
        for pkg in packages:
            all_items.append({
                'type': 'Package',
                'name': pkg.get('name', 'Unknown Package'),
                'install_name': pkg.get('install_name', 'N/A'),
                'latest_version': pkg.get('latest_version', pkg.get('version', 'N/A')),
                'version': pkg.get('version', 'N/A')
            })
    elif packages is None: # Handle fetch error
        click.echo("Warning: Could not retrieve package list.", err=True)

    # Sort combined list primarily by type, then by name/display_name
    all_items.sort(key=lambda x: (x['type'], x.get('name', x.get('display_name', ''))))

    click.echo(f"{'Type':<10} {'Display Name':<30} {'Install Name / Version':<30} {'Details':<20}")
    click.echo("-" * 90)

    for item in all_items:
        if item['type'] == 'Package':
            name = item.get('name', 'N/A')
            install_name = item.get('install_name', 'N/A')
            version = item.get('latest_version', item.get('version', 'N/A'))
            click.echo(f"{item['type']:<10} {name:<30} {install_name + ' / ' + str(version):<30}")
        elif item['type'] == 'Server':
            display_name = item.get('display_name', 'N/A')
            registry_name = item.get('registry_name', 'N/A') # This is the install name
            language = item.get('language', 'N/A')
            click.echo(f"{item['type']:<10} {display_name:<30} {registry_name:<30} (Lang: {language})")

@cli.command()
@click.argument('package_name') # This name can be a package name or a server registry_name
@click.option('--target', default=None, help='Target tool to add server configuration to (e.g., "windsurf").')
def install(package_name, target):
    """Installs a package or configures a registered server (optionally adding config to a target tool)."""
    registry_url = get_registry_url()
    if not registry_url:
        click.echo("Error: MCPM_REGISTRY_URL is not set.", err=True)
        sys.exit(1)

    click.echo(f"Checking registry for server or package: {package_name}...")

    # 1. Check if it's a registered server (using registry_name)
    server_info = get_registry_server(package_name) # Pass the name directly
    if server_info:
        click.echo(f"Found registered server '{package_name}' (Display: {server_info.get('display_name', 'N/A')}).")
        # Output the configuration command associated with the server
        config_command_str = server_info.get('config_command')
        if not config_command_str:
            click.echo(f"Warning: Server '{package_name}' is registered but has no configuration command defined.", err=True)
            # Decide if we should still attempt target update? Probably not.
            sys.exit(1) # Exit if no config command

        # Try to parse the server config string into JSON upfront
        try:
            server_config_json = json.loads(config_command_str)
            if not isinstance(server_config_json, dict):
                 click.echo(f"Error: Configuration for server '{package_name}' is not a valid JSON object.", err=True)
                 sys.exit(1)
        except json.JSONDecodeError:
            click.echo(f"Error: Configuration for server '{package_name}' is not valid JSON.", err=True)
            # Print the raw string for manual inspection if desired
            click.echo("\nRaw configuration string:")
            click.echo("-" * 20)
            click.echo(config_command_str)
            click.echo("-" * 20)
            sys.exit(1)

        # --- Target Tool Integration ---
        if target:
            target_path = get_target_config_path(target)
            if target_path:
                click.echo(f"Attempting to add configuration to target '{target}' at {target_path}...")
                if not update_mcp_config_file(target_path, package_name, server_info.get('config_command')):
                     # Error message already printed by update_mcp_config_file
                     click.echo("Failed to automatically update target configuration file.", err=True)
                     # Optionally print config anyway?
                # Regardless of success/failure of update, we are done with server install
                return
            else:
                click.echo(f"Warning: Unknown target tool '{target}'. No configuration file path defined.", err=True)
                # Fall through to printing config instead

        # --- Default Behavior: Print Config ---
        click.echo("\nServer configuration retrieved. Add this to your target tool's MCP config:")
        click.echo("-" * 20)
        # We already parsed it, so dump the parsed version prettily
        pretty_json = json.dumps(server_config_json, indent=2)
        click.echo(pretty_json)
        click.echo("-" * 20)
        # Add hint about --target
        click.echo(f"\nHint: Use `mcpm install {package_name} --target <tool_name>` (e.g., --target windsurf) to attempt automatic configuration.")
        return # Successfully handled as a server

    # 2. If not a server, attempt to install as a package (Keep existing package install logic)
    click.echo(f"'{package_name}' not found as a registered server. Attempting to install as a package...")
    package_dir = INSTALL_DIR # Use the expanded path constant
    os.makedirs(package_dir, exist_ok=True)
    download_url = f"{registry_url}/packages/{package_name}/latest/download" # Use 'latest' for now

    # Download the package zip file
    filename = f"{package_name}.zip" # Default filename
    package_path = os.path.join(package_dir, filename)
    click.echo(f"Downloading package from: {download_url}")
    tmp_package_path = package_path + ".tmp"  # Always define before try so it's available in except
    try:
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        with open(tmp_package_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Atomic rename after successful download
        os.rename(tmp_package_path, package_path)

        click.echo(f"[LOG] Calling install_package_from_zip for {filename}...")
        install_success, install_inputs_values = install_package_from_zip(package_path, package_name)
        if not install_success:
            click.echo(f"[LOG] Error: install_package_from_zip failed for {package_name}.", err=True)
            sys.exit(1)
        else:
            click.echo(f"[LOG] install_package_from_zip completed for {package_name}.")
    except requests.exceptions.RequestException as e:
        click.echo(f"[LOG] Error downloading package {package_name}: {e}", err=True)
        if tmp_package_path and os.path.exists(tmp_package_path):
            os.remove(tmp_package_path) # Clean up partial download
        click.echo(f"[LOG] Failed to find or download package '{package_name}'.")
        sys.exit(1)

    # If target tool specified, try to update its config using ide_config_commands in mcp_package.json
    if target:
        target_path = get_target_config_path(target)
        if target_path:
            click.echo(f"Attempting to add configuration to target '{target}' at {target_path}...")
            install_path = os.path.join(INSTALL_DIR, package_name)
            mcp_json_path = os.path.join(install_path, "mcp_package.json")
            try:
                with open(mcp_json_path, "r") as f:
                    metadata = json.load(f)
                ide_configs = metadata.get("ide_config_commands", {})
                config_block = ide_configs.get(target)
                if config_block:
                    # Substitute install_inputs_values into config_block
                    def substitute_vars(obj):
                        if isinstance(obj, dict):
                            return {k: substitute_vars(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [substitute_vars(x) for x in obj]
                        elif isinstance(obj, str):
                            result = obj
                            for var, val in install_inputs_values.items():
                                result = result.replace(f"${{{var}}}", val)
                            return result
                        else:
                            return obj
                    config_block_sub = substitute_vars(config_block)
                    config_str = json.dumps({"mcpServers": {package_name: config_block_sub}}, indent=2)
                    if not update_mcp_config_file(target_path, package_name, config_str):
                        click.echo("Failed to automatically update target configuration file.", err=True)
                else:
                    click.echo(f"No IDE config command found for target '{target}' in mcp_package.json. Skipping target update.")
            except Exception as e:
                click.echo(f"Error reading IDE config commands from mcp_package.json: {e}", err=True)
                click.echo("Skipping target configuration update.")

@cli.command(name='uninstall')
@click.argument('package_name')
@click.option('--target', default=None, help="Remove server configuration from the specified target tool's config file (e.g., 'windsurf').")
def uninstall(package_name, target):
    """Uninstalls a package and optionally removes its configuration from a target tool."""
    package_path = INSTALL_DIR / package_name
    
    # --- Configuration Removal Logic ---
    if target:
        target_config_path = get_target_config_path(target)
        if not target_config_path:
            click.echo(f"Error: Unknown target tool '{target}'. Cannot remove configuration.", err=True)
            # Decide if this should prevent package removal? For now, let's continue.
        else:
            click.echo(f"Attempting to remove configuration for '{package_name}' from target '{target}' ({target_config_path})...")
            # Try to find the IDE config block for this package/target from mcp_package.json
            mcp_json_path = package_path / "mcp_package.json"
            server_short_name = package_name  # Default to package name
            if mcp_json_path.exists():
                try:
                    with open(mcp_json_path, "r") as f:
                        metadata = json.load(f)
                    ide_configs = metadata.get("ide_config_commands", {})
                    if target in ide_configs:
                        # Use the package_name as the key in the config file, matching install logic
                        remove_server_from_mcp_config(target_config_path, package_name)
                        click.echo(f"Removed IDE config for '{package_name}' from '{target}'.")
                    else:
                        click.echo(f"No IDE config command found for target '{target}' in mcp_package.json. Skipping config removal.")
                except Exception as e:
                    click.echo(f"Error reading IDE config commands from mcp_package.json: {e}", err=True)
                    click.echo("Skipping IDE config removal.")
            else:
                click.echo(f"No mcp_package.json found in package directory {package_path}. Skipping IDE config removal.")
    # --- First: Remove from IDE configs if target specified ---
    if target:
        target_config_path = get_target_config_path(target)
        if not target_config_path:
            click.echo(f"Error: Unknown target tool '{target}'. Cannot remove configuration.", err=True)
        else:
            click.echo(f"Attempting to remove configuration for '{package_name}' from target '{target}' ({target_config_path})...")
            mcp_json_path = package_path / "mcp_package.json"
            if mcp_json_path.exists():
                try:
                    with open(mcp_json_path, "r") as f:
                        metadata = json.load(f)
                    ide_configs = metadata.get("ide_config_commands", {})
                    if target in ide_configs:
                        remove_server_from_mcp_config(target_config_path, package_name)
                        click.echo(f"Removed IDE config for '{package_name}' from '{target}'.")
                    else:
                        click.echo(f"No IDE config command found for target '{target}' in mcp_package.json. Skipping config removal.")
                except Exception as e:
                    click.echo(f"Error reading IDE config commands from mcp_package.json: {e}", err=True)
                    click.echo("Skipping IDE config removal.")
            else:
                click.echo(f"No mcp_package.json found in package directory {package_path}. Skipping IDE config removal.")

    # --- Second: Run uninstall_steps from mcp_package.json ---
    mcp_json_path = package_path / "mcp_package.json"
    if mcp_json_path.exists():
        try:
            with open(mcp_json_path, "r") as f:
                metadata = json.load(f)
            uninstall_steps = metadata.get("uninstall_steps", [])
            if uninstall_steps:
                click.echo(f"Running uninstall steps for {package_name}...")
                for idx, step in enumerate(uninstall_steps, 1):
                    if step.get("type") == "shell" and "command" in step:
                        command = step["command"]
                        click.echo(f"Uninstall Step {idx}: {command}")
                        if click.confirm(f"Do you want to run this uninstall command?", default=True):
                            result = os.system(command)
                            if result != 0:
                                click.echo(f"Warning: Uninstall command '{command}' exited with code {result}", err=True)
                        else:
                            click.echo("Skipped this uninstall step.")
                    else:
                        click.echo(f"Unknown or unsupported uninstall step type: {step}", err=True)
            else:
                click.echo("No uninstall steps defined in mcp_package.json.")
        except Exception as e:
            click.echo(f"Error reading uninstall_steps from mcp_package.json: {e}", err=True)
    else:
        click.echo(f"No mcp_package.json found in package directory {package_path}. Skipping uninstall steps.")

    # --- Package Directory Removal Logic ---
    if package_path.exists() and package_path.is_dir():
        try:
            shutil.rmtree(package_path)
            click.echo(f"Successfully uninstalled package '{package_name}' from {package_path}.")
        except OSError as e:
            click.echo(f"Error removing package directory {package_path}: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(f"Package '{package_name}' not found at {package_path}. Nothing to uninstall.")
        # If target was specified but package wasn't found, config removal might still have run.
        # Exit with non-zero code if package removal was the primary goal and failed?
        # For now, if config removal happened, maybe exit 0?

    # --- Zip File Removal Logic ---
    # Try to find and remove the zip file for this package in the install dir
    zip_filename = f"{package_name}.zip"
    zip_path = INSTALL_DIR / zip_filename
    if zip_path.exists():
        try:
            os.remove(zip_path)
            click.echo(f"Removed zip file: {zip_path}")
        except Exception as e:
            click.echo(f"Warning: Could not remove zip file {zip_path}: {e}", err=True)

@cli.command()
@click.option('--output', '-o', default=None, help='Output filename (e.g., my-package.zip)')
@click.option('--source', '-s', default='.', help='Source directory to package')
def create(output, source):
    """Create an MCP server package (zip) from the current directory."""
    metadata_file = Path('mcp_package.json')
    if not metadata_file.exists():
        click.echo("No mcp_package.json found. Let's create one interactively.")
        # Required fields
        name = click.prompt("Package name", type=str)
        version = click.prompt("Version", type=str)
        # Recommended fields
        description = click.prompt("Description", type=str, default="", show_default=False)
        entrypoint = click.prompt("Entrypoint (main file to run)", type=str, default="", show_default=False)
        author = click.prompt("Author (name and email)", type=str, default="", show_default=False)
        license_ = click.prompt("License", type=str, default="", show_default=False)
        # Install steps
        install_steps = []
        if click.confirm("Add install steps?", default=False):
            while True:
                command = click.prompt("Install step shell command", type=str)
                install_steps.append({"type": "shell", "command": command})
                if not click.confirm("Add another install step?", default=False):
                    break
        # Uninstall steps
        uninstall_steps = []
        if click.confirm("Add uninstall steps?", default=False):
            while True:
                command = click.prompt("Uninstall step shell command", type=str)
                uninstall_steps.append({"type": "shell", "command": command})
                if not click.confirm("Add another uninstall step?", default=False):
                    break
        # Build metadata dict
        metadata = {"name": name, "version": version}
        if description:
            metadata["description"] = description
        if entrypoint:
            metadata["entrypoint"] = entrypoint
        if author:
            metadata["author"] = author
        if license_:
            metadata["license"] = license_
        if install_steps:
            metadata["install_steps"] = install_steps
        if uninstall_steps:
            metadata["uninstall_steps"] = uninstall_steps
        # Write to file
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        click.echo(f"Created {metadata_file}.")

    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f"Error reading {metadata_file}: Invalid JSON - {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error reading {metadata_file}: {e}", err=True)
        return

    package_name = metadata.get('name')
    package_version = metadata.get('version')

    # Required fields
    missing_fields = []
    if not package_name:
        missing_fields.append('name')
    if not package_version:
        missing_fields.append('version')
    if missing_fields:
        click.echo(f"Error: The following required fields are missing from {metadata_file}: {', '.join(missing_fields)}", err=True)
        return

    # Recommended fields
    recommended_fields = ['description', 'entrypoint', 'author', 'license']
    for field in recommended_fields:
        if field not in metadata:
            click.echo(f"Warning: Recommended field '{field}' is missing from {metadata_file}.")

    # Validate install_steps and uninstall_steps (if present)
    for steps_key in ['install_steps', 'uninstall_steps']:
        steps = metadata.get(steps_key)
        if steps is not None:
            if not isinstance(steps, list):
                click.echo(f"Error: '{steps_key}' must be a list if present.", err=True)
                return
            for i, step in enumerate(steps, 1):
                if not isinstance(step, dict) or step.get('type') != 'shell' or 'command' not in step:
                    click.echo(f"Error: Each step in '{steps_key}' must be an object with type 'shell' and a 'command' string. Problem at index {i-1}.", err=True)
                    return

    # Sanitize name for filename (basic example)
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in package_name)
    output_filename = f"{safe_name}-{package_version}.zip"

    # Ensure mcp_package.json is at the root of the zip
    if not Path('mcp_package.json').exists():
        click.echo("Error: mcp_package.json must be present at the root of the package directory.", err=True)
        return

    create_package_archive(output_filename, source_dir='.')
    click.echo(f"Package created: {output_filename}")

@cli.command()
@click.argument('package_file', type=click.Path(exists=True, dir_okay=False, readable=True))
def publish(package_file):
    """Publish an MCP server package to the registry."""
    package_path = Path(package_file).resolve()
    metadata_path = Path.cwd() / 'mcp_package.json' # Assume metadata in CWD

    if not metadata_path.exists():
        click.echo(f"Error: {metadata_path.name} not found in the current directory ({Path.cwd()}).", err=True)
        click.echo("Publish command expects to be run from the package source directory.", err=True)
        return

    click.echo(f"Preparing to publish {package_path.name} using metadata from {metadata_path.name}...")

    try:
        with open(metadata_path, 'r') as f_meta:
            metadata_content = f_meta.read()
            # Validate JSON structure early
            json.loads(metadata_content)
    except json.JSONDecodeError as e:
        click.echo(f"Error reading {metadata_path.name}: Invalid JSON - {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error reading {metadata_path.name}: {e}", err=True)
        return

    publish_url = f"{get_registry_url()}/packages/publish" # Append specific path
    click.echo(f"Uploading to {publish_url}...")

    try:
        with open(package_path, 'rb') as f_pkg:
            files = {
                'package': (package_path.name, f_pkg, 'application/zip'),
                'metadata': (None, metadata_content) # Send metadata as a string field
            }
            response = requests.post(publish_url, files=files)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # Success
            try:
                resp_json = response.json()
                click.echo(f"Success: {resp_json.get('message', 'Package published.')}")
                click.echo(f"  Name: {resp_json.get('name', 'N/A')}, Version: {resp_json.get('version', 'N/A')}")
            except json.JSONDecodeError:
                click.echo(f"Success: Package published (non-JSON response: {response.text})")

    except requests.exceptions.ConnectionError as e:
        click.echo(f"Error connecting to registry at {publish_url}: {e}", err=True)
    except requests.exceptions.HTTPError as e:
        # Attempt to get error details from JSON response if possible
        error_detail = e.response.text
        try:
            error_json = e.response.json()
            error_detail = error_json.get('error', 'Unknown error')
            details = error_json.get('details')
            if details:
                error_detail += f" ({details})"
        except json.JSONDecodeError:
            pass # Use the raw text if not JSON
        click.echo(f"Error publishing package: {e.response.status_code} {e.response.reason} - {error_detail}", err=True)
    except Exception as e:
        click.echo(f"An unexpected error occurred during publishing: {e}", err=True)


if __name__ == '__main__':
    cli()
