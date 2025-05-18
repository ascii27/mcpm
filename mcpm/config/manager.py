"""
Configuration file management for MCP tools.
"""
import os
import json
import click
from pathlib import Path

from mcpm.config.constants import DEFAULT_TARGET_CONFIG_PATHS, WINDSURF_CONFIG_ENV_VAR

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

def update_mcp_config_file(config_path: Path, server_registry_name: str, server_config_str: str):
    """
    Reads, updates, and writes the target MCP JSON configuration file.
    
    Args:
        config_path: Path to the target JSON file (e.g., windsurf mcp_config.json).
        server_registry_name: The unique name used in the registry (e.g., 'my-calculator-server').
            This is currently NOT used as the key in the target file.
        server_config_str: The JSON string fetched from the registry's 'config_command' field.
            Expected format: '{"mcpServers": {"<short_name>": { ... server config ...}}}'.
    """
    if not config_path:
        click.echo("Error: No configuration path provided.", err=True)
        return False
    
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Parse the server configuration JSON string
    try:
        server_config = json.loads(server_config_str)
        if not isinstance(server_config, dict) or 'mcpServers' not in server_config:
            click.echo(f"Error: Invalid server configuration format. Expected a JSON object with 'mcpServers' key.", err=True)
            return False
    except json.JSONDecodeError:
        click.echo(f"Error: Could not parse server configuration JSON: {server_config_str}", err=True)
        return False
    
    # Get the server name and configuration from the parsed JSON
    # The config format should be: {"mcpServers": {"<short_name>": { ... server config ...}}}
    mcpServers = server_config.get('mcpServers', {})
    if not mcpServers:
        click.echo("Error: No server configuration found in the 'mcpServers' object.", err=True)
        return False
    
    # There should be exactly one server in the mcpServers object
    if len(mcpServers) != 1:
        click.echo(f"Warning: Expected exactly one server in configuration, found {len(mcpServers)}.", err=True)
    
    # Get the first (and hopefully only) server key and config
    server_short_name = next(iter(mcpServers))
    server_config_obj = mcpServers[server_short_name]
    
    # Read the existing configuration file or create a new one
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                existing_config = json.load(f)
        except json.JSONDecodeError:
            click.echo(f"Warning: Could not parse existing configuration file {config_path}. Will create a new one.", err=True)
        except IOError as e:
            click.echo(f"Warning: Could not read existing configuration file {config_path}: {e}. Will create a new one.", err=True)
    
    # Ensure the mcpServers key exists in the existing config
    if 'mcpServers' not in existing_config:
        existing_config['mcpServers'] = {}
    
    # Update the server configuration
    existing_config['mcpServers'][server_short_name] = server_config_obj
    
    # Write the updated configuration back to the file
    try:
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)
        click.echo(f"Successfully updated configuration at {config_path}")
        return True
    except IOError as e:
        click.echo(f"Error writing configuration to {config_path}: {e}", err=True)
        return False

def remove_server_from_mcp_config(config_path: Path, server_short_name: str):
    """
    Reads a target MCP JSON configuration file, removes a server entry, and writes it back.

    Args:
        config_path: Path to the target JSON configuration file.
        server_short_name: The key name of the server to remove within the 'mcpServers' object.

    Returns:
        True if successful or server was already absent, False on error.
    """
    if not config_path:
        click.echo("Error: No configuration path provided.", err=True)
        return False
    
    # If the config file doesn't exist, there's nothing to remove
    if not config_path.exists():
        click.echo(f"Configuration file {config_path} does not exist. Nothing to remove.", err=True)
        return True  # Not an error, just nothing to do
    
    # Read the existing configuration file
    try:
        with open(config_path, 'r') as f:
            existing_config = json.load(f)
    except json.JSONDecodeError:
        click.echo(f"Error: Could not parse configuration file {config_path}.", err=True)
        return False
    except IOError as e:
        click.echo(f"Error reading configuration file {config_path}: {e}", err=True)
        return False
    
    # Check if the mcpServers key exists
    if 'mcpServers' not in existing_config:
        click.echo(f"No 'mcpServers' key found in {config_path}. Nothing to remove.")
        return True  # Not an error, just nothing to do
    
    # Check if the server exists in the configuration
    if server_short_name not in existing_config['mcpServers']:
        click.echo(f"Server '{server_short_name}' not found in {config_path}. Nothing to remove.")
        return True  # Not an error, just nothing to do
    
    # Remove the server from the configuration
    del existing_config['mcpServers'][server_short_name]
    
    # Write the updated configuration back to the file
    try:
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)
        click.echo(f"Successfully removed server '{server_short_name}' from {config_path}")
        return True
    except IOError as e:
        click.echo(f"Error writing configuration to {config_path}: {e}", err=True)
        return False

def update_mcp_config_file_for_configure(config_path: Path, server_key_in_target: str, config_snippet_obj: dict, package_install_path: Path, input_values=None):
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
    if not config_path:
        click.echo("Error: No configuration path provided.", err=True)
        return False
    
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read the existing configuration file or create a new one
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                existing_config = json.load(f)
        except json.JSONDecodeError:
            click.echo(f"Warning: Could not parse existing configuration file {config_path}. Will create a new one.", err=True)
        except IOError as e:
            click.echo(f"Warning: Could not read existing configuration file {config_path}: {e}. Will create a new one.", err=True)
    
    # Ensure the mcpServers key exists in the existing config
    if 'mcpServers' not in existing_config:
        existing_config['mcpServers'] = {}
    
    # Process the config snippet to resolve relative paths and substitute variables
    processed_config = _process_config_snippet(config_snippet_obj, package_install_path, input_values)
    
    # Update the server configuration
    existing_config['mcpServers'][server_key_in_target] = processed_config
    
    # Write the updated configuration back to the file
    try:
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)
        click.echo(f"Successfully updated configuration at {config_path}")
        return True
    except IOError as e:
        click.echo(f"Error writing configuration to {config_path}: {e}", err=True)
        return False

def _process_config_snippet(config_snippet: dict, package_install_path: Path, input_values=None):
    """
    Process a configuration snippet to resolve relative paths and substitute variables.
    
    Args:
        config_snippet: The configuration snippet (dict) to process.
        package_install_path: Absolute path to the package installation directory.
        input_values: Dictionary of input values to substitute in string values.
        
    Returns:
        A processed copy of the configuration snippet with resolved paths and substituted variables.
    """
    import copy
    import json
    
    # Make a deep copy to avoid modifying the original
    processed = copy.deepcopy(config_snippet)
    
    # Resolve relative paths in the configuration
    if 'path' in processed and processed['path'] == '.':
        processed['path'] = str(package_install_path)
    
    # Substitute variables in string values if input_values provided
    if input_values:
        # Convert to JSON string
        config_str = json.dumps(processed)
        
        # Substitute variables in the string
        for var, val in input_values.items():
            config_str = config_str.replace(f"${{{var}}}", val)
        
        # Convert back to dict
        processed = json.loads(config_str)
    
    return processed
