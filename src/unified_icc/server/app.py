"""FastAPI app factory with gateway lifecycle management.

Creates a FastAPI application that owns a ``UnifiedICC`` gateway instance.
Gateway callbacks push events into the ConnectionManager for WebSocket delivery.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from unified_icc import UnifiedICC
from unified_icc.config import config
from unified_icc.event_types import (
    AgentMessageEvent,
    HookEvent,
    StatusEvent,
    WindowChangeEvent,
)

from .connection_manager import manager
from .routes import register_routes
from .routes.ws import router as ws_router
from .ws_protocol import (
    make_agent_message,
    make_agent_status,
    make_hook_event,
    make_window_change,
)

logger = logging.getLogger(__name__)

# Module-level reference to the gateway, set during lifespan
_gateway: UnifiedICC | None = None


def _get_app_gateway() -> UnifiedICC | None:
    """Return the gateway instance owned by the running server."""
    return _gateway


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage gateway lifecycle: start on startup, stop on shutdown."""
    global _gateway

    logger.info("Starting UnifiedICC gateway for API server")
    _gateway = UnifiedICC()
    await _gateway.start()

    # Register gateway callbacks → ConnectionManager
    _gateway.on_message(_on_agent_message)
    _gateway.on_status(_on_agent_status)
    _gateway.on_hook_event(_on_hook_event)
    _gateway.on_window_change(_on_window_change)

    logger.info("API server ready on %s:%d", config.api_host, config.api_port)

    yield

    logger.info("Shutting down API server")
    if _gateway:
        await _gateway.stop()
        _gateway = None


# ---------------------------------------------------------------------------
# Gateway event callbacks
# ---------------------------------------------------------------------------


async def _on_agent_message(event: AgentMessageEvent) -> None:
    """Push agent output to subscribed WebSocket connections."""
    messages = []
    for m in event.messages:
        messages.append({
            "text": m.text,
            "role": m.role,
            "content_type": m.content_type,
            "is_complete": m.is_complete,
            "phase": m.phase,
            "tool_use_id": m.tool_use_id,
            "tool_name": m.tool_name,
        })

    for cid in event.channel_ids:
        msg = make_agent_message(
            channel_id=cid,
            session_id=event.session_id,
            messages=messages,
        )
        await manager.broadcast_to_channel(cid, msg)

    # Also broadcast to global subscribers
    if event.channel_ids:
        msg_global = {
            "type": "agent.message",
            "window_id": event.window_id,
            "session_id": event.session_id,
            "channel_ids": event.channel_ids,
            "messages": messages,
        }
        await manager.broadcast_global(msg_global)


async def _on_agent_status(event: StatusEvent) -> None:
    """Push status changes to subscribed WebSocket connections."""
    interactive = event.status == "interactive"

    for cid in event.channel_ids:
        msg = make_agent_status(
            channel_id=cid,
            session_id=event.session_id,
            status=event.status,
            display_label=event.display_label,
            provider=event.provider,
            interactive=interactive,
        )
        await manager.broadcast_to_channel(cid, msg)

    if event.channel_ids:
        msg_global = {
            "type": "agent.status",
            "window_id": event.window_id,
            "session_id": event.session_id,
            "channel_ids": event.channel_ids,
            "status": event.status,
            "display_label": event.display_label,
            "provider": event.provider,
            "interactive": interactive,
        }
        await manager.broadcast_global(msg_global)


async def _on_hook_event(event: HookEvent) -> None:
    """Forward hook events to subscribed WebSocket connections."""
    msg = make_hook_event(
        window_id=event.window_id,
        event_type=event.event_type,
        session_id=event.session_id,
        data=event.data,
    )
    await manager.broadcast_global(msg)


async def _on_window_change(event: WindowChangeEvent) -> None:
    """Forward window change events to subscribed WebSocket connections."""
    msg = make_window_change(
        window_id=event.window_id,
        change_type=event.change_type,
        provider=event.provider,
        cwd=event.cwd,
        display_name=event.display_name,
    )
    await manager.broadcast_global(msg)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Unified ICC API",
        description="HTTP/WebSocket API for managing AI coding agents",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST routes
    register_routes(app)

    # Register WebSocket route
    app.include_router(ws_router)

    return app
