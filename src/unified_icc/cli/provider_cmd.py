"""unified-icc provider list/get"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from unified_icc.providers import get_provider, registry

console = Console()
app = typer.Typer(help="Manage agent providers.", no_args_is_help=True)


@app.command("list")
def provider_list() -> None:
    """List all available providers."""
    # Trigger lazy registration
    get_provider()
    names = registry.provider_names()
    table = Table(title="Available Providers")
    table.add_column("Name", style="cyan")
    table.add_column("YOLO", style="yellow")
    table.add_column("Launch Command", style="dim")

    for name in names:
        prov = registry.get(name)
        caps = prov.capabilities
        yolo = "yes" if caps.has_yolo_confirmation else "no"
        table.add_row(name, yolo, caps.launch_command)

    console.print(table)


@app.command("get")
def provider_get(
    name: str | None = typer.Option(None, "--name", help="Provider name (default: current)"),
) -> None:
    """Show details of a provider."""
    # Ensure providers are registered
    get_provider()
    if name is None:
        prov = get_provider()
        name = prov.capabilities.name

    if not registry.is_valid(name):
        console.print(f"[red]Unknown provider: {name}[/red]")
        raise typer.Exit(1)

    prov = registry.get(name)
    caps = prov.capabilities
    table = Table(title=f"Provider: {name}", show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Name", caps.name)
    table.add_row("Launch Command", caps.launch_command)
    table.add_row("YOLO Mode", "yes" if caps.has_yolo_confirmation else "no")
    table.add_row("Hook Support", "yes" if caps.supports_hook else "no")
    table.add_row("Resume", "yes" if caps.supports_resume else "no")
    table.add_row("Continue", "yes" if caps.supports_continue else "no")
    table.add_row("Transcript Format", caps.transcript_format)
    console.print(table)
