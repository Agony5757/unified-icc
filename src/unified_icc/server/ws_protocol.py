"""WebSocket protocol message types for the unified-icc server.

All messages are JSON with a ``type`` field for dispatch.
Client messages use snake_case dotted types (``session.create``).
Server responses mirror the type or use a past-tense form (``session.created``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Client → Server messages
# ---------------------------------------------------------------------------


@dataclass
class SessionCreateMsg:
    type: str = field(default="session.create", init=False)
    request_id: str = ""
    work_dir: str = ""
    provider: str = "claude"
    mode: str = "normal"
    name: str = ""


@dataclass
class SessionListMsg:
    type: str = field(default="session.list", init=False)
    request_id: str = ""


@dataclass
class SessionCloseMsg:
    type: str = field(default="session.close", init=False)
    request_id: str = ""
    channel_id: str = ""


@dataclass
class InputMsg:
    type: str = field(default="input", init=False)
    request_id: str = ""
    text: str = ""
    enter: bool = True
    literal: bool = True


@dataclass
class InputRawMsg:
    type: str = field(default="input.raw", init=False)
    request_id: str = ""
    text: str = ""


@dataclass
class KeyMsg:
    type: str = field(default="key", init=False)
    request_id: str = ""
    key: str = ""


@dataclass
class CapturePaneMsg:
    type: str = field(default="capture.pane", init=False)
    request_id: str = ""


@dataclass
class CaptureScreenshotMsg:
    type: str = field(default="capture.screenshot", init=False)
    request_id: str = ""


@dataclass
class VerboseSetMsg:
    type: str = field(default="verbose.set", init=False)
    request_id: str = ""
    enabled: bool = True


@dataclass
class WizardBrowseMsg:
    type: str = field(default="wizard.browse", init=False)
    request_id: str = ""
    path: str = ""


@dataclass
class WizardMkdirMsg:
    type: str = field(default="wizard.mkdir", init=False)
    request_id: str = ""
    name: str = ""


@dataclass
class PingMsg:
    type: str = field(default="ping", init=False)
    request_id: str = ""


_CLIENT_TYPES: dict[str, type] = {
    "session.create": SessionCreateMsg,
    "session.list": SessionListMsg,
    "session.close": SessionCloseMsg,
    "input": InputMsg,
    "input.raw": InputRawMsg,
    "key": KeyMsg,
    "capture.pane": CapturePaneMsg,
    "capture.screenshot": CaptureScreenshotMsg,
    "verbose.set": VerboseSetMsg,
    "wizard.browse": WizardBrowseMsg,
    "wizard.mkdir": WizardMkdirMsg,
    "ping": PingMsg,
}

# Union of all client message types
ClientMessage = (
    SessionCreateMsg
    | SessionListMsg
    | SessionCloseMsg
    | InputMsg
    | InputRawMsg
    | KeyMsg
    | CapturePaneMsg
    | CaptureScreenshotMsg
    | VerboseSetMsg
    | WizardBrowseMsg
    | WizardMkdirMsg
    | PingMsg
)


def parse_client_message(raw: dict[str, Any]) -> ClientMessage:
    """Parse a raw JSON dict into a typed client message."""
    msg_type = raw.get("type", "")
    cls = _CLIENT_TYPES.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown message type: {msg_type}")
    # Filter out keys not in the dataclass fields
    valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in raw.items() if k in valid_keys}
    return cls(**filtered)


# ---------------------------------------------------------------------------
# Server → Client messages (plain dicts for JSON serialization)
# ---------------------------------------------------------------------------


def make_session_created(
    *,
    channel_id: str,
    window_id: str,
    provider: str,
    mode: str,
    cwd: str,
    display_name: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "session.created",
        "request_id": request_id,
        "channel_id": channel_id,
        "window_id": window_id,
        "provider": provider,
        "mode": mode,
        "cwd": cwd,
        "display_name": display_name,
    }


def make_session_list(
    *,
    sessions: list[dict[str, Any]],
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "session.list",
        "request_id": request_id,
        "sessions": sessions,
    }


def make_session_closed(
    *,
    channel_id: str,
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "session.closed",
        "request_id": request_id,
        "channel_id": channel_id,
    }


def make_agent_message(
    *,
    channel_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "agent.message",
        "channel_id": channel_id,
        "session_id": session_id,
        "messages": messages,
    }


def make_agent_status(
    *,
    channel_id: str,
    session_id: str,
    status: str,
    display_label: str,
    provider: str = "",
    interactive: bool = False,
    prompt_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "type": "agent.status",
        "channel_id": channel_id,
        "session_id": session_id,
        "status": status,
        "display_label": display_label,
        "provider": provider,
        "interactive": interactive,
    }
    if prompt_state is not None:
        msg["prompt_state"] = prompt_state
    return msg


def make_window_change(
    *,
    window_id: str,
    change_type: str,
    provider: str,
    cwd: str,
    display_name: str = "",
) -> dict[str, Any]:
    return {
        "type": "window.change",
        "window_id": window_id,
        "change_type": change_type,
        "provider": provider,
        "cwd": cwd,
        "display_name": display_name,
    }


def make_hook_event(
    *,
    window_id: str,
    event_type: str,
    session_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "hook.event",
        "window_id": window_id,
        "event_type": event_type,
        "session_id": session_id,
        "data": data,
    }


def make_capture_pane(
    *,
    channel_id: str,
    content: str,
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "capture.pane",
        "request_id": request_id,
        "channel_id": channel_id,
        "content": content,
    }


def make_capture_screenshot(
    *,
    channel_id: str,
    image_base64: str,
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "capture.screenshot",
        "request_id": request_id,
        "channel_id": channel_id,
        "image_base64": image_base64,
    }


def make_error(
    *,
    message: str,
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "error",
        "request_id": request_id,
        "message": message,
    }


def make_pong(request_id: str = "") -> dict[str, Any]:
    return {
        "type": "pong",
        "request_id": request_id,
    }


def make_wizard_browse(
    *,
    path: str,
    directories: list[str],
    parent: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    return {
        "type": "wizard.browse",
        "request_id": request_id,
        "path": path,
        "directories": directories,
        "parent": parent,
    }
