"""Event data types for the session monitor subsystem.

Dependency-free dataclasses shared between transcript_reader, session_monitor,
and handler modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionInfo:
    """Information about a session file found on disk during project scanning."""

    session_id: str
    file_path: Path
    cwd: str = ""


@dataclass
class NewMessage:
    """A new message event emitted by the session monitor on each poll cycle."""

    session_id: str
    text: str
    is_complete: bool
    content_type: str = "text"
    phase: str | None = None
    tool_use_id: str | None = None
    role: str = "assistant"
    tool_name: str | None = None


@dataclass
class NewWindowEvent:
    """A new tmux window detected via session_map changes or live tmux scan."""

    window_id: str
    session_id: str
    window_name: str
    cwd: str
