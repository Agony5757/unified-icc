:orphan:

# First Steps

This guide walks you through building a simple messaging frontend adapter.

## Building a Custom Frontend Adapter

### Step 1: Implement the FrontendAdapter Protocol

```python
from unified_icc import FrontendAdapter, CardPayload, InteractivePrompt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from your_messaging_sdk import MessagingClient

class MyPlatformAdapter(FrontendAdapter):
    def __init__(self, client: "MessagingClient"):
        self.client = client

    async def send_text(self, channel_id: str, text: str) -> str:
        return await self.client.send_message(channel_id, text)

    async def send_card(self, channel_id: str, card: CardPayload) -> str:
        formatted = self._format_card(card)
        return await self.client.send_card(channel_id, formatted)

    async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
        formatted = self._format_card(card)
        await self.client.update_message(channel_id, card_id, formatted)

    async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
        return await self.client.upload_image(channel_id, image_bytes, caption)

    async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
        return await self.client.upload_file(channel_id, file_path, caption)

    async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
        buttons = [opt["text"] for opt in prompt.options]
        return await self.client.send_buttons(channel_id, prompt.title, buttons)

    def _format_card(self, card: CardPayload) -> dict:
        # Convert CardPayload to your platform's card format
        return {
            "title": card.title,
            "body": card.body,
            "fields": card.fields,
            "actions": card.actions,
            "color": card.color,
        }
```

### Step 2: Wire Up the Event Handlers

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    adapter = MyPlatformAdapter(messaging_client)

    # Route agent messages to the frontend
    def on_agent_message(event):
        # event.messages contains parsed AgentMessage objects
        for msg in event.messages:
            if msg.role == "assistant":
                # Send as a card for rich formatting
                card = CardPayload(
                    title="Claude",
                    body=msg.text,
                    color="#007AFF"
                )
                for channel_id in event.channel_ids:
                    asyncio.create_task(adapter.send_card(channel_id, card))

    gateway.on_message(on_agent_message)

    # Route status changes
    def on_status_change(event):
        status_text = f"Status: {event.status}"
        for channel_id in event.channel_ids:
            asyncio.create_task(adapter.send_text(channel_id, status_text))

    gateway.on_status(on_status_change)

    # Route window events
    def on_window_event(event):
        text = f"New window: {event.display_name}"
        # Broadcast to all bound channels or specific ones
        asyncio.create_task(adapter.send_text("admin_channel", text))

    gateway.on_window_change(on_window_event)

    # Keep running
    await asyncio.Event().wait()

asyncio.run(main())
```

### Step 3: Handle Incoming Messages

```python
async def handle_incoming_message(channel_id: str, text: str):
    # Resolve the window for this channel
    window_id = gateway.resolve_window(channel_id)
    if not window_id:
        await adapter.send_text(channel_id, "No active session for this channel")
        return

    # Send to the agent
    await gateway.send_to_window(window_id, text)

# In your webhook handler:
async def webhook_handler(request):
    payload = await request.json()
    channel_id = payload["channel_id"]
    text = payload["text"]
    await handle_incoming_message(channel_id, text)
    return {"status": "ok"}
```

### Step 4: Run Your Application

```python
# Run both the gateway and your web server
async def run():
    gateway = UnifiedICC()
    await gateway.start()

    # Start your web server in the background
    server = MyWebServer(webhook_handler)
    await server.start()

    try:
        await asyncio.Event().wait()
    finally:
        await gateway.stop()

asyncio.run(run())
```

## Complete Example: Simple CLI Frontend

```python
"""Simple CLI frontend that reads from stdin and writes to stdout."""
import asyncio
import sys
from unified_icc import UnifiedICC, CardPayload

async def cli_frontend():
    gateway = UnifiedICC()
    await gateway.start()

    # Create a window for the CLI interaction
    window = await gateway.create_window("/tmp", provider="claude")
    gateway.bind_channel("cli:stdin", window.window_id)

    def on_message(event):
        for msg in event.messages:
            if msg.text:
                print(f"\n[Agent] {msg.text}\n> ", end="", flush=True)

    gateway.on_message(on_message)

    # Read from stdin
    async def read_stdin():
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            await gateway.send_to_window(window.window_id, line.rstrip())

    await asyncio.gather(read_stdin())

if __name__ == "__main__":
    asyncio.run(cli_frontend())
```

## Next Steps

- Review the [API Reference](../api-reference/index.rst) for all available methods
- See the [Providers](../providers/index.rst) documentation for provider-specific details
- Check [Configuration](../configuration.rst) for environment variables
