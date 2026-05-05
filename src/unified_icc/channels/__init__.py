"""Channel subsystem: registry of channel backends.

Each channel backend (Feishu, Telegram, etc.) implements the ChannelBackend ABC
and is registered with the ChannelRegistry. The registry starts all backends
when the gateway starts and stops them on shutdown.
"""

from __future__ import annotations

import asyncio
import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unified_icc.core.gateway import UnifiedICC

logger = structlog.get_logger()


class ChannelRegistry:
    """Owns and manages all channel backends.

    On `start()`, each backend creates its own Gateway instance(s) and wires
    adapters to the event callbacks. On `stop()`, all backends are shut down.
    """

    def __init__(self) -> None:
        self._backends: dict[str, ChannelBackend] = {}

    def register(self, name: str, backend: ChannelBackend) -> None:
        """Register a channel backend by name."""
        self._backends[name] = backend

    async def start_all(self) -> dict[str, UnifiedICC]:
        """Start all registered backends.

        Returns a dict mapping tmux_session_name → UnifiedICC gateway instance.
        Each backend may create one or more gateway instances (e.g., one per
        tmux session in multi-app mode).
        """
        gateway_map: dict[str, UnifiedICC] = {}
        start_tasks: list[asyncio.Task[None]] = []

        for name, backend in self._backends.items():
            logger.info("Starting channel backend: %s", name)
            task = asyncio.create_task(backend.start(gateway_map))
            start_tasks.append(task)

        # Wait for all backends to finish starting
        results = await asyncio.gather(*start_tasks, return_exceptions=True)
        for name, result in zip(self._backends.keys(), results):
            if isinstance(result, Exception):
                logger.error("Channel backend %s failed to start: %s", name, result)

        return gateway_map

    async def stop_all(self) -> None:
        """Gracefully stop all registered backends."""
        stop_tasks: list[asyncio.Task[None]] = []
        for name, backend in self._backends.items():
            logger.info("Stopping channel backend: %s", name)
            task = asyncio.create_task(backend.stop())
            stop_tasks.append(task)

        await asyncio.gather(*stop_tasks, return_exceptions=True)


class ChannelBackend:
    """Abstract base class for channel backends.

    Implement this to add a new messaging platform (Feishu, Telegram, Discord, etc.).
    """

    async def start(self, gateway_map: dict[str, UnifiedICC]) -> None:
        """Start the channel backend.

        Create Gateway instance(s) for the tmux sessions this backend manages,
        and register the appropriate adapters/callbacks. Populate gateway_map
        with session_name → UnifiedICC entries.

        Args:
            gateway_map: Mutable dict that backends should populate with their
                Gateway instances keyed by tmux_session_name.
        """
        raise NotImplementedError

    async def stop(self) -> None:
        """Gracefully stop the channel backend."""
        raise NotImplementedError
