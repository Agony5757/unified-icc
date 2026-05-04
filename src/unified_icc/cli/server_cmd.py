"""unified-icc server start/stop/status.

Manages the API server lifecycle: start (foreground or detached),
stop, and status inspection.
"""

from __future__ import annotations

import os
import signal
import time

import typer
from rich.console import Console
from rich.table import Table
from unified_icc.utils import unified_icc_dir

console = Console()
app = typer.Typer(help="Manage the unified-icc API server.", no_args_is_help=True)

SERVER_PID_FILE = unified_icc_dir() / "server.pid"


def _read_pid() -> int | None:
    if not SERVER_PID_FILE.exists():
        return None
    try:
        return int(SERVER_PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _remove_pid() -> None:
    from contextlib import suppress
    with suppress(OSError):
        SERVER_PID_FILE.unlink(missing_ok=True)


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8900, "--port", "-p", help="Bind port"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
) -> None:
    """Start the unified-icc API server."""
    pid = _read_pid()
    if pid is not None and _pid_is_alive(pid):
        console.print(f"[yellow]API server is already running (PID {pid}).[/yellow]")
        raise typer.Exit(1)

    if detach:
        child_pid = os.fork()
        if child_pid != 0:
            # Parent: wait briefly then exit
            time.sleep(0.5)
            pid = _read_pid()
            if pid and _pid_is_alive(pid):
                console.print(f"[green]API server started (background, PID {pid}).[/green]")
            else:
                console.print("[yellow]Server forked but may not be ready yet.[/yellow]")
            raise typer.Exit(0)

        # Child: detach
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)

        _run_foreground(host, port)
    else:
        console.print(f"[green]Starting API server on {host}:{port}...[/green]")
        _run_foreground(host, port)


def _run_foreground(host: str, port: int) -> None:
    """Run the server in the current process (foreground)."""
    SERVER_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERVER_PID_FILE.write_text(str(os.getpid()))

    try:
        from unified_icc.server import run_server
        run_server(host=host, port=port)
    except KeyboardInterrupt:
        pass
    finally:
        _remove_pid()


@app.command()
def stop() -> None:
    """Stop the API server."""
    pid = _read_pid()
    if pid is None or not _pid_is_alive(pid):
        console.print("[yellow]API server is not running.[/yellow]")
        _remove_pid()
        raise typer.Exit(0)

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        console.print(f"[red]Failed to send SIGTERM to PID {pid}: {e}[/red]")
        raise typer.Exit(1)

    for _ in range(50):
        if not _pid_is_alive(pid):
            break
        time.sleep(0.1)
    else:
        console.print("[yellow]Server did not stop gracefully, sending SIGKILL...[/yellow]")
        from contextlib import suppress
        with suppress(OSError):
            os.kill(pid, signal.SIGKILL)

    _remove_pid()
    console.print("[green]API server stopped.[/green]")


@app.command("status")
def status() -> None:
    """Show API server status."""
    pid = _read_pid()
    alive = pid is not None and _pid_is_alive(pid)

    table = Table(title="API Server Status", show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    if alive:
        table.add_row("Status", "[green]running[/green]")
        table.add_row("PID", str(pid))
        table.add_row("PID file", str(SERVER_PID_FILE))
    else:
        table.add_row("Status", "[red]stopped[/red]")
        if pid is not None:
            table.add_row("Stale PID", str(pid))

    console.print(table)
