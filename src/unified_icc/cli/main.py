"""unified-icc CLI root application."""

from __future__ import annotations

import typer

from unified_icc.cli import gateway_cmd, session_cmd, provider_cmd, config_cmd, server_cmd

app = typer.Typer(
    name="unified-icc",
    help="Unified ICC — Gateway Session Manager for AI Coding Agents.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(gateway_cmd.app, name="gateway")
app.add_typer(session_cmd.app, name="session")
app.add_typer(provider_cmd.app, name="provider")
app.add_typer(config_cmd.app, name="config")
app.add_typer(server_cmd.app, name="server")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", is_eager=True, help="Show version"),
) -> None:
    """Unified ICC — manage multiple AI coding agent sessions via tmux."""
    if version:
        from unified_icc import __version__
        typer.echo(f"unified-icc {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
