"""Expandable-quote markup contract — sentinel constants and wrap helper.

Producers (transcript_parser, codex provider, history rendering) wrap text
in these sentinels when the result should display as an expandable
blockquote.
"""

from __future__ import annotations

EXPANDABLE_QUOTE_START = "\x02EXPQUOTE_START\x02"
EXPANDABLE_QUOTE_END = "\x02EXPQUOTE_END\x02"

_EXPANDABLE_QUOTE_MAX_CHARS = 3500


def format_expandable_quote(text: str) -> str:
    """Wrap text with sentinel markers for an expandable blockquote.

    Truncates content exceeding the budget.
    """
    if len(text) > _EXPANDABLE_QUOTE_MAX_CHARS:
        text = (
            text[:_EXPANDABLE_QUOTE_MAX_CHARS]
            + f"\n\n… (truncated, {len(text)} chars total)"
        )
    return f"{EXPANDABLE_QUOTE_START}{text}{EXPANDABLE_QUOTE_END}"
