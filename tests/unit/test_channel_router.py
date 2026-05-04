"""Tests for channel_router module."""

import pytest
from unittest.mock import patch

from unified_icc.core.channel_router import ChannelRouter


@pytest.fixture
def router():
    """Create a fresh ChannelRouter for each test with _schedule_save mocked."""
    r = ChannelRouter()
    r._schedule_save = lambda: None  # Mock to avoid SessionManager requirement
    return r


class TestChannelRouterBind:
    """Tests for bind() method."""

    def test_bind_creates_binding(self, router):
        """Binding a channel to a window should create the binding."""
        router.bind("feishu:chat-1", "@1", display_name="test-window")

        assert router.resolve_window("feishu:chat-1") == "@1"
        assert "feishu:chat-1" in router.resolve_channels("@1")

    def test_bind_twice_same_window_is_noop(self, router):
        """Binding the same channel to the same window should be a no-op."""
        router.bind("feishu:chat-1", "@1")
        router.bind("feishu:chat-1", "@1")

        # Should still have exactly one binding
        assert len(router._bindings) == 1
        assert router.resolve_window("feishu:chat-1") == "@1"

    def test_bind_channel_to_different_window_replaces(self, router):
        """Binding a channel to a different window should replace the binding."""
        router.bind("feishu:chat-1", "@1")
        router.bind("feishu:chat-1", "@2")

        assert router.resolve_window("feishu:chat-1") == "@2"
        assert router.resolve_window("feishu:chat-1") != "@1"

    def test_bind_stores_display_name(self, router):
        """Binding with a display_name should store it."""
        router.bind("feishu:chat-1", "@1", display_name="My Window")

        assert router.get_display_name("@1") == "My Window"

    def test_bind_stores_user_metadata(self, router):
        """Binding with user_id should store it in channel_meta."""
        router.bind("feishu:chat-1", "@1", user_id="user-123")

        assert router._channel_meta["feishu:chat-1"]["user_id"] == "user-123"


class TestChannelRouterUnbind:
    """Tests for unbind() method."""

    def test_unbind_removes_binding(self, router):
        """Unbinding a channel should remove its binding."""
        router.bind("feishu:chat-1", "@1")
        router.unbind_window("@1")

        assert router.resolve_window("feishu:chat-1") is None

    def test_unbind_nonexistent_window_is_noop(self, router):
        """Unbinding a non-existent window should be a no-op."""
        initial_bindings = dict(router._bindings)
        router.unbind_window("@999")

        assert router._bindings == initial_bindings


class TestChannelRouterResolve:
    """Tests for resolve methods."""

    def test_resolve_window_returns_none_for_unknown(self, router):
        """Resolving an unknown channel should return None."""
        assert router.resolve_window("feishu:unknown") is None

    def test_resolve_channels_returns_empty_for_unknown(self, router):
        """Resolving channels for an unknown window should return empty list."""
        assert router.resolve_channels("@999") == []

    def test_resolve_channels_returns_bound_channels(self, router):
        """Resolving channels for a window should return all bound channels."""
        router.bind("feishu:chat-1", "@1")
        router.bind("feishu:chat-2", "@2")

        channels = router.resolve_channels("@1")
        assert len(channels) == 1
        assert "feishu:chat-1" in channels

        channels = router.resolve_channels("@2")
        assert len(channels) == 1
        assert "feishu:chat-2" in channels


class TestChannelRouterDisplayNames:
    """Tests for display name methods."""

    def test_get_display_name_unknown_window(self, router):
        """Unknown windows should return their window_id as fallback."""
        assert router.get_display_name("@999") == "@999"

    def test_get_display_name_stored(self, router):
        """Stored display names should be returned."""
        router.bind("feishu:chat-1", "@1", display_name="My Window")
        assert router.get_display_name("@1") == "My Window"

    def test_pop_display_name_returns_and_removes(self, router):
        """pop_display_name should return and remove the name."""
        router.bind("feishu:chat-1", "@1", display_name="My Window")
        result = router.pop_display_name("@1")

        assert result == "My Window"
        assert router.get_display_name("@1") == "@1"  # Falls back to window_id


class TestChannelRouterSync:
    """Tests for sync_display_names method."""

    def test_sync_display_names_updates_names(self, router):
        """sync_display_names should update display names from live windows."""
        router.bind("feishu:chat-1", "@1")

        live_windows = [
            {"window_id": "@1", "window_name": "New Name"},
            {"window_id": "@2", "window_name": "Other Window"},
        ]

        changed = router.sync_display_names(live_windows)

        assert changed is True
        assert router.get_display_name("@1") == "New Name"
        assert router.get_display_name("@2") == "Other Window"

    def test_sync_display_names_no_change(self, router):
        """sync_display_names should return False if no names changed."""
        router.bind("feishu:chat-1", "@1", display_name="Same Name")

        live_windows = [
            {"window_id": "@1", "window_name": "Same Name"},
        ]

        changed = router.sync_display_names(live_windows)

        assert changed is False


class TestChannelRouterNestedBindings:
    """Tests for nested_bindings property."""

    def test_nested_bindings_groups_by_platform(self, router):
        """nested_bindings should group bindings by platform prefix."""
        router.bind("feishu:chat-1", "@1")
        router.bind("feishu:chat-2", "@2")
        router.bind("telegram:user-1", "@3")

        nested = router.nested_bindings

        assert "feishu" in nested
        assert "telegram" in nested
        assert nested["feishu"]["chat-1"] == "@1"
        assert nested["feishu"]["chat-2"] == "@2"
        assert nested["telegram"]["user-1"] == "@3"
