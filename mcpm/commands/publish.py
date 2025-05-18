"""
Publish command implementation for MCPM.
"""
import click
import requests
import json
import zipfile
from pathlib import Path

from mcpm.registry.api import get_registry_url

def publish(package_file):
    """
    Publish an MCP server package to the registry.
    
    Args:
        package_file: Path to the package zip file to publish.
    """
    package_path = Path(package_file)
    if not package_path.exists():
        click.echo(f"Error: Package file '{package_file}' does not exist.", err=True)
        return
    
    # Validate the package file
    try:
        with zipfile.ZipFile(package_path, 'r') as zip_ref:
            # Check for mcp_package.json
            if "mcp_package.json" not in zip_ref.namelist():
                click.echo("Error: Package does not contain mcp_package.json.", err=True)
                return
            
            # Read the metadata
            with zip_ref.open("mcp_package.json") as f:
                metadata = json.loads(f.read().decode('utf-8'))
            
            # Check for required fields
            required_fields = ["name", "version"]
            missing_fields = [field for field in required_fields if field not in metadata]
            
            if missing_fields:
                click.echo(f"Error: mcp_package.json is missing required fields: {', '.join(missing_fields)}", err=True)
                return
            
            package_name = metadata["name"]
            package_version = metadata["version"]
    except zipfile.BadZipFile:
        click.echo(f"Error: '{package_file}' is not a valid zip file.", err=True)
        return
    except json.JSONDecodeError:
        click.echo("Error: mcp_package.json is not valid JSON.", err=True)
        return
    except Exception as e:
        click.echo(f"Error validating package: {e}", err=True)
        return
    
    # Upload the package to the registry
    click.echo(f"Publishing {package_name} (v{package_version}) to registry...")
    
    # Get the registry URL
    registry_url = get_registry_url()
    
    # Use the correct endpoint for publishing packages
    # Based on the server code, the endpoint is /api/packages/publish
    upload_url = f"{registry_url}/packages/publish"
    
    click.echo(f"Using registry URL: {registry_url}")
    click.echo(f"Publishing to: {upload_url}")
    
    try:
        with open(package_path, 'rb') as f:
            # Use the 'package' field name as expected by the server
            files = {'package': (package_path.name, f)}
            
            # Create a metadata object and convert it to a JSON string
            metadata_obj = {
                'name': package_name,
                'version': package_version,
                'description': metadata.get('description', ''),
                'author': metadata.get('author', ''),
                'license': metadata.get('license', ''),
                'runtime': metadata.get('runtime', 'generic'),
                'entrypoint': metadata.get('entrypoint', '')
            }
            
            # Send metadata as a JSON string in a field called 'metadata'
            data = {
                'metadata': json.dumps(metadata_obj)
            }
            
            # Make the request
            response = requests.post(upload_url, files=files, data=data)
            
            if response.status_code == 200 or response.status_code == 201:
                click.echo(f"Successfully published {package_name} (v{package_version}) to registry.")
            else:
                click.echo(f"Error publishing package: {response.text}", err=True)
    except requests.exceptions.RequestException as e:
        click.echo(f"Error connecting to registry: {e}", err=True)
