"""Unified ICC — platform-agnostic gateway for managing AI coding agents via tmux."""

from unified_icc.gateway import UnifiedICC, WindowInfo
from unified_icc.adapter import FrontendAdapter, CardPayload, InteractivePrompt
from unified_icc.event_types import AgentMessageEvent, StatusEvent, HookEvent, WindowChangeEvent
from unified_icc.config import GatewayConfig, config

__all__ = [
    "UnifiedICC",
    "WindowInfo",
    "FrontendAdapter",
    "CardPayload",
    "InteractivePrompt",
    "AgentMessageEvent",
    "StatusEvent",
    "HookEvent",
    "WindowChangeEvent",
    "GatewayConfig",
    "config",
]
