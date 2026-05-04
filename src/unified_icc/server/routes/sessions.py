"""REST API routes for session management and agent interaction."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from unified_icc.channel_router import channel_router
from unified_icc.gateway import UnifiedICC, WindowInfo
from unified_icc.providers import registry as provider_registry
from unified_icc.window_state_store import window_store

from ..auth import verify_api_key

router = APIRouter(prefix="/api/v1", tags=["sessions"])


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    work_dir: str = Field(default="", description="Working directory for the agent")
    provider: str = Field(default="claude", description="Agent provider: claude, codex, gemini, pi, shell")
    mode: str = Field(default="normal", description="Approval mode: normal or yolo")
    name: str = Field(default="", description="Optional display name")


class InputRequest(BaseModel):
    text: str
    enter: bool = True
    literal: bool = True
    raw: bool = False


class KeyRequest(BaseModel):
    key: str


class VerboseRequest(BaseModel):
    enabled: bool


class BrowseRequest(BaseModel):
    path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_gateway() -> UnifiedICC:
    """Retrieve the gateway instance stored on the app state."""
    from ..app import _get_app_gateway
    gw = _get_app_gateway()
    if gw is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    return gw


def _resolve_channel(channel_id: str, gateway: UnifiedICC) -> str:
    """Resolve a channel_id to its window_id, raising 404 if not found."""
    window_id = gateway.resolve_window(channel_id)
    if window_id is None:
        raise HTTPException(status_code=404, detail=f"No session found for channel {channel_id}")
    return window_id


def _window_info_to_dict(info: WindowInfo) -> dict[str, Any]:
    return {
        "window_id": info.window_id,
        "display_name": info.display_name,
        "provider": info.provider,
        "cwd": info.cwd,
        "session_id": info.session_id,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", dependencies=[Depends(verify_api_key)])
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    """Create a new agent session."""
    gateway = _get_gateway()

    if not provider_registry.is_valid(req.provider):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    work_dir = req.work_dir or os.getcwd()
    if not Path(work_dir).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {work_dir}")

    channel_id = f"api:{uuid.uuid4()}"
    window = await gateway.create_window(
        work_dir=work_dir,
        provider=req.provider,
        mode=req.mode,
    )
    gateway.bind_channel(channel_id, window.window_id)

    if req.name:
        from unified_icc.tmux_manager import tmux_manager
        await tmux_manager.rename_window(window.window_id, req.name)

    # Persist metadata in window_store (same pattern as daemon.py)
    window_store.mark_window_created(window.window_id)
    state = window_store.get_window_state(window.window_id)
    state.provider_name = req.provider
    state.cwd = work_dir
    state.channel_id = channel_id
    if req.name:
        state.window_name = req.name

    return {
        "channel_id": channel_id,
        "window_id": window.window_id,
        "provider": req.provider,
        "mode": req.mode,
        "cwd": work_dir,
        "display_name": req.name or window.display_name,
    }


@router.get("/sessions", dependencies=[Depends(verify_api_key)])
async def list_sessions() -> dict[str, Any]:
    """List all managed sessions."""
    gateway = _get_gateway()
    windows = await gateway.list_windows()
    sessions = []
    for w in windows:
        sessions.append(_window_info_to_dict(w))
    # Also include channel_id from window_store
    for s in sessions:
        wid = s["window_id"]
        ws = window_store.window_states.get(wid)
        if ws:
            s["channel_id"] = ws.channel_id
    return {"sessions": sessions}


@router.get("/sessions/{channel_id}", dependencies=[Depends(verify_api_key)])
async def get_session(channel_id: str) -> dict[str, Any]:
    """Get status of a specific session."""
    gateway = _get_gateway()
    window_id = _resolve_channel(channel_id, gateway)
    state = window_store.get_window_state(window_id)

    return {
        "channel_id": channel_id,
        "window_id": window_id,
        "provider": state.provider_name,
        "cwd": state.cwd,
        "session_id": state.session_id,
        "approval_mode": state.approval_mode,
        "batch_mode": state.batch_mode,
        "display_name": channel_router.get_display_name(window_id),
    }


@router.delete("/sessions/{channel_id}", dependencies=[Depends(verify_api_key)])
async def close_session(channel_id: str) -> dict[str, Any]:
    """Close a session and kill its tmux window."""
    gateway = _get_gateway()
    killed = await gateway.kill_channel_windows(channel_id)
    return {"channel_id": channel_id, "killed_windows": killed}


@router.post("/sessions/{channel_id}/input", dependencies=[Depends(verify_api_key)])
async def send_input(channel_id: str, req: InputRequest) -> dict[str, Any]:
    """Send text input to the agent window."""
    gateway = _get_gateway()
    window_id = _resolve_channel(channel_id, gateway)
    await gateway.send_input_to_window(
        window_id,
        req.text,
        enter=req.enter,
        literal=req.literal,
        raw=req.raw,
    )
    return {"ok": True}


@router.post("/sessions/{channel_id}/key", dependencies=[Depends(verify_api_key)])
async def send_key(channel_id: str, req: KeyRequest) -> dict[str, Any]:
    """Send a special key to the agent window."""
    gateway = _get_gateway()
    window_id = _resolve_channel(channel_id, gateway)
    await gateway.send_key(window_id, req.key)
    return {"ok": True}


@router.get("/sessions/{channel_id}/pane", dependencies=[Depends(verify_api_key)])
async def capture_pane(channel_id: str) -> dict[str, Any]:
    """Capture current pane content as plain text."""
    gateway = _get_gateway()
    window_id = _resolve_channel(channel_id, gateway)
    content = await gateway.capture_pane(window_id)
    return {"channel_id": channel_id, "content": content or ""}


@router.get("/sessions/{channel_id}/screenshot", dependencies=[Depends(verify_api_key)])
async def capture_screenshot(channel_id: str) -> Response:
    """Capture pane screenshot as PNG."""
    gateway = _get_gateway()
    window_id = _resolve_channel(channel_id, gateway)
    image_bytes = await gateway.capture_screenshot(window_id)
    if not image_bytes:
        raise HTTPException(status_code=404, detail="Screenshot not available")
    return Response(content=image_bytes, media_type="image/png")


@router.post("/sessions/{channel_id}/verbose", dependencies=[Depends(verify_api_key)])
async def set_verbose(channel_id: str, req: VerboseRequest) -> dict[str, Any]:
    """Toggle verbose mode (controls thinking content visibility)."""
    # Verbose state is per-frontend, not stored in gateway. For API server
    # this is a no-op placeholder — the full content is always returned
    # via WebSocket events. The endpoint exists for API parity with #command.
    return {"channel_id": channel_id, "verbose": req.enabled}


@router.post("/directories/browse", dependencies=[Depends(verify_api_key)])
async def browse_directory(req: BrowseRequest) -> dict[str, Any]:
    """List subdirectories of a given path."""
    target = Path(req.path).resolve()
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")

    try:
        entries = sorted(
            [d.name for d in target.iterdir() if d.is_dir() and not d.name.startswith(".")]
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {req.path}")

    return {
        "path": str(target),
        "directories": entries,
        "parent": str(target.parent) if str(target) != "/" else "",
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check."""
    from ..app import _get_app_gateway
    gateway = _get_app_gateway()
    return {
        "status": "ok" if gateway is not None else "not_ready",
    }
