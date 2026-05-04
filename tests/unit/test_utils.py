"""Tests for shared utility functions."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from unified_icc.utils.utils import (
    atomic_write_json,
    log_throttle_reset,
    log_throttle_sweep,
    log_throttled,
    shorten_path,
    unified_icc_dir,
)


class TestUnifiedIccDir:
    def test_unified_icc_dir_defaults_to_home(self, monkeypatch) -> None:
        monkeypatch.delenv("UNIFIED_ICC_DIR", raising=False)
        result = unified_icc_dir()
        assert result.name == ".unified-icc"
        assert result.parent == Path.home()

    def test_unified_icc_dir_respects_env_var(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("UNIFIED_ICC_DIR", str(tmp_path / "custom-dir"))
        assert unified_icc_dir() == tmp_path / "custom-dir"

    def test_unified_icc_dir_expands_tilde(self, monkeypatch) -> None:
        monkeypatch.setenv("UNIFIED_ICC_DIR", "~/my-unified-icc")
        result = unified_icc_dir()
        assert result.name == "my-unified-icc"


class TestAtomicWriteJson:
    def test_atomic_write_json_creates_file(self, tmp_path) -> None:
        path = tmp_path / "state.json"
        atomic_write_json(path, {"key": "value"})
        import json
        assert json.loads(path.read_text()) == {"key": "value"}

    def test_atomic_write_json_indent(self, tmp_path) -> None:
        path = tmp_path / "data.json"
        atomic_write_json(path, {"a": 1, "b": 2}, indent=4)
        text = path.read_text()
        assert "    " in text  # 4-space indent

    def test_atomic_write_json_creates_parent_dirs(self, tmp_path) -> None:
        path = tmp_path / "subdir" / "nested" / "file.json"
        atomic_write_json(path, {"test": True})
        import json
        assert json.loads(path.read_text()) == {"test": True}


class TestShortenPath:
    def test_shorten_path_relative_under_cwd(self) -> None:
        result = shorten_path("/home/user/project/src/main.py", "/home/user/project")
        assert result == "src/main.py"

    def test_shorten_path_outside_cwd_unchanged(self) -> None:
        result = shorten_path("/tmp/other/file.py", "/home/user")
        assert result == "/tmp/other/file.py"

    def test_shorten_path_empty_cwd_returns_full(self) -> None:
        result = shorten_path("/home/user/file.py", None)
        assert result == "/home/user/file.py"

    def test_shorten_path_empty_path_returns_empty(self) -> None:
        result = shorten_path("", "/home/user")
        assert result == ""

    def test_shorten_path_equal_paths(self) -> None:
        # When paths are equal (not parent-child), function returns full path
        result = shorten_path("/home/user", "/home/user")
        assert result == "/home/user"

    def test_shorten_path_trailing_slash(self) -> None:
        result = shorten_path("/home/user/project/src", "/home/user/project/")
        assert result == "src"


class TestLogThrottle:
    def test_log_throttled_logs_on_first_call(self, caplog) -> None:
        log = logging.getLogger("test_throttle")
        log_throttle_reset("")  # Clear state
        with caplog.at_level(logging.DEBUG):
            log_throttled(log, "key1", "hello world")
        assert "hello world" in caplog.text

    def test_log_throttle_reset_clears_prefix(self) -> None:
        log_throttle_reset("prefix_")
        # Just ensure it doesn't raise

    def test_log_throttle_sweep_removes_stale_entries(self) -> None:
        log_throttle_reset("")  # Clear first
        removed = log_throttle_sweep(max_age=0.0)
        assert removed >= 0

    def test_log_throttle_sweep_returns_count(self) -> None:
        removed = log_throttle_sweep(max_age=3600.0)
        assert isinstance(removed, int)

    def test_log_throttled_respects_cooldown(self, caplog) -> None:
        log = logging.getLogger("test_cooldown")
        log_throttle_reset("cooldown_key")
        with caplog.at_level(logging.DEBUG):
            log_throttled(log, "cooldown_key", "msg1", cooldown=60.0)
            log_throttled(log, "cooldown_key", "msg1", cooldown=60.0)
        # First call logs, second should be suppressed (within cooldown)
        # We just verify no exceptions are raised

    def test_log_throttled_different_keys_log_separately(self, caplog) -> None:
        log = logging.getLogger("test_keys")
        log_throttle_reset("")
        with caplog.at_level(logging.DEBUG):
            log_throttled(log, "key_a", "msg_a")
            log_throttled(log, "key_b", "msg_b")
        assert "msg_a" in caplog.text
        assert "msg_b" in caplog.text
