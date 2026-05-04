"""Frontend adapter module — bridges frontend events to unified-icc gateway."""

from .adapter import FrontendAdapter, CardPayload, InteractivePrompt
from .cc_commands import CC_BUILTINS, CCCommand, discover_cc_commands

__all__ = [
    "FrontendAdapter",
    "CardPayload",
    "InteractivePrompt",
    "CC_BUILTINS",
    "CCCommand",
    "discover_cc_commands",
]
