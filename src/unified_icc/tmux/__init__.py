"""Tmux management module — window operations and terminal parsing."""

from .tmux_manager import TmuxManager, TmuxWindow, tmux_manager, send_to_window
from .window_resolver import is_window_id, is_foreign_window
from .window_state_store import window_store
from .window_view import WindowView

__all__ = [
    "TmuxManager",
    "TmuxWindow",
    "tmux_manager",
    "send_to_window",
    "is_window_id",
    "is_foreign_window",
    "window_store",
    "WindowView",
]
