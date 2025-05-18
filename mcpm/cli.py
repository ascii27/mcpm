"""
Main CLI entry point for MCPM.
"""
import click

from mcpm.commands.list import list_items
from mcpm.commands.install import install_command_func
from mcpm.commands.uninstall import uninstall_command_func
from mcpm.commands.configure import configure_command_func
from mcpm.commands.create import create
from mcpm.commands.publish import publish

@click.group()
def cli():
    """Model Context Protocol Manager (MCPM)"""
    pass

@cli.command("list")
@click.option("--non-interactive", is_flag=True, help="Run in non-interactive mode")
@click.option("--search", help="Search term to filter packages")
def list_command(non_interactive, search):
    """Fetches and lists packages and servers from the registry."""
    list_items(non_interactive, search)

@cli.command("create")
@click.option("--output", "-o", help="Output filename for the package zip")
@click.option("--source", "-s", default=".", help="Source directory to package")
def create_command(output, source):
    """Create an MCP server package (zip) from the current directory."""
    create(output, source)

@cli.command("publish")
@click.argument("package_file")
def publish_command(package_file):
    """Publish an MCP server package to the registry."""
    publish(package_file)

@cli.command("install")
@click.argument("package_name")
@click.option("--target", "-t", help="Target tool to configure (e.g., 'windsurf')")
def install_command(package_name, target):
    """Installs a package or configures a server."""
    install_command_func(package_name, target)

@cli.command("uninstall")
@click.argument("package_name")
@click.option("--target", "-t", help="Target tool to de-configure (e.g., 'windsurf')")
def uninstall_command(package_name, target):
    """Uninstalls a package or de-configures a server."""
    uninstall_command_func(package_name, target)

@cli.command("configure")
@click.option("--package-name", "-p", help="Name of the package to configure")
@click.option("--target-ide", "-t", help="Target IDE to configure for (e.g., 'windsurf')")
@click.option("--action", "-a", type=click.Choice(["add", "remove"]), help="Action to perform")
@click.option("--non-interactive", is_flag=True, help="Run in non-interactive mode")
def configure_command(package_name, target_ide, action, non_interactive):
    """Configures an installed MCP package for a target IDE."""
    configure_command_func(package_name, target_ide, action, non_interactive)

if __name__ == "__main__":
    cli()
