# Welcome to Unified ICC

**ICC** = **I**nteractive **C**oding **CLI** — a platform-agnostic gateway for managing AI coding agents (Claude Code, Codex CLI, etc.) via tmux.

Unified ICC extracts the core logic from [ccgram](https://github.com/alexei-led/ccgram) into a reusable Python library, enabling any messaging frontend (Feishu, Telegram, Discord, Slack...) to drive AI coding sessions through a clean async API.

## Key Features

- **Platform-agnostic**: No Telegram, Slack, or other messaging platform dependencies in the core library
- **Multi-provider support**: Seamlessly manage Claude Code, Codex CLI, Gemini CLI, Pi, and Shell sessions
- **Async-first**: Full async/await API for modern Python applications
- **Event-driven**: Subscribe to messages, status changes, window events, and hooks
- **State persistence**: Debounced JSON persistence with crash recovery

## Documentation Sections

```{toctree}
:maxdepth: 2
:caption: Contents

getting-started/index
getting-started/installation
getting-started/first-steps
architecture/index
architecture
providers/index
api-reference/index
api-reference/gateway
api-reference/adapter
api-reference/events
api-reference/channel-router
api-reference/call-stacks
events/index
configuration
troubleshooting
contributing
```

## Quick Example

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    # Create gateway
    gateway = UnifiedICC()
    await gateway.start()

    # Create a new Claude Code window
    window = await gateway.create_window("/path/to/project")

    # Bind a messaging channel to the window
    gateway.bind_channel("feishu:chat_123:thread_456", window.window_id)

    # Subscribe to agent messages
    def on_message(event):
        print(f"Agent: {event.messages[-1].text}")

    gateway.on_message(on_message)

    # Send input to the agent
    await gateway.send_to_window(window.window_id, "Hello, help me with this project")

    await gateway.stop()

asyncio.run(main())
```

## Related Projects

| Project | Description |
|---------|-------------|
| [cclark](https://github.com/Agony5757/cclark) | Feishu frontend consuming unified-icc |
| [ccgram](https://github.com/alexei-led/ccgram) | Original Telegram frontend (upstream reference) |

## Indices and Tables

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
