"""Frontend adapter protocol — defines the interface each platform must implement.

Each messaging platform (Feishu, Telegram, Discord) provides an adapter
that implements this protocol to handle outbound communication from the gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class CardPayload:
    """Platform-agnostic card/message payload."""

    title: str = ""
    body: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    actions: list[dict[str, str]] = field(default_factory=list)
    color: str = ""


@dataclass
class InteractivePrompt:
    """A prompt requiring user interaction."""

    prompt_type: str  # "question", "permission", "selection"
    title: str
    options: list[dict[str, str]] = field(default_factory=list)
    cancel_text: str = "Cancel"


@runtime_checkable
class FrontendAdapter(Protocol):
    """Protocol that each messaging platform adapter must implement."""

    # Outbound: Gateway → Platform
    async def send_text(self, channel_id: str, text: str) -> str:
        """Send plain text. Returns platform message_id."""
        ...

    async def send_card(self, channel_id: str, card: CardPayload) -> str:
        """Send a rich card. Returns platform message_id."""
        ...

    async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
        """Update an existing card in-place."""
        ...

    async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
        """Send an image. Returns platform message_id."""
        ...

    async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
        """Send a file attachment. Returns platform message_id."""
        ...

    async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
        """Show an interactive prompt (buttons, selections). Returns message_id."""
        ...
