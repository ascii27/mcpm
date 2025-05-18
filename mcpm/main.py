import click
import os
import subprocess
import requests
import zipfile
import json
import shutil
import sys
import re
from pathlib import Path
import sqlite3

# --- Constants ---
# Default installation directory for packages
INSTALL_DIR = Path("~/.mcpm/packages").expanduser()
# Default registry URL (can be overridden by environment variable)
DEFAULT_REGISTRY_URL = "http://localhost:8000/api" # Example default
# Environment variable name for the registry URL
REGISTRY_URL_ENV_VAR = "MCPM_REGISTRY_URL"
# Environment variable for Windsurf config path override
WINDSURF_CONFIG_ENV_VAR = "WINDSURF_MCP_CONFIG_PATH"

# --- Local Database Constants ---
LOCAL_DB_DIR = Path("~/.mcpm").expanduser()
LOCAL_DB_PATH = LOCAL_DB_DIR / "local_registry.db"

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
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(target_install_path) # target_install_path is defined earlier
                        click.echo(f"Changed directory to {target_install_path} for install steps.")
                        for idx, step in enumerate(install_steps, 1):
                            if step.get("type") == "shell" and "command" in step:
                                command = step["command"]
                                # Substitute variables in the command
                                for var, val in install_inputs_values.items():
                                    command = command.replace(f"${{{var}}}", val)
                                click.echo(f"Step {idx}: {command}")
                                if click.confirm(f"Do you want to run this command in {os.getcwd()}?", default=True):
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
                    except FileNotFoundError:
                        click.echo(f"Error: Package directory {target_install_path} not found for running install steps.", err=True)
                    except Exception as e_chdir:
                        click.echo(f"Error changing directory or running install steps: {e_chdir}", err=True)
                    finally:
                        os.chdir(original_cwd)
                        click.echo(f"Restored directory to {original_cwd}.")
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

# --- Local SQLite Database Helper Functions ---

def _get_local_db_connection():
    """Ensures the local DB directory exists and returns a SQLite connection."""
    try:
        LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(LOCAL_DB_PATH)
        return conn
    except sqlite3.Error as e:
        click.echo(f"Error connecting to local database {LOCAL_DB_PATH}: {e}", err=True)
        return None

def init_local_db():
    """Initializes the local SQLite database and creates tables if they don't exist."""
    conn = _get_local_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS installed_packages (
                    name TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    install_path TEXT NOT NULL,
                    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        except sqlite3.Error as e:
            click.echo(f"Error initializing local database table: {e}", err=True)
        finally:
            conn.close()

def is_package_installed(package_install_name):
    """Checks if a package is listed as installed in the local database."""
    conn = _get_local_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM installed_packages WHERE name = ?", (package_install_name,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            click.echo(f"Error querying local database for {package_install_name}: {e}", err=True)
            return False
        finally:
            conn.close()
    return False

def add_package_to_local_db(install_name, version, install_path):
    """Adds or updates a package record in the local installed_packages database."""
    conn = _get_local_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO installed_packages (name, version, install_path, installed_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (install_name, version, str(install_path)))
            conn.commit()
            click.echo(f"Package {install_name} (v{version}) marked as installed locally.")
        except sqlite3.Error as e:
            click.echo(f"Error adding package {install_name} to local database: {e}", err=True)
        finally:
            conn.close()

def remove_package_from_local_db(install_name):
    """Removes a package record from the local installed_packages database."""
    conn = _get_local_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM installed_packages WHERE name = ?", (install_name,))
            conn.commit()
            if cursor.rowcount > 0:
                click.echo(f"Package {install_name} marked as uninstalled locally.")
            else:
                click.echo(f"Package {install_name} was not found in the local installation record.", err=True)
        except sqlite3.Error as e:
            click.echo(f"Error removing package {install_name} from local database: {e}", err=True)
        finally:
            conn.close()

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
    init_local_db() # Ensure DB is initialized
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
            status_marker = "[INSTALLED]" if install_name != 'N/A' and is_package_installed(install_name) else ""
            click.echo(f"{item['type']:<10} {name:<30} {install_name + ' / ' + str(version):<30} {status_marker}")
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
    tmp_package_path = package_path + ".tmp"
    package_data_for_db = {} # To store version and install_name for DB

    try:
        click.echo(f"Downloading package from: {download_url}")
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        # Try to get 'install_name' and 'version' from headers or a preliminary metadata fetch if possible
        # For now, we'll rely on the package_name from the CLI and assume it's the install_name,
        # and try to get version from mcp_package.json after download.
        # This part might need refinement if the downloaded package has a different install_name or if version is critical before full extraction.

        with open(tmp_package_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Atomic rename after successful download
        os.rename(tmp_package_path, package_path)
        click.echo(f"Package downloaded to {package_path}")

        # Extract install_name and version from mcp_package.json inside the zip for DB logging
        # This is a simplified approach; ideally, the registry would provide this directly or via headers.
        actual_install_name = package_name # Default to CLI arg
        installed_version = "unknown"      # Default version
        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                if 'mcp_package.json' in zf.namelist():
                    with zf.open('mcp_package.json') as meta_file:
                        metadata = json.load(meta_file)
                        actual_install_name = metadata.get('install_name', actual_install_name)
                        installed_version = metadata.get('version', installed_version)
                else:
                    click.echo("Warning: mcp_package.json not found in the zip. Using provided name and 'unknown' version for local tracking.", err=True)
        except Exception as e_zip_meta:
            click.echo(f"Warning: Could not read metadata from zip {package_path}: {e_zip_meta}. Using provided name and 'unknown' version for local tracking.", err=True)

        click.echo(f"[LOG] Calling install_package_from_zip for {filename}...")
        install_success, install_inputs_values = install_package_from_zip(package_path, actual_install_name)

        if not install_success:
            click.echo(f"[LOG] Error: install_package_from_zip failed for {actual_install_name}.", err=True)
            # Clean up downloaded zip if install script failed, but keep DB entry attempt to mark 'failed' if desired (not implemented here)
            if os.path.exists(package_path):
                 os.remove(package_path) # Or move to a failed/quarantine area
            sys.exit(1)
        else:
            add_package_to_local_db(actual_install_name, installed_version, INSTALL_DIR / actual_install_name)
            click.echo(f"[LOG] Successfully processed {actual_install_name} after install_package_from_zip.")
            click.echo(f"Package '{actual_install_name}' (v{installed_version}) installed successfully.")

    except requests.exceptions.RequestException as e:
        click.echo(f"[LOG] Error downloading package {package_name}: {e}", err=True)
        if os.path.exists(tmp_package_path):
            os.remove(tmp_package_path) # Clean up partial download
        click.echo(f"[LOG] Failed to find or download package '{package_name}'.")
        sys.exit(1)
    except Exception as e_general: # Catch other potential errors during the process
        click.echo(f"An unexpected error occurred during package installation: {e_general}", err=True)
        if os.path.exists(tmp_package_path):
            os.remove(tmp_package_path)
        if os.path.exists(package_path) and not is_package_installed(actual_install_name if 'actual_install_name' in locals() else package_name):
            # If package_path exists but it's not marked installed, it might be a failed install's artifact
            click.echo(f"Cleaning up potentially incomplete installation at {package_path}", err=True)
            # shutil.rmtree(INSTALL_DIR / (actual_install_name if 'actual_install_name' in locals() else package_name)) # If it's a dir
            # os.remove(package_path) # If it's just the zip
        sys.exit(1)

    # If target tool specified, try to update its config using ide_config_commands in mcp_package.json
    # This logic should be AFTER successful package installation and DB update.
    if target:
        # Ensure actual_install_name is defined here. It should be from the metadata extraction earlier.
        # If metadata extraction failed, actual_install_name defaults to package_name.
        install_dir_for_pkg = INSTALL_DIR / actual_install_name
        mcp_json_path = install_dir_for_pkg / "mcp_package.json"
        target_path = get_target_config_path(target)

        if target_path and mcp_json_path.exists():
            click.echo(f"Attempting to add configuration to target '{target}' at {target_path}...")
            try:
                with open(mcp_json_path, "r") as f:
                    metadata = json.load(f)
                ide_configs = metadata.get("ide_config_commands", {})
                # The key for the config block in ide_config_commands should match the 'target' option
                # The value associated with this key is the actual config block to be inserted.
                # The 'server_registry_name' to update_mcp_config_file should be the package's install_name.
                # The config_block itself should be a string representation of the JSON for that server.

                config_block_for_target = ide_configs.get(target)
                if config_block_for_target:
                    # Substitute install_inputs_values into config_block
                    def substitute_vars(obj):
                        if isinstance(obj, dict):
                            return {k: substitute_vars(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [substitute_vars(x) for x in obj]
                        elif isinstance(obj, str):
                            result = obj
                            for var, val in install_inputs_values.items(): # install_inputs_values from install_package_from_zip
                                result = result.replace(f"${{{var}}}", val)
                            return result
                        else:
                            return obj
                    
                    config_block_sub = substitute_vars(config_block_for_target)
                    # The update_mcp_config_file expects the value part of "mcpServers": { "<short_name>": <value_part> }
                    # So we need to pass the 'actual_install_name' as the key and then the substituted config block as the value string.
                    # The `config_command` arg to update_mcp_config_file is a string that looks like: '{"mcpServers": {"my-server": { ... }}}'
                    # We need to construct this string using actual_install_name and config_block_sub.
                    # The key in the target MCP config will be `actual_install_name`.
                    final_config_str_for_update = json.dumps({"mcpServers": {actual_install_name: config_block_sub}})

                    if not update_mcp_config_file(target_path, actual_install_name, final_config_str_for_update):
                        click.echo(f"Failed to automatically update target configuration file for {actual_install_name}.", err=True)
                    else:
                        click.echo(f"Successfully updated target '{target}' configuration for {actual_install_name}.")
                else:
                    click.echo(f"No IDE config command found for target '{target}' in {mcp_json_path}. Skipping target update.")
            except Exception as e:
                click.echo(f"Error reading or processing {mcp_json_path} for target '{target}': {e}", err=True)
                click.echo("Skipping target configuration update.")
        elif target and not mcp_json_path.exists():
            click.echo(f"Warning: {mcp_json_path} not found. Cannot configure target '{target}'.", err=True)
        elif target and not target_path:
             click.echo(f"Warning: Unknown target '{target}'. Cannot configure.", err=True)


@cli.command(name='uninstall')
@click.argument('package_name')
@click.option('--target', default=None, help="Remove server configuration from the specified target tool's config file (e.g., 'windsurf').")
def uninstall(package_name, target):
    """Uninstalls a package or removes a server's configuration."""
    click.echo(f"Attempting to uninstall or remove configuration for: {package_name}")
    init_local_db() # Ensure DB is initialized for lookups

    package_path = INSTALL_DIR / package_name
    package_zip_path = INSTALL_DIR / f"{package_name}.zip" 

    is_physically_installed_package = package_path.is_dir()
    server_details = get_registry_server(package_name) 

    actual_install_name = package_name 

    if is_physically_installed_package:
        click.echo(f"Found installed package directory at: {package_path}")
        metadata_path = package_path / "mcp_package.json"
        # Initialize server_short_name_for_config, will be updated if metadata is found
        server_short_name_for_config = package_name # Default, may be overridden by metadata
        # actual_install_name is already defined from package_name and will be updated from metadata

        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                actual_install_name = metadata.get('install_name', actual_install_name) # Update from metadata
                server_short_name_for_config = metadata.get('config_key_name', actual_install_name) # Update from metadata

                uninstall_steps = metadata.get("uninstall_steps", [])
                if uninstall_steps:
                    click.echo(f"Running uninstall steps for {actual_install_name}...")
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(package_path) # package_path is the package's installation directory
                        click.echo(f"Changed directory to {package_path} for uninstall steps.")
                        for idx, step in enumerate(uninstall_steps, 1):
                            if step.get("type") == "shell" and "command" in step:
                                command_to_run = step["command"]
                                click.echo(f"Uninstall Step {idx}: {command_to_run}")
                                if click.confirm(f"Run uninstall command: '{command_to_run}' in {os.getcwd()}?", default=True):
                                    process_result = subprocess.run(command_to_run, shell=True, capture_output=True, text=True)
                                    if process_result.stdout:
                                        click.echo(f"Output:\n{process_result.stdout.strip()}")
                                    if process_result.stderr:
                                        click.echo(f"Error output:\n{process_result.stderr.strip()}", err=True)
                                    if process_result.returncode != 0:
                                        click.echo(f"Warning: Uninstall command '{command_to_run}' exited with code {process_result.returncode}", err=True)
                                else:
                                    click.echo("Skipped uninstall step.")
                            else:
                                click.echo(f"Skipping unknown or malformed uninstall step: {step}", err=True)
                    except FileNotFoundError:
                        click.echo(f"Error: Package directory {package_path} not found for running uninstall steps.", err=True)
                    except Exception as e_chdir:
                        click.echo(f"Error changing directory or running uninstall steps: {e_chdir}", err=True)
                    finally:
                        os.chdir(original_cwd)
                        click.echo(f"Restored directory to {original_cwd}.")
                else:
                    click.echo(f"No uninstall steps defined in {metadata_path.name} for {actual_install_name}.")
            except Exception as e_meta:
                click.echo(f"Error reading or processing {metadata_path} for uninstall_steps: {e_meta}. Proceeding with removal.", err=True)
        else:
            click.echo(f"No {metadata_path.name} found at {metadata_path}. Skipping custom uninstall steps.")
            # If metadata not found, actual_install_name remains as initialized (package_name)
            # and server_short_name_for_config also remains as initialized (package_name).

        if target: # Target removal logic, using potentially updated server_short_name_for_config
            target_config_path = get_target_config_path(target)
            if target_config_path:
                click.echo(f"Attempting to remove '{server_short_name_for_config}' configuration from target '{target}'...")
                if remove_server_from_mcp_config(target_config_path, server_short_name_for_config):
                    click.echo(f"Successfully checked/removed configuration for '{server_short_name_for_config}' from '{target}'.")
                else:
                    click.echo(f"Failed to remove configuration for '{server_short_name_for_config}' from '{target}'.", err=True)
            else:
                click.echo(f"Warning: Unknown target '{target}'. Cannot remove configuration.", err=True)

        try:
            shutil.rmtree(package_path)
            click.echo(f"Successfully removed package directory: {package_path}")
            remove_package_from_local_db(actual_install_name) 
        except OSError as e:
            click.echo(f"Error removing package directory {package_path}: {e}", err=True)
            if is_package_installed(actual_install_name):
                remove_package_from_local_db(actual_install_name)

        if package_zip_path.exists():
            try:
                os.remove(package_zip_path)
                click.echo(f"Successfully removed package zip: {package_zip_path}")
            except OSError as e:
                click.echo(f"Warning: Could not remove package zip {package_zip_path}: {e}", err=True)

    elif server_details: 
        click.echo(f"'{package_name}' is a registered server. It's not installed as a directory package.")
        if target:
            target_config_path = get_target_config_path(target)
            server_key_in_config = package_name 
            if target_config_path:
                click.echo(f"Attempting to remove '{server_key_in_config}' configuration from target '{target}'...")
                if remove_server_from_mcp_config(target_config_path, server_key_in_config):
                    click.echo(f"Successfully checked/removed configuration for '{server_key_in_config}' from '{target}'.")
                else:
                    click.echo(f"Failed to remove configuration for '{server_key_in_config}' from '{target}'.", err=True)
            else:
                click.echo(f"Warning: Unknown target '{target}'. Cannot remove configuration.", err=True)
        else:
            click.echo(f"No --target specified. To remove configuration for server '{package_name}', use --target.")
    else:
        click.echo(f"Package or server '{package_name}' not found as an installed directory or a known server.")
        if is_package_installed(package_name):
            click.echo(f"However, '{package_name}' was found in the local installation records. Removing from records.")
            remove_package_from_local_db(package_name)
        else:
            click.echo("No action taken.")


@cli.command()
@click.option('--output', '-o', default=None, help='Output filename (e.g., my-package.zip)')
@click.option('--source', '-s', default='.', help='Source directory to package')
def create(output, source):
    """Create an MCP server package (zip) from the current directory."""
    # Ensure metadata path is relative to the source directory
    source_path = Path(source).resolve()
    metadata_file = source_path / 'mcp_package.json'

    if not metadata_file.exists():
        click.echo(f"No {metadata_file.name} found in {source_path}. Let's create one interactively.")
        # Required fields
        name = click.prompt("Package name (e.g., my-cool-tool)", type=str)
        install_name = click.prompt("Install name (unique key, e.g., my-cool-tool-server, no spaces)", type=str, default=re.sub(r'\s+', '-', name.lower()))
        version = click.prompt("Version (e.g., 0.1.0)", type=str)
        # Recommended fields
        description = click.prompt("Description", type=str, default="", show_default=False)
        entrypoint = click.prompt("Entrypoint (main file/command to run if applicable)", type=str, default="", show_default=False)
        author = click.prompt("Author (name and email)", type=str, default="", show_default=False)
        license_ = click.prompt("License (e.g., MIT, Apache-2.0)", type=str, default="", show_default=False)
        language = click.prompt("Primary language (e.g., python, javascript)", type=str, default="", show_default=False)
        
        # IDE Config Commands (Optional)
        ide_config_commands = {}
        if click.confirm("Add IDE configuration block (e.g., for 'windsurf')?", default=False):
            target_tool_name = click.prompt("Enter target tool name (e.g., windsurf)")
            click.echo(f"Enter the JSON configuration block for '{target_tool_name}'. This is the part that goes inside \"mcpServers\": {{ \"{install_name}\": {{ ... }} }}.")
            click.echo("Example: { \"command\": \"python\", \"args\": [\"server.py\"] }")
            config_block_str = click.prompt(f"JSON config for {install_name} under {target_tool_name}", type=str)
            try:
                config_block_json = json.loads(config_block_str)
                ide_config_commands[target_tool_name] = config_block_json
            except json.JSONDecodeError:
                click.echo("Invalid JSON provided for IDE config. Skipping.", err=True)

        # Install steps (Optional)
        install_steps = []
        if click.confirm("Add custom installation steps (shell commands run after extraction)?", default=False):
            while True:
                command = click.prompt("Install step shell command (leave blank to finish)", type=str, default="", show_default=False)
                if not command:
                    break
                install_steps.append({"type": "shell", "command": command})
        # Uninstall steps
        uninstall_steps = []
        if click.confirm("Add uninstall steps?", default=False):
            while True:
                command = click.prompt("Uninstall step shell command", type=str)
                uninstall_steps.append({"type": "shell", "command": command})
                if not click.confirm("Add another uninstall step?", default=False):
                    break
        # Build metadata dict
        metadata = {
            "name": name,
            "install_name": install_name,
            "version": version
        }
        if description:
            metadata["description"] = description
        if entrypoint:
            metadata["entrypoint"] = entrypoint
        if author:
            metadata["author"] = author
        if license_:
            metadata["license"] = license_ # mcp_package.json key is 'license'
        if language:
            metadata["language"] = language
        if ide_config_commands:
            metadata["ide_config_commands"] = ide_config_commands
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
