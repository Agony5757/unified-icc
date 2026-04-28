"""unified-icc session list/create/kill/attach/status"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import typer
from rich.console import Console
from rich.table import Table

from unified_icc.cli.client import daemon_is_running, send_command, DaemonError

console = Console()
app = typer.Typer(help="Manage gateway sessions (tmux windows).", no_args_is_help=True)


def require_daemon() -> None:
    if not daemon_is_running():
        console.print(
            "[red]Gateway daemon is not running.[/red]\n"
            "Start it: unified-icc gateway start --detach"
        )
        raise typer.Exit(1)


@app.command("list")
def session_list() -> None:
    """List all active sessions."""
    require_daemon()
    try:
        result = send_command("session_list")
    except DaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    sessions: list[dict[str, Any]] = result if isinstance(result, list) else []
    if not sessions:
        console.print("[dim]No active sessions.[/dim]")
        return

    table = Table(title="Active Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Workdir", style="dim")
    table.add_column("Display Name", style="green")

    for s in sessions:
        table.add_row(
            s.get("session_id", ""),
            s.get("provider", ""),
            s.get("workdir", ""),
            s.get("display_name", ""),
        )
    console.print(table)


@app.command("create")
def session_create(
    name: str | None = typer.Option(None, "--name", help="Display name for the session"),
    provider: str = typer.Option("claude", "--provider", "-p", help="Agent provider to use"),
    workspace: Path = typer.Option(
        Path.cwd(), "--workspace", "-w", help="Working directory for the session"
    ),
    mode: Literal["normal", "yolo"] = typer.Option(
        "normal", "--mode", "-m", help="Session mode: normal or yolo"
    ),
) -> None:
    """Create a new session."""
    require_daemon()
    try:
        result = send_command(
            "session_create",
            provider=provider,
            workspace=str(workspace),
            name=name,
            mode=mode,
        )
    except DaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    session_id = result.get("session_id", "?")
    display = result.get("display_name", session_id)
    console.print(f"[green]Session created:[/green] {display}")
    console.print(f"  Session ID : {session_id}")
    console.print(f"  Provider   : {result.get('provider', provider)}")
    console.print(f"  Workdir    : {result.get('workdir', workspace)}")
    console.print()
    console.print(f"[dim]Attach: unified-icc session attach {session_id}[/dim]")


@app.command("attach")
def session_attach(
    session_id: str = typer.Argument(..., help="Session ID to attach to"),
) -> None:
    """Attach to a session's tmux window."""
    require_daemon()
    try:
        send_command("session_status", session_id=session_id)
    except DaemonError as e:
        console.print(f"[red]Session not found or unreachable: {e}[/red]")
        raise typer.Exit(1)

    # tmux attach-session -t <window_id>
    # window_id format from UnifiedICC: "sess:@N" (foreign) or just "@N" (managed)
    sys.exit(subprocess.call(["tmux", "attach-session", "-t", session_id]))


@app.command("kill")
def session_kill(
    session_id: str = typer.Argument(..., help="Session ID to kill"),
) -> None:
    """Kill a session."""
    require_daemon()
    try:
        send_command("session_kill", session_id=session_id)
    except DaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Session killed:[/green] {session_id}")


@app.command("status")
def session_status(
    session_id: str | None = typer.Argument(None, help="Session ID. Lists all if omitted."),
) -> None:
    """Show session status."""
    require_daemon()
    try:
        result = send_command("session_status", session_id=session_id)
    except DaemonError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if session_id:
        output = result[0].get("output", "(no output)") if isinstance(result, list) and result else "(not found)"
        console.print(f"[cyan]Session:[/cyan] {session_id}")
        console.print(output)
    else:
        if not result:
            console.print("[dim]No active sessions.[/dim]")
            return
        table = Table(title="Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Display Name", style="green")
        for s in result if isinstance(result, list) else []:
            table.add_row(s.get("session_id", ""), s.get("display_name", ""))
        console.print(table)
