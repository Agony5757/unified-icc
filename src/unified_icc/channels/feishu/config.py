"""Feishu channel configuration and channel ID helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeishuAppConfig:
    """Configuration for a single Feishu app/bot."""

    name: str
    app_id: str
    app_secret: str
    allowed_users: set[str] | None = None  # None = allow all
    tmux_session: str = "unified-icc"  # tmux session for this bot's windows

    @classmethod
    def from_dict(cls, data: dict) -> "FeishuAppConfig":
        """Parse from a dict (e.g., loaded from YAML)."""
        allowed_raw = data.get("allowed_users", "all")
        if isinstance(allowed_raw, str):
            allowed_users: set[str] | None = None if allowed_raw == "all" else set(
                u.strip() for u in allowed_raw.split(",") if u.strip()
            )
        elif isinstance(allowed_raw, list):
            allowed_users = set(allowed_raw)
        else:
            allowed_users = None

        return cls(
            name=data.get("name", "default"),
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
            allowed_users=allowed_users,
            tmux_session=data.get("tmux_session", "unified-icc"),
        )


def build_feishu_channel_id(
    app_name: str, chat_id: str, thread_id: str = ""
) -> str:
    """Build a channel ID for Feishu.

    Format: feishu:{app_name}:{chat_id}[:{thread_id}]
    """
    if thread_id:
        return f"feishu:{app_name}:{chat_id}:{thread_id}"
    return f"feishu:{app_name}:{chat_id}"


def split_feishu_channel_id(channel_id: str) -> tuple[str, str, str]:
    """Split a Feishu channel ID into (app_name, chat_id, thread_id).

    Format: feishu:{app_name}:{chat_id}[:{thread_id}]
    """
    parts = channel_id.split(":", 3)
    if len(parts) < 3:
        # Legacy single-app format: feishu:chat_id[:thread_id]
        if len(parts) == 2:
            return ("default", parts[1], "")
        return ("default", parts[1], parts[2] if len(parts) > 2 else "")

    # feishu:{app_name}:{chat_id}[:{thread_id}]
    app_name = parts[1]
    chat_id = parts[2]
    thread_id = parts[3] if len(parts) > 3 else ""
    return (app_name, chat_id, thread_id)


def is_feishu_channel_id(channel_id: str) -> bool:
    """Check if a channel ID is a Feishu channel."""
    return channel_id.startswith("feishu:")
