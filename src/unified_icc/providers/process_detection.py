"""Foreground process detection for tmux panes via ``ps -t``.

All supported CLIs (claude, codex, gemini) are Node.js scripts — tmux's
``pane_current_command`` shows ``bun`` or ``node`` instead of the CLI name.
This module inspects the actual foreground process group on the pane's TTY
to reliably identify which provider is running.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from ..topic_state_registry import topic_state

logger = structlog.get_logger()

_WRAPPER_TOKENS = frozenset(
    {"sudo", "env", "node", "bun", "npx", "bunx", "uv", "python", "python3"}
)

_PROVIDER_BASENAMES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"claude", "ce", "cc-mirror", "zai"}), "claude"),
    (frozenset({"codex"}), "codex"),
    (frozenset({"gemini"}), "gemini"),
    (frozenset({"pi"}), "pi"),
)

_PROVIDER_PATH_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("claude-code", "cc-team"), "claude"),
    (("@openai/codex", "/codex/", "/codex-"), "codex"),
    (("gemini-cli",), "gemini"),
    (("@mariozechner/pi-coding-agent", "/pi-coding-agent/"), "pi"),
)

JS_RUNTIMES = frozenset({"node", "bun", "npx", "bunx"})

KNOWN_SHELLS = frozenset({"bash", "zsh", "sh", "fish", "dash", "ksh", "csh", "tcsh"})


def _match_token(token: str) -> str:
    basename = os.path.basename(token).lower().lstrip("-")

    for names, provider in _PROVIDER_BASENAMES:
        if basename in names or basename.startswith(f"{provider}-"):
            return provider
    if basename in KNOWN_SHELLS:
        return "shell"

    token_lower = token.lower()
    for markers, provider in _PROVIDER_PATH_MARKERS:
        if any(m in token_lower for m in markers):
            return provider

    return ""


def classify_provider_from_args(args: str) -> str:
    if not args:
        return ""

    for token in args.split():
        cleaned = os.path.basename(token).lower().lstrip("-")
        if cleaned in _WRAPPER_TOKENS:
            continue
        return _match_token(token)

    return ""


async def _run_ps(tty_path: str) -> bytes | None:
    import contextlib

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ps", "-t", tty_path, "-o", "pid=,pgid=,stat=,args=",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with asyncio.timeout(3.0):
            stdout, _ = await proc.communicate()
    except TimeoutError:
        if proc:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
                await proc.wait()
        return None
    except OSError:
        return None
    return stdout if proc.returncode == 0 else None


async def get_foreground_args(tty_path: str) -> tuple[str, int]:
    if not tty_path:
        return "", 0

    stdout = await _run_ps(tty_path)
    if not stdout:
        return "", 0

    best_args = ""
    best_pgid = 0
    for line in stdout.decode("utf-8", errors="replace").strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_s, pgid_s, stat, args = parts
        if "+" not in stat:
            continue
        try:
            pid = int(pid_s)
            pgid = int(pgid_s)
        except ValueError:
            continue
        if pid == pgid:
            return args, pgid
        if not best_args:
            best_args = args
            best_pgid = pgid

    return best_args, best_pgid


async def detect_provider_from_tty(tty_path: str) -> str:
    args, _ = await get_foreground_args(tty_path)
    return classify_provider_from_args(args)


_pgid_cache: dict[str, tuple[int, str]] = {}


async def detect_provider_cached(window_id: str, tty_path: str) -> str:
    args, pgid = await get_foreground_args(tty_path)
    if not args or pgid == 0:
        return ""

    cached = _pgid_cache.get(window_id)
    if cached and cached[0] == pgid:
        return cached[1]

    provider = classify_provider_from_args(args)
    if provider:
        _pgid_cache[window_id] = (pgid, provider)
    return provider


@topic_state.register("window")
def clear_detection_cache(window_id: str | None = None) -> None:
    if window_id is None:
        _pgid_cache.clear()
    else:
        _pgid_cache.pop(window_id, None)
