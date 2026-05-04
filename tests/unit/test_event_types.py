"""Tests for gateway event-type dataclasses."""
from __future__ import annotations

import pytest

from unified_icc.events.event_types import (
    AgentMessageEvent,
    HookEvent,
    StatusEvent,
    WindowChangeEvent,
)
from unified_icc.providers.base import AgentMessage


def test_agent_message_event_defaults() -> None:
    msg = AgentMessage(text="hello", role="assistant", content_type="text")
    event = AgentMessageEvent(
        window_id="@2",
        session_id="sid-1",
        messages=[msg],
    )
    assert event.channel_ids == []
    assert len(event.messages) == 1


def test_agent_message_event_with_channel_ids() -> None:
    msg = AgentMessage(text="hello", role="assistant", content_type="text")
    event = AgentMessageEvent(
        window_id="@2",
        session_id="sid-1",
        messages=[msg],
        channel_ids=["feishu:chat-1"],
    )
    assert event.channel_ids == ["feishu:chat-1"]


def test_status_event_fields() -> None:
    event = StatusEvent(
        window_id="@2",
        session_id="sid-1",
        status="working",
        display_label="claude",
        provider="claude",
    )
    assert event.status == "working"
    assert event.channel_ids == []
    assert event.provider == "claude"


def test_status_event_with_channel_ids() -> None:
    event = StatusEvent(
        window_id="@2",
        session_id="sid-1",
        status="idle",
        display_label="codex",
        channel_ids=["telegram:123:456"],
    )
    assert event.channel_ids == ["telegram:123:456"]


def test_hook_event_fields() -> None:
    event = HookEvent(
        window_id="@2",
        event_type="SessionStart",
        session_id="sid-1",
        data={"key": "value"},
    )
    assert event.event_type == "SessionStart"
    assert event.data["key"] == "value"
    assert event.window_id == "@2"


def test_hook_event_empty_data() -> None:
    event = HookEvent(
        window_id="@3",
        event_type="Stop",
        session_id="sid-2",
        data={},
    )
    assert event.data == {}


def test_window_change_event_defaults() -> None:
    event = WindowChangeEvent(
        window_id="@3",
        change_type="new",
        provider="codex",
        cwd="/tmp",
        display_name="codex-win",
    )
    assert event.display_name == "codex-win"
    assert event.change_type == "new"


def test_window_change_event_empty_display_name() -> None:
    event = WindowChangeEvent(
        window_id="@4",
        change_type="removed",
        provider="gemini",
        cwd="/home",
    )
    assert event.display_name == ""


def test_window_change_event_change_types() -> None:
    for change_type in ("new", "removed", "died"):
        event = WindowChangeEvent(
            window_id="@1",
            change_type=change_type,
            provider="claude",
            cwd="/tmp",
        )
        assert event.change_type == change_type


def test_status_event_status_values() -> None:
    for status in ("working", "idle", "done", "dead", "interactive"):
        event = StatusEvent(
            window_id="@1",
            session_id="sid",
            status=status,
            display_label="test",
        )
        assert event.status == status
