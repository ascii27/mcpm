"""
Constants used throughout the MCPM application.
"""
import os
from pathlib import Path

# --- Installation Constants ---
# Default installation directory for packages
INSTALL_DIR = Path("~/.mcpm/packages").expanduser()

# --- Registry Constants ---
# Default registry URL (can be overridden by environment variable)
DEFAULT_REGISTRY_URL = "http://localhost:8000/api"  # Example default
# Environment variable name for the registry URL
REGISTRY_URL_ENV_VAR = "MCPM_REGISTRY_URL"

# --- Configuration Constants ---
# Environment variable for Windsurf config path override
WINDSURF_CONFIG_ENV_VAR = "WINDSURF_MCP_CONFIG_PATH"

# Default target tool configuration paths
DEFAULT_TARGET_CONFIG_PATHS = {
    "windsurf": Path("~/.codeium/windsurf/mcp_config.json"),
    # Add other tools here if needed
    # "claude-desktop": Path("~/.config/claude/mcp_servers.json"),
}

# --- Local Database Constants ---
LOCAL_DB_DIR = Path("~/.mcpm").expanduser()
LOCAL_DB_PATH = LOCAL_DB_DIR / "local_registry.db"
