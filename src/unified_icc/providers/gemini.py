"""Gemini CLI provider — whole-file JSON with resume support."""

from __future__ import annotations

from typing import Any

from unified_icc.providers._jsonl import JsonlProvider
from unified_icc.providers.base import ProviderCapabilities

_GEMINI_BUILTINS: dict[str, str] = {
    "clear": "Clear conversation",
    "help": "Show help",
    "resume": "Resume a session",
}


class GeminiProvider(JsonlProvider):
    _CAPS = ProviderCapabilities(
        name="gemini",
        launch_command="gemini",
        supports_resume=True,
        supports_structured_transcript=True,
        supports_incremental_read=False,
        transcript_format="jsonl",
        uses_pane_title=True,
        builtin_commands=tuple(_GEMINI_BUILTINS.keys()),
    )
    _BUILTINS = _GEMINI_BUILTINS
