"""Channel routing -- platform-agnostic channel<->window binding.

Replaces ccgram's ThreadRouter with a platform-agnostic version that uses
string-based channel IDs instead of Telegram-specific integer pairs.

Channel ID format is platform-specific but always a string:
  - "feishu:chat_id:thread_id" for Feishu
  - "telegram:user_id:topic_id" for Telegram
  - Any platform can define its own format

Key class: ChannelRouter (singleton instantiated as ``channel_router``).
Key data:
  - _bindings   (channel_id -> window_id)
  - _reverse    (window_id -> list[channel_id])
  - _display_names (window_id -> display name)
  - _channel_meta  (channel_id -> metadata dict)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

from .state_persistence import unwired_save

logger = structlog.get_logger()


@dataclass
class ChannelRouter:
    """Bidirectional channel<->window mapping.

    Replaces ccgram's ThreadRouter with a platform-agnostic version
    that uses string channel IDs instead of Telegram-specific int pairs.
    """

    # Core mapping: channel_id -> window_id
    _bindings: dict[str, str] = field(default_factory=dict)
    # Reverse: window_id -> list of channel_ids
    _reverse: dict[str, list[str]] = field(default_factory=dict)
    # Display names: window_id -> display_name
    _display_names: dict[str, str] = field(default_factory=dict)
    # Channel metadata: channel_id -> dict (user_id, etc.)
    _channel_meta: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._schedule_save: Callable[[], None] = unwired_save("ChannelRouter")

    # ------------------------------------------------------------------
    # Compatibility properties (for session.py migration from thread_router)
    # ------------------------------------------------------------------

    @property
    def window_display_names(self) -> dict[str, str]:
        return self._display_names

    @property
    def channel_bindings(self) -> dict[str, str]:
        return self._bindings

    @property
    def group_chat_ids(self) -> dict[str, str]:
        """Stub — group_chat_ids are Telegram-specific and not used in gateway core."""
        return {}

    def sync_display_names(self, live_windows: list) -> bool:
        """Sync display names from live windows. Returns True if changed."""
        changed = False
        for w in live_windows:
            wid = w.window_id if hasattr(w, 'window_id') else w.get('window_id', '')
            name = w.window_name if hasattr(w, 'window_name') else w.get('window_name', '')
            if wid and name and self._display_names.get(wid) != name:
                self._display_names[wid] = name
                changed = True
        return changed

    def pop_display_name(self, window_id: str) -> str:
        return self._display_names.pop(window_id, window_id)

    def _has_window_state(self, wid: str) -> bool:
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_reverse_index(self) -> None:
        """Rebuild _reverse from _bindings."""
        self._reverse = {}
        for channel_id, window_id in self._bindings.items():
            self._reverse.setdefault(window_id, []).append(channel_id)

    # ------------------------------------------------------------------
    # Core binding operations
    # ------------------------------------------------------------------

    def bind(
        self,
        channel_id: str,
        window_id: str,
        *,
        user_id: str = "",
        display_name: str = "",
    ) -> None:
        """Bind a channel to a window. Unbinds previous channel-window associations.

        Enforces 1 channel = 1 window and 1 window = 1 primary channel.
        If the channel was previously bound to a different window, the old
        binding is removed.  If another channel was already bound to this
        window, the stale binding is evicted.
        """
        # If channel already bound to this exact window, nothing to do
        old_window = self._bindings.get(channel_id)
        if old_window == window_id:
            return

        # Remove old binding for this channel (if any)
        if old_window is not None:
            self._remove_from_reverse(channel_id, old_window)
            logger.info(
                "Evicted channel %s from window %s (rebinding to %s)",
                channel_id,
                old_window,
                window_id,
            )

        # Evict any existing channel bound to this window
        stale_channels = list(self._reverse.get(window_id, []))
        for stale_ch in stale_channels:
            if stale_ch != channel_id:
                del self._bindings[stale_ch]
                self._channel_meta.pop(stale_ch, None)
                logger.info(
                    "Evicted stale binding: channel %s -> window %s "
                    "(replaced by channel %s)",
                    stale_ch,
                    window_id,
                    channel_id,
                )
        # Clean up the reverse list for this window
        self._reverse.pop(window_id, None)

        # Apply new binding
        self._bindings[channel_id] = window_id
        self._reverse.setdefault(window_id, []).append(channel_id)

        # Store metadata
        if user_id:
            self._channel_meta.setdefault(channel_id, {})["user_id"] = user_id

        if display_name:
            self._display_names[window_id] = display_name

        self._schedule_save()
        display = display_name or self.get_display_name(window_id)
        logger.info(
            "Bound channel %s -> window %s (%s)",
            channel_id,
            window_id,
            display,
        )

    def unbind(self, channel_id: str) -> None:
        """Remove a channel binding."""
        window_id = self._bindings.pop(channel_id, None)
        if window_id is None:
            return
        self._remove_from_reverse(channel_id, window_id)
        self._channel_meta.pop(channel_id, None)

        # Clean up orphaned display name if nothing references this window
        if not self._reverse.get(window_id):
            self._display_names.pop(window_id, None)

        self._schedule_save()
        logger.info("Unbound channel %s (was window %s)", channel_id, window_id)

    def unbind_window(self, window_id: str) -> list[str]:
        """Remove all bindings for a window. Returns the removed channel_ids."""
        channels = self._reverse.pop(window_id, [])
        for channel_id in channels:
            self._bindings.pop(channel_id, None)
            self._channel_meta.pop(channel_id, None)
        self._display_names.pop(window_id, None)

        if channels:
            self._schedule_save()
            logger.info(
                "Unbound window %s, removed channels: %s",
                window_id,
                channels,
            )
        return channels

    # ------------------------------------------------------------------
    # Lookup operations
    # ------------------------------------------------------------------

    def resolve_window(self, channel_id: str) -> str | None:
        """Look up window_id for a channel."""
        return self._bindings.get(channel_id)

    def resolve_channels(self, window_id: str) -> list[str]:
        """Look up all channel_ids bound to a window."""
        return list(self._reverse.get(window_id, []))

    def resolve_channel_for_window(self, window_id: str) -> str | None:
        """Return the first channel_id for a window, or None."""
        channels = self._reverse.get(window_id)
        if channels:
            return channels[0]
        return None

    # ------------------------------------------------------------------
    # Display name management
    # ------------------------------------------------------------------

    def get_display_name(self, window_id: str) -> str:
        """Get display name for a window, defaults to window_id."""
        return self._display_names.get(window_id, window_id)

    def set_display_name(self, window_id: str, name: str) -> None:
        """Set display name for a window."""
        if self._display_names.get(window_id) != name:
            self._display_names[window_id] = name
            self._schedule_save()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_bound(self, channel_id: str) -> bool:
        """Check if a channel is bound."""
        return channel_id in self._bindings

    def is_window_bound(self, window_id: str) -> bool:
        """Check if any channel is bound to a window."""
        return bool(self._reverse.get(window_id))

    def bound_window_ids(self) -> set[str]:
        """Return all bound window IDs."""
        return set(self._reverse.keys())

    def bound_channel_ids(self) -> set[str]:
        """Return all bound channel IDs."""
        return set(self._bindings.keys())

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize for state.json."""
        return {
            "channel_bindings": dict(self._bindings),
            "channel_meta": dict(self._channel_meta),
            "display_names": dict(self._display_names),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Load from state.json data. Handles migration from thread_router format.

        Does NOT call ``_schedule_save`` -- loading from disk must not
        trigger a write.
        """
        # Prefer the new format
        if "channel_bindings" in data:
            self._bindings = dict(data["channel_bindings"])
            self._channel_meta = {
                k: dict(v) for k, v in data.get("channel_meta", {}).items()
            }
            self._display_names = dict(data.get("display_names", {}))
        elif "thread_bindings" in data:
            # Migrate from ccgram's thread_router format:
            #   dict[int, dict[int, str]]  (user_id -> thread_id -> window_id)
            #   -> dict[str, str]  (channel_id -> window_id)
            self._bindings = {}
            self._channel_meta = {}
            self._display_names = dict(data.get("window_display_names", {}))

            for uid_str, bindings in data["thread_bindings"].items():
                try:
                    uid = int(uid_str)
                except (ValueError, TypeError):
                    logger.warning(
                        "Migration: skipping non-integer user_id %r", uid_str
                    )
                    continue
                if not isinstance(bindings, dict):
                    continue
                for tid_str, wid in bindings.items():
                    try:
                        tid = int(tid_str)
                    except (ValueError, TypeError):
                        logger.warning(
                            "Migration: skipping non-integer thread_id %r "
                            "for user %d",
                            tid_str,
                            uid,
                        )
                        continue
                    channel_id = f"telegram:{uid}:{tid}"
                    self._bindings[channel_id] = wid
                    self._channel_meta[channel_id] = {"user_id": str(uid)}

            logger.info(
                "Migrated thread_bindings -> channel_bindings (%d entries)",
                len(self._bindings),
            )
        else:
            self._bindings = {}
            self._channel_meta = {}
            self._display_names = {}

        self._rebuild_reverse_index()

    # ------------------------------------------------------------------
    # Internal helpers (private)
    # ------------------------------------------------------------------

    def _remove_from_reverse(self, channel_id: str, window_id: str) -> None:
        """Remove a channel_id from the reverse index for a window."""
        channels = self._reverse.get(window_id)
        if channels is None:
            return
        channels = [ch for ch in channels if ch != channel_id]
        if channels:
            self._reverse[window_id] = channels
        else:
            del self._reverse[window_id]


# Module-level singleton -- wired by SessionManager.__post_init__()
channel_router = ChannelRouter()
