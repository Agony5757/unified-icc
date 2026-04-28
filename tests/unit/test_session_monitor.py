from pathlib import Path

import pytest

from unified_icc.monitor_events import SessionInfo
from unified_icc.monitor_state import TrackedSession
from unified_icc.session_monitor import SessionMonitor
from unified_icc.window_state_store import window_store


class _IdleTrackerStub:
    def get_last_activity(self, _session_id: str):
        return None

    def record_activity(self, _session_id: str) -> None:
        return None

    def clear_session(self, _session_id: str) -> None:
        return None


def test_link_window_for_session_info_matches_unique_created_window_by_cwd(tmp_path: Path) -> None:
    window_store.reset()
    try:
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.cwd = "/home/agony/projects/claude-code-lark"

        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()

        session = SessionInfo(
            session_id="01554dc4-2b42-479c-a41c-886573d2a57b",
            file_path=tmp_path / "session.jsonl",
            cwd="/home/agony/projects/claude-code-lark",
        )

        assert monitor._link_window_for_session_info(session) == "@2"
    finally:
        window_store.reset()


def test_link_window_for_session_info_requires_unique_cwd_match(tmp_path: Path) -> None:
    window_store.reset()
    try:
        for wid in ("@2", "@3"):
            window_store.mark_window_created(wid)
            ws = window_store.get_window_state(wid)
            ws.cwd = "/home/agony/projects/claude-code-lark"

        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()

        session = SessionInfo(
            session_id="01554dc4-2b42-479c-a41c-886573d2a57b",
            file_path=tmp_path / "session.jsonl",
            cwd="/home/agony/projects/claude-code-lark",
        )

        assert monitor._link_window_for_session_info(session) == ""
    finally:
        window_store.reset()


@pytest.mark.asyncio
async def test_check_for_updates_processes_tracked_sessions_when_current_map_empty(
    tmp_path: Path,
) -> None:
    window_store.reset()
    try:
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.cwd = "/home/agony/projects/claude-code-lark"
        ws.session_id = "sid-123"

        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()
        transcript = tmp_path / "sid-123.jsonl"
        transcript.write_text("")
        monitor.state.update_session(
            TrackedSession(
                session_id="sid-123",
                file_path=str(transcript),
                last_byte_offset=0,
            )
        )
        monitor._fallback_scan_done = True

        calls: list[tuple[str, str]] = []

        async def fake_process_session_file(
            session_id: str,
            file_path: Path,
            new_messages: list,
            window_id: str = "",
        ) -> None:
            calls.append((session_id, window_id))

        monitor._process_session_file = fake_process_session_file  # type: ignore[method-assign]

        result = await monitor.check_for_updates({})

        assert result == []
        assert calls == [("sid-123", "@2")]
    finally:
        window_store.reset()
