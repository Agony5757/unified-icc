"""Unified ICC — platform-agnostic gateway for managing AI coding agents via tmux."""

__version__ = "0.1.0"

from unified_icc.core import UnifiedICC, WindowInfo
from unified_icc.core import channel_router, session_manager
from unified_icc.adapter import FrontendAdapter, CardPayload, InteractivePrompt
from unified_icc.events import AgentMessageEvent, StatusEvent, HookEvent, WindowChangeEvent
from unified_icc.utils import GatewayConfig, config, IdleTracker
from unified_icc.state import StatePersistence
from unified_icc.tmux import window_store
from unified_icc.utils import user_preferences
from unified_icc.tmux import TmuxWindow, tmux_manager

__all__ = [
    "UnifiedICC",
    "WindowInfo",
    "channel_router",
    "session_manager",
    "FrontendAdapter",
    "CardPayload",
    "InteractivePrompt",
    "AgentMessageEvent",
    "StatusEvent",
    "HookEvent",
    "WindowChangeEvent",
    "GatewayConfig",
    "config",
    "IdleTracker",
    "StatePersistence",
    "window_store",
    "user_preferences",
    "TmuxWindow",
    "tmux_manager",
]
