"""unified-icc config list/get/set"""

from __future__ import annotations


import typer
from rich.console import Console

from unified_icc.utils.config import config

console = Console()
app = typer.Typer(help="View and modify gateway configuration.", no_args_is_help=True)

# Keys that users can see/get
CONFIG_KEYS = {
    "tmux_session_name": "Tmux session name",
    "provider_name": "Default agent provider",
    "monitor_poll_interval": "Monitor poll interval (seconds)",
    "autoclose_done_minutes": "Auto-close done sessions after (minutes)",
    "autoclose_dead_minutes": "Auto-close dead sessions after (minutes)",
    "config_dir": "Config directory",
}


@app.command("list")
def config_list() -> None:
    """List all configuration keys and values."""
    from rich.table import Table
    table = Table(title="Gateway Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Description", style="dim")

    for key, desc in CONFIG_KEYS.items():
        val = str(getattr(config, key, "(not set)"))
        table.add_row(key, val, desc)

    console.print(table)


@app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Configuration key"),
) -> None:
    """Get a configuration value."""
    if not hasattr(config, key):
        console.print(f"[red]Unknown key: {key}[/red]")
        console.print("[dim]Run 'unified-icc config list' for available keys.[/dim]")
        raise typer.Exit(1)
    console.print(getattr(config, key))


@app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
) -> None:
    """Set a configuration value (writes to environment / .env file)."""
    # Configuration is env-var driven. We persist by appending to .env.
    env_key_map = {
        "tmux_session_name": "TMUX_SESSION_NAME",
        "provider_name": "CCLARK_PROVIDER",
        "monitor_poll_interval": "MONITOR_POLL_INTERVAL",
        "autoclose_done_minutes": "AUTOCLOSE_DONE_MINUTES",
        "autoclose_dead_minutes": "AUTOCLOSE_DEAD_MINUTES",
    }

    if key not in CONFIG_KEYS:
        console.print(f"[red]Unknown key: {key}[/red]")
        raise typer.Exit(1)

    env_key = env_key_map.get(key, key.upper())
    env_file = config.config_dir / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if env_file.exists():
        lines = env_file.read_text().splitlines()

    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{env_key}="):
            new_lines.append(f"{env_key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{env_key}={value}")

    env_file.write_text("\n".join(new_lines) + "\n")
    console.print(f"[green]Set {key} = {value}[/green]")
    console.print("[dim]Restart the gateway daemon for changes to take effect.[/dim]")
