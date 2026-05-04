"""Unified ICC API Server.

Exposes the gateway as an HTTP/WebSocket API server using FastAPI.

Usage::

    from unified_icc.server import run_server, create_app

    # Run the server directly
    run_server(host="0.0.0.0", port=8900)

    # Or get the FastAPI app for custom deployment
    app = create_app()
"""

from __future__ import annotations

from .app import create_app as create_app


def run_server(
    *,
    host: str | None = None,
    port: int | None = None,
    log_level: str = "info",
) -> None:
    """Run the unified-icc API server using uvicorn.

    This is a blocking call that starts the event loop.
    """
    import uvicorn

    from unified_icc.config import config

    host = host or config.api_host
    port = port or config.api_port

    uvicorn.run(
        "unified_icc.server.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
    )
