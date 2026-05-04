"""Event types emitted by the gateway to frontends.

Platform-agnostic events that any frontend adapter can consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..providers.base import AgentMessage


@dataclass
class AgentMessageEvent:
    """Emitted when the agent produces new output."""

    window_id: str
    session_id: str
    messages: list[AgentMessage]
    channel_ids: list[str] = field(default_factory=list)


@dataclass
class StatusEvent:
    """Emitted when agent status changes."""

    window_id: str
    session_id: str
    status: str  # "working", "idle", "done", "dead", "interactive"
    display_label: str
    channel_ids: list[str] = field(default_factory=list)
    provider: str = ""


@dataclass
class HookEvent:
    """Forwarded hook event from the agent."""

    window_id: str
    event_type: str
    session_id: str
    data: dict[str, Any]


@dataclass
class WindowChangeEvent:
    """Emitted when a window is created or removed."""

    window_id: str
    change_type: str  # "new", "removed", "died"
    provider: str
    cwd: str
    display_name: str = ""
