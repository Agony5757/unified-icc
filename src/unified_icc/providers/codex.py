"""Codex CLI provider — JSONL-based with resume support."""

from __future__ import annotations


from unified_icc.providers._jsonl import JsonlProvider
from unified_icc.providers.base import ProviderCapabilities

_CODEX_BUILTINS: dict[str, str] = {
    "clear": "Clear conversation",
    "help": "Show help",
    "history": "Show conversation history",
    "resume": "Resume a session",
}


class CodexProvider(JsonlProvider):
    _CAPS = ProviderCapabilities(
        name="codex",
        launch_command="codex",
        supports_resume=True,
        supports_structured_transcript=True,
        supports_incremental_read=True,
        transcript_format="jsonl",
        builtin_commands=tuple(_CODEX_BUILTINS.keys()),
    )
    _BUILTINS = _CODEX_BUILTINS
