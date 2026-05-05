"""Feishu channel backend — manages Feishu adapters, WS clients, and gateway callbacks."""

from __future__ import annotations

import asyncio
import structlog
from typing import TYPE_CHECKING, Any

from unified_icc.channels import ChannelBackend, ChannelRegistry
from unified_icc.channels.feishu.adapter import FeishuAdapter
from unified_icc.channels.feishu.config import FeishuAppConfig
from unified_icc.channels.feishu.feishu_client import FeishuClient
from unified_icc.channels.feishu.ws_client import FeishuWSClient

if TYPE_CHECKING:
    from unified_icc.core.gateway import UnifiedICC

logger = structlog.get_logger()

# Re-export for convenience
__all__ = ["ChannelBackend", "ChannelRegistry", "FeishuChannel", "FeishuAdapter", "FeishuAppConfig"]


class FeishuChannel(ChannelBackend):
    """Manages all Feishu app instances within one unified-icc process.

    Each configured Feishu app gets its own FeishuAdapter + FeishuWSClient pair.
    Multiple apps can share one Gateway (same tmux session) or get their own.
    """

    def __init__(self, apps: list[FeishuAppConfig]) -> None:
        self._apps = apps
        self._adapters: dict[str, FeishuAdapter] = {}
        self._clients: dict[str, FeishuClient] = {}
        self._ws_clients: dict[str, FeishuWSClient] = {}
        self._handlers: dict[str, Any] = {}  # app_name -> MessageCommandHandler

    async def start(self, gateway_map: dict[str, UnifiedICC]) -> None:
        """Start the Feishu channel — create adapters and WS clients for all apps."""
        from unified_icc.channels.feishu.handlers.message import MessageCommandHandler

        # Group apps by tmux_session
        session_apps: dict[str, list[FeishuAppConfig]] = {}
        for app in self._apps:
            session = app.tmux_session
            if session not in session_apps:
                session_apps[session] = []
            session_apps[session].append(app)

        # Create adapters for each app
        for app in self._apps:
            client = FeishuClient(app.app_id, app.app_secret)
            adapter = FeishuAdapter(client, app_name=app.name)
            self._clients[app.name] = client
            self._adapters[app.name] = adapter

        # Find or create a gateway for each tmux session
        for tmux_session, apps_in_session in session_apps.items():
            if tmux_session not in gateway_map:
                from unified_icc.core.gateway import UnifiedICC
                from unified_icc.utils.config import GatewayConfig

                gw_config = GatewayConfig()
                gw_config.tmux_session = tmux_session
                gateway = UnifiedICC(gateway_config=gw_config)
                await gateway.start()
                gateway_map[tmux_session] = gateway
                logger.info("FeishuChannel: created gateway for session %s", tmux_session)

        # Register handlers for each (gateway, app) pair
        for tmux_session, apps_in_session in session_apps.items():
            gateway = gateway_map[tmux_session]
            for app in apps_in_session:
                adapter = self._adapters[app.name]
                handler = MessageCommandHandler(gateway, adapter, app.name)
                self._handlers[app.name] = handler

                # Wire gateway callbacks (outbound: gateway → Feishu)
                gateway.on_message(handler.on_agent_message)
                gateway.on_status(handler.on_agent_status)
                gateway.on_hook_event(handler.on_agent_hook)

        # Start WS clients (inbound: Feishu → gateway)
        for app in self._apps:
            ws = FeishuWSClient(
                app_id=app.app_id,
                app_secret=app.app_secret,
                app_name=app.name,
                allowed_users=app.allowed_users,
                on_message=self._handle_inbound,
            )
            self._ws_clients[app.name] = ws
            asyncio.create_task(ws.start())
            logger.info("FeishuChannel: started WS client for app %s", app.name)

    async def _handle_inbound(self, event: Any) -> None:
        """Route an inbound Feishu message to the appropriate handler."""
        app_name = getattr(event, "app_name", "default")
        handler = self._handlers.get(app_name)
        logger.info("FeishuChannel._handle_inbound: app_name=%s chat_id=%s handler_exists=%s",
                    app_name, getattr(event, "chat_id", "?"), handler is not None)
        if handler is None:
            logger.warning("No handler for app %s", app_name)
            return
        await handler.handle_message(event)

    async def stop(self) -> None:
        """Stop all WS clients and Feishu clients."""
        for ws in self._ws_clients.values():
            await ws.stop()
        for client in self._clients.values():
            await client.close()
        logger.info("FeishuChannel: stopped all clients")
