"""CLI → daemon communication over Unix socket."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import Any

SOCKET_PATH = Path.home() / ".cclark" / "gateway.sock"


class DaemonError(Exception):
    """Raised when the daemon returns an error or is unreachable."""

    pass


def _run_async(coro) -> Any:
    """Run a coroutine in a fresh event loop (avoids 'loop already closed' issues)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _async_send_command(cmd: str, **kwargs: Any) -> dict[str, Any]:
    if not SOCKET_PATH.exists():
        raise DaemonError(
            f"Gateway daemon is not running. Start it with: unified-icc gateway start"
        )

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(SOCKET_PATH)),
            timeout=5.0,
        )
    except (ConnectionRefusedError, socket.error, asyncio.TimeoutError) as e:
        raise DaemonError(
            f"Cannot connect to gateway daemon socket: {e}"
        ) from e

    try:
        request = {"cmd": cmd, **kwargs}
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        response_line = await asyncio.wait_for(reader.readline(), timeout=30.0)
        if not response_line:
            raise DaemonError("Gateway daemon closed the connection.")

        response = json.loads(response_line.decode())
        if not response.get("ok", False):
            raise DaemonError(response.get("error", "Unknown daemon error"))
        return response.get("data", {})
    finally:
        writer.close()
        await writer.wait_closed()


def send_command(cmd: str, **kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper for CLI commands."""
    return _run_async(_async_send_command(cmd, **kwargs))


def daemon_is_running() -> bool:
    """Check if the daemon socket is present and reachable."""
    if not SOCKET_PATH.exists():
        return False

    async def _check() -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(SOCKET_PATH)),
                timeout=3.0,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    return _run_async(_check())
