"""
Local SQLite database operations for tracking installed packages.
"""
import sqlite3
import click
import json
from pathlib import Path

from mcpm.config.constants import LOCAL_DB_DIR, LOCAL_DB_PATH

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
            
            # Create table for storing package input values
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS package_input_values (
                    package_name TEXT NOT NULL,
                    input_name TEXT NOT NULL,
                    input_value TEXT NOT NULL,
                    is_secret INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (package_name, input_name)
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
            # Remove from installed_packages table
            cursor.execute("DELETE FROM installed_packages WHERE name = ?", (install_name,))
            
            # Also remove any stored input values for this package
            cursor.execute("DELETE FROM package_input_values WHERE package_name = ?", (install_name,))
            
            conn.commit()
            if cursor.rowcount > 0:
                click.echo(f"Package {install_name} marked as uninstalled locally.")
            else:
                click.echo(f"Package {install_name} was not found in the local installation record.", err=True)
        except sqlite3.Error as e:
            click.echo(f"Error removing package {install_name} from local database: {e}", err=True)
        finally:
            conn.close()

def get_all_installed_package_details():
    """Fetches details for all installed packages from the local database.
    
    Returns:
        A list of dictionaries, each containing package details (name, version, install_path, installed_at).
    """
    conn = _get_local_db_connection()
    if not conn:
        return []
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name, version, install_path, installed_at FROM installed_packages")
        rows = cursor.fetchall()
        
        # Convert rows to a list of dictionaries
        packages = []
        for row in rows:
            packages.append({
                "name": row[0],
                "version": row[1],
                "install_path": row[2],
                "installed_at": row[3]
            })
        return packages
    except sqlite3.Error as e:
        click.echo(f"Error fetching installed packages: {e}", err=True)
        return []
    finally:
        conn.close()

def store_package_input_values(package_name, input_values):
    """Stores input values for a package in the local database.
    
    Args:
        package_name: The name of the package (install_name).
        input_values: Dictionary of input values to store.
    """
    if not input_values:
        return
        
    conn = _get_local_db_connection()
    if not conn:
        return
        
    try:
        cursor = conn.cursor()
        for input_name, input_value in input_values.items():
            # Check if this is a secret value
            is_secret = False
            
            # Store the input value
            cursor.execute('''
                INSERT OR REPLACE INTO package_input_values 
                (package_name, input_name, input_value, is_secret, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (package_name, input_name, input_value, 1 if is_secret else 0))
        
        conn.commit()
        click.echo(f"Stored input values for package {package_name}.")
    except sqlite3.Error as e:
        click.echo(f"Error storing input values for package {package_name}: {e}", err=True)
    finally:
        conn.close()

def get_package_input_values(package_name):
    """Retrieves stored input values for a package from the local database.
    
    Args:
        package_name: The name of the package (install_name).
        
    Returns:
        A dictionary of input values keyed by input name.
    """
    conn = _get_local_db_connection()
    if not conn:
        return {}
        
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT input_name, input_value, is_secret FROM package_input_values WHERE package_name = ?", 
            (package_name,)
        )
        rows = cursor.fetchall()
        
        # Convert rows to a dictionary
        input_values = {}
        for row in rows:
            input_name, input_value, is_secret = row
            input_values[input_name] = input_value
            
        return input_values
    except sqlite3.Error as e:
        click.echo(f"Error retrieving input values for package {package_name}: {e}", err=True)
        return {}
    finally:
        conn.close()
