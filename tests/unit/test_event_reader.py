"""Tests for the incremental hook-event reader."""
from __future__ import annotations

import json

import pytest

from unified_icc.events.event_reader import read_new_events


@pytest.mark.asyncio
async def test_read_new_events_empty_file(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    events, offset = await read_new_events(path, current_offset=0)
    assert events == []
    assert offset == 0


@pytest.mark.asyncio
async def test_read_new_events_reads_all_lines(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps({"event": "SessionStart", "window_key": "@2",
                    "session_id": "sid-1", "data": {}, "ts": 1000.0}) + "\n"
        + json.dumps({"event": "Stop", "window_key": "@2",
                      "session_id": "sid-1", "data": {}, "ts": 2000.0}) + "\n"
    )
    events, offset = await read_new_events(path, current_offset=0)
    assert len(events) == 2
    assert events[0].event_type == "SessionStart"
    assert events[1].event_type == "Stop"
    assert offset == path.stat().st_size


@pytest.mark.asyncio
async def test_read_new_events_incremental_from_offset(tmp_path) -> None:
    line1 = json.dumps({"event": "SessionStart", "window_key": "@2",
                         "session_id": "sid-1", "data": {}, "ts": 1000.0}) + "\n"
    line2 = json.dumps({"event": "Stop", "window_key": "@2",
                         "session_id": "sid-1", "data": {}, "ts": 2000.0}) + "\n"
    path = tmp_path / "events.jsonl"
    path.write_text(line1 + line2)
    # Resume after first line
    events, offset = await read_new_events(path, current_offset=len(line1))
    assert len(events) == 1
    assert events[0].event_type == "Stop"


@pytest.mark.asyncio
async def test_read_new_events_skips_malformed_lines(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        "not-valid-json\n"
        + json.dumps({"event": "SessionStart", "window_key": "@2",
                      "session_id": "sid-1", "data": {}, "ts": 1000.0}) + "\n"
        + "also-broken\n"
    )
    events, _ = await read_new_events(path, current_offset=0)
    assert len(events) == 1
    assert events[0].event_type == "SessionStart"


@pytest.mark.asyncio
async def test_read_new_events_skips_empty_lines(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n"
        + json.dumps({"event": "SessionStart", "window_key": "@2",
                      "session_id": "sid-1", "data": {}, "ts": 1000.0}) + "\n"
        + "\n"
    )
    events, _ = await read_new_events(path, current_offset=0)
    assert len(events) == 1
    assert events[0].event_type == "SessionStart"


@pytest.mark.asyncio
async def test_read_new_events_truncation_recovery(tmp_path) -> None:
    """If offset exceeds file size (log rotated), reset to 0 internally and read all."""
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps({"event": "SessionStart", "window_key": "@2",
                    "session_id": "sid-1", "data": {}, "ts": 1000.0}) + "\n"
    )
    events, offset = await read_new_events(path, current_offset=9999)
    assert len(events) == 1
    # Function internally resets offset when file shrunk, reads all content
    assert offset == path.stat().st_size


@pytest.mark.asyncio
async def test_read_new_events_maps_fields_correctly(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps({
            "event": "UserInput",
            "window_key": "@5",
            "session_id": "sid-xyz",
            "data": {"text": "hello"},
            "ts": 1234.567,
        }) + "\n"
    )
    events, _ = await read_new_events(path, current_offset=0)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "UserInput"
    assert event.window_key == "@5"
    assert event.session_id == "sid-xyz"
    assert event.data == {"text": "hello"}
    assert event.timestamp == 1234.567
