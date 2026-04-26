# Unified ICC

**ICC** = **I**nteractive **C**oding **CLI** — a platform-agnostic gateway for managing AI coding agents (Claude Code, Codex CLI, Gemini CLI, Pi, etc.) via tmux.

[![CI](https://github.com/Agony5757/unified-icc/actions/workflows/ci.yml/badge.svg)](https://github.com/Agony5757/unified-icc/actions)
[![PyPI version](https://badge.fury.io/py/unified-icc.svg)](https://badge.fury.io/py/unified-icc)

Unified ICC extracts the core logic from [ccgram](https://github.com/alexei-led/ccgram) into a reusable Python library, enabling any messaging frontend (Feishu, Telegram, Discord, Slack...) to drive AI coding sessions through a clean async API.

## Key Features

- **Platform-agnostic**: No messaging platform dependencies in the core library
- **Multi-provider support**: Seamlessly manage Claude Code, Codex CLI, Gemini CLI, Pi, and Shell sessions
- **Async-first**: Full async/await API for modern Python applications
- **Event-driven**: Subscribe to messages, status changes, window events, and hooks
- **State persistence**: Debounced JSON persistence with crash recovery

## Installation

```bash
uv pip install unified-icc
```

Or from source:

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv pip install -e .
```

## Quick Start

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    # Create a new Claude Code window
    window = await gateway.create_window("/path/to/project", provider="claude")

    # Bind a messaging channel
    gateway.bind_channel("feishu:chat_123:thread_456", window.window_id)

    # Subscribe to agent messages
    def on_message(event):
        for msg in event.messages:
            print(f"Agent: {msg.text}")

    gateway.on_message(on_message)

    # Send input to the agent
    await gateway.send_to_window(window.window_id, "Hello!")

    await gateway.stop()

asyncio.run(main())
```

## Documentation

| Section | Description |
|---------|-------------|
| [Getting Started](https://unified-icc.readthedocs.io/) | Installation, quick start, first steps |
| [Architecture](https://unified-icc.readthedocs.io/architecture.html) | System design, components, data flow |
| [API Reference](https://unified-icc.readthedocs.io/api-reference/index.html) | Complete API documentation |
| [Providers](https://unified-icc.readthedocs.io/providers/index.html) | Agent provider support |
| [Events](https://unified-icc.readthedocs.io/events/index.html) | Event system and handlers |
| [Configuration](https://unified-icc.readthedocs.io/configuration.html) | Environment variables and config |
| [Troubleshooting](https://unified-icc.readthedocs.io/troubleshooting.html) | Common issues and solutions |
| [Contributing](https://unified-icc.readthedocs.io/contributing.html) | Development guide |

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│  cclark     │  │  ccgram     │  │  future      │
│  (Feishu)   │  │  (Telegram) │  │  (Discord)   │
└──────┬──────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │
       │   FrontendAdapter API             │
       └────────────┬────┴────────────────┘
                    │
       ┌────────────┴────────────┐
       │    unified_icc          │
       │  ┌──────────────────┐   │
       │  │ UnifiedICC       │   │
       │  │ ChannelRouter    │   │
       │  │ SessionMonitor   │   │
       │  │ TmuxManager      │   │
       │  │ ProviderRegistry │   │
       │  └──────────────────┘   │
       └────────────┬────────────┘
                    │
       ┌────────────┴────────────┐
       │     tmux session        │
       │  ┌───┐ ┌───┐ ┌───┐     │
       │  │@0 │ │@1 │ │@2 │ ... │
       │  │CC │ │CX │ │GM │     │
       │  └───┘ └───┘ └───┘     │
       └─────────────────────────┘
```

## Supported Providers

| Provider | Launch Command | Features |
|----------|---------------|----------|
| Claude Code | `claude` | Hook events, JSONL transcript, resume, /continue |
| Codex CLI | `codex` | Plain text transcript, yolo mode |
| Gemini CLI | `gemini` | JSONL transcript, yolo mode |
| Pi | `pi` | JSONL transcript |
| Shell | interactive shell | Basic terminal support |

## Configuration

Configure via environment variables:

```bash
# Core settings
CCLARK_CONFIG_DIR=~/.cclark
CCLARK_PROVIDER=claude

# Tmux
TMUX_SESSION_NAME=cclark

# Monitoring
MONITOR_POLL_INTERVAL=1.0
```

See the [Configuration Reference](https://unified-icc.readthedocs.io/configuration.html) for all options.

## Design Documents

| Document | Description |
|---|---|
| [dev-design.md](dev-design.md) | Main design document — project overview, ccgram analysis, gateway architecture |
| [design/module-gateway-core.md](design/module-gateway-core.md) | UnifiedICC gateway internals |
| [design/module-adapter-layer.md](design/module-adapter-layer.md) | Frontend adapter abstraction |
| [design/module-feishu-frontend.md](design/module-feishu-frontend.md) | Feishu-specific implementation |
| [design/module-card-renderer.md](design/module-card-renderer.md) | Card rendering + verbose mode |
| [design/module-mvp.md](design/module-mvp.md) | MVP implementation plan |

## Related Projects

| Project | Repo | Description |
|---|---|---|
| **cclark** | [Agony5757/cclark](https://github.com/Agony5757/cclark) | Feishu frontend consuming unified-icc |
| **ccgram** | [alexei-led/ccgram](https://github.com/alexei-led/ccgram) | Original Telegram frontend (upstream reference) |

## What ICC Stands For

**ICC = Interactive Coding CLI** — the class of tools that run as interactive terminal sessions:

- **Claude Code** — Anthropic's AI coding agent CLI
- **Codex CLI** — OpenAI's coding agent CLI
- **Future agents** — any new CLI that follows the tmux-compatible interactive pattern

Unified ICC treats each CLI as a "provider" with a standardized protocol (`AgentProvider`), so the gateway can manage them uniformly regardless of their specific transcript format, hook system, or resume capabilities.

## License

MIT
