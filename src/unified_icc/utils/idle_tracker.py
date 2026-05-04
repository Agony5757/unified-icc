"""Per-session idle timer tracking.

Stores the last-activity monotonic timestamp for each session.

Key class: IdleTracker.
"""

import time


class IdleTracker:
    """Tracks per-session activity timestamps for idle detection.

    Stores a monotonic timestamp for each active session ID. Used by the monitor
    loop to detect sessions that have gone quiet (idle timeout).
    """

    def __init__(self) -> None:
        self._last_activity: dict[str, float] = {}

    def record_activity(self, session_id: str, ts: float | None = None) -> None:
        self._last_activity[session_id] = ts if ts is not None else time.monotonic()

    def get_last_activity(self, session_id: str) -> float | None:
        return self._last_activity.get(session_id)

    def clear_session(self, session_id: str) -> None:
        self._last_activity.pop(session_id, None)
