import click
import os
import requests
import zipfile
import json
import shutil
from pathlib import Path

# --- Constants ---
# Read registry URL from environment variable or use default
DEFAULT_REGISTRY_URL = "http://localhost:8000/api" # Correct base URL
REGISTRY_URL = os.environ.get("MCPM_REGISTRY_URL", DEFAULT_REGISTRY_URL).rstrip('/')

# Configuration
INSTALL_DIR = Path.home() / ".mcpm" / "packages"

# Ensure installation directory exists
INSTALL_DIR.mkdir(parents=True, exist_ok=True)

# --- Helper Functions (Stubs/Placeholders) ---

def get_registry_packages():
    """Fetches the list of available packages (latest versions) from the registry."""
    packages_url = f"{REGISTRY_URL}/packages/" # Append specific path
    try:
        response = requests.get(packages_url)
        response.raise_for_status() # Raise an exception for bad status codes
        return response.json() # Assuming the registry returns JSON list of packages
    except requests.exceptions.RequestException as e:
        click.echo(f"Error connecting to registry at {REGISTRY_URL}: {e}", err=True)
        return None

def get_registry_servers():
    """Fetches the list of all registered servers from the registry."""
    servers_url = f"{REGISTRY_URL}/servers" # Append specific path
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

def get_registry_server(server_name):
    """Fetches a specific server registration from the registry."""
    servers = get_registry_servers() # Can reuse the all-servers fetch
    if servers:
        for server in servers:
            if server.get('name') == server_name:
                return server # Return the dictionary for the found server
    return None # Return None if fetch failed or server not found

def download_package(package_name, version="latest"):
    """Downloads a specific package version from the registry."""
    # TODO: Implement version handling
    download_url = f"{REGISTRY_URL}/packages/{package_name}/{version}/download" # Append specific path
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
    """Installs a package from a downloaded zip file."""
    target_install_path = INSTALL_DIR / package_name
    try:
        if target_install_path.exists():
            # Handle upgrades/reinstalls more gracefully
            click.echo(f"Package {package_name} already exists. Removing existing version.")
            shutil.rmtree(target_install_path) # Use shutil to remove existing directory

        click.echo(f"Installing {package_name} to {target_install_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_install_path)

        # Clean up the temporary zip file
        os.remove(zip_path)
        click.echo(f"Successfully installed {package_name}.")
        return True
    except zipfile.BadZipFile:
        click.echo(f"Error: Downloaded file {zip_path} is not a valid zip file.", err=True)
        if os.path.exists(zip_path): os.remove(zip_path)
        return False
    except Exception as e:
        click.echo(f"Error installing package {package_name}: {e}", err=True)
        # Clean up partially extracted files? Maybe later.
        if os.path.exists(zip_path): os.remove(zip_path)
        return False

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

# --- CLI Commands ---

@click.group()
def cli():
    """Model Context Protocol Manager (MCPM)"""
    pass

@cli.command()
def list():
    """List available packages and registered servers in the registry."""
    click.echo("Fetching data from registry...")

    # Fetch Servers
    servers = get_registry_servers()
    click.echo("\n--- Registered Servers ---")
    if servers is None:
        click.echo("Could not retrieve server list.")
    elif not servers:
        click.echo("No servers registered.")
    else:
        for server in servers:
            name = server.get('name', 'Unknown')
            lang = server.get('language', 'N/A')
            url = server.get('github_url', '')
            click.echo(f"- {name} (Language: {lang}) {f'[{url}]' if url else ''}")

    # Fetch Packages
    packages = get_registry_packages()
    click.echo("\n--- Available Packages (Latest Versions) ---")
    if packages is None:
        click.echo("Could not retrieve package list.")
    elif not packages:
        click.echo("No packages published.")
    else:
        # Assuming packages is a list of dicts with a 'name' key
        for pkg in packages:
            # Adjust based on actual registry API response format
            name = pkg.get('name', 'Unknown')
            version = pkg.get('latest_version', 'N/A')
            description = pkg.get('description', '')
            click.echo(f"- {name} (v{version}): {description}")

@cli.command()
@click.argument('package_name')
# @click.option('--version', default='latest', help='Specify package version.') # Add later
def install(package_name):
    """Install an MCP server package or display registered server config."""
    click.echo(f"Checking registry for server or package: {package_name}...")

    # 1. Check if it's a registered server
    server_info = get_registry_server(package_name)
    if server_info:
        click.echo(f"Found registered server entry: {package_name}")
        click.echo("Configuration command:")
        # Pretty print the config if it's valid JSON, otherwise print raw
        config_command = server_info.get('config_command')
        try:
            # Attempt to parse and pretty-print JSON
            config_json = json.loads(config_command)
            click.echo(json.dumps(config_json, indent=2))
        except (json.JSONDecodeError, TypeError):
            # If not valid JSON or None, print as is
            click.echo(config_command if config_command else "(No config command provided)")
        return # Exit after printing config

    # 2. If not a server, try installing as a package (existing logic)
    click.echo(f"'{package_name}' not found as a registered server. Attempting to install as a package...")
    version = "latest" # Assuming 'latest' for now
    zip_path = download_package(package_name, version)
    if zip_path:
        install_package_from_zip(zip_path, package_name)
        # Clean up the downloaded zip file after successful installation
        try:
            os.remove(zip_path)
            click.echo(f"Cleaned up temporary file: {zip_path}")
        except OSError as e:
            click.echo(f"Warning: Could not remove temporary file {zip_path}: {e}", err=True)
    else:
        # download_package already prints errors if download fails or package not found
        click.echo(f"Failed to find or download package '{package_name}'.", err=True)

@cli.command(name='uninstall')
@click.argument('package_name')
def uninstall(package_name):
    """Uninstall an installed MCP server package."""
    target_path = INSTALL_DIR / package_name
    if target_path.exists() and target_path.is_dir():
        try:
            click.echo(f"Removing package {package_name} from {target_path}...")
            shutil.rmtree(target_path) # Use shutil for actual removal
            click.echo(f"Successfully removed {package_name}.")
        except OSError as e:
            click.echo(f"Error removing package {package_name}: {e}", err=True)
    else:
        click.echo(f"Package {package_name} is not installed or is not a directory.", err=True)

@cli.command()
def create():
    """Create an MCP server package (zip) from the current directory."""
    metadata_file = Path('mcp_package.json')
    if not metadata_file.exists():
        click.echo(f"Error: {metadata_file} not found in the current directory.", err=True)
        click.echo("Please create this file with package name and version.")
        return

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

    if not package_name or not package_version:
        click.echo(f"Error: 'name' and 'version' must be defined in {metadata_file}.", err=True)
        return

    # Sanitize name for filename (basic example)
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in package_name)
    output_filename = f"{safe_name}-{package_version}.zip"

    create_package_archive(output_filename, source_dir='.')

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

    publish_url = f"{REGISTRY_URL}/packages/publish" # Append specific path
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
