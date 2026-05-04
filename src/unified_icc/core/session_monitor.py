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
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ..utils.config import config
from ..events.event_reader import read_new_events
from ..utils.idle_tracker import IdleTracker
from ..state.monitor_state import MonitorState
from ..providers import detect_provider_from_command, get_provider_for_window, registry  # noqa: F401 (used by test patches)
from ..providers.base import StatusUpdate
from ..state.session_map import parse_session_map
from .session_lifecycle import session_lifecycle
from ..tmux.tmux_manager import tmux_manager
from ..events.monitor_events import NewMessage, NewWindowEvent, SessionInfo
from ..protocol.transcript_reader import TranscriptReader
from ..utils.utils import task_done_callback
from ..tmux.window_state_store import window_store

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
_SESSION_ID_PROBE_READY_TIMEOUT = 5.0
_SESSION_ID_PROBE_READY_INTERVAL = 0.2
_SESSION_ID_PROBE_CLAUDE_SETTLE_DELAY = 0.6
_TRUST_WORKSPACE_MARKERS = (
    "Quick safety check: Is this a project you created or one you trust?",
    "Claude Code'll be able to read, edit, and execute files here.",
)

_CODEX_TRUST_MARKERS = (
    "project-local config, hooks, and exec policies to load",
    "Yes, continue",
)

_CODEX_UI_MARKER = "OpenAI Codex"

logger = structlog.get_logger()

_SessionMapError = (json.JSONDecodeError, OSError)

# Regex to extract session_id from /status output.
# Matches "Session: <uuid>" or "session id: <uuid>" (case-insensitive).
_SESSION_ID_RE = re.compile(
    r"(?:Session|session)[_\s]*(?:ID|id)?[:\s]+([a-zA-Z0-9_-]{8,})", re.IGNORECASE
)


def extract_session_id_from_status(status_text: str) -> str | None:
    """Extract session_id from the raw output of /status."""
    if not status_text:
        return None
    match = _SESSION_ID_RE.search(status_text)
    if match:
        return match.group(1)
    return None


_extract_session_id_from_status = extract_session_id_from_status


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError, ValueError):
        return path


def _is_claude_trust_workspace_prompt(pane_text: str | None) -> bool:
    """Return true when Claude is waiting for the startup workspace trust prompt."""
    if not pane_text:
        return False
    if not all(marker in pane_text for marker in _TRUST_WORKSPACE_MARKERS):
        return False
    if "1. Yes, I trust this folder" not in pane_text:
        return False

    lines = [line.rstrip() for line in pane_text.splitlines()]
    trust_idx = -1
    for idx, line in enumerate(lines):
        if "1. Yes, I trust this folder" in line:
            trust_idx = idx

    if trust_idx < 0:
        return False

    trailing = [line.strip() for line in lines[trust_idx + 1 :] if line.strip()]
    if not trailing:
        return False
    if not any("Enter to confirm" in line for line in trailing):
        return False

    # Ignore historical scrollback: once the shell prompt appears after the
    # trust prompt, the prompt is no longer the focused Claude UI.
    return not any("$" in line or "command not found" in line for line in trailing)


async def _accept_claude_trust_workspace_prompt(window_id: str) -> bool:
    """Accept Claude's first-run trust prompt for a cclark-created workspace."""
    pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
    if not _is_claude_trust_workspace_prompt(pane_text):
        return False

    logger.info("Accepting Claude trust-workspace prompt for %s", window_id)
    await tmux_manager.send_keys(
        window_id,
        "1",
        enter=True,
        literal=True,
        raw=True,
    )
    await asyncio.sleep(0.5)
    return True


def _is_codex_trust_prompt(pane_text: str | None) -> bool:
    """Return true when Codex is waiting for the startup workspace trust prompt."""
    if not pane_text:
        return False
    return all(marker in pane_text for marker in _CODEX_TRUST_MARKERS)


async def _accept_codex_trust_prompt(window_id: str) -> bool:
    """Accept Codex's first-run trust prompt for a cclark-created workspace."""
    pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
    if not _is_codex_trust_prompt(pane_text):
        return False

    logger.info("Accepting Codex trust-workspace prompt for %s", window_id)
    await tmux_manager.send_keys(
        window_id,
        "1",
        enter=True,
        literal=True,
        raw=True,
    )
    await asyncio.sleep(0.5)
    return True


async def _wait_for_agent_pane(window_id: str, provider_name: str = "claude") -> bool:
    """Wait briefly until the target pane is ready for agent slash commands."""
    provider = registry.get(provider_name) if registry.is_valid(provider_name) else None
    launch_command = provider.capabilities.launch_command if provider else provider_name

    deadline = time.monotonic() + _SESSION_ID_PROBE_READY_TIMEOUT
    while time.monotonic() < deadline:
        if provider_name == "codex":
            await _accept_codex_trust_prompt(window_id)
        elif provider_name == "claude":
            await _accept_claude_trust_workspace_prompt(window_id)
        window = await tmux_manager.find_window_by_id(window_id)
        if not window:
            await asyncio.sleep(_SESSION_ID_PROBE_READY_INTERVAL)
            continue
        pane_cmd = window.pane_current_command
        is_ready = pane_cmd == launch_command
        # Codex CLI is a Node.js script; tmux reports pane_current_command as
        # "node" rather than "codex".  When waiting for codex, accept "node"
        # once we can verify the codex UI or trust prompt is visible.
        if not is_ready and provider_name == "codex" and pane_cmd == "node":
            pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
            if pane_text and (
                _CODEX_UI_MARKER in pane_text
                or _is_codex_trust_prompt(pane_text)
            ):
                is_ready = True
        if is_ready:
            if provider_name == "claude":
                # Claude can report as the active process before its first-run
                # trust prompt has finished rendering. Give the startup UI one
                # short settle window, then re-check the pane before probing.
                await asyncio.sleep(_SESSION_ID_PROBE_CLAUDE_SETTLE_DELAY)
                if await _accept_claude_trust_workspace_prompt(window_id):
                    continue
            if provider_name == "codex":
                # Codex may show a trust prompt after initially appearing ready.
                # Give it a short settle window, then re-check.
                await asyncio.sleep(0.3)
                if await _accept_codex_trust_prompt(window_id):
                    continue
            return True
        await asyncio.sleep(_SESSION_ID_PROBE_READY_INTERVAL)
    return False


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
        self._last_status_by_window: dict[str, str] = {}
        self._last_session_id_probe: dict[str, float] = {}
        self._session_id_probe_locks: dict[str, asyncio.Lock] = {}
        self._message_callback: Callable[[NewMessage], Awaitable[None]] | None = None
        self._status_callback: (
            Callable[[str, StatusUpdate], Awaitable[None]] | None
        ) = None
        self._new_window_callback: (
            Callable[[NewWindowEvent], Awaitable[None]] | None
        ) = None
        from ..providers.base import HookEvent

        self._hook_event_callback: Callable[[HookEvent], Awaitable[None]] | None = None

        self._idle_tracker = IdleTracker()
        self._transcript_reader = TranscriptReader(self.state, self._idle_tracker)

    # ── Session ID active detection ────────────────────────────────────────────

    async def detect_session_id(self, window_id: str) -> str | None:
        """Actively query session_id by sending /status to the window.

        Sends /status, captures pane output, extracts session_id, presses Escape
        to dismiss the status view.
        """
        lock = self._session_id_probe_locks.setdefault(window_id, asyncio.Lock())
        async with lock:
            existing = window_store.get_session_id_for_window(window_id)
            if existing:
                return existing
            return await self._detect_session_id_unlocked(window_id)

    async def _detect_session_id_unlocked(self, window_id: str) -> str | None:
        """Implementation for detect_session_id; caller must hold the window lock."""
        ws = window_store.get_window_state(window_id)
        provider_name = ws.provider_name or "claude"
        if not await _wait_for_agent_pane(window_id, provider_name):
            logger.warning(
                "detect_session_id: pane for %s did not become %s before probe",
                window_id,
                provider_name,
            )
            return None

        # Send /status without the normal TUI workarounds. The regular literal
        # path probes vim insert mode by typing "i", which can pollute Claude's
        # input box when the pane is a Claude TUI rather than vim.
        await tmux_manager.send_keys(
            window_id, "C-u", enter=False, literal=False, raw=True
        )
        ok = await tmux_manager.send_keys(
            window_id, "/status", enter=False, literal=True, raw=True
        )
        if not ok:
            logger.warning("detect_session_id: failed to send /status to %s", window_id)
            return None
        await asyncio.sleep(0.5)
        await tmux_manager.send_keys(
            window_id, "Enter", enter=False, literal=False, raw=True
        )

        session_id = None
        for _ in range(10):
            await asyncio.sleep(0.2)
            pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
            session_id = extract_session_id_from_status(pane_text or "")
            if session_id:
                break

        # Dismiss the status view
        await tmux_manager.send_keys(
            window_id, "Escape", enter=False, literal=False, raw=True
        )
        await asyncio.sleep(0.2)
        await tmux_manager.send_keys(
            window_id, "Escape", enter=False, literal=False, raw=True
        )
        await tmux_manager.send_keys(
            window_id, "C-u", enter=False, literal=False, raw=True
        )
        await asyncio.sleep(0.05)

        if session_id:
            if window_store.has_window(window_id):
                ws = window_store.get_window_state(window_id)
                if not ws.session_id:
                    ws.session_id = session_id
                    window_store._schedule_save()
            logger.info("detect_session_id: %s → %s", window_id, session_id)
        else:
            logger.warning(
                "detect_session_id: no session_id found in pane for %s", window_id
            )
        return session_id

    async def detect_missing_session_ids(self, *, min_interval: float = 5.0) -> None:
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
            now = time.monotonic()
            last_probe = self._last_session_id_probe.get(wid, 0.0)
            if min_interval > 0 and now - last_probe < min_interval:
                continue
            self._last_session_id_probe[wid] = now
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

    def set_status_callback(
        self, callback: Callable[[str, StatusUpdate], Awaitable[None]]
    ) -> None:
        self._status_callback = callback

    def set_hook_event_callback(self, callback: Callable[..., Awaitable[None]]) -> None:
        self._hook_event_callback = callback

    async def _check_terminal_statuses(self, windows: list[Any]) -> None:
        """Detect terminal-native interactive prompts and emit deduped status events."""
        if self._status_callback is None:
            return

        from .channel_router import channel_router

        for window in windows:
            window_id = getattr(window, "window_id", "")
            if not window_id:
                continue
            if (
                not window_store.is_created_window(window_id)
                and not channel_router.is_window_bound(window_id)
            ):
                continue

            ws = window_store.get_window_state(window_id)
            provider = get_provider_for_window(window_id, ws.provider_name or None)
            pane_text = await tmux_manager.capture_pane(window_id, with_ansi=False)
            update = provider.parse_terminal_status(pane_text or "")
            if update is None or not update.is_interactive:
                continue

            key = f"{update.ui_type or ''}\n{update.raw_text}"
            if self._last_status_by_window.get(window_id) == key:
                continue
            self._last_status_by_window[window_id] = key
            await self._status_callback(window_id, update)

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
                bound_window_id = window_store.find_window_by_session(session_id) or ""
                if not bound_window_id:
                    logger.debug(
                        "Skipping unbound tracked session while session_map is empty: %s",
                        session_id,
                    )
                    continue
                file_path = Path(tracked.file_path)
                if not file_path.exists():
                    continue
                try:
                    await self._process_session_file(
                        session_id,
                        file_path,
                        new_messages,
                        window_id=bound_window_id,
                    )
                    processed_session_ids.add(session_id)
                except Exception:
                    logger.exception("Error processing tracked session %s", session_id)

        if not current_map:
            bound_session_ids = {
                state.session_id
                for wid in window_store.get_created_windows()
                for state in [window_store.get_window_state(wid)]
                if state.session_id
            }
            missing_bound_session_ids = bound_session_ids - processed_session_ids
            if missing_bound_session_ids:
                active_cwds = await self._get_active_cwds()
                sessions = self._scan_projects_sync(active_cwds) if active_cwds else []
                for session_info in sessions:
                    if session_info.session_id not in missing_bound_session_ids:
                        continue
                    bound_window_id = (
                        window_store.find_window_by_session(session_info.session_id)
                        or ""
                    )
                    if not bound_window_id:
                        continue
                    try:
                        await self._process_session_file(
                            session_info.session_id,
                            session_info.file_path,
                            new_messages,
                            window_id=bound_window_id,
                        )
                        processed_session_ids.add(session_info.session_id)
                    except Exception:
                        logger.exception(
                            "Error processing bound session %s",
                            session_info.session_id,
                        )

                # Provider-specific discovery for non-Claude bound sessions
                # that _scan_projects_sync cannot find.
                still_missing = missing_bound_session_ids - processed_session_ids
                for session_id in still_missing:
                    wid = window_store.find_window_by_session(session_id)
                    if not wid:
                        continue
                    ws = window_store.get_window_state(wid)
                    provider_name = ws.provider_name or "claude"
                    if provider_name == "claude":
                        continue
                    if not registry.is_valid(provider_name):
                        continue
                    provider = registry.get(provider_name)
                    if not ws.cwd:
                        continue
                    try:
                        event = provider.discover_transcript(
                            ws.cwd, wid, max_age=0,
                        )
                    except (OSError, json.JSONDecodeError, ValueError):
                        continue
                    if not event or not event.transcript_path:
                        continue
                    try:
                        await self._process_session_file(
                            session_id,
                            Path(event.transcript_path),
                            new_messages,
                            window_id=wid,
                        )
                        processed_session_ids.add(session_id)
                    except Exception:
                        logger.exception(
                            "Error processing %s session %s",
                            provider_name, session_id,
                        )

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
                    if not wid:
                        logger.debug(
                            "Skipping unbound fallback session %s from %s",
                            session_info.session_id,
                            session_info.file_path,
                        )
                        continue
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

        # Provider-specific discovery for non-Claude providers (e.g. Codex).
        # These providers store transcripts outside ~/.claude/projects/ and
        # use discover_transcript() to locate them by cwd.  Runs every poll
        # until the session is discovered (transient — Codex may need a few
        # seconds to write the first transcript line).
        for wid in window_store.get_created_windows():
            ws = window_store.get_window_state(wid)
            if ws.session_id:
                continue  # already discovered
            provider_name = ws.provider_name or "claude"
            if provider_name == "claude":
                continue  # handled by _scan_projects_sync / hooks
            if not registry.is_valid(provider_name):
                continue
            provider = registry.get(provider_name)
            if not ws.cwd:
                continue
            try:
                event = provider.discover_transcript(ws.cwd, wid)
            except (OSError, json.JSONDecodeError, ValueError):
                logger.debug(
                    "Provider %s discover_transcript failed for %s",
                    provider_name, wid,
                )
                continue
            if not event:
                continue
            ws.session_id = event.session_id
            window_store._schedule_save()
            logger.info(
                "Discovered %s session %s for window %s via provider",
                provider_name, event.session_id, wid,
            )
            if event.transcript_path:
                try:
                    await self._process_session_file(
                        event.session_id,
                        Path(event.transcript_path),
                        new_messages,
                        window_id=wid,
                    )
                except Exception:
                    logger.exception(
                        "Error processing %s session %s",
                        provider_name, event.session_id,
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
                        provider=details.get("provider_name", ""),
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

        from ..state.session_map import session_map_sync

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
                await self.detect_missing_session_ids()

                all_windows = await tmux_manager.list_windows()
                external_windows = await tmux_manager.discover_external_sessions()
                all_windows = all_windows + external_windows
                await self._check_terminal_statuses(all_windows)
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
                            provider=detect_provider_from_command(window.pane_current_command),
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


def set_active_monitor(monitor: SessionMonitor | None) -> None:
    """Set the active SessionMonitor instance (called by bot.py post_init)."""
    global _active_monitor  # noqa: PLW0603
    _active_monitor = monitor


def get_active_monitor() -> SessionMonitor | None:
    """Return the active SessionMonitor instance."""
    return _active_monitor
