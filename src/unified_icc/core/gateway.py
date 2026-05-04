"""UnifiedICC Gateway — the main public API of the unified_icc library.

Orchestrates tmux management, session monitoring, channel routing, and
event dispatch for any messaging frontend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from .channel_router import channel_router
from ..utils.config import GatewayConfig, config
from ..events.event_types import AgentMessageEvent, HookEvent, StatusEvent, WindowChangeEvent
from ..events.monitor_events import NewMessage, NewWindowEvent
from ..providers import resolve_launch_command
from .session import session_manager
from .session_monitor import SessionMonitor, extract_session_id_from_status
from ..state.state_persistence import StatePersistence
from ..tmux.tmux_manager import send_to_window as _send_to_window, tmux_manager
from ..tmux.window_state_store import window_store

logger = structlog.get_logger()


@dataclass
class WindowInfo:
    """Information about a managed tmux window.

    Returned by UnifiedICC.create_window, list_windows, and list_orphaned_agent_windows.
    """

    window_id: str
    display_name: str
    provider: str
    cwd: str
    session_id: str = ""


class UnifiedICC:
    """Core gateway for managing AI coding agents via tmux.

    Usage::

        gateway = UnifiedICC()
        await gateway.start()
        window = await gateway.create_window("/path/to/project")
        gateway.bind_channel("feishu:chat_123:msg_456", window.window_id)
        await gateway.send_to_window(window.window_id, "hello")
        await gateway.stop()
    """

    def __init__(self, gateway_config: GatewayConfig | None = None) -> None:
        self._config = gateway_config or config
        self.channel_router = channel_router
        self._monitor: SessionMonitor | None = None
        self._persistence: StatePersistence | None = None

        # Event callbacks
        self._message_callbacks: list[Callable[[AgentMessageEvent], Any]] = []
        self._status_callbacks: list[Callable[[StatusEvent], Any]] = []
        self._hook_callbacks: list[Callable[[HookEvent], Any]] = []
        self._window_change_callbacks: list[Callable[[WindowChangeEvent], Any]] = []

    async def start(self) -> None:
        """Start the gateway: connect to tmux, load state, begin monitoring."""
        logger.info("Starting UnifiedICC gateway", session=self._config.tmux_session_name)

        # Connect to tmux session
        tmux_manager.ensure_session()
        self._config.own_window_id = tmux_manager.own_window_id

        # Wire singletons
        session_manager._wire_singletons()

        # Startup cleanup: evict orphaned tmux windows with no active channel binding.
        # This handles the case where cclark was killed while a session was active,
        # leaving stale window_states entries. Also populate _created_windows for any
        # window that has a channel binding (proving it was cclark-created).
        await self._startup_cleanup()

        # Start session monitor
        self._monitor = SessionMonitor()
        from .session_monitor import set_active_monitor

        set_active_monitor(self._monitor)
        self._monitor.set_message_callback(self._on_new_message)
        self._monitor.set_new_window_callback(self._on_new_window)
        self._monitor.set_hook_event_callback(self._on_hook_event)
        self._monitor.set_status_callback(self._on_terminal_status)
        self._monitor.start()

        logger.info("UnifiedICC gateway started")

    async def stop(self) -> None:
        """Stop the gateway: flush state, stop monitoring."""
        logger.info("Stopping UnifiedICC gateway")

        if self._monitor:
            from .session_monitor import get_active_monitor, set_active_monitor

            if get_active_monitor() is self._monitor:
                set_active_monitor(None)  # type: ignore[arg-type]
            self._monitor.stop()
            self._monitor = None

        session_manager.flush_state()

        logger.info("UnifiedICC gateway stopped")

    # ── Window management ──────────────────────────────────────────────

    async def create_window(
        self,
        work_dir: str,
        provider: str = "claude",
        mode: str = "normal",
    ) -> WindowInfo:
        """Create a new tmux window running an agent."""
        approval_mode = "normal" if mode == "standard" else mode
        command = resolve_launch_command(provider, approval_mode=approval_mode)
        _success, _msg, _name, window_id = await tmux_manager.create_window(
            work_dir=work_dir,
            launch_command=command,
            agent_args="",
        )
        display_name = channel_router.get_display_name(window_id)
        return WindowInfo(
            window_id=window_id,
            display_name=display_name,
            provider=provider,
            cwd=work_dir,
        )

    async def kill_window(self, window_id: str) -> None:
        """Kill a tmux window and clean up bindings."""
        channel_router.unbind_window(window_id, kill=False)
        window_store.remove_created_window(window_id)
        window_store.remove_window(window_id)
        await tmux_manager.kill_window(window_id)
        logger.info("Killed window %s", window_id)

    async def kill_channel_windows(self, channel_id: str) -> list[str]:
        """Kill every managed window known to belong to a channel."""
        window_ids: set[str] = set()
        bound_window = channel_router.resolve_window(channel_id)
        if bound_window:
            window_ids.add(bound_window)

        for wid, state in list(window_store.window_states.items()):
            if state.channel_id == channel_id:
                window_ids.add(wid)

        killed: list[str] = []
        for wid in sorted(window_ids):
            await self.kill_window(wid)
            killed.append(wid)
        return killed

    async def list_orphaned_agent_windows(self) -> list[WindowInfo]:
        """List live agent tmux windows that are not monitored by cclark state."""
        from ..providers import detect_provider_from_command

        bound_wids = channel_router.bound_window_ids()
        state_wids = set(window_store.iter_window_ids())
        managed_wids = bound_wids | state_wids | window_store.get_created_windows()
        orphans: list[WindowInfo] = []

        for window in await tmux_manager.list_windows():
            if window.window_id in managed_wids:
                continue
            provider = detect_provider_from_command(window.pane_current_command)
            if not provider or provider == "shell":
                continue
            orphans.append(
                WindowInfo(
                    window_id=window.window_id,
                    display_name=window.window_name,
                    provider=provider,
                    cwd=window.cwd,
                )
            )
        return orphans

    async def list_windows(self) -> list[WindowInfo]:
        """List tmux windows created by cclark (guarded by is_created_window)."""
        windows = []
        for wid in window_store.iter_window_ids():
            if not window_store.is_created_window(wid):
                continue
            state = window_store.get_window_state(wid)
            windows.append(WindowInfo(
                window_id=wid,
                display_name=channel_router.get_display_name(wid),
                provider=state.provider_name or "claude",
                cwd=state.cwd,
                session_id=state.session_id,
            ))
        return windows

    # ── Message dispatch ───────────────────────────────────────────────

    async def send_to_window(self, window_id: str, text: str) -> None:
        """Send text input to a tmux window."""
        await _send_to_window(window_id, text)

    async def send_input_to_window(
        self,
        window_id: str,
        text: str,
        *,
        enter: bool = True,
        literal: bool = True,
        raw: bool = False,
    ) -> None:
        """Send text or key input to a tmux window with explicit Enter control."""
        await tmux_manager.send_keys(
            window_id,
            text,
            enter=enter,
            literal=literal,
            raw=raw,
        )

    async def send_key(self, window_id: str, key: str) -> None:
        """Send a special key to a tmux window."""
        await tmux_manager.send_keys(window_id, key, enter=False, literal=False)

    # ── Output capture ─────────────────────────────────────────────────

    async def capture_pane(self, window_id: str) -> str:
        """Capture the current pane content."""
        return await tmux_manager.capture_pane(window_id) or ""

    async def capture_screenshot(self, window_id: str) -> bytes:
        """Capture a screenshot of the pane as PNG bytes."""
        return await tmux_manager.capture_screenshot(window_id)

    # ── Event subscription ─────────────────────────────────────────────

    def on_message(self, callback: Callable[[AgentMessageEvent], Any]) -> None:
        self._message_callbacks.append(callback)

    def on_status(self, callback: Callable[[StatusEvent], Any]) -> None:
        self._status_callbacks.append(callback)

    def on_hook_event(self, callback: Callable[[HookEvent], Any]) -> None:
        self._hook_callbacks.append(callback)

    def on_window_change(self, callback: Callable[[WindowChangeEvent], Any]) -> None:
        self._window_change_callbacks.append(callback)

    # ── Channel routing ────────────────────────────────────────────────

    def bind_channel(self, channel_id: str, window_id: str) -> None:
        channel_router.bind(channel_id, window_id)

    def unbind_channel(self, channel_id: str) -> None:
        channel_router.unbind(channel_id)

    def resolve_window(self, channel_id: str) -> str | None:
        return channel_router.resolve_window(channel_id)

    def resolve_channels(self, window_id: str) -> list[str]:
        return channel_router.resolve_channels(window_id)

    # ── Provider management ────────────────────────────────────────────

    def get_provider(self, window_id: str) -> Any:
        from ..providers import get_provider_for_window
        state = window_store.get_window_state(window_id)
        return get_provider_for_window(window_id, state.provider_name or None)

    # ── Internal event dispatchers ─────────────────────────────────────

    # ── Startup cleanup ──────────────────────────────────────────────────

    async def _startup_cleanup(self) -> None:
        """Kill tmux windows with no active channel binding and populate _created_windows.

        On startup, window_states may contain entries for windows that were bound
        to channels in a previous run but are no longer active. These orphaned
        windows must be killed (or ignored). Windows that do have an active
        channel binding must be marked as cclark-created so the fallback scan
        guard works correctly.
        """
        from ..providers import detect_provider_from_command

        bound_wids = self.channel_router.bound_window_ids()
        live_windows = await tmux_manager.list_windows()
        live_by_id = {w.window_id: w for w in live_windows}
        live_window_ids = set(live_by_id)

        for wid in list(window_store.get_created_windows()):
            if wid not in live_window_ids or (
                not window_store.has_window(wid) and wid not in bound_wids
            ):
                logger.info(
                    "Startup cleanup: removing stale created-window marker %s",
                    wid,
                )
                window_store.remove_created_window(wid)

        for wid in list(bound_wids):
            if wid not in live_window_ids:
                logger.info(
                    "Startup cleanup: removing dead bound window %s from persisted state",
                    wid,
                )
                self.channel_router.unbind_window(wid, kill=False)
                window_store.remove_window(wid)
                window_store.remove_created_window(wid)
                continue

            live = live_by_id[wid]
            ws = window_store.get_window_state(wid)
            if not ws.cwd:
                ws.cwd = live.cwd
            if not ws.window_name:
                ws.window_name = live.window_name
            if not ws.provider_name:
                ws.provider_name = detect_provider_from_command(live.pane_current_command) or "claude"
            if not ws.channel_id:
                channel_id = self.channel_router.resolve_channel_for_window(wid)
                if channel_id:
                    ws.channel_id = channel_id
            window_store.mark_window_created(wid)

        for wid in list(window_store.iter_window_ids()):
            if wid in bound_wids:
                continue

            # Orphaned: no active channel binding. Kill the tmux window and clean up.
            ws = window_store.get_window_state(wid)
            state_desc = (
                f"cwd={ws.cwd} provider={ws.provider_name} "
                f"session={ws.session_id[:8] if ws.session_id else 'none'}"
            )
            logger.info("Startup cleanup: killing orphaned window %s (%s)", wid, state_desc)
            try:
                await tmux_manager.kill_window(wid)
            except Exception:
                logger.exception("Failed to kill orphaned window %s", wid)
            window_store.remove_window(wid)
            window_store.remove_created_window(wid)

    async def _on_new_message(self, msg: NewMessage) -> None:
        # session_id → window_id → channel_ids
        window_id = window_store.find_window_by_session(msg.session_id) or ""
        channels = channel_router.resolve_channels(window_id)
        from typing import cast
        from ..providers.base import AgentMessage, MessageRole, ContentType
        agent_msg = AgentMessage(
            text=msg.text,
            role=cast(MessageRole, msg.role),
            content_type=cast(ContentType, msg.content_type),
            is_complete=msg.is_complete,
            tool_name=msg.tool_name,
        )
        event = AgentMessageEvent(
            window_id=window_id,
            session_id=msg.session_id,
            messages=[agent_msg],
            channel_ids=channels,
        )
        for cb in self._message_callbacks:
            try:
                await cb(event)
            except Exception:
                logger.exception("Message callback error")

    async def _on_new_window(self, event: NewWindowEvent) -> None:
        channel_router.resolve_channels(event.window_id)
        provider = event.provider or "claude"
        change = WindowChangeEvent(
            window_id=event.window_id,
            change_type="new",
            provider=provider,
            cwd=event.cwd,
            display_name=event.window_name,
        )
        for cb in self._window_change_callbacks:
            try:
                await cb(change)
            except Exception:
                logger.exception("Window change callback error")

    async def _on_hook_event(self, event: Any) -> None:
        wid = window_store.find_window_by_session(event.session_id) or ""
        hook_evt = HookEvent(
            window_id=wid,
            event_type=event.event_type,
            session_id=event.session_id,
            data=event.data,
        )
        for cb in self._hook_callbacks:
            try:
                await cb(hook_evt)
            except Exception:
                logger.exception("Hook event callback error")

    async def _on_terminal_status(self, window_id: str, update: Any) -> None:
        ws = window_store.get_window_state(window_id)
        display_label = (
            getattr(update, "raw_text", "")
            or getattr(update, "display_label", "")
        )
        detected_session_id = extract_session_id_from_status(display_label)
        if detected_session_id and detected_session_id != ws.session_id:
            logger.info(
                "Updating window %s session_id from terminal status: %s -> %s",
                window_id,
                ws.session_id or "(empty)",
                detected_session_id,
            )
            ws.session_id = detected_session_id
            window_store._schedule_save()

        channels = channel_router.resolve_channels(window_id)
        if not channels and ws.channel_id:
            channels = [ws.channel_id]

        status_evt = StatusEvent(
            window_id=window_id,
            session_id=ws.session_id,
            status=(
                "interactive"
                if getattr(update, "is_interactive", False)
                else "status"
            ),
            display_label=display_label,
            channel_ids=channels,
            provider=ws.provider_name or "claude",
        )
        for cb in self._status_callbacks:
            try:
                await cb(status_evt)
            except Exception:
                logger.exception("Status callback error")
