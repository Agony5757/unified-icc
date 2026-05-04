"""Tests for session_map module."""

import pytest

from unified_icc.state.session_map import parse_session_map, parse_emdash_provider


class TestParseSessionMap:
    """Tests for parse_session_map function."""

    def test_parses_matching_prefix(self):
        """Should parse entries matching the prefix."""
        raw = {
            "ccgram:@1": {
                "session_id": "sid-123",
                "cwd": "/tmp/project",
                "window_name": "test-window",
            }
        }
        result = parse_session_map(raw, "ccgram:")

        assert "@1" in result
        assert result["@1"]["session_id"] == "sid-123"
        assert result["@1"]["cwd"] == "/tmp/project"

    def test_ignores_nonmatching_prefix(self):
        """Should ignore entries that don't match the prefix."""
        raw = {
            "other:@1": {
                "session_id": "sid-123",
                "cwd": "/tmp/project",
            }
        }
        result = parse_session_map(raw, "ccgram:")

        assert "@1" not in result

    def test_handles_missing_session_id(self):
        """Should skip entries without session_id."""
        raw = {
            "ccgram:@1": {
                "cwd": "/tmp/project",
                # no session_id
            }
        }
        result = parse_session_map(raw, "ccgram:")

        assert "@1" not in result

    def test_handles_non_dict_values(self):
        """Should skip entries that are not dicts."""
        raw = {
            "ccgram:@1": "not-a-dict",
        }
        result = parse_session_map(raw, "ccgram:")

        assert "@1" not in result

    def test_includes_all_fields(self):
        """Should include all relevant fields from entry."""
        raw = {
            "ccgram:@1": {
                "session_id": "sid-123",
                "cwd": "/home/project",
                "window_name": "my-window",
                "transcript_path": "/path/to/transcript",
                "provider_name": "claude",
            }
        }
        result = parse_session_map(raw, "ccgram:")

        assert result["@1"] == {
            "session_id": "sid-123",
            "cwd": "/home/project",
            "window_name": "my-window",
            "transcript_path": "/path/to/transcript",
            "provider_name": "claude",
        }

    def test_legacy_ccbot_prefix(self):
        """Should also match legacy ccbot: prefix when prefix is ccgram:."""
        raw = {
            "ccbot:@1": {
                "session_id": "sid-legacy",
                "cwd": "/tmp",
            }
        }
        result = parse_session_map(raw, "ccgram:")

        assert "@1" in result
        assert result["@1"]["session_id"] == "sid-legacy"

    def test_does_not_match_ccbot_when_prefix_not_ccgram(self):
        """Should not match ccbot: prefix when prefix is not ccgram:."""
        raw = {
            "ccbot:@1": {
                "session_id": "sid-123",
                "cwd": "/tmp",
            }
        }
        result = parse_session_map(raw, "unified-icc:")

        assert "@1" not in result


class TestParseEmdashProvider:
    """Tests for parse_emdash_provider function."""

    def test_extracts_provider_from_main_session(self):
        """Should extract provider from emdash-{provider}-main-{id} format."""
        session_name = "emdash-claude-main-12345"
        result = parse_emdash_provider(session_name)

        assert result == "claude"

    def test_extracts_provider_from_chat_session(self):
        """Should extract provider from emdash-{provider}-chat-{id} format."""
        session_name = "emdash-codex-chat-67890"
        result = parse_emdash_provider(session_name)

        assert result == "codex"

    def test_returns_empty_for_non_emdash(self):
        """Should return empty string for non-emdash session names."""
        result = parse_emdash_provider("regular-session-name")

        assert result == ""

    def test_returns_empty_for_partial_match(self):
        """Should return empty string when separator not found."""
        result = parse_emdash_provider("emdash-claude-12345")

        assert result == ""

    def test_handles_gemini_provider(self):
        """Should correctly parse gemini provider."""
        session_name = "emdash-gemini-main-session-abc"
        result = parse_emdash_provider(session_name)

        assert result == "gemini"
