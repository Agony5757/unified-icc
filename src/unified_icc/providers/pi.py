"""Pi CLI provider — JSONL-based with resume support."""

from __future__ import annotations


from unified_icc.providers._jsonl import JsonlProvider
from unified_icc.providers.base import ProviderCapabilities

_PI_BUILTINS: dict[str, str] = {
    "clear": "Clear conversation",
    "help": "Show help",
    "resume": "Resume a session",
}


class PiProvider(JsonlProvider):
    _CAPS = ProviderCapabilities(
        name="pi",
        launch_command="pi",
        supports_resume=True,
        supports_continue=True,
        supports_structured_transcript=True,
        supports_incremental_read=True,
        transcript_format="jsonl",
        builtin_commands=tuple(_PI_BUILTINS.keys()),
    )
    _BUILTINS = _PI_BUILTINS
