"""WebSocket endpoint for bidirectional agent communication."""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from unified_icc.providers import registry as provider_registry
from unified_icc.window_state_store import window_store

from ..auth import verify_ws_token
from ..connection_manager import manager
from ..ws_protocol import (
    parse_client_message,
    make_session_created,
    make_session_list,
    make_session_closed,
    make_capture_pane,
    make_capture_screenshot,
    make_error,
    make_pong,
    make_wizard_browse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_gateway():
    from ..app import _get_app_gateway
    return _get_app_gateway()


async def _ws_recv_loop(ws: WebSocket, channel_id: str | None) -> None:
    """Main receive loop for a WebSocket connection."""
    while True:
        raw_text = await ws.receive_text()
        if not raw_text.strip():
            continue

        import json
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            await manager.send_to(ws, make_error(message=f"Invalid JSON: {e}"))
            continue

        try:
            msg = parse_client_message(raw)
        except ValueError as e:
            await manager.send_to(ws, make_error(
                message=str(e),
                request_id=raw.get("request_id", ""),
            ))
            continue

        await _dispatch(ws, msg, channel_id)


async def _dispatch(ws: WebSocket, msg: Any, channel_id: str | None) -> None:
    """Dispatch a parsed client message to the appropriate handler."""
    msg_type = msg.type
    request_id = getattr(msg, "request_id", "")

    try:
        if msg_type == "ping":
            await manager.send_to(ws, make_pong(request_id=request_id))

        elif msg_type == "session.create":
            await _handle_session_create(ws, msg)

        elif msg_type == "session.list":
            await _handle_session_list(ws, request_id)

        elif msg_type == "session.close":
            await _handle_session_close(ws, msg)

        elif msg_type == "input":
            await _handle_input(ws, msg, channel_id)

        elif msg_type == "input.raw":
            await _handle_input_raw(ws, msg, channel_id)

        elif msg_type == "key":
            await _handle_key(ws, msg, channel_id)

        elif msg_type == "capture.pane":
            await _handle_capture_pane(ws, msg, request_id, channel_id)

        elif msg_type == "capture.screenshot":
            await _handle_capture_screenshot(ws, msg, request_id, channel_id)

        elif msg_type == "verbose.set":
            # No-op for API server — full content always streamed
            await manager.send_to(ws, {
                "type": "verbose.updated",
                "request_id": request_id,
                "enabled": msg.enabled,
            })

        elif msg_type == "wizard.browse":
            await _handle_wizard_browse(ws, msg, request_id)

        elif msg_type == "wizard.mkdir":
            await _handle_wizard_mkdir(ws, msg, request_id)

        else:
            await manager.send_to(ws, make_error(
                message=f"Unhandled message type: {msg_type}",
                request_id=request_id,
            ))

    except Exception as e:
        logger.exception("Error handling WS message type=%s", msg_type)
        await manager.send_to(ws, make_error(
            message=str(e),
            request_id=request_id,
        ))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_session_create(ws: WebSocket, msg: Any) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    provider = getattr(msg, "provider", "claude") or "claude"
    if not provider_registry.is_valid(provider):
        await manager.send_to(ws, make_error(message=f"Unknown provider: {provider}"))
        return

    work_dir = getattr(msg, "work_dir", "") or os.getcwd()
    mode = getattr(msg, "mode", "normal") or "normal"

    new_channel_id = getattr(msg, "channel_id", "") or f"api:{uuid.uuid4()}"
    window = await gateway.create_window(work_dir=work_dir, provider=provider, mode=mode)
    gateway.bind_channel(new_channel_id, window.window_id)

    # Persist metadata
    window_store.mark_window_created(window.window_id)
    state = window_store.get_window_state(window.window_id)
    state.provider_name = provider
    state.cwd = work_dir
    state.channel_id = new_channel_id
    state.approval_mode = "normal" if mode == "standard" else mode

    name = getattr(msg, "name", "")
    if name:
        from unified_icc.tmux_manager import tmux_manager
        await tmux_manager.rename_window(window.window_id, name)
        state.window_name = name

    # Subscribe this connection to the new channel
    await manager.subscribe(new_channel_id, ws)

    await manager.send_to(ws, make_session_created(
        channel_id=new_channel_id,
        window_id=window.window_id,
        provider=provider,
        mode=mode,
        cwd=work_dir,
        display_name=name or window.display_name,
        request_id=getattr(msg, "request_id", ""),
    ))


async def _handle_session_list(ws: WebSocket, request_id: str) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_session_list(sessions=[], request_id=request_id))
        return

    windows = await gateway.list_windows()
    sessions = []
    for w in windows:
        entry = {
            "window_id": w.window_id,
            "display_name": w.display_name,
            "provider": w.provider,
            "cwd": w.cwd,
            "session_id": w.session_id,
        }
        ws_state = window_store.window_states.get(w.window_id)
        if ws_state:
            entry["channel_id"] = ws_state.channel_id
        sessions.append(entry)

    await manager.send_to(ws, make_session_list(sessions=sessions, request_id=request_id))


async def _handle_session_close(ws: WebSocket, msg: Any) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "")
    if not cid:
        await manager.send_to(ws, make_error(message="channel_id required"))
        return

    await gateway.kill_channel_windows(cid)
    await manager.unsubscribe(cid, ws)
    await manager.send_to(ws, make_session_closed(
        channel_id=cid,
        request_id=getattr(msg, "request_id", ""),
    ))


async def _handle_input(ws: WebSocket, msg: Any, channel_id: str | None) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "") or channel_id or ""
    window_id = gateway.resolve_window(cid)
    if window_id is None:
        await manager.send_to(ws, make_error(message=f"No session for channel {cid}"))
        return

    await gateway.send_input_to_window(
        window_id,
        msg.text,
        enter=getattr(msg, "enter", True),
        literal=getattr(msg, "literal", True),
        raw=getattr(msg, "raw", False),
    )


async def _handle_input_raw(ws: WebSocket, msg: Any, channel_id: str | None) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "") or channel_id or ""
    window_id = gateway.resolve_window(cid)
    if window_id is None:
        await manager.send_to(ws, make_error(message=f"No session for channel {cid}"))
        return

    await gateway.send_input_to_window(window_id, msg.text, enter=True, literal=True, raw=True)


async def _handle_key(ws: WebSocket, msg: Any, channel_id: str | None) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "") or channel_id or ""
    window_id = gateway.resolve_window(cid)
    if window_id is None:
        await manager.send_to(ws, make_error(message=f"No session for channel {cid}"))
        return

    await gateway.send_key(window_id, msg.key)


async def _handle_capture_pane(
    ws: WebSocket,
    msg: Any,
    request_id: str,
    channel_id: str | None,
) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "") or channel_id or ""
    window_id = gateway.resolve_window(cid)
    if window_id is None:
        await manager.send_to(ws, make_error(message=f"No session for channel {cid}"))
        return

    content = await gateway.capture_pane(window_id)
    await manager.send_to(ws, make_capture_pane(
        channel_id=cid,
        content=content or "",
        request_id=request_id,
    ))


async def _handle_capture_screenshot(
    ws: WebSocket,
    msg: Any,
    request_id: str,
    channel_id: str | None,
) -> None:
    gateway = _get_gateway()
    if gateway is None:
        await manager.send_to(ws, make_error(message="Gateway not initialized"))
        return

    cid = getattr(msg, "channel_id", "") or channel_id or ""
    window_id = gateway.resolve_window(cid)
    if window_id is None:
        await manager.send_to(ws, make_error(message=f"No session for channel {cid}"))
        return

    image_bytes = await gateway.capture_screenshot(window_id)
    await manager.send_to(ws, make_capture_screenshot(
        channel_id=cid,
        image_base64=base64.b64encode(image_bytes).decode() if image_bytes else "",
        request_id=request_id,
    ))


async def _handle_wizard_browse(ws: WebSocket, msg: Any, request_id: str) -> None:
    target = Path(msg.path).resolve()
    if not target.is_dir():
        await manager.send_to(ws, make_error(
            message=f"Not a directory: {msg.path}",
            request_id=request_id,
        ))
        return

    try:
        entries = sorted(
            [d.name for d in target.iterdir() if d.is_dir() and not d.name.startswith(".")]
        )
    except PermissionError:
        await manager.send_to(ws, make_error(
            message=f"Permission denied: {msg.path}",
            request_id=request_id,
        ))
        return

    await manager.send_to(ws, make_wizard_browse(
        path=str(target),
        directories=entries,
        parent=str(target.parent) if str(target) != "/" else "",
        request_id=request_id,
    ))


async def _handle_wizard_mkdir(ws: WebSocket, msg: Any, request_id: str) -> None:
    # mkdir needs a parent path context — not available without session state.
    # Simplified: treat name as an absolute or relative path.
    target = Path(msg.name)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        await manager.send_to(ws, make_error(
            message=f"Failed to create directory: {e}",
            request_id=request_id,
        ))
        return

    await manager.send_to(ws, {
        "type": "wizard.mkdir",
        "request_id": request_id,
        "path": str(target.resolve()),
    })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/api/v1/ws")
@router.websocket("/api/v1/ws/{channel_id}")
async def websocket_endpoint(
    ws: WebSocket,
    channel_id: str | None = None,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for bidirectional communication.

    Connect with an optional channel_id to subscribe to that session's events.
    Connect without to use as a global listener or create sessions via WS messages.
    """
    # Authenticate
    try:
        await verify_ws_token(token)
    except ValueError:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()

    # Subscribe to the requested channel, or to global events when no channel is
    # specified. The global mode is what frontend bridges use: one WebSocket
    # receives events for all externally named channels.
    if channel_id:
        await manager.subscribe(channel_id, ws)
    else:
        await manager.subscribe_global(ws)

    try:
        await _ws_recv_loop(ws, channel_id)
    except WebSocketDisconnect:
        pass
    finally:
        if channel_id:
            await manager.unsubscribe(channel_id, ws)
        else:
            await manager.unsubscribe_global(ws)
