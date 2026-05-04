"""Tests for the Codex provider."""
from __future__ import annotations

import pytest

from unified_icc.codex_format import format_codex_interactive_prompt
from unified_icc.codex_status import has_codex_assistant_output_since
from unified_icc.expandable_quote import (
    EXPANDABLE_QUOTE_END,
    EXPANDABLE_QUOTE_START,
    format_expandable_quote,
)
from unified_icc.providers.codex import CodexProvider


class TestCodexProviderCapabilities:
    def test_provider_name(self) -> None:
        p = CodexProvider()
        assert p.capabilities.name == "codex"

    def test_launch_command(self) -> None:
        p = CodexProvider()
        assert p.capabilities.launch_command == "codex"

    def test_supports_resume(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_resume is True

    def test_supports_continue(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_continue is True

    def test_supports_structured_transcript(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_structured_transcript is True

    def test_supports_incremental_read(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_incremental_read is True

    def test_transcript_format(self) -> None:
        p = CodexProvider()
        assert p.capabilities.transcript_format == "jsonl"

    def test_supports_hook_false(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_hook is False

    def test_supports_status_snapshot(self) -> None:
        p = CodexProvider()
        assert p.capabilities.supports_status_snapshot is True

    def test_builtin_commands(self) -> None:
        p = CodexProvider()
        expected = {
            "/clear", "/compact", "/init", "/mcp", "/mention",
            "/mode", "/model", "/permissions", "/plan", "/status",
        }
        assert set(p.capabilities.builtin_commands) == expected


class TestMakeLaunchArgs:
    def test_no_args(self) -> None:
        p = CodexProvider()
        assert p.make_launch_args() == ""

    def test_resume_with_id(self) -> None:
        p = CodexProvider()
        assert p.make_launch_args(resume_id="abc123") == "resume abc123"

    def test_resume_invalid_id_raises(self) -> None:
        p = CodexProvider()
        with pytest.raises(ValueError, match="Invalid resume_id"):
            p.make_launch_args(resume_id="has space")

    def test_continue(self) -> None:
        p = CodexProvider()
        assert p.make_launch_args(use_continue=True) == "resume --last"


class TestParseTranscriptEntries:
    def test_user_input_item(self) -> None:
        p = CodexProvider()
        entries = [
            {"type": "input_item", "payload": {"role": "user", "content": "Hello"}},
        ]
        msgs, pending = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].text == "Hello"
        assert pending == {}

    def test_assistant_message(self) -> None:
        p = CodexProvider()
        entries = [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hello!"}],
                },
            },
        ]
        msgs, _ = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].text == "Hello!"

    def test_function_call(self) -> None:
        p = CodexProvider()
        entries = [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "exec_command",
                    "arguments": {"cmd": "ls -la"},
                },
            },
        ]
        msgs, pending = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].content_type == "tool_use"
        assert msgs[0].tool_name == "exec_command"
        assert msgs[0].tool_use_id == "call_1"
        assert "ls -la" in msgs[0].text

    def test_function_call_output(self) -> None:
        p = CodexProvider()
        pending = {"call_1": ("exec_command", "exec_command")}
        entries = [
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "file1.py\nfile2.py",
                },
            },
        ]
        msgs, _ = p.parse_transcript_entries(entries, pending)
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].content_type == "tool_result"
        assert "file1.py" in msgs[0].text

    def test_custom_tool_call_apply_patch(self) -> None:
        p = CodexProvider()
        entries = [
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "patch_1",
                    "name": "apply_patch",
                    "input": "*** Update File: src/foo.py\n*** Update File: src/bar.py",
                },
            },
        ]
        msgs, pending = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].content_type == "tool_use"
        assert msgs[0].tool_name == "Edit"
        assert msgs[0].tool_use_id == "patch_1"
        assert "2 file(s)" in msgs[0].text

    def test_event_msg_agent_message(self) -> None:
        p = CodexProvider()
        entries = [
            {
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "Working on it...",
                },
            },
        ]
        msgs, _ = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].text == "Working on it..."

    def test_event_msg_task_complete(self) -> None:
        p = CodexProvider()
        entries = [
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "last_agent_message": "Done!",
                },
            },
        ]
        msgs, _ = p.parse_transcript_entries(entries, {})
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].text == "Done!"
        assert msgs[0].phase == "final_answer"


class TestIsUserTranscriptEntry:
    def test_input_item_user(self) -> None:
        p = CodexProvider()
        assert p.is_user_transcript_entry(
            {"type": "input_item", "payload": {"role": "user"}}
        ) is True

    def test_response_item_user(self) -> None:
        p = CodexProvider()
        assert p.is_user_transcript_entry(
            {"type": "response_item", "payload": {"role": "user", "content": []}}
        ) is True

    def test_response_item_assistant(self) -> None:
        p = CodexProvider()
        assert p.is_user_transcript_entry(
            {"type": "response_item", "payload": {"role": "assistant"}}
        ) is False

    def test_response_item_user_permissions_stripped(self) -> None:
        p = CodexProvider()
        assert p.is_user_transcript_entry(
            {
                "type": "response_item",
                "payload": {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "<permissions>allow</permissions>"}],
                },
            }
        ) is False


class TestParseHistoryEntry:
    def test_response_item_user(self) -> None:
        p = CodexProvider()
        entry = {
            "type": "response_item",
            "payload": {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            },
        }
        msg = p.parse_history_entry(entry)
        assert msg is not None
        assert msg.role == "user"
        assert msg.text == "Hello"

    def test_response_item_assistant(self) -> None:
        p = CodexProvider()
        entry = {
            "type": "response_item",
            "payload": {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hi there"}],
            },
        }
        msg = p.parse_history_entry(entry)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.text == "Hi there"

    def test_input_item_user(self) -> None:
        p = CodexProvider()
        entry = {
            "type": "input_item",
            "payload": {"role": "user", "content": "Goodbye"},
        }
        msg = p.parse_history_entry(entry)
        assert msg is not None
        assert msg.role == "user"
        assert msg.text == "Goodbye"

    def test_event_msg_returns_none(self) -> None:
        p = CodexProvider()
        entry = {"type": "event_msg", "payload": {"type": "agent_message", "message": "hi"}}
        assert p.parse_history_entry(entry) is None


class TestParseTerminalStatus:
    def test_edit_prompt(self) -> None:
        p = CodexProvider()
        pane = (
            "some output\n"
            "Do you want to make this edit to src/main.py?\n"
            "  - old line\n"
            "  + new line\n"
            "Enter to confirm, Esc to cancel"
        )
        update = p.parse_terminal_status(pane)
        assert update is not None
        assert update.is_interactive is True
        assert update.ui_type == "AskUserQuestion"
        assert "src/main.py" in update.raw_text

    def test_no_interactive_returns_none(self) -> None:
        p = CodexProvider()
        pane = "just some regular output\nwith no interactive prompts"
        update = p.parse_terminal_status(pane)
        assert update is None


class TestDiscoverTranscript:
    def test_nonexistent_dir_returns_none(self) -> None:
        p = CodexProvider()
        result = p.discover_transcript("/tmp/this_path_does_not_exist_12345", "test:@0")
        assert result is None


class TestBuildStatusSnapshot:
    def test_nonexistent_file_returns_none(self) -> None:
        p = CodexProvider()
        result = p.build_status_snapshot("/nonexistent/file.jsonl", display_name="test")
        assert result is None


class TestHasOutputSince:
    def test_nonexistent_file_returns_false(self) -> None:
        result = has_codex_assistant_output_since("/nonexistent/file.jsonl", 0)
        assert result is False


class TestExpandableQuote:
    def test_wraps_with_sentinels(self) -> None:
        text = "line1\nline2"
        result = format_expandable_quote(text)
        assert result.startswith(EXPANDABLE_QUOTE_START)
        assert result.endswith(EXPANDABLE_QUOTE_END)
        assert "line1\nline2" in result

    def test_truncates_long_text(self) -> None:
        text = "x" * 4000
        result = format_expandable_quote(text)
        assert EXPANDABLE_QUOTE_START in result
        assert EXPANDABLE_QUOTE_END in result


class TestFormatCodexInteractivePrompt:
    def test_edit_prompt_extracted(self) -> None:
        raw = (
            "Do you want to make this edit to src/main.py?\n"
            "  - old line\n"
            "  + new line\n"
            "Enter to confirm, Esc to cancel"
        )
        result = format_codex_interactive_prompt(raw)
        assert "src/main.py" in result
        assert "Changes:" in result

    def test_non_edit_prompt_passed_through(self) -> None:
        raw = "What would you like me to do?\nEsc to cancel"
        result = format_codex_interactive_prompt(raw)
        assert "What would you like me to do" in result
