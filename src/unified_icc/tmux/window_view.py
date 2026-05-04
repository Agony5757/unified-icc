"""Read-only window projection — frozen snapshot for handler reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WindowView:
    """Read-only snapshot of a window's state."""

    window_id: str
    cwd: str
    provider_name: str
    approval_mode: str
    notification_mode: str
    batch_mode: str
    transcript_path: Path | None
    window_name: str
    session_id: str
    external: bool
