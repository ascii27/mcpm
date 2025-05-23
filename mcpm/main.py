"""MCPM - Model Context Protocol Manager"""

# This file is kept for backward compatibility
# New code should import from the appropriate modules

from mcpm.cli import cli

# Re-export all the CLI commands for backward compatibility
from mcpm.commands.list import list_items
from mcpm.commands.install import install_command_func
from mcpm.commands.uninstall import uninstall_command_func
from mcpm.commands.configure import configure_command_func
from mcpm.commands.create import create
from mcpm.commands.publish import publish

if __name__ == '__main__':
    cli()
