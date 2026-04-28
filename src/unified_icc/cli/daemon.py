"""Gateway daemon: runs in background, owns UnifiedICC, serves commands via Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from unified_icc import UnifiedICC
from unified_icc.providers import detect_provider_from_command

PID_FILE = Path.home() / ".cclark" / "gateway.pid"
SOCKET_PATH = Path.home() / ".cclark" / "gateway.sock"

_gateway: UnifiedICC | None = None
_shutdown_event: asyncio.Event | None = None


# ---------------------------------------------------------------------------
# PID file helpers
# ---------------------------------------------------------------------------


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def remove_pid() -> None:
    from contextlib import suppress
    with suppress(OSError):
        PID_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Socket command handlers
# ---------------------------------------------------------------------------


async def _handle_session_list() -> list[dict[str, Any]]:
    if _gateway is None:
        return []
    # Use tmux_manager directly to list actual tmux windows
    from unified_icc.tmux_manager import tmux_manager
    tmux_windows = await tmux_manager.list_windows()
    return [
        {
            "session_id": w.window_id,
            "provider": detect_provider_from_command(w.pane_current_command) or "claude",
            "workdir": w.cwd,
            "display_name": w.window_name,
        }
        for w in tmux_windows
    ]


async def _handle_session_create(
    provider: str = "claude",
    workspace: str | None = None,
    name: str | None = None,
    mode: str = "normal",
) -> dict[str, Any]:
    if _gateway is None:
        raise RuntimeError("Gateway not initialized")
    if workspace is None:
        workspace = str(Path.cwd())
    window = await _gateway.create_window(
        work_dir=workspace,
        provider=provider,
        mode=mode,
    )
    if name:
        from unified_icc.tmux_manager import tmux_manager
        await tmux_manager.rename_window(window.window_id, name)
    # Register in window_store so gateway.list_windows() works
    from unified_icc.window_state_store import window_store
    state = window_store.get_window_state(window.window_id)
    state.provider_name = provider
    state.cwd = workspace
    state.window_name = name or window.display_name
    return {
        "session_id": window.window_id,
        "display_name": name or window.display_name,
        "provider": provider,
        "workdir": workspace,
    }


async def _handle_session_kill(session_id: str) -> None:
    from unified_icc.tmux_manager import tmux_manager
    await tmux_manager.kill_window(session_id)


async def _handle_session_status(session_id: str | None = None) -> list[dict[str, Any]]:
    if _gateway is None:
        return []
    from unified_icc.tmux_manager import tmux_manager
    if session_id:
        try:
            pane = await tmux_manager.capture_pane(session_id)
            return [{"session_id": session_id, "output": pane or ""}]
        except (OSError, RuntimeError):
            return [{"session_id": session_id, "output": "(unavailable)"}]
    tmux_windows = await tmux_manager.list_windows()
    return [{"session_id": w.window_id, "display_name": w.window_name} for w in tmux_windows]


async def _handle_ping() -> str:
    return "pong"


DISPATCH: dict[str, Any] = {
    "session_list": _handle_session_list,
    "session_create": _handle_session_create,
    "session_kill": _handle_session_kill,
    "session_status": _handle_session_status,
    "ping": _handle_ping,
}


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("sockname")
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=30.0)
        if not line:
            return

        try:
            req = json.loads(line.decode())
        except json.JSONDecodeError:
            writer.write(json.dumps({"ok": False, "error": "Invalid JSON"}).encode() + b"\n")
            await writer.drain()
            return

        cmd = req.pop("cmd", None)
        handler = DISPATCH.get(cmd)

        if handler is None:
            writer.write(json.dumps({"ok": False, "error": f"Unknown command: {cmd}"}).encode() + b"\n")
            await writer.drain()
            return

        try:
            if asyncio.iscoroutinefunction(handler):
                data = await handler(**req)
            else:
                data = handler(**req)
            writer.write(json.dumps({"ok": True, "data": data}).encode() + b"\n")
        except Exception as exc:  # noqa: BLE001
            writer.write(json.dumps({"ok": False, "error": str(exc)}).encode() + b"\n")
        await writer.drain()
    except asyncio.TimeoutError:
        pass
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[daemon] client handler error {addr}: {e}\n")
    finally:
        writer.close()
        await writer.wait_closed()


# ---------------------------------------------------------------------------
# Daemon lifecycle
# ---------------------------------------------------------------------------


async def _sigwaiter(loop: asyncio.AbstractEventLoop) -> None:
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()

    def _on_signal(sig: int) -> None:
        sys.stderr.write(f"[daemon] received signal {sig}, shutting down...\n")
        if _shutdown_event:
            _shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal, sig)


async def run_daemon(*, verbose: bool = False) -> None:
    """Run the gateway daemon in the current process (foreground mode)."""
    global _gateway, _shutdown_event

    pid = read_pid()
    if pid is not None and pid_is_alive(pid):
        sys.stderr.write(
            f"Gateway daemon is already running (PID {pid}).\n"
            f"Stop it first: unified-icc gateway stop\n"
        )
        sys.exit(1)

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)

    write_pid()

    server = await asyncio.start_unix_server(
        lambda r, w: _handle_client(r, w),
        str(SOCKET_PATH),
    )
    SOCKET_PATH.chmod(0o600)

    async def _cleanup() -> None:
        server.close()
        await server.wait_closed()
        if _gateway:
            await _gateway.stop()
        remove_pid()
        SOCKET_PATH.unlink(missing_ok=True)
        if verbose:
            sys.stderr.write("[daemon] shutdown complete.\n")

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    _shutdown_event = shutdown_event

    async def _on_signal(sig: int) -> None:
        sys.stderr.write(f"[daemon] signal {sig}, shutting down...\n")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _on_signal(s))

    try:
        _gateway = UnifiedICC()
        await _gateway.start()
        if verbose:
            sys.stderr.write(f"[daemon] started, PID {os.getpid()}\n")

        await shutdown_event.wait()
    finally:
        await _cleanup()


def start_detached() -> int | None:
    """Fork and run the daemon in a detached child process. Returns child PID."""
    pid = os.fork()
    if pid != 0:
        return pid  # parent returns child PID

    # Child: detach from controlling terminal
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    os.chdir("/")
    os.umask(0)

    # Second fork to prevent acquiring a controlling terminal
    pid2 = os.fork()
    if pid2 != 0:
        os._exit(0)

    # Now in fully detached grandchild
    asyncio.run(run_daemon(verbose=False))


def wait_for_socket(timeout: float = 5.0) -> bool:
    """Wait for the socket to appear and be reachable (parent use after start_detached)."""

    loop = asyncio.new_event_loop()
    try:
        async def _check() -> bool:
            for _ in range(int(timeout * 20)):
                if SOCKET_PATH.exists():
                    try:
                        r, w = await asyncio.wait_for(
                            asyncio.open_unix_connection(str(SOCKET_PATH)),
                            timeout=1.0,
                        )
                        w.close()
                        await w.wait_closed()
                        return True
                    except Exception:  # noqa: BLE001
                        pass
                await asyncio.sleep(0.05)
            return False

        return loop.run_until_complete(_check())
    finally:
        loop.close()
