"""WebSocket connection manager for the unified-icc server.

Tracks active WebSocket connections per channel_id and broadcasts
gateway events to subscribed connections.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for event streaming."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, set[WebSocket]] = {}
        self._global: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, channel_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._subscriptions.setdefault(channel_id, set()).add(ws)

    async def unsubscribe(self, channel_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._subscriptions.get(channel_id)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    del self._subscriptions[channel_id]

    async def subscribe_global(self, ws: WebSocket) -> None:
        async with self._lock:
            self._global.add(ws)

    async def unsubscribe_global(self, ws: WebSocket) -> None:
        async with self._lock:
            self._global.discard(ws)

    async def broadcast_to_channel(
        self, channel_id: str, message: dict[str, Any]
    ) -> None:
        """Send a JSON message to all connections subscribed to a channel."""
        async with self._lock:
            conns = list(self._subscriptions.get(channel_id, set()))
        await self._send_to_all(conns, message)

    async def broadcast_to_channels(
        self, channel_ids: list[str], message: dict[str, Any]
    ) -> None:
        """Send a JSON message to connections subscribed to any of the channels."""
        async with self._lock:
            seen: set[WebSocket] = set()
            conns: list[WebSocket] = []
            for cid in channel_ids:
                for ws in self._subscriptions.get(cid, set()):
                    if ws not in seen:
                        seen.add(ws)
                        conns.append(ws)
        await self._send_to_all(conns, message)

    async def broadcast_global(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all global subscribers."""
        async with self._lock:
            conns = list(self._global)
        await self._send_to_all(conns, message)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a JSON message to a single connection."""
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to send to WebSocket, removing")
            await self._remove_connection(ws)

    async def _send_to_all(
        self, conns: list[WebSocket], message: dict[str, Any]
    ) -> None:
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            await self._remove_connections(dead)

    async def _remove_connection(self, ws: WebSocket) -> None:
        async with self._lock:
            for cid, conns in list(self._subscriptions.items()):
                conns.discard(ws)
                if not conns:
                    del self._subscriptions[cid]
            self._global.discard(ws)

    async def _remove_connections(self, dead: list[WebSocket]) -> None:
        async with self._lock:
            dead_set = set(dead)
            for cid, conns in list(self._subscriptions.items()):
                conns -= dead_set
                if not conns:
                    del self._subscriptions[cid]
            self._global -= dead_set

    @property
    def channel_count(self) -> int:
        return len(self._subscriptions)

    @property
    def total_connections(self) -> int:
        count = len(self._global)
        for conns in self._subscriptions.values():
            count += len(conns)
        return count


manager = ConnectionManager()
