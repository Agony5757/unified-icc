"""Session monitoring service — thin coordinator and poll loop.

Orchestrates the session-monitoring subsystem:
  1. Reads hook events via event_reader and dispatches them.
  2. Reconciles session_map changes via SessionLifecycle.
  3. Reads transcript updates via TranscriptReader.
  4. Emits NewMessage / NewWindowEvent to registered callbacks.

All heavy logic lives in the extracted modules:
  - event_reader.py   — reads events.jsonl incrementally
  - idle_tracker.py   — per-session idle timers
  - session_lifecycle.py — session-map diff, claude_task_state authority
  - transcript_reader.py — transcript I/O and parsing

Key classes: SessionMonitor, NewMessage, NewWindowEvent, SessionInfo.
Re-exported from transcript_reader for backward-compatible imports.
"""

import asyncio
import re
import structlog
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .config import config
from .event_reader import read_new_events
from .idle_tracker import IdleTracker
from .monitor_state import MonitorState
from .providers import get_provider_for_window, registry  # noqa: F401 (used by test patches)
from .session_map import parse_session_map
from .session_lifecycle import session_lifecycle
from .tmux_manager import tmux_manager
from .monitor_events import NewMessage, NewWindowEvent, SessionInfo
from .transcript_reader import TranscriptReader
from .utils import task_done_callback
from .window_state_store import window_store

import aiofiles
import json

# Re-export for backward-compatible imports from other modules
__all__ = [
    "NewMessage",
    "NewWindowEvent",
    "SessionInfo",
    "SessionMonitor",
    "get_active_monitor",
    "set_active_monitor",
]

_CallbackError = Exception
_LoopError = (OSError, RuntimeError, json.JSONDecodeError, ValueError)

_BACKOFF_MIN = 2.0
_BACKOFF_MAX = 30.0
_MSG_PREVIEW_LENGTH = 80

logger = structlog.get_logger()

_SessionMapError = (json.JSONDecodeError, OSError)

# Regex to extract session_id from /status output.
# Matches "Session: <uuid>" or "session id: <uuid>" (case-insensitive).
_SESSION_ID_RE = re.compile(
    r"(?:Session|session)[_\s]*(?:ID|id)?[:\s]+([a-zA-Z0-9_-]{8,})", re.IGNORECASE
)


def _extract_session_id_from_status(status_text: str) -> str | None:
    """Extract session_id from the raw output of /status."""
    if not status_text:
        return None
    match = _SESSION_ID_RE.search(status_text)
    if match:
        return match.group(1)
    return None


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError, ValueError):
        return path


class SessionMonitor:
    """Monitors Claude Code sessions for new assistant messages.

    Thin coordinator: delegates I/O to TranscriptReader, event reading to
    event_reader, session-map diffing to SessionLifecycle, and idle tracking
    to IdleTracker.
    """

    def __init__(
        self,
        projects_path: Path | None = None,
        poll_interval: float | None = None,
        state_file: Path | None = None,
    ):
        self.projects_path = (
            projects_path if projects_path is not None else config.claude_projects_path
        )
        self.poll_interval = (
            poll_interval if poll_interval is not None else config.monitor_poll_interval
        )

        self.state = MonitorState(state_file=state_file or config.monitor_state_file)
        self.state.load()

        self._running = False
        self._task: asyncio.Task | None = None
        self._fallback_scan_done = False
        self._message_callback: Callable[[NewMessage], Awaitable[None]] | None = None
        self._new_window_callback: (
            Callable[[NewWindowEvent], Awaitable[None]] | None
        ) = None
        from .providers.base import HookEvent

        self._hook_event_callback: Callable[[HookEvent], Awaitable[None]] | None = None

        self._idle_tracker = IdleTracker()
        self._transcript_reader = TranscriptReader(self.state, self._idle_tracker)

    # ── Session ID active detection ────────────────────────────────────────────

    async def detect_session_id(self, window_id: str) -> str | None:
        """Actively query session_id by sending /status to the window.

        Sends /status, captures pane output, extracts session_id, presses Escape
        to dismiss the status view.
        """
        # Send /status command
        ok = await tmux_manager.send_keys(window_id, "/status", enter=True, literal=True)
        if not ok:
            logger.warning("detect_session_id: failed to send /status to %s", window_id)
            return None

        # Wait for output to appear
        await asyncio.sleep(0.3)

        # Capture pane and extract session_id
        pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
        session_id = _extract_session_id_from_status(pane_text or "")

        # Dismiss the status view
        await tmux_manager.send_keys(window_id, "Escape", enter=False, literal=False)
        await asyncio.sleep(0.05)

        if session_id:
            logger.info("detect_session_id: %s → %s", window_id, session_id)
        else:
            logger.warning(
                "detect_session_id: no session_id found in pane for %s", window_id
            )
        return session_id

    async def detect_missing_session_ids(self) -> None:
        """Query /status for all cclark-created windows that lack a session_id.

        Called once at startup to populate session_ids for windows where the hook
        did not fire or session_map.json was empty.
        """
        for wid in window_store.iter_window_ids():
            if not window_store.is_created_window(wid):
                continue
            ws = window_store.get_window_state(wid)
            if ws.session_id:
                continue
            session_id = await self.detect_session_id(wid)
            if session_id:
                ws.session_id = session_id
                window_store._schedule_save()

    def _link_window_for_session_info(self, session_info: SessionInfo) -> str:
        """Resolve a window_id for a discovered session.

        Prefer exact session_id matches. If the session has not been linked yet,
        fall back to a unique created window whose cwd matches and whose
        session_id is still empty.
        """
        wid = window_store.find_window_by_session(session_info.session_id) or ""
        if wid:
            return wid

        target_cwd = _normalize_path(session_info.cwd)
        if not target_cwd:
            return ""

        candidates: list[str] = []
        for window_id in window_store.get_created_windows():
            state = window_store.get_window_state(window_id)
            if state.session_id:
                continue
            if _normalize_path(state.cwd) != target_cwd:
                continue
            candidates.append(window_id)

        if len(candidates) == 1:
            return candidates[0]
        return ""

    # Delegation properties for backward-compatible test access
    @property
    def _last_session_map(self) -> dict:
        return session_lifecycle.last_session_map

    @_last_session_map.setter
    def _last_session_map(self, value: dict) -> None:
        session_lifecycle.initialize(value)

    @property
    def _last_activity(self) -> dict:
        return self._idle_tracker._last_activity

    @property
    def _file_mtimes(self) -> dict:
        return self._transcript_reader._file_mtimes

    @property
    def _pending_tools(self) -> dict:
        return self._transcript_reader._pending_tools

    def get_last_activity(self, session_id: str) -> float | None:
        """Get monotonic timestamp of last transcript activity for a session."""
        return self._idle_tracker.get_last_activity(session_id)

    def set_message_callback(
        self, callback: Callable[[NewMessage], Awaitable[None]]
    ) -> None:
        self._message_callback = callback

    def set_new_window_callback(
        self, callback: Callable[[NewWindowEvent], Awaitable[None]]
    ) -> None:
        self._new_window_callback = callback

    def set_hook_event_callback(self, callback: Callable[..., Awaitable[None]]) -> None:
        self._hook_event_callback = callback

    def record_hook_activity(self, window_id: str) -> None:
        """Record hook-based activity for a window (resets idle timers)."""
        session_id = session_lifecycle.resolve_session_id(window_id)
        if session_id:
            self._idle_tracker.record_activity(session_id)

    async def check_for_updates(self, current_map: dict) -> list[NewMessage]:
        """Check all sessions for new assistant messages."""
        new_messages: list[NewMessage] = []
        sid_to_wid = {v["session_id"]: wid for wid, v in current_map.items()}
        processed_session_ids: set[str] = set()

        direct_sessions: list[tuple[str, Path]] = []
        fallback_session_ids: set[str] = set()

        for details in current_map.values():
            session_id = details["session_id"]
            transcript_path = details.get("transcript_path", "")
            if transcript_path:
                path = Path(transcript_path)
                if path.exists():
                    direct_sessions.append((session_id, path))
                    continue
            fallback_session_ids.add(session_id)

        for session_id, file_path in direct_sessions:
            try:
                await self._process_session_file(
                    session_id,
                    file_path,
                    new_messages,
                    window_id=sid_to_wid.get(session_id, ""),
                )
                processed_session_ids.add(session_id)
            except Exception:
                logger.exception("Error processing session %s", session_id)

        if fallback_session_ids:
            active_cwds = await self._get_active_cwds()
            sessions = self._scan_projects_sync(active_cwds) if active_cwds else []
            for session_info in sessions:
                if session_info.session_id not in fallback_session_ids:
                    continue
                try:
                    await self._process_session_file(
                        session_info.session_id,
                        session_info.file_path,
                        new_messages,
                        window_id=sid_to_wid.get(session_info.session_id, ""),
                    )
                    processed_session_ids.add(session_info.session_id)
                except Exception:
                    logger.exception(
                        "Error processing session %s", session_info.session_id
                    )

        # session_map.json can legitimately stay empty even while cclark-created
        # windows are active. In that case, keep polling already-tracked
        # transcript files from MonitorState so output continues to stream.
        if not current_map and self.state.tracked_sessions:
            for session_id, tracked in list(self.state.tracked_sessions.items()):
                if session_id in processed_session_ids:
                    continue
                file_path = Path(tracked.file_path)
                if not file_path.exists():
                    continue
                try:
                    await self._process_session_file(
                        session_id,
                        file_path,
                        new_messages,
                        window_id=window_store.find_window_by_session(session_id) or "",
                    )
                    processed_session_ids.add(session_id)
                except Exception:
                    logger.exception("Error processing tracked session %s", session_id)

        self.state.save_if_dirty()

        # Fallback: when session_map is empty but cclark has created windows,
        # scan filesystem for matching sessions and link them to those windows.
        # Only runs once — repeated scans are wasteful and can cause message storms.
        # The _created_windows guard prevents the feedback-loop bug where the
        # cclark dev session gets linked to a real window.
        if (
            not current_map
            and window_store.get_created_windows()
            and not self._fallback_scan_done
        ):
            self._fallback_scan_done = True
            active_cwds = await self._get_active_cwds()
            if active_cwds:
                sessions = self._scan_projects_sync(active_cwds)
                logger.debug(
                    "Fallback scan: %d active_cwds, %d sessions found",
                    len(active_cwds), len(sessions),
                )

                for session_info in sessions:
                    # Match by session_id (exact, non-ambiguous).
                    # CWD fallback was removed: matching by directory is unreliable when
                    # multiple sessions exist in the same project.
                    wid = self._link_window_for_session_info(session_info)

                    # KEY GUARD: only link to windows that cclark created.
                    # This prevents the cclark dev session from being linked.
                    if wid and not window_store.is_created_window(wid):
                        logger.debug(
                            "Fallback: session %s matched window %s but window "
                            "is not in _created_windows — skipping link",
                            session_info.session_id, wid,
                        )
                        wid = ""

                    # Record session_id → window_id in window_store
                    if wid and session_info.session_id:
                        ws = window_store.get_window_state(wid)
                        if not ws.session_id:
                            ws.session_id = session_info.session_id
                            window_store._schedule_save()
                            logger.info(
                                "Linked window %s → session %s (created-window via fallback)",
                                wid, session_info.session_id,
                            )
                    try:
                        await self._process_session_file(
                            session_info.session_id,
                            session_info.file_path,
                            new_messages,
                            window_id=wid,
                        )
                    except Exception:
                        logger.exception(
                            "Error processing session %s", session_info.session_id
                        )

        return new_messages

    async def _process_session_file(
        self, session_id: str, file_path: Path, new_messages: list, window_id: str = ""
    ) -> None:
        """Process a single session file (delegates to TranscriptReader)."""
        await self._transcript_reader._process_session_file(
            session_id, file_path, new_messages, window_id=window_id
        )

    def _scan_projects_sync(self, active_cwds: set) -> list:
        """Scan projects synchronously (delegates to TranscriptReader)."""
        return self._transcript_reader._scan_projects_sync(
            self.projects_path, active_cwds
        )

    async def _get_active_cwds(self) -> set[str]:
        """Get normalized cwds of all active tmux windows (delegates to TranscriptReader)."""
        return await self._transcript_reader._get_active_cwds()

    async def _read_new_lines(
        self, session: Any, file_path: Path, window_id: str = ""
    ) -> list:
        """Read new lines from session file (delegates to TranscriptReader)."""
        return await self._transcript_reader._read_new_lines(
            session, file_path, window_id
        )

    async def _read_hook_events(self) -> None:
        """Read new lines from events.jsonl and dispatch via callback."""
        if not self._hook_event_callback:
            return

        offset_before = self.state.events_offset
        events, new_offset = await read_new_events(
            config.events_file, self.state.events_offset
        )
        self.state.events_offset = new_offset
        if new_offset != offset_before:
            self.state._dirty = True

        for event in events:
            try:
                await self._hook_event_callback(event)
            except _CallbackError:
                logger.exception("Hook event callback error for %s", event.event_type)

    async def _load_current_session_map(self) -> dict[str, dict[str, str]]:
        """Load current session_map and return window_key -> details mapping."""
        if config.session_map_file.exists():
            try:
                async with aiofiles.open(config.session_map_file, "r") as f:
                    content = await f.read()
                raw = json.loads(content)
                prefix = f"{config.tmux_session_name}:"
                return parse_session_map(raw, prefix)
            except _SessionMapError:
                pass
        return {}

    async def _cleanup_all_stale_sessions(self) -> None:
        """Clean up all tracked sessions not in current session_map (startup)."""
        current_map = await self._load_current_session_map()
        active_session_ids = {v["session_id"] for v in current_map.values()}

        stale_sessions = [
            sid for sid in self.state.tracked_sessions if sid not in active_session_ids
        ]
        if stale_sessions:
            logger.info(
                "[Startup cleanup] Removing %d stale sessions", len(stale_sessions)
            )
            for session_id in stale_sessions:
                self._transcript_reader.clear_session(session_id)
                self._idle_tracker.clear_session(session_id)
            self.state.save_if_dirty()

    async def _detect_and_cleanup_changes(self) -> dict[str, dict[str, str]]:
        """Reconcile session_map; clean up replaced/removed sessions; fire new-window events."""
        current_map = await self._load_current_session_map()
        result = session_lifecycle.reconcile(current_map, self._idle_tracker)

        for session_id in result.sessions_to_remove:
            self._transcript_reader.clear_session(session_id)
        if result.sessions_to_remove:
            self.state.save_if_dirty()

        if result.new_windows:
            from .session import session_manager as _sm

            for window_id, details in result.new_windows.items():
                provider_name = details.get("provider_name", "")
                if provider_name:
                    _sm.set_window_provider(window_id, provider_name)

                if self._new_window_callback:
                    event = NewWindowEvent(
                        window_id=window_id,
                        session_id=details["session_id"],
                        window_name=details.get("window_name", ""),
                        cwd=details.get("cwd", ""),
                    )
                    try:
                        await self._new_window_callback(event)
                    except _CallbackError:
                        logger.exception("New window callback error for %s", window_id)

        return result.current_map

    async def _monitor_loop(self) -> None:
        """Background poll loop."""
        logger.info("Session monitor started, polling every %ss", self.poll_interval)
        logger.info("Session monitor: about to import session_map_sync")

        from .session_map import session_map_sync

        logger.info("Session monitor loop starting")
        await self._cleanup_all_stale_sessions()
        initial_map = await self._load_current_session_map()
        session_lifecycle.initialize(initial_map)
        logger.info("Session monitor: initial_map has %d entries", len(initial_map))

        # Actively query session_ids for windows that don't have one yet.
        # This runs once at startup to handle cases where the hook did not fire
        # or session_map.json was empty.
        await self.detect_missing_session_ids()

        error_streak = 0
        while self._running:
            try:
                await self._read_hook_events()
                await session_map_sync.load_session_map()

                current_map = await self._detect_and_cleanup_changes()

                all_windows = await tmux_manager.list_windows()
                external_windows = await tmux_manager.discover_external_sessions()
                all_windows = all_windows + external_windows
                live_window_ids = {w.window_id for w in all_windows}
                session_map_sync.prune_session_map(live_window_ids)
                known_window_ids = set(current_map.keys())
                for window in all_windows:
                    if window.window_id in known_window_ids:
                        continue
                    from .channel_router import channel_router

                    already_bound = any(
                        wid == window.window_id
                        for _, _, wid in channel_router.iter_channel_bindings()
                    )
                    if not already_bound and self._new_window_callback:
                        event = NewWindowEvent(
                            window_id=window.window_id,
                            session_id="",
                            window_name=window.window_name,
                            cwd=window.cwd,
                        )
                        try:
                            await self._new_window_callback(event)
                        except _CallbackError:
                            logger.exception(
                                "New window callback error for %s",
                                window.window_id,
                            )

                new_messages = await self.check_for_updates(current_map)

                for msg in new_messages:
                    structlog.contextvars.clear_contextvars()
                    structlog.contextvars.bind_contextvars(session_id=msg.session_id)
                    status = "complete" if msg.is_complete else "streaming"
                    preview = msg.text[:_MSG_PREVIEW_LENGTH] + (
                        "..." if len(msg.text) > _MSG_PREVIEW_LENGTH else ""
                    )
                    logger.debug("[%s] session=%s: %s", status, msg.session_id, preview)
                    if self._message_callback:
                        try:
                            await self._message_callback(msg)
                        except _CallbackError:
                            logger.exception(
                                "Message callback error for session=%s",
                                msg.session_id,
                            )

            except _LoopError:
                logger.exception("Monitor loop error")
                backoff_delay = min(_BACKOFF_MAX, _BACKOFF_MIN * (2**error_streak))
                error_streak += 1
                await asyncio.sleep(backoff_delay)
                continue
            except Exception:
                logger.exception("Unexpected error in monitor loop")
                backoff_delay = min(_BACKOFF_MAX, _BACKOFF_MIN * (2**error_streak))
                error_streak += 1
                await asyncio.sleep(backoff_delay)
                continue

            error_streak = 0
            await asyncio.sleep(self.poll_interval)

        logger.info("Session monitor stopped")

    def start(self) -> None:
        if self._running:
            logger.debug("Monitor already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        self._task.add_done_callback(task_done_callback)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.state.save()
        logger.info("Session monitor stopped and state saved")


_active_monitor: SessionMonitor | None = None


def set_active_monitor(monitor: SessionMonitor) -> None:
    """Set the active SessionMonitor instance (called by bot.py post_init)."""
    global _active_monitor  # noqa: PLW0603
    _active_monitor = monitor


def get_active_monitor() -> SessionMonitor | None:
    """Return the active SessionMonitor instance."""
    return _active_monitor
