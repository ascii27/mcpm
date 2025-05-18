"""
Helper functions for package operations.
"""
import os
import json
import click
import zipfile
import shutil
import subprocess
from pathlib import Path

from mcpm.config.constants import INSTALL_DIR
from mcpm.database.local_db import add_package_to_local_db, remove_package_from_local_db, store_package_input_values

def get_installed_packages():
    """Lists locally installed packages."""
    if not INSTALL_DIR.exists():
        return []
    return [d.name for d in INSTALL_DIR.iterdir() if d.is_dir()]

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
                
                # Extract package metadata for local DB
                install_name = metadata.get("install_name", package_name)
                version = metadata.get("version", "0.0.1")
                
                # Store input values in the database for later use
                store_package_input_values(install_name, install_inputs_values)
                
                # Add to local database
                add_package_to_local_db(install_name, version, str(target_install_path))
                
            except Exception as e:
                click.echo(f"Error reading install_steps from mcp_package.json: {e}", err=True)
        else:
            click.echo("No mcp_package.json found in the installed package directory.")
            # Add to local database with default values
            add_package_to_local_db(package_name, "N/A", str(target_install_path))
            
        return True, install_inputs_values
    except zipfile.BadZipFile:
        click.echo(f"Error: Downloaded file {zip_path} is not a valid zip file.", err=True)
        if os.path.exists(zip_path): os.remove(zip_path)
        return False, {}
    except Exception as e:
        click.echo(f"Error installing package {package_name}: {e}", err=True)
        if os.path.exists(zip_path): os.remove(zip_path)
        return False, {}

def create_package_archive(output_filename, source_dir='.'):
    """Creates a zip archive of the source directory."""
    source_path = Path(source_dir).resolve()
    exclude_patterns = ['.git', '__pycache__', '*.pyc', '.DS_Store', output_filename, '.venv', 'venv', '*.zip', '*.mcpz']

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

def _get_package_data_by_name(package_name, all_packages_data):
    """Finds and returns the full data dictionary for a package by its name."""
    if not all_packages_data:
        return None
    for pkg_data in all_packages_data:
        if pkg_data.get("name") == package_name:
            return pkg_data
    return None
