:orphan:

# Getting Started

## Installation

### Using uv (Recommended)

```bash
uv pip install unified-icc
```

Or add to your project:

```bash
uv add unified-icc
```

### From Source

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv pip install -e .
```

### Development Installation

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv sync
uv pip install -e ".[dev]"
```

## Requirements

- Python 3.12 or higher
- tmux 2.6 or higher
- A supported agent CLI (Claude Code, Codex CLI, Gemini CLI, etc.)

## Quick Start

### 1. Create a Gateway Instance

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    # Your code here...

    await gateway.stop()

asyncio.run(main())
```

### 2. Create a Window with an Agent

```python
window = await gateway.create_window(
    work_dir="/path/to/project",
    provider="claude",  # or "codex", "gemini", "pi", "shell"
)
print(f"Created window: {window.window_id}")
```

### 3. Bind a Messaging Channel

```python
gateway.bind_channel(
    channel_id="feishu:chat_123:thread_456",
    window_id=window.window_id,
)
```

### 4. Subscribe to Events

```python
def handle_message(event):
    for msg in event.messages:
        print(f"[{msg.role}] {msg.text}")

gateway.on_message(handle_message)
```

### 5. Send Input to the Agent

```python
await gateway.send_to_window(window.window_id, "Hello!")
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UNIFIED_ICC_DIR` | `~/.unified-icc` | Configuration directory |
| `TMUX_SESSION_NAME` | `cclark` | tmux session name |
| `CCLARK_PROVIDER` | `claude` | Default agent provider |
| `MONITOR_POLL_INTERVAL` | `1.0` | Poll interval in seconds |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | Claude config directory |

## Next Steps

- Read the [Architecture Overview](../architecture.rst) for a deeper understanding
- Explore the [API Reference](../api-reference/index.rst) for all available methods
- Learn about [Providers](../providers/index.rst) and how they work
- Check [Configuration](../configuration.rst) for all options
