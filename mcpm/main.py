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
import questionary
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


def get_all_installed_package_details():
    """Fetches details for all installed packages from the local database as a list of dictionaries."""
    conn = None
    try:
        conn = _get_local_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, version, install_path, installed_at FROM installed_packages")
        packages_tuples = cursor.fetchall()
        
        packages_list_of_dicts = []
        for row_tuple in packages_tuples:
            packages_list_of_dicts.append({
                "name": row_tuple[0], # This is the package's install_name
                "version": row_tuple[1],
                "install_path": row_tuple[2],
                "installed_at": row_tuple[3]
            })
        return packages_list_of_dicts
    except sqlite3.Error as e:
        click.echo(f"Database error while fetching installed package details: {e}", err=True)
        return [] 
    finally:
        if conn:
            conn.close()

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

# --- Helper for 'configure' command: Update MCP JSON config with object ---
def update_mcp_config_file_for_configure(config_path: Path, server_key_in_target: str, config_snippet_obj: dict, package_install_path: Path):
    """
    Reads, updates, and writes the target MCP JSON configuration file using a snippet object.
    The server_key_in_target (package's install_name) will be the key for the snippet.
    Relative paths within the snippet (e.g., "path": ".") will be resolved.

    Args:
        config_path: Path to the target JSON file (e.g., windsurf mcp_config.json).
        server_key_in_target: The key for this server entry in the target config (package's install_name).
        config_snippet_obj: The configuration snippet (dict) to add/update.
        package_install_path: Absolute path to the package installation directory.
    """
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if config_path.exists() and config_path.stat().st_size > 0:
            with open(config_path, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        click.echo(f"Warning: Existing config file {config_path} does not contain a JSON object. Initializing structure.", err=True)
                        data = {}
                except json.JSONDecodeError:
                    click.echo(f"Warning: Could not parse existing config file {config_path}. Backing up and creating new.", err=True)
                    backup_path = config_path.with_suffix(config_path.suffix + '.bak')
                    try:
                        shutil.copyfile(config_path, backup_path)
                        click.echo(f"Backed up existing config to {backup_path}")
                    except Exception as backup_e:
                        click.echo(f"Warning: Failed to back up existing config file: {backup_e}", err=True)
                    data = {}
        
        if 'mcpServers' not in data or not isinstance(data.get('mcpServers'), dict):
            click.echo(f"Initializing 'mcpServers' object in {config_path}.")
            data['mcpServers'] = {}

        # Process the snippet: copy and resolve paths
        processed_snippet = json.loads(json.dumps(config_snippet_obj)) # Deep copy

        if 'path' in processed_snippet and isinstance(processed_snippet['path'], str) and not Path(processed_snippet['path']).is_absolute():
            original_snippet_path = processed_snippet['path']
            absolute_path = (package_install_path / original_snippet_path).resolve()
            processed_snippet['path'] = str(absolute_path)
            click.echo(f"Resolved path for server '{server_key_in_target}' from '{original_snippet_path}' to '{absolute_path}'.")

        click.echo(f"Adding/Updating configuration for server '{server_key_in_target}' in {config_path}...")
        data['mcpServers'][server_key_in_target] = processed_snippet

        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

        click.echo(f"Successfully updated {config_path} for server '{server_key_in_target}'.")
        return True

    except IOError as e:
        click.echo(f"Error writing to config file {config_path}: {e}", err=True)
        return False
    except Exception as e:
        import traceback
        click.echo(f"An unexpected error occurred while updating {config_path} for '{server_key_in_target}':", err=True)
        click.echo(traceback.format_exc(), err=True)
        return False

# --- CLI Commands ---

@click.group()
def cli():
    """Model Context Protocol Manager (MCPM)"""
    pass

@cli.command("list")
@click.option('--non-interactive', is_flag=True, help="Run in non-interactive mode, just lists packages and servers.")
def list_items(non_interactive):
    """Fetches and lists both packages and servers from the registry.
    In interactive mode (default), allows management of packages.
    """
    init_local_db() # Ensure DB is initialized

    click.echo("Fetching packages from registry...")
    packages_data = get_registry_packages()
    click.echo("Fetching servers from registry...")
    servers_data = get_registry_servers() # Assuming this returns a list of server dicts

    # Get details of all installed packages from the local DB
    # get_all_installed_package_details() now returns a list of dictionaries
    installed_packages_list_of_dicts = get_all_installed_package_details()
    
    # For quick lookup by install_name (which is 'name' in the dicts)
    installed_packages_info = {
        pkg_dict['name']: {
            "version": pkg_dict.get('version'),
            "path": pkg_dict.get('install_path'),
            "installed_at": pkg_dict.get('installed_at')
        }
        for pkg_dict in installed_packages_list_of_dicts
    }

    if non_interactive:
        click.echo("\n--- Available Packages ---")
        if packages_data:
            for pkg in packages_data:
                pkg_name = pkg.get("name") # This is the registry name
                pkg_version = pkg.get("version")
                install_status = ""
                if pkg_name in installed_packages_info: # Check against our prepared dict
                    install_status = f"[INSTALLED v{installed_packages_info[pkg_name].get('version', 'N/A')}]"
                click.echo(f"- {pkg_name} (v{pkg_version}) {install_status}")
        else:
            click.echo("No packages found in the registry or registry is unavailable.")

        click.echo("\n--- Registered MCP Servers ---")
        if servers_data:
            for server in servers_data:
                server_reg_name = server.get('registry_name', 'Unknown Server Name')
                description = server.get('description', 'No description')
                install_status = ""
                if server_reg_name in installed_packages_info: # Assuming server_reg_name can be an install_name
                     install_status = f"[CONFIGURED/INSTALLED v{installed_packages_info[server_reg_name].get('version', 'N/A')}]" 
                click.echo(f"- {server_reg_name}: {description} {install_status}")
        else:
            click.echo("No MCP servers found in the registry or registry is unavailable.")
        return

    # --- Interactive Mode ---
    choices = []
    if packages_data:
        choices.append(questionary.Separator("-- Available Packages (from Registry) --"))
        for pkg_data in packages_data:
            pkg_registry_name = pkg_data.get("name")
            pkg_registry_version = pkg_data.get("version", "N/A")
            
            is_installed = pkg_registry_name in installed_packages_info
            
            action_verb = "Uninstall" if is_installed else "Install"
            display_version = installed_packages_info[pkg_registry_name].get('version', pkg_registry_version) if is_installed else pkg_registry_version
            
            title = f"{action_verb} {pkg_registry_name} (v{display_version})"
            if is_installed:
                title += f" - Installed at {installed_packages_info[pkg_registry_name].get('path', 'N/A')}"
            
            value_action = "uninstall" if is_installed else "install"
            value = f"{value_action}:{pkg_registry_name}"

            choices.append(questionary.Choice(title=title, value=value))

    if installed_packages_list_of_dicts:
        choices.append(questionary.Separator("-- Locally Installed Packages (from DB) --"))
        for pkg_dict in installed_packages_list_of_dicts:
            if not any(hasattr(choice, 'value') and choice.value == f"uninstall:{pkg_dict['name']}" for choice in choices):
                choices.append(
                    questionary.Choice(
                        title=f"Uninstall {pkg_dict['name']} (v{pkg_dict.get('version', 'N/A')}) - Installed at {pkg_dict.get('install_path', 'N/A')}",
                        value=f"uninstall:{pkg_dict['name']}"
                    )
                )
    
    if not choices:
        click.echo("No packages available in registry or installed locally.")
        return

    selected_action_value = questionary.select(
        "Manage Packages (select to install/uninstall, or Exit):",
        choices=choices + [questionary.Separator(), questionary.Choice("Exit", value="exit_interactive_list")],
        use_shortcuts=True
    ).ask()

    if selected_action_value and selected_action_value != "exit_interactive_list":
        action_type, name = selected_action_value.split(":", 1)
        ctx = click.get_current_context()
        if action_type == "install":
            click.echo(f"Preparing to install '{name}'...")
            ctx.invoke(cli.commands['install'], package_name=name, target=None)
        elif action_type == "uninstall":
            click.echo(f"Preparing to uninstall '{name}'...")
            ctx.invoke(cli.commands['uninstall'], package_name=name, target=None)
    else:
        click.echo("Exiting package management or no action selected.")


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


@cli.command(name="install")
@click.argument('package_name')
@click.option('--target', default=None, help="Target tool for server configuration (e.g., 'windsurf')")
def install_command_func(package_name, target):
    """Installs a package or configures a server."""
    # For now, this function primarily handles package installation logic
    # Server configuration logic would need to be distinctly handled if 'target' is specified.
    click.echo(f"Attempting to install package: {package_name}")

    downloaded_zip = download_package(package_name) # Assumes version='latest'
    if downloaded_zip:
        # install_package_from_zip returns: success (bool), install_inputs_values (dict)
        success, _ = install_package_from_zip(downloaded_zip, package_name)
        if success:
            package_install_full_path = INSTALL_DIR / package_name
            metadata_path = package_install_full_path / "mcp_package.json"
            version_to_store = "unknown"
            install_name_to_store = package_name # Default to the argument if no metadata

            if metadata_path.exists():
                try:
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    # Use 'install_name' from metadata for DB key if available, else use package_name argument
                    install_name_to_store = metadata.get("install_name", package_name)
                    version_to_store = metadata.get("version", "unknown")
                except Exception as e:
                    click.echo(f"Warning: Could not read metadata from {metadata_path} for version/install_name: {e}", err=True)
            
            add_package_to_local_db(install_name_to_store, version_to_store, str(package_install_full_path))
            # click.echo(f"Package {install_name_to_store} (v{version_to_store}) recorded as installed.") # Redundant with add_package_to_local_db output
        else:
            click.echo(f"Installation process failed for {package_name}.", err=True)
    else:
        click.echo(f"Download failed for package {package_name}.", err=True)


@cli.command(name="uninstall")
@click.argument('package_name') # This should ideally be the 'install_name' used in the DB
@click.option('--target', default=None, help="Target tool for server de-configuration (e.g., 'windsurf')")
def uninstall_command_func(package_name, target):
    """Uninstalls a package or de-configures a server."""
    # This function primarily handles package uninstallation.
    # Server de-configuration would be separate.
    click.echo(f"Attempting to uninstall package: {package_name}")

    # We should use the name that's stored in the database (install_name).
    # For now, we assume package_name argument IS the install_name.
    if not is_package_installed(package_name):
        click.echo(f"Package '{package_name}' is not listed as installed in the local database.", err=True)
        return

    # To get the actual install path, we'd ideally query the DB.
    # For now, construct path using INSTALL_DIR and the assumed package_name (as dir name)
    package_install_full_path = INSTALL_DIR / package_name 

    # --- Run uninstall_steps from mcp_package.json --- 
    metadata_path = package_install_full_path / "mcp_package.json"
    if metadata_path.exists() and package_install_full_path.exists(): # only chdir if path exists
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            uninstall_steps = metadata.get("uninstall_steps", [])
            if uninstall_steps:
                click.echo(f"Running uninstall steps for {package_name} from {package_install_full_path}...")
                original_cwd = os.getcwd()
                try:
                    os.chdir(package_install_full_path)
                    click.echo(f"Changed directory to {package_install_full_path} for uninstall steps.")
                    for idx, step in enumerate(uninstall_steps, 1):
                        if step.get("type") == "shell" and "command" in step:
                            command = step["command"]
                            click.echo(f"Step {idx}: {command}")
                            if click.confirm(f"Run uninstall command: '{command}' in {os.getcwd()}?", default=True):
                                process_result = subprocess.run(command, shell=True, capture_output=True, text=True)
                                if process_result.stdout: click.echo(f"Output:\n{process_result.stdout.strip()}")
                                if process_result.stderr: click.echo(f"Error output:\n{process_result.stderr.strip()}", err=True)
                                if process_result.returncode != 0:
                                    click.echo(f"Warning: Uninstall command '{command}' exited with code {process_result.returncode}", err=True)
                            else:
                                click.echo("Skipped this uninstall step.")
                except FileNotFoundError:
                    click.echo(f"Error: Package directory {package_install_full_path} not found for running uninstall steps.", err=True)
                except Exception as e_chdir:
                    click.echo(f"Error changing directory or running uninstall steps: {e_chdir}", err=True)
                finally:
                    os.chdir(original_cwd)
                    click.echo(f"Restored directory to {original_cwd}.")
            else:
                click.echo("No uninstall steps defined in mcp_package.json.")
        except Exception as e:
            click.echo(f"Error reading uninstall_steps from {metadata_path}: {e}", err=True)
    elif not package_install_full_path.exists():
        click.echo(f"Package directory {package_install_full_path} does not exist. Cannot run uninstall steps.", err=True)
    else: # metadata_path does not exist but package_install_full_path does
        click.echo(f"No {metadata_path.name} found in {package_install_full_path}. Skipping uninstall steps.")

    # --- Remove package directory --- 
    if package_install_full_path.exists():
        try:
            shutil.rmtree(package_install_full_path)
            click.echo(f"Successfully removed directory {package_install_full_path}.")
            # Remove from local DB *after* successful directory removal
            remove_package_from_local_db(package_name) 
        except OSError as e:
            click.echo(f"Error removing package directory {package_install_full_path}: {e}", err=True)
            click.echo("You may need to remove it manually. The record in local DB will remain until resolved.")
    else:
        click.echo(f"Package directory {package_install_full_path} not found. Assuming already removed.")
        # If directory is gone, ensure it's also removed from DB
        remove_package_from_local_db(package_name)

@cli.command("configure")
@click.option('--package-name', default=None, help="The (install) name of the package to configure. Required in non-interactive mode.")
@click.option('--target-ide', default=None, help="The target IDE to configure (e.g., 'windsurf'). Required in non-interactive mode.")
@click.option('--action', type=click.Choice(['add', 'remove'], case_sensitive=False), default=None, help="Action to perform: 'add' or 'remove'. Required in non-interactive mode.")
@click.option('--non-interactive', is_flag=True, help="Run in non-interactive mode, requires all options to be set.")
def configure_command_func(package_name, target_ide, action, non_interactive):
    """Configures an installed MCP package for a target IDE."""
    init_local_db() # Ensure DB is initialized

    if non_interactive:
        if not all([package_name, target_ide, action]):
            click.echo("Error: In non-interactive mode, --package-name, --target-ide, and --action are required.", err=True)
            sys.exit(1)
        
        # Fetch details for the specified package
        installed_packages_list = get_all_installed_package_details() # Returns list of dicts
        selected_package_details = None
        for pkg_dict in installed_packages_list:
            if pkg_dict['name'] == package_name: # 'name' in DB is the install_name
                selected_package_details = pkg_dict
                break
        
        if not selected_package_details:
            click.echo(f"Error: Package '{package_name}' not found or not installed.", err=True)
            sys.exit(1)
        
        pkg_install_name = selected_package_details['name'] # This is the name from the DB, used as key
        pkg_install_path = Path(selected_package_details['install_path'])

    else: # Interactive mode
        installed_packages = get_all_installed_package_details() # list of dicts
        if not installed_packages:
            click.echo("No packages are currently installed. Cannot configure.", err=True)
            return

        package_choices = [
            # Display format: "PackageName (v1.0) - /path/to/install"
            f"{pkg['name']} (v{pkg.get('version', 'N/A')}) - {pkg.get('install_path', 'N/A')}" 
            for pkg in installed_packages
        ]
        if not package_choices:
            click.echo("No installed packages found to configure (this should not happen if installed_packages is not empty).", err=True)
            return

        selected_pkg_display_name = questionary.select(
            "Select the package to configure:",
            choices=package_choices
        ).ask()

        if not selected_pkg_display_name:
            click.echo("No package selected. Exiting.")
            return

        # Find the full details of the selected package
        # Because display name includes version and path, we need to find the match carefully
        selected_package_details = None
        for pkg in installed_packages:
            # Reconstruct the display name to match
            current_pkg_display = f"{pkg['name']} (v{pkg.get('version', 'N/A')}) - {pkg.get('install_path', 'N/A')}"
            if current_pkg_display == selected_pkg_display_name:
                selected_package_details = pkg
                break
        
        if not selected_package_details: # Should not happen if selection was from list
            click.echo("Error: Could not retrieve details for the selected package.", err=True)
            sys.exit(1)

        pkg_install_name = selected_package_details['name']
        pkg_install_path = Path(selected_package_details['install_path'])

        # Load mcp_package.json to get available IDEs for selection
        mcp_package_json_path_interactive = pkg_install_path / "mcp_package.json"
        if not mcp_package_json_path_interactive.exists():
            click.echo(f"Error: mcp_package.json not found at {mcp_package_json_path_interactive} for package '{pkg_install_name}'.", err=True)
            click.echo("Cannot determine available IDEs for configuration.")
            return 

        try:
            with open(mcp_package_json_path_interactive, 'r') as f_interactive:
                package_metadata_interactive = json.load(f_interactive)
        except json.JSONDecodeError:
            click.echo(f"Error: Could not parse {mcp_package_json_path_interactive} when attempting to list available IDEs.", err=True)
            return
        except IOError as e:
            click.echo(f"Error reading {mcp_package_json_path_interactive} for IDE selection: {e}", err=True)
            return

        ide_configs_from_pkg_json = package_metadata_interactive.get('ide_config_commands', {})
        if not ide_configs_from_pkg_json:
            click.echo(f"No IDE configurations ('ide_config_commands') found in {mcp_package_json_path_interactive} for package '{pkg_install_name}'.", err=True)
            click.echo("Cannot proceed to select an IDE.")
            return
        
        available_ide_keys = list(ide_configs_from_pkg_json.keys())
        if not available_ide_keys: # Should be caught by the above, but as a safeguard
            click.echo(f"No IDE keys found under 'ide_config_commands' in {mcp_package_json_path_interactive}.", err=True)
            return

        target_ide = questionary.select(
            f"Select target IDE to configure for package '{pkg_install_name}':",
            choices=available_ide_keys
        ).ask()

        if not target_ide:
            click.echo("No target IDE selected. Exiting.")
            return
        
        action = questionary.select(
            "Select action to perform:",
            choices=[
                questionary.Choice("Add/Update configuration in IDE", "add"),
                questionary.Choice("Remove configuration from IDE", "remove")
            ]
        ).ask()

        if not action:
            click.echo("No action selected. Exiting.")
            return

    # --- Common logic for both interactive and non-interactive modes from here ---
    
    # Re-fetch mcp_package.json for the selected package to get the config snippet
    # This is slightly redundant if in interactive mode but ensures consistency
    mcp_package_json_path = pkg_install_path / "mcp_package.json"
    if not mcp_package_json_path.exists(): # Should have been caught earlier in interactive
        click.echo(f"Error: Critical - mcp_package.json not found at {mcp_package_json_path}", err=True)
        sys.exit(1)

    try:
        with open(mcp_package_json_path, 'r') as f:
            package_metadata = json.load(f)
    except json.JSONDecodeError:
        click.echo(f"Error: Could not parse mcp_package.json at {mcp_package_json_path}", err=True)
        sys.exit(1)
    except IOError as e:
        click.echo(f"Error reading mcp_package.json at {mcp_package_json_path}: {e}", err=True)
        sys.exit(1)

    # Validate install_name consistency (DB vs mcp_package.json)
    # pkg_install_name is from DB (and is the key for IDE config)
    # package_metadata.get('install_name') is from the package's own JSON file.
    metadata_actual_install_name = package_metadata.get('install_name')
    if metadata_actual_install_name != pkg_install_name:
        click.echo(f"Warning: Mismatch detected in 'install_name' for the package.", err=True)
        click.echo(f"  - The local database record (and IDE configuration key) uses: '{pkg_install_name}'.")
        click.echo(f"  - The package's mcp_package.json file specifies: '{metadata_actual_install_name}'.")
        click.echo(f"  Proceeding with '{pkg_install_name}' as the key for IDE configuration.", err=True)
        click.echo("  It is highly recommended that 'install_name' in mcp_package.json matches the initial installation name and remains unique and stable.", err=True)
        # We use pkg_install_name from the DB as the definitive key for the IDE config,
        # as this is what would have been used if it was previously configured.

    ide_configs = package_metadata.get('ide_config_commands', {})
    if target_ide not in ide_configs:
        click.echo(f"Error: Target IDE '{target_ide}' not found in 'ide_config_commands' within {mcp_package_json_path} for package '{pkg_install_name}'.", err=True)
        available_ides_final_check = list(ide_configs.keys())
        if available_ides_final_check:
            click.echo(f"Available IDE configurations in this package: {', '.join(available_ides_final_check)}")
        else:
            click.echo("No IDE configurations are defined in this package's mcp_package.json.")
        sys.exit(1)

    config_snippet_obj = ide_configs[target_ide] # This is the JSON object for the target IDE
    if not isinstance(config_snippet_obj, dict):
        click.echo(f"Error: Configuration snippet for '{target_ide}' in {mcp_package_json_path} is not a valid JSON object (dictionary).", err=True)
        sys.exit(1)

    target_mcp_config_file_path = get_target_config_path(target_ide)
    if not target_mcp_config_file_path:
        click.echo(f"Error: Could not determine the MCP configuration file path for target IDE '{target_ide}'.", err=True)
        click.echo(f"Please check DEFAULT_TARGET_CONFIG_PATHS in mcpm/main.py or relevant environment variables (e.g., {WINDSURF_CONFIG_ENV_VAR} for Windsurf).", err=True)
        sys.exit(1)

    # Confirmation prompt (unless in non-interactive mode and --yes is implied)
    confirmation_message = ""
    if action == 'add':
        confirmation_message = f"This will ADD/UPDATE the configuration for package '{pkg_install_name}' (IDE: {target_ide}) in the file: {target_mcp_config_file_path}."
    elif action == 'remove':
        confirmation_message = f"This will REMOVE the configuration for package '{pkg_install_name}' (IDE: {target_ide}) from the file: {target_mcp_config_file_path}."
    
    if not non_interactive: # Always confirm in interactive mode
        if not click.confirm(f"{confirmation_message}\nProceed?", default=True):
            click.echo("Operation cancelled by user.")
            return
    # In non-interactive, providing all flags implies confirmation for now.
    # A future --yes flag would make this more explicit.

    if action == 'add':
        click.echo(f"Adding/Updating configuration for '{pkg_install_name}' in '{target_mcp_config_file_path}' for IDE '{target_ide}'...")
        success = update_mcp_config_file_for_configure(
            config_path=target_mcp_config_file_path,
            server_key_in_target=pkg_install_name, # Use the DB install_name as the key
            config_snippet_obj=config_snippet_obj,
            package_install_path=pkg_install_path
        )
        if success:
            click.echo(f"Successfully ADDED/UPDATED configuration for '{pkg_install_name}' for IDE '{target_ide}'.")
        else:
            click.echo(f"FAILED to add/update configuration for '{pkg_install_name}' for IDE '{target_ide}'.", err=True)

    elif action == 'remove':
        click.echo(f"Removing configuration for '{pkg_install_name}' from '{target_mcp_config_file_path}' for IDE '{target_ide}'...")
        success = remove_server_from_mcp_config(
            config_path=target_mcp_config_file_path,
            server_short_name=pkg_install_name # Use the DB install_name as the key to remove
        )
        if success:
            click.echo(f"Successfully REMOVED configuration for '{pkg_install_name}' for IDE '{target_ide}'.")
        else:
            click.echo(f"FAILED to remove configuration for '{pkg_install_name}' for IDE '{target_ide}'. Check if it existed or if there was a file access issue.", err=True)
    else:
        # This case should ideally not be reached due to click.Choice and interactive selection
        click.echo(f"Error: Unknown action '{action}'. This should have been caught earlier.", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
