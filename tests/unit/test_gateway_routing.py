import pytest
from types import SimpleNamespace

from unified_icc.gateway import UnifiedICC
from unified_icc.monitor_events import NewMessage
from unified_icc.session_monitor import SessionMonitor, get_active_monitor
from unified_icc.tmux_manager import TmuxWindow, tmux_manager
from unified_icc.window_state_store import window_store


@pytest.mark.asyncio
async def test_on_new_message_does_not_route_unknown_session() -> None:
    window_store.reset()
    gateway: UnifiedICC | None = None
    try:
        gateway = UnifiedICC()
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        seen = []

        async def callback(event):
            seen.append(event)

        gateway.on_message(callback)

        await gateway._on_new_message(
            NewMessage(
                session_id="sid-unknown",
                text="hello",
                is_complete=True,
            )
        )

        assert len(seen) == 1
        assert seen[0].window_id == ""
        assert seen[0].channel_ids == []
    finally:
        if gateway is not None:
            gateway.channel_router._bindings.clear()
            gateway.channel_router._reverse.clear()
            gateway.channel_router._display_names.clear()
            gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_on_new_message_routes_known_session_to_bound_window() -> None:
    window_store.reset()
    gateway: UnifiedICC | None = None
    try:
        gateway = UnifiedICC()
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        gateway.channel_router.bind("feishu:chat-1", "@2")
        ws = window_store.get_window_state("@2")
        ws.session_id = "sid-known"
        ws.channel_id = "feishu:chat-1"

        seen = []

        async def callback(event):
            seen.append(event)

        gateway.on_message(callback)

        await gateway._on_new_message(
            NewMessage(
                session_id="sid-known",
                text="hello",
                is_complete=True,
            )
        )

        assert len(seen) == 1
        assert seen[0].window_id == "@2"
        assert seen[0].channel_ids == ["feishu:chat-1"]
    finally:
        if gateway is not None:
            gateway.channel_router._bindings.clear()
            gateway.channel_router._reverse.clear()
            gateway.channel_router._display_names.clear()
            gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_terminal_status_updates_window_session_id() -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        ws = window_store.get_window_state("@2")
        ws.session_id = "old-session"
        ws.channel_id = "feishu:chat-1"

        seen = []

        async def callback(event):
            seen.append(event)

        gateway.on_status(callback)

        await gateway._on_terminal_status(
            "@2",
            SimpleNamespace(
                is_interactive=True,
                raw_text="""
❯ /status

─────
   Status   Config   Usage   Stats

  Version:             2.1.122
  Session ID:          e682d1c5-878a-4a73-b747-475b6127f577
  cwd:                 /tmp/project
  Esc to cancel
""",
            ),
        )

        assert window_store.get_window_state("@2").session_id == (
            "e682d1c5-878a-4a73-b747-475b6127f577"
        )
        assert len(seen) == 1
        assert seen[0].session_id == "e682d1c5-878a-4a73-b747-475b6127f577"
        assert seen[0].channel_ids == ["feishu:chat-1"]
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_startup_cleanup_removes_dead_bound_windows(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        ws = window_store.get_window_state("@2")
        ws.channel_id = "feishu:chat-1"
        ws.cwd = "/tmp/project"

        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@9",
                    window_name="live",
                    cwd="/tmp/other",
                )
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        await gateway._startup_cleanup()

        assert gateway.channel_router.resolve_window("feishu:chat-1") is None
        assert not window_store.has_window("@2")
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_startup_cleanup_prunes_stale_created_window_markers(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        window_store.mark_window_created("@3")

        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@9",
                    window_name="live",
                    cwd="/tmp/other",
                )
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        await gateway._startup_cleanup()

        assert not window_store.is_created_window("@3")
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_startup_cleanup_recovers_live_bound_window_without_state(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        window_store.remove_window("@2")

        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@2",
                    window_name="project",
                    cwd="/tmp/project",
                )
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        await gateway._startup_cleanup()

        assert gateway.channel_router.resolve_window("feishu:chat-1") == "@2"
        assert window_store.has_window("@2")
        assert window_store.is_created_window("@2")
        state = window_store.get_window_state("@2")
        assert state.channel_id == "feishu:chat-1"
        assert state.cwd == "/tmp/project"
        assert state.window_name == "project"
        assert state.provider_name == "claude"
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_kill_window_awaits_tmux_kill(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.channel_id = "feishu:chat-1"

        killed = []

        async def fake_kill_window(window_id: str) -> bool:
            killed.append(window_id)
            return True

        monkeypatch.setattr(tmux_manager, "kill_window", fake_kill_window)

        await gateway.kill_window("@2")

        assert killed == ["@2"]
        assert gateway.channel_router.resolve_window("feishu:chat-1") is None
        assert gateway.channel_router.resolve_channels("@2") == []
        assert not window_store.has_window("@2")
        assert not window_store.is_created_window("@2")
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_kill_channel_windows_removes_all_state_for_channel(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        window_store.mark_window_created("@2")
        ws = window_store.get_window_state("@2")
        ws.channel_id = "feishu:chat-1"

        window_store.mark_window_created("@3")
        stale_ws = window_store.get_window_state("@3")
        stale_ws.channel_id = "feishu:chat-1"

        killed = []

        async def fake_kill_window(window_id: str) -> bool:
            killed.append(window_id)
            return True

        monkeypatch.setattr(tmux_manager, "kill_window", fake_kill_window)

        result = await gateway.kill_channel_windows("feishu:chat-1")

        assert result == ["@2", "@3"]
        assert killed == ["@2", "@3"]
        assert gateway.channel_router.resolve_window("feishu:chat-1") is None
        assert not window_store.has_window("@2")
        assert not window_store.has_window("@3")
        assert not window_store.is_created_window("@2")
        assert not window_store.is_created_window("@3")
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_list_orphaned_agent_windows_excludes_managed_windows(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        gateway.channel_router.bind("feishu:chat-1", "@2")
        window_store.mark_window_created("@2")
        window_store.get_window_state("@2").channel_id = "feishu:chat-1"

        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@2",
                    window_name="managed",
                    cwd="/tmp/project",
                    pane_current_command="claude",
                ),
                TmuxWindow(
                    window_id="@3",
                    window_name="orphan",
                    cwd="/tmp/project",
                    pane_current_command="claude",
                ),
                TmuxWindow(
                    window_id="@4",
                    window_name="shell",
                    cwd="/tmp/project",
                    pane_current_command="bash",
                ),
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        orphans = await gateway.list_orphaned_agent_windows()

        assert [w.window_id for w in orphans] == ["@3"]
        assert orphans[0].display_name == "orphan"
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_create_window_uses_launch_command_without_provider_duplication(
    monkeypatch,
) -> None:
    gateway = UnifiedICC()

    captured = {}

    async def fake_create_window(**kwargs):
        captured.update(kwargs)
        return (True, "ok", "proj", "@7")

    monkeypatch.setattr(tmux_manager, "create_window", fake_create_window)

    window = await gateway.create_window(
        "/tmp/project",
        provider="claude",
        mode="standard",
    )

    assert window.window_id == "@7"
    assert captured["agent_args"] == ""
    assert captured["launch_command"] == "claude --permission-mode default"


@pytest.mark.asyncio
async def test_gateway_start_registers_active_monitor(monkeypatch) -> None:
    gateway = UnifiedICC()

    monkeypatch.setattr(tmux_manager, "ensure_session", lambda: None)

    async def fake_startup_cleanup() -> None:
        return None

    monkeypatch.setattr(gateway, "_startup_cleanup", fake_startup_cleanup)

    started = {"called": False, "stopped": False}

    def fake_monitor_start(self) -> None:
        started["called"] = True

    def fake_monitor_stop(self) -> None:
        started["stopped"] = True

    monkeypatch.setattr(SessionMonitor, "start", fake_monitor_start)
    monkeypatch.setattr(SessionMonitor, "stop", fake_monitor_stop)

    await gateway.start()

    assert gateway._monitor is not None
    assert get_active_monitor() is gateway._monitor
    assert started["called"] is True

    await gateway.stop()
    assert started["stopped"] is True


@pytest.mark.asyncio
async def test_list_orphaned_agent_windows_detects_codex_windows(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@1",
                    window_name="codex-orphan",
                    cwd="/tmp/project",
                    pane_current_command="codex",
                ),
                TmuxWindow(
                    window_id="@2",
                    window_name="bash-shell",
                    cwd="/tmp/project",
                    pane_current_command="bash",
                ),
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        orphans = await gateway.list_orphaned_agent_windows()

        assert len(orphans) == 1
        assert orphans[0].window_id == "@1"
        assert orphans[0].provider == "codex"
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_list_orphaned_agent_windows_detects_multiple_providers(monkeypatch) -> None:
    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        async def fake_list_windows():
            return [
                TmuxWindow(
                    window_id="@1",
                    window_name="claude-orphan",
                    cwd="/tmp/a",
                    pane_current_command="claude",
                ),
                TmuxWindow(
                    window_id="@2",
                    window_name="codex-orphan",
                    cwd="/tmp/b",
                    pane_current_command="codex",
                ),
                TmuxWindow(
                    window_id="@3",
                    window_name="bash",
                    cwd="/tmp/c",
                    pane_current_command="bash",
                ),
            ]

        monkeypatch.setattr(tmux_manager, "list_windows", fake_list_windows)

        orphans = await gateway.list_orphaned_agent_windows()

        assert len(orphans) == 2
        assert orphans[0].provider == "claude"
        assert orphans[1].provider == "codex"
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()


@pytest.mark.asyncio
async def test_on_new_window_uses_event_provider(monkeypatch) -> None:
    from unified_icc.monitor_events import NewWindowEvent

    window_store.reset()
    gateway = UnifiedICC()
    gateway.channel_router._bindings.clear()
    gateway.channel_router._reverse.clear()
    gateway.channel_router._display_names.clear()
    gateway.channel_router._channel_meta.clear()

    try:
        captured = []

        async def capture_change(change):
            captured.append(change)

        gateway.on_window_change(capture_change)

        event = NewWindowEvent(
            window_id="@5",
            session_id="sess-123",
            window_name="codex-window",
            cwd="/tmp/project",
            provider="codex",
        )
        await gateway._on_new_window(event)

        assert len(captured) == 1
        assert captured[0].provider == "codex"
        assert captured[0].window_id == "@5"
    finally:
        gateway.channel_router._bindings.clear()
        gateway.channel_router._reverse.clear()
        gateway.channel_router._display_names.clear()
        gateway.channel_router._channel_meta.clear()
        window_store.reset()
    assert get_active_monitor() is None
