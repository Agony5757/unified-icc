"""Shared utility functions used across unified_icc modules.

Platform-agnostic utilities only — no messaging platform dependencies.
"""

import asyncio
import contextlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# --- Log throttling -----------------------------------------------------------

_throttle_state: dict[str, tuple[float, str]] = {}


def log_throttled(
    log: Any,
    key: str,
    msg: str,
    *args: object,
    cooldown: float = 300.0,
    _clock: Callable[[], float] = time.monotonic,
) -> None:
    """Log at debug level, suppressing repeated identical messages per key."""
    formatted = msg % args if args else msg
    now = _clock()
    prev = _throttle_state.get(key)
    if prev and prev[1] == formatted and (now - prev[0]) < cooldown:
        return
    _throttle_state[key] = (now, formatted)
    log.debug(msg, *args)


def log_throttle_reset(prefix: str) -> None:
    to_remove = [k for k in _throttle_state if k.startswith(prefix)]
    for k in to_remove:
        del _throttle_state[k]


def log_throttle_sweep(
    max_age: float = 600.0,
    _clock: Callable[[], float] = time.monotonic,
) -> int:
    """Remove throttle entries older than *max_age* seconds."""
    now = _clock()
    stale = [k for k, (ts, _) in _throttle_state.items() if now - ts >= max_age]
    for k in stale:
        del _throttle_state[k]
    return len(stale)


# --- Config directory ---------------------------------------------------------

UNIFIED_ICC_DIR_ENV = "UNIFIED_ICC_DIR"

_SCAN_LINES = 20
_SUMMARY_MAX_CHARS = 80


def unified_icc_dir() -> Path:
    """Resolve config directory from env vars or default ~/.unified-icc.
    """
    raw = os.environ.get(UNIFIED_ICC_DIR_ENV, "")
    if raw:
        return Path(raw).expanduser()

    return Path.home() / ".unified-icc"


def tmux_session_name() -> str:
    """Get tmux session name from TMUX_SESSION_NAME env var or default 'cclark'."""
    return os.environ.get("TMUX_SESSION_NAME", "unified-icc")


# --- JSON utilities -----------------------------------------------------------


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON data to a file atomically via temp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=indent)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=f".{path.name}."
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


# --- JSONL utilities ----------------------------------------------------------


def read_cwd_from_jsonl(file_path: str | Path) -> str:
    """Read the cwd field from the first JSONL entry that has one."""
    cwd, _ = read_session_metadata_from_jsonl(file_path)
    return cwd


def _extract_user_text(msg: dict[str, object]) -> str:
    content = msg.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    return text[:_SUMMARY_MAX_CHARS]
    elif isinstance(content, str) and content:
        return content[:_SUMMARY_MAX_CHARS]
    return ""


def _extract_metadata_from_entry(data: dict, cwd: str, summary: str) -> tuple[str, str]:
    if not cwd:
        found_cwd = data.get("cwd")
        if found_cwd and isinstance(found_cwd, str):
            cwd = found_cwd
    if not summary and data.get("type") == "user":
        msg = data.get("message", {})
        if isinstance(msg, dict):
            summary = _extract_user_text(msg)
    return cwd, summary


def read_session_metadata_from_jsonl(file_path: str | Path) -> tuple[str, str]:
    """Extract cwd and summary from a JSONL transcript in a single file read."""
    cwd = ""
    summary = ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                cwd, summary = _extract_metadata_from_entry(data, cwd, summary)
                if cwd and summary:
                    break
    except OSError:
        pass
    return cwd, summary


# --- tmux context detection ---------------------------------------------------


def detect_tmux_context() -> tuple[str | None, str | None]:
    """Detect tmux session name and own window ID in a single tmux call."""
    if not os.environ.get("TMUX"):
        return None, None
    pane_id = os.environ.get("TMUX_PANE")
    if not pane_id:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None, None
            name = result.stdout.strip()
            return (name or None), None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None, None
    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-t",
                pane_id,
                "-p",
                "#{session_name}\t#{window_id}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None, None
        parts = result.stdout.strip().split("\t", 1)
        session_name = parts[0] if parts[0] else None
        window_id = parts[1] if len(parts) > 1 and parts[1] else None
        return session_name, window_id
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, None


def check_duplicate_instance(session_name: str, instance_name: str = "unified_icc") -> str | None:
    """Check if another instance is running in the session."""
    own_pane = os.environ.get("TMUX_PANE", "")
    if not own_pane:
        return None
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-s",
                "-t",
                session_name,
                "-F",
                "#{pane_id}\t#{window_id}\t#{pane_current_command}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        pane_id, window_id, cmd = parts
        if pane_id == own_pane:
            continue
        if cmd.strip() == instance_name:
            return (
                f"Another {instance_name} instance is already running in "
                f"tmux session '{session_name}' (window {window_id})"
            )
    return None


# --- Path utilities -----------------------------------------------------------


def shorten_path(full_path: str, cwd: str | None) -> str:
    """Return path relative to cwd if it's a subpath, else return as-is."""
    if not cwd or not full_path:
        return full_path
    cwd = cwd.rstrip("/")
    if full_path.startswith(cwd + "/"):
        return os.path.relpath(full_path, cwd)
    return full_path


def task_done_callback(task: asyncio.Task[None]) -> None:
    """Log unhandled exceptions from background asyncio tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background task %s failed", task.get_name(), exc_info=exc)
