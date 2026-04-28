"""Window state storage — per-window mode and session metadata.

Key class: WindowStateStore (singleton as ``window_store``).
"""

from __future__ import annotations

import structlog
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Self

from .state_persistence import unwired_save

logger = structlog.get_logger()

APPROVAL_MODES: frozenset[str] = frozenset({"normal", "yolo"})
DEFAULT_APPROVAL_MODE = "normal"
YOLO_APPROVAL_MODE = "yolo"

BATCH_MODES: frozenset[str] = frozenset({"batched", "verbose"})
DEFAULT_BATCH_MODE = "batched"

NOTIFICATION_MODES: tuple[str, ...] = ("all", "errors_only", "muted")


@dataclass
class WindowState:
    """Persistent state for a tmux window."""

    session_id: str = ""
    cwd: str = ""
    window_name: str = ""
    transcript_path: str = ""
    notification_mode: str = "all"
    provider_name: str = ""
    approval_mode: str = DEFAULT_APPROVAL_MODE
    batch_mode: str = DEFAULT_BATCH_MODE
    external: bool = False
    channel_id: str = ""
    """Feishu (or platform) channel_id bound to this window, for reverse routing."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": self.session_id,
            "cwd": self.cwd,
        }
        if self.window_name:
            d["window_name"] = self.window_name
        if self.transcript_path:
            d["transcript_path"] = self.transcript_path
        if self.notification_mode != "all":
            d["notification_mode"] = self.notification_mode
        if self.provider_name:
            d["provider_name"] = self.provider_name
        if self.approval_mode != DEFAULT_APPROVAL_MODE:
            d["approval_mode"] = self.approval_mode
        if self.batch_mode != DEFAULT_BATCH_MODE:
            d["batch_mode"] = self.batch_mode
        if self.external:
            d["external"] = True
        if self.channel_id:
            d["channel_id"] = self.channel_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            session_id=data.get("session_id", ""),
            cwd=data.get("cwd", ""),
            window_name=data.get("window_name", ""),
            transcript_path=data.get("transcript_path", ""),
            notification_mode=data.get("notification_mode", "all"),
            provider_name=data.get("provider_name", ""),
            approval_mode=data.get("approval_mode", DEFAULT_APPROVAL_MODE),
            batch_mode=data.get("batch_mode", DEFAULT_BATCH_MODE),
            external=data.get("external", False),
            channel_id=data.get("channel_id", ""),
        )


@dataclass
class WindowStateStore:
    """Per-window mode and session metadata store."""

    window_states: dict[str, WindowState] = field(default_factory=dict)
    # Maps app_name → set of window_ids that cclark created via create_window().
    # Used to guard the fallback scan: only link sessions to windows in this set,
    # preventing the cclark dev session from being linked and causing a feedback loop.
    _created_windows: dict[str, set[str]] = field(
        default_factory=lambda: {"": set()}
    )

    def __post_init__(self) -> None:
        self._schedule_save: Callable[[], None] = unwired_save("WindowStateStore")
        self._on_hookless_provider_switch: Callable[[str], None] = lambda _wid: None

    def reset(self) -> None:
        self.window_states.clear()
        self._created_windows = {"": set()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_states": {k: v.to_dict() for k, v in self.window_states.items()},
            "_created_windows": {
                name: list(wids) for name, wids in self._created_windows.items()
            },
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self.window_states = {
            k: WindowState.from_dict(v)
            for k, v in data.get("window_states", data).items()
            if isinstance(v, dict)
        }
        raw = data.get("_created_windows", {})
        self._created_windows = {name: set(wids) for name, wids in raw.items()}
        self._created_windows.setdefault("", set())

    # ── Created-window tracking ───────────────────────────────────────────────

    def mark_window_created(self, window_id: str, app_name: str = "") -> None:
        """Record that cclark created this window (enables fallback-scan guard)."""
        self._created_windows.setdefault(app_name, set()).add(window_id)
        self._schedule_save()
        logger.debug("Marked window %s as created (app=%s)", window_id, app_name or "(default)")

    def is_created_window(self, window_id: str, app_name: str = "") -> bool:
        """Return True if cclark created this window (guards the fallback scan)."""
        if window_id in self._created_windows.get("", set()):
            return True
        return window_id in self._created_windows.get(app_name, set())

    def remove_created_window(self, window_id: str, app_name: str = "") -> None:
        """Remove window from created set (called on kill/unbind)."""
        for name, windows in list(self._created_windows.items()):
            windows.discard(window_id)
            if not windows:
                del self._created_windows[name]
        self._created_windows.setdefault("", set())
        self._schedule_save()

    def get_created_windows(self, app_name: str = "") -> set[str]:
        """Return all window_ids marked as created (for any app or a specific app)."""
        if app_name:
            return set(self._created_windows.get(app_name, set()))
        result: set[str] = set()
        for windows in self._created_windows.values():
            result.update(windows)
        return result

    def get_window_state(self, window_id: str) -> WindowState:
        if window_id not in self.window_states:
            self.window_states[window_id] = WindowState()
        return self.window_states[window_id]

    def update_cwd(self, window_id: str, cwd: str) -> None:
        if window_id in self.window_states:
            self.window_states[window_id].cwd = cwd
            self._schedule_save()

    def clear_session_fields(self, window_id: str) -> None:
        if window_id in self.window_states:
            self.window_states[window_id].session_id = ""
            self.window_states[window_id].cwd = ""
            self._schedule_save()

    def clear_window_session(self, window_id: str) -> None:
        state = self.get_window_state(window_id)
        state.session_id = ""
        state.notification_mode = "all"
        self._schedule_save()

    def get_session_id_for_window(self, window_id: str) -> str | None:
        state = self.window_states.get(window_id)
        return state.session_id if state and state.session_id else None

    def find_window_by_session(self, session_id: str) -> str | None:
        """Reverse lookup: find window_id for a given session_id."""
        for wid, state in self.window_states.items():
            if state.session_id == session_id:
                return wid
        return None

    def set_window_channel(self, window_id: str, channel_id: str) -> None:
        """Record the Feishu channel bound to a window (for reverse routing)."""
        state = self.get_window_state(window_id)
        state.channel_id = channel_id
        self._schedule_save()

    def find_channel_by_session(self, session_id: str) -> str | None:
        """Find the Feishu channel_id for a session by looking up window_store.

        Strategy:
        1. Exact session_id match in window_states
        2. If no session_id is set (newly created window before monitor linked it),
           return the channel_id of the first window that has one (single-session assumption).
        """
        window_id = self.find_window_by_session(session_id)
        if window_id:
            state = self.window_states.get(window_id)
            if state and state.channel_id:
                return state.channel_id

        # Fallback: session_id not yet linked to window (new window before monitor ran).
        # Return channel_id of the first window that has one — valid for single-session bots.
        if session_id:
            for wid, state in self.window_states.items():
                if state.channel_id:
                    return state.channel_id
        return None

    def has_window(self, window_id: str) -> bool:
        return window_id in self.window_states

    def iter_window_ids(self) -> list[str]:
        return list(self.window_states)

    def remove_window(self, window_id: str) -> bool:
        if window_id not in self.window_states:
            return False
        del self.window_states[window_id]
        self._schedule_save()
        return True

    def set_window_provider(
        self,
        window_id: str,
        provider_name: str,
        *,
        cwd: str | None = None,
        new_provider_supports_hook: bool = True,
    ) -> None:
        state = self.get_window_state(window_id)
        old_provider = state.provider_name
        state.provider_name = provider_name
        if cwd:
            state.cwd = cwd

        if (
            old_provider != provider_name
            and provider_name
            and not new_provider_supports_hook
        ):
            if state.session_id:
                state.session_id = ""
                state.transcript_path = ""
            self._on_hookless_provider_switch(window_id)

        self._schedule_save()

    _NOTIFICATION_MODES = NOTIFICATION_MODES

    def get_notification_mode(self, window_id: str) -> str:
        state = self.window_states.get(window_id)
        return state.notification_mode if state else "all"

    def set_notification_mode(self, window_id: str, mode: str) -> None:
        if mode not in self._NOTIFICATION_MODES:
            raise ValueError(f"Invalid notification mode: {mode!r}")
        state = self.get_window_state(window_id)
        if state.notification_mode != mode:
            state.notification_mode = mode
            self._schedule_save()

    def cycle_notification_mode(self, window_id: str) -> str:
        current = self.get_notification_mode(window_id)
        modes = self._NOTIFICATION_MODES
        idx = modes.index(current) if current in modes else 0
        new_mode = modes[(idx + 1) % len(modes)]
        self.set_notification_mode(window_id, new_mode)
        return new_mode

    def get_approval_mode(self, window_id: str) -> str:
        state = self.window_states.get(window_id)
        mode = state.approval_mode if state else DEFAULT_APPROVAL_MODE
        return mode if mode in APPROVAL_MODES else DEFAULT_APPROVAL_MODE

    def set_window_approval_mode(self, window_id: str, mode: str) -> None:
        normalized = mode.lower()
        if normalized not in APPROVAL_MODES:
            raise ValueError(f"Invalid approval mode: {mode!r}")
        state = self.get_window_state(window_id)
        state.approval_mode = normalized
        self._schedule_save()

    def get_batch_mode(self, window_id: str) -> str:
        state = self.window_states.get(window_id)
        mode = state.batch_mode if state else DEFAULT_BATCH_MODE
        return mode if mode in BATCH_MODES else DEFAULT_BATCH_MODE

    def set_batch_mode(self, window_id: str, mode: str) -> None:
        if mode not in BATCH_MODES:
            raise ValueError(f"Invalid batch mode: {mode!r}")
        state = self.get_window_state(window_id)
        if state.batch_mode != mode:
            state.batch_mode = mode
            self._schedule_save()

    def cycle_batch_mode(self, window_id: str) -> str:
        current = self.get_batch_mode(window_id)
        new_mode = "verbose" if current == "batched" else "batched"
        self.set_batch_mode(window_id, new_mode)
        return new_mode

    def prune_stale_window_states(
        self,
        live_window_ids: set[str],
        session_map_wids: set[str],
        bound_window_ids: set[str],
    ) -> bool:
        stale = [
            wid
            for wid in self.window_states
            if (
                wid not in session_map_wids
                and wid not in bound_window_ids
                and wid not in live_window_ids
            )
        ]
        if not stale:
            return False
        for wid in stale:
            logger.info("Pruning stale window_state: %s", wid)
            del self.window_states[wid]
        self._schedule_save()
        return True


window_store = WindowStateStore()
