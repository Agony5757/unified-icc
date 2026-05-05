from pathlib import Path

import pytest

from unified_icc.utils.idle_tracker import IdleTracker
from unified_icc.events import SessionInfo
from unified_icc.state import TrackedSession
from unified_icc.core.session_monitor import (
    SessionMonitor,
    _is_claude_trust_workspace_prompt,
    _is_codex_trust_prompt,
    _wait_for_agent_pane,
)
from unified_icc.tmux import TmuxWindow, tmux_manager
from unified_icc.tmux.window_state_store import window_store


class _IdleTrackerStub(IdleTracker):
    def get_last_activity(self, session_id: str):
        return None

    def record_activity(self, session_id: str, ts: float | None = None) -> None:
        pass

    def clear_session(self, session_id: str) -> None:
        pass


def test_trust_workspace_prompt_detector_ignores_historical_scrollback() -> None:
    pane = """
Quick safety check: Is this a project you created or one you trust?
Claude Code'll be able to read, edit, and execute files here.
❯ 1. Yes, I trust this folder
  2. No, exit
Enter to confirm · Esc to cancel
(base) agony@host:~/project$ 1
-bash: 1: command not found
(base) agony@host:~/project$
"""

    assert _is_claude_trust_workspace_prompt(pane) is False


@pytest.mark.asyncio
async def test_detect_session_id_uses_raw_status_probe(monkeypatch, tmp_path: Path) -> None:
    monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
    calls = []

    async def fake_send_keys(
        window_id: str,
        text: str,
        enter: bool = True,
        literal: bool = True,
        *,
        raw: bool = False,
    ) -> bool:
        calls.append((window_id, text, enter, literal, raw))
        return True

    async def fake_capture_pane(window_id: str, with_ansi: bool = True) -> str:
        assert window_id == "@2"
        assert with_ansi is False
        return "Session ID: sid-12345678"

    async def fake_find_window_by_id(window_id: str) -> TmuxWindow:
        assert window_id == "@2"
        return TmuxWindow(
            window_id="@2",
            window_name="claude",
            cwd="/tmp",
            pane_current_command="claude",
        )

    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window_by_id)

    assert await monitor.detect_session_id("@2") == "sid-12345678"
    assert calls == [
        ("@2", "C-u", False, False, True),
        ("@2", "/status", False, True, True),
        ("@2", "Enter", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "C-u", False, False, True),
    ]


@pytest.mark.asyncio
async def test_detect_session_id_accepts_trust_workspace_prompt_before_status_probe(
    monkeypatch, tmp_path: Path
) -> None:
    monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
    calls = []
    accepted = False

    async def fake_send_keys(
        window_id: str,
        text: str,
        enter: bool = True,
        literal: bool = True,
        *,
        raw: bool = False,
    ) -> bool:
        nonlocal accepted
        calls.append((window_id, text, enter, literal, raw))
        if text == "1":
            accepted = True
        return True

    async def fake_capture_pane(window_id: str, with_ansi: bool = True) -> str:
        assert window_id == "@2"
        if not accepted:
            return """
Accessing workspace:

/tmp/project

Quick safety check: Is this a project you created or one you trust?

Claude Code'll be able to read, edit, and execute files here.

❯ 1. Yes, I trust this folder
  2. No, exit

Enter to confirm · Esc to cancel
"""
        assert with_ansi is False
        return "Session ID: sid-12345678"

    async def fake_find_window_by_id(window_id: str) -> TmuxWindow:
        assert window_id == "@2"
        return TmuxWindow(
            window_id="@2",
            window_name="claude",
            cwd="/tmp",
            pane_current_command="claude" if accepted else "bash",
        )

    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window_by_id)

    assert await monitor.detect_session_id("@2") == "sid-12345678"
    assert calls == [
        ("@2", "1", True, True, True),
        ("@2", "C-u", False, False, True),
        ("@2", "/status", False, True, True),
        ("@2", "Enter", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "C-u", False, False, True),
    ]


@pytest.mark.asyncio
async def test_detect_session_id_waits_for_delayed_trust_prompt_before_status_probe(
    monkeypatch, tmp_path: Path
) -> None:
    monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
    calls = []
    capture_count = 0
    accepted = False

    async def fake_send_keys(
        window_id: str,
        text: str,
        enter: bool = True,
        literal: bool = True,
        *,
        raw: bool = False,
    ) -> bool:
        nonlocal accepted
        calls.append((window_id, text, enter, literal, raw))
        if text == "1":
            accepted = True
        return True

    async def fake_capture_pane(window_id: str, with_ansi: bool = True) -> str:
        nonlocal capture_count
        assert window_id == "@2"
        capture_count += 1
        if not accepted and capture_count == 1:
            return ""
        if not accepted:
            return """
Accessing workspace:

/tmp/project

Quick safety check: Is this a project you created or one you trust?

Claude Code'll be able to read, edit, and execute files here.

❯ 1. Yes, I trust this folder
  2. No, exit

Enter to confirm · Esc to cancel
"""
        assert with_ansi is False
        return "Session ID: sid-12345678"

    async def fake_find_window_by_id(window_id: str) -> TmuxWindow:
        assert window_id == "@2"
        return TmuxWindow(
            window_id="@2",
            window_name="claude",
            cwd="/tmp",
            pane_current_command="claude",
        )

    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window_by_id)
    monkeypatch.setattr(
        "unified_icc.core.session_monitor._SESSION_ID_PROBE_CLAUDE_SETTLE_DELAY", 0
    )

    assert await monitor.detect_session_id("@2") == "sid-12345678"
    assert calls == [
        ("@2", "1", True, True, True),
        ("@2", "C-u", False, False, True),
        ("@2", "/status", False, True, True),
        ("@2", "Enter", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "Escape", False, False, True),
        ("@2", "C-u", False, False, True),
    ]


@pytest.mark.asyncio
async def test_detect_session_id_does_not_probe_before_claude_is_running(
    monkeypatch, tmp_path: Path
) -> None:
    monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
    calls = []

    async def fake_send_keys(*args, **kwargs) -> bool:
        calls.append((args, kwargs))
        return True

    async def fake_find_window_by_id(window_id: str) -> TmuxWindow:
        assert window_id == "@2"
        return TmuxWindow(
            window_id="@2",
            window_name="claude",
            cwd="/tmp",
            pane_current_command="bash",
        )

    async def fake_capture_pane(window_id: str, with_ansi: bool = True) -> str:
        assert window_id == "@2"
        return ""

    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)
    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window_by_id)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(
        "unified_icc.core.session_monitor._SESSION_ID_PROBE_READY_TIMEOUT", 0.01
    )
    monkeypatch.setattr(
        "unified_icc.core.session_monitor._SESSION_ID_PROBE_READY_INTERVAL", 0.001
    )

    assert await monitor.detect_session_id("@2") is None
    assert calls == []


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


@pytest.mark.asyncio
async def test_check_for_updates_skips_unbound_tracked_sessions_when_current_map_empty(
    tmp_path: Path,
) -> None:
    window_store.reset()
    try:
        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()
        transcript = tmp_path / "sid-orphan.jsonl"
        transcript.write_text("")
        monitor.state.update_session(
            TrackedSession(
                session_id="sid-orphan",
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
        assert calls == []
        assert monitor.state.get_session("sid-orphan") is None
    finally:
        window_store.reset()


@pytest.mark.asyncio
async def test_check_for_updates_tracks_bound_session_when_current_map_empty(
    tmp_path: Path,
) -> None:
    window_store.reset()
    try:
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.cwd = "/home/agony/projects/claude-code-lark"
        ws.session_id = "sid-bound"

        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()
        transcript = tmp_path / "sid-bound.jsonl"
        transcript.write_text("")

        async def fake_get_active_cwds() -> set[str]:
            return {"/home/agony/projects/claude-code-lark"}

        monitor._get_active_cwds = fake_get_active_cwds  # type: ignore[method-assign]
        monitor._scan_projects_sync = lambda _active_cwds: [  # type: ignore[method-assign]
            SessionInfo(
                session_id="sid-bound",
                file_path=transcript,
                cwd="/home/agony/projects/claude-code-lark",
            )
        ]
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
        assert calls == [("sid-bound", "@2")]
    finally:
        window_store.reset()


@pytest.mark.asyncio
async def test_check_for_updates_skips_unbound_sessions_during_fallback_scan(
    tmp_path: Path,
) -> None:
    window_store.reset()
    try:
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.cwd = "/home/agony/projects/claude-code-lark"

        monitor = SessionMonitor(state_file=tmp_path / "monitor_state.json")
        monitor._idle_tracker = _IdleTrackerStub()

        transcript = tmp_path / "sid-unbound.jsonl"
        transcript.write_text("")

        async def fake_get_active_cwds() -> set[str]:
            return {"/home/agony/projects/claude-code-lark"}

        monitor._get_active_cwds = fake_get_active_cwds  # type: ignore[method-assign]
        monitor._scan_projects_sync = lambda _active_cwds: [  # type: ignore[method-assign]
            SessionInfo(
                session_id="sid-unbound",
                file_path=transcript,
                cwd="/some/other/project",
            )
        ]

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
        assert calls == []
    finally:
        window_store.reset()


@pytest.mark.asyncio
async def test_wait_for_agent_pane_waits_for_codex_command(monkeypatch) -> None:
    """_wait_for_agent_pane should wait for the provider's launch_command."""
    call_count = {"n": 0}

    async def fake_find_window(window_id):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            return TmuxWindow(
                window_id=window_id,
                window_name="codex-win",
                cwd="/tmp",
                pane_current_command="codex",
            )
        return TmuxWindow(
            window_id=window_id,
            window_name="loading",
            cwd="/tmp",
            pane_current_command="bash",
        )

    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window)

    result = await _wait_for_agent_pane("@1", provider_name="codex")
    assert result is True


@pytest.mark.asyncio
async def test_wait_for_agent_pane_skips_claude_trust_prompt_for_codex(monkeypatch) -> None:
    """Claude trust prompt acceptance must not be called for non-Claude providers."""
    trust_calls = {"called": False}

    async def fake_accept_trust(window_id):
        trust_calls["called"] = True
        return False

    async def fake_find_window(window_id):
        return TmuxWindow(
            window_id=window_id,
            window_name="codex-win",
            cwd="/tmp",
            pane_current_command="codex",
        )

    async def fake_capture_pane(window_id, with_ansi=True):
        return ""

    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(
        "unified_icc.core.session_monitor._accept_claude_trust_workspace_prompt",
        fake_accept_trust,
    )

    result = await _wait_for_agent_pane("@1", provider_name="codex")
    assert result is True
    assert trust_calls["called"] is False


@pytest.mark.asyncio
async def test_wait_for_agent_pane_accepts_node_for_codex(monkeypatch) -> None:
    """_wait_for_agent_pane should accept 'node' as pane command for codex."""
    capture_count = {"n": 0}

    async def fake_find_window(window_id):
        return TmuxWindow(
            window_id=window_id,
            window_name="codex-win",
            cwd="/tmp",
            pane_current_command="node",
        )

    async def fake_capture_pane(window_id, with_ansi=True):
        capture_count["n"] += 1
        # First capture: trust prompt. Second: UI visible.
        if capture_count["n"] <= 1:
            return (
                "  project-local config, hooks, and exec policies to load.\n"
                "\n"
                "› 1. Yes, continue\n"
                "  2. No, quit\n"
                "\n"
                "  Press enter to continue\n"
            )
        return (
            "╭─────────────────────────────────────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.128.0)                          │\n"
            "╰─────────────────────────────────────────────────────╯\n"
        )

    async def fake_send_keys(window_id, text, enter=True, literal=True, *, raw=False):
        return True

    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)

    result = await _wait_for_agent_pane("@1", provider_name="codex")
    assert result is True


@pytest.mark.asyncio
async def test_wait_for_agent_pane_auto_accepts_codex_trust_prompt(monkeypatch) -> None:
    """_wait_for_agent_pane should auto-accept Codex trust prompt."""
    send_calls = []

    async def fake_find_window(window_id):
        return TmuxWindow(
            window_id=window_id,
            window_name="codex-win",
            cwd="/tmp",
            pane_current_command="node",
        )

    async def fake_capture_pane(window_id, with_ansi=True):
        if not send_calls:
            return (
                "  project-local config, hooks, and exec policies to load.\n"
                "\n"
                "› 1. Yes, continue\n"
                "  2. No, quit\n"
                "\n"
                "  Press enter to continue\n"
            )
        return (
            "╭─────────────────────────────────────────────────────╮\n"
            "│ >_ OpenAI Codex (v0.128.0)                          │\n"
            "╰─────────────────────────────────────────────────────╯\n"
        )

    async def fake_send_keys(window_id, text, enter=True, literal=True, *, raw=False):
        send_calls.append((window_id, text))
        return True

    monkeypatch.setattr(tmux_manager, "find_window_by_id", fake_find_window)
    monkeypatch.setattr(tmux_manager, "capture_pane", fake_capture_pane)
    monkeypatch.setattr(tmux_manager, "send_keys", fake_send_keys)

    result = await _wait_for_agent_pane("@1", provider_name="codex")
    assert result is True
    assert ("@1", "1") in send_calls


def test_is_codex_trust_prompt() -> None:
    pane = (
        "  project-local config, hooks, and exec policies to load.\n"
        "\n"
        "› 1. Yes, continue\n"
        "  2. No, quit\n"
        "\n"
        "  Press enter to continue\n"
    )
    assert _is_codex_trust_prompt(pane) is True


def test_is_codex_trust_prompt_rejects_empty() -> None:
    assert _is_codex_trust_prompt("") is False
    assert _is_codex_trust_prompt(None) is False
