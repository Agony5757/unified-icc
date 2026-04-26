"""UnifiedICC Gateway — the main public API of the unified_icc library.

Orchestrates tmux management, session monitoring, channel routing, and
event dispatch for any messaging frontend.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from .channel_router import channel_router
from .config import GatewayConfig, config
from .event_types import AgentMessageEvent, HookEvent, StatusEvent, WindowChangeEvent
from .monitor_events import NewMessage, NewWindowEvent
from .providers import resolve_launch_command
from .session import session_manager
from .session_monitor import SessionMonitor
from .state_persistence import StatePersistence
from .tmux_manager import send_to_window as _send_to_window, tmux_manager
from .window_state_store import window_store

logger = structlog.get_logger()


@dataclass
class WindowInfo:
    """Information about a managed tmux window."""

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

        # Start session monitor
        self._monitor = SessionMonitor()
        self._monitor.set_message_callback(self._on_new_message)
        self._monitor.set_new_window_callback(self._on_new_window)
        self._monitor.set_hook_event_callback(self._on_hook_event)
        self._monitor.start()

        logger.info("UnifiedICC gateway started")

    async def stop(self) -> None:
        """Stop the gateway: flush state, stop monitoring."""
        logger.info("Stopping UnifiedICC gateway")

        if self._monitor:
            self._monitor.stop()
            self._monitor = None

        if self._persistence:
            self._persistence.flush()

        logger.info("UnifiedICC gateway stopped")

    # ── Window management ──────────────────────────────────────────────

    async def create_window(
        self,
        work_dir: str,
        provider: str = "claude",
        mode: str = "normal",
    ) -> WindowInfo:
        """Create a new tmux window running an agent."""
        command = resolve_launch_command(provider, approval_mode=mode)
        _success, _msg, _name, window_id = await tmux_manager.create_window(
            work_dir=work_dir,
            launch_command=command,
            agent_args=provider,
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
        channel_router.unbind_window(window_id)
        window_store.remove_window(window_id)
        await asyncio.to_thread(tmux_manager.kill_window, window_id)
        logger.info("Killed window %s", window_id)

    async def list_windows(self) -> list[WindowInfo]:
        """List all managed windows."""
        windows = []
        for wid in window_store.iter_window_ids():
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

    async def send_key(self, window_id: str, key: str) -> None:
        """Send a special key to a tmux window."""
        await asyncio.to_thread(tmux_manager.send_keys, window_id, key)

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
        from .providers import get_provider_for_window
        state = window_store.get_window_state(window_id)
        return get_provider_for_window(window_id, state.provider_name or None)

    # ── Internal event dispatchers ─────────────────────────────────────

    async def _on_new_message(self, msg: NewMessage) -> None:
        channels = channel_router.resolve_channels(msg.session_id)
        # For now, use a simple approach: match window by session_id
        from typing import cast
        from .providers.base import AgentMessage, MessageRole, ContentType
        agent_msg = AgentMessage(
            text=msg.text,
            role=cast(MessageRole, msg.role),
            content_type=cast(ContentType, msg.content_type),
            is_complete=msg.is_complete,
            tool_name=msg.tool_name,
        )
        event = AgentMessageEvent(
            window_id="",
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
        change = WindowChangeEvent(
            window_id=event.window_id,
            change_type="new",
            provider="claude",
            cwd=event.cwd,
            display_name=event.window_name,
        )
        for cb in self._window_change_callbacks:
            try:
                await cb(change)
            except Exception:
                logger.exception("Window change callback error")

    async def _on_hook_event(self, event: Any) -> None:
        hook_evt = HookEvent(
            window_id="",
            event_type=event.event_type,
            session_id=event.session_id,
            data=event.data,
        )
        for cb in self._hook_callbacks:
            try:
                await cb(hook_evt)
            except Exception:
                logger.exception("Hook event callback error")
