"""unified-icc gateway start/stop/restart/status.

Manages the background gateway daemon lifecycle: start (foreground or detached),
stop, restart, and status inspection via PID file and Unix socket.
"""

from __future__ import annotations

import os
import signal
import time

import typer
from rich.console import Console
from rich.table import Table

from unified_icc.cli.client import daemon_is_running
from unified_icc.cli.daemon import (
    read_pid,
    pid_is_alive,
    remove_pid,
    start_detached,
    wait_for_socket,
)

console = Console()
app = typer.Typer(help="Manage the gateway daemon.", no_args_is_help=True)


@app.command()
def start(
    detach: bool = typer.Option(
        False, "--detach", "-d", help="Run daemon in the background"
    ),
) -> None:
    """Start the gateway daemon."""
    pid = read_pid()
    if pid is not None and pid_is_alive(pid):
        console.print(f"[yellow]Gateway daemon is already running (PID {pid}).[/yellow]")
        raise typer.Exit(1)

    if detach:
        child_pid = start_detached()
        if child_pid is None:
            console.print("[red]Failed to fork daemon process.[/red]")
            raise typer.Exit(1)
        if not wait_for_socket(timeout=5.0):
            console.print("[yellow]Daemon forked but socket not ready yet. Try 'gateway status' in a moment.[/yellow]")
        else:
            console.print(f"[green]Gateway daemon started (background, PID {child_pid}).[/green]")
    else:
        from unified_icc.cli.daemon import run_daemon
        console.print("[green]Starting gateway daemon (foreground)...[/green]")
        try:
            import asyncio
            asyncio.run(run_daemon(verbose=True))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")


@app.command()
def stop() -> None:
    """Stop the gateway daemon."""
    pid = read_pid()
    if pid is None or not pid_is_alive(pid):
        console.print("[yellow]Gateway daemon is not running.[/yellow]")
        remove_pid()
        raise typer.Exit(0)

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        console.print(f"[red]Failed to send SIGTERM to PID {pid}: {e}[/red]")
        raise typer.Exit(1)

    # Wait up to 5s for process to die
    for _ in range(50):
        if not pid_is_alive(pid):
            break
        time.sleep(0.1)
    else:
        console.print("[yellow]Daemon did not stop gracefully, sending SIGKILL...[/yellow]")
        from contextlib import suppress
        with suppress(OSError):
            os.kill(pid, signal.SIGKILL)

    remove_pid()
    console.print("[green]Gateway daemon stopped.[/green]")


@app.command()
def restart(
    detach: bool = typer.Option(False, "--detach", "-d", help="Run new daemon in background"),
) -> None:
    """Restart the gateway daemon."""
    stop()
    time.sleep(0.5)
    start(detach=detach)


@app.command("status")
def status() -> None:
    """Show gateway daemon status."""
    pid = read_pid()
    alive = pid is not None and pid_is_alive(pid)
    running = alive and daemon_is_running()

    table = Table(title="Gateway Daemon Status", show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    if running:
        table.add_row("Status", "[green]running[/green]")
        table.add_row("PID", str(pid))
    elif alive:
        table.add_row("Status", "[yellow]PID file exists but socket unreachable[/yellow]")
        table.add_row("PID", str(pid))
    else:
        table.add_row("Status", "[red]stopped[/red]")
        if pid is not None:
            table.add_row("Stale PID", str(pid))

    console.print(table)
