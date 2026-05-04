# Unified ICC

**ICC** = **I**nteractive **C**oding **CLI** — a platform-agnostic gateway library that manages AI programming assistant sessions (Claude Code, Codex CLI, Gemini CLI, Pi, Shell) over tmux.

Unified ICC extracts the core logic of [ccgram](https://github.com/alexei-led/ccgram) into a reusable Python library, so any messaging frontend (Feishu, Telegram, Discord, Slack…) can drive AI coding sessions through a clean async API.

[![CI](https://github.com/Agony5757/unified-icc/actions/workflows/ci.yml/badge.svg)](https://github.com/Agony5757/unified-icc/actions)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [API Server](#api-server)
- [Module Reference](#module-reference)
- [FrontendAdapter Protocol](#frontendadapter-protocol)
- [Event Types](#event-types)
- [Provider System](#provider-system)
- [State & Persistence](#state--persistence)
- [CLI Commands](#cli-commands)
- [Configuration](#configuration)
- [Design Documents](#design-documents)
- [Related Projects](#related-projects)

---

## Overview

```
Feishu (cclark)  →  unified-icc gateway  →  tmux  →  AI agent (Claude/Codex/Gemini/Pi/Shell)
Telegram (ccgram)→  unified-icc gateway  →  tmux  →  AI agent
HTTP/WS client   →  unified-icc API server  →  tmux  →  AI agent
...any frontend  →  unified-icc gateway  →  tmux  →  AI agent
```

The gateway (`UnifiedICC`) owns tmux windows and routes messages between channel IDs (frontend-specific) and window IDs (tmux-specific). It monitors transcript files, emits typed events to frontends, and handles the full session lifecycle.

**Core design principles:**
- **Platform-agnostic core** — no messaging-platform imports in unified-icc
- **Async-first** — full async/await API
- **1 channel : 1 tmux window** — enforced by `ChannelRouter.kill_channel_windows`
- **Crash recovery** — state persisted to JSON; restored on restart
- **Capability-gated UX** — frontends only offer features the active provider supports

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (cclark)                        │
│                                                                  │
│   ws_client.py        handlers/           adapter.py            │
│   WS events ─────────► classify ──────────► gateway.send_*()   │
│                       #command vs. forward                       │
│                                                                  │
│   adapter.py ◄────────────────── gateway.on_message() callbacks  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  FrontendAdapter calls (async)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      UnifiedICC Gateway                           │
│                                                                   │
│  gateway.py          channel_router.py    session_monitor.py      │
│  UnifiedICC ───────► ChannelRouter ────► SessionMonitor        │
│  (public API)       (binding map)         (1s poll loop)        │
│                        ↕ persist             ↓                    │
│                     state.json          event_types.py            │
│                                        AgentMessageEvent         │
│                                        StatusEvent               │
│                                        HookEvent                 │
│                                        WindowChangeEvent         │
│                                                                   │
│  tmux_manager.py        session_lifecycle.py   providers/       │
│  TmuxManager ◄────────── SessionLifecycle ◄───── ProviderRegistry│
│  (libtmux wrap)         (session-map diff)      claude.py        │
│                                                   codex.py       │
│                                                   gemini.py       │
│                                                   pi.py           │
│                                                   shell.py        │
└───────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                        tmux session                               │
│                                                                   │
│  @0 (claude)     @1 (codex)     @2 (gemini)     @3 (pi)         │
│  transcript.json  stdout.txt    transcript.json  transcript.json │
│  events.jsonl      (plain)         (JSONL)         (JSONL)        │
└───────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File | Role |
|-----------|------|------|
| **Gateway** | `gateway.py` | Public API: `create_window`, `bind_channel`, `send_to_window`, `start`, `stop` |
| **ChannelRouter** | `channel_router.py` | Bidirectional channel↔window binding map; enforces 1:1 |
| **SessionMonitor** | `session_monitor.py` | 1s poll loop reading hook events + transcripts, dispatching events |
| **TmuxManager** | `tmux_manager.py` | Async libtmux wrapper: create/kill windows, send keys, capture pane |
| **SessionLifecycle** | `session_lifecycle.py` | Detects session_map changes; authority for `claude_task_state` mutations |
| **EventReader** | `event_reader.py` | Incremental byte-offset reading of `events.jsonl` |
| **TranscriptReader** | `transcript_reader.py` | Reads and parses transcript files per provider format |
| **WindowStateStore** | `window_state_store.py` | Tracks cclark-created windows for orphan detection |
| **StatePersistence** | `state_persistence.py` | Persists/restores `state.json` (bindings, display names) |
| **SessionMap** | `session_map.py` | Reads Claude hook-written `session_map.json` |
| **Providers** | `providers/` | ProviderRegistry + per-provider startup commands, transcript parsing, capability flags |
| **FrontendAdapter** | `adapter.py` | Protocol definition; unified-icc is frontend-agnostic |
| **API Server** | `server/` | FastAPI HTTP/WebSocket server exposing the gateway as an API |

---

## Quick Start

### Installation

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv sync --extra dev
```

### Programmatic usage

```python
import asyncio
from unified_icc import UnifiedICC
from unified_icc.adapter import CardPayload, Button

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    # Create a Claude Code window in /tmp/project
    window = await gateway.create_window(
        "/tmp/project",
        provider="claude",
        mode="standard",      # "standard" = --permission-mode default
        # mode="yolo"         # "yolo" = --dangerously-skip-permissions
    )

    # Bind a Feishu chat to this window
    gateway.bind_channel("feishu:oc_chat123:om_thread456", window.window_id)

    # Receive agent output
    def on_message(event):
        for msg in event.messages:
            print(f"[{msg.content_type}] {msg.text}")

    gateway.on_message(on_message)

    # Send user input
    await gateway.send_to_window(window.window_id, "Hello, explain this codebase")

    await asyncio.sleep(60)
    await gateway.stop()

asyncio.run(main())
```

### Gateway API Cheatsheet

```python
# Windows
window = await gateway.create_window(cwd, provider, mode)  # → WindowInfo
await gateway.destroy_window(window.window_id)
await gateway.send_to_window(window_id, text, enter=True)  # enter=False for plan mode step 2

# Channels
gateway.bind_channel(channel_id, window_id)
gateway.unbind_channel(channel_id)
gateway.kill_channel_windows(channel_id)   # Enforce 1-channel:1-window

# Events
gateway.on_message(callback)    # AgentMessageEvent
gateway.on_status(callback)     # StatusEvent
gateway.on_hook(callback)        # HookEvent
gateway.on_window_change(callback)  # WindowChangeEvent

# Introspection
gateway.list_windows()          # → list[WindowInfo]
gateway.get_channel(channel_id) # → window_id or None
gateway.list_orphaned_agent_windows()  # Live tmux windows not in state
```

---

## API Server

Unified ICC can run as a standalone HTTP/WebSocket server, exposing AI agents via a REST + WebSocket API. This allows any HTTP client (curl, SDK, web UI, custom scripts) to create and interact with agent sessions without a messaging frontend.

### Installation

```bash
uv sync --extra server
```

### Starting the Server

```bash
# Foreground
unified-icc server start --port 8900

# Background (detached)
unified-icc server start --port 8900 --detach

# Check status
unified-icc server status

# Stop
unified-icc server stop
```

### REST Endpoints

All endpoints are prefixed with `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create agent session. Body: `{work_dir, provider, mode}` |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/sessions/{channel_id}` | Get session status |
| `DELETE` | `/sessions/{channel_id}` | Close session |
| `POST` | `/sessions/{channel_id}/input` | Send text input. Body: `{text, enter?, literal?, raw?}` |
| `POST` | `/sessions/{channel_id}/key` | Send special key. Body: `{key}` |
| `GET` | `/sessions/{channel_id}/pane` | Capture pane text |
| `GET` | `/sessions/{channel_id}/screenshot` | Capture pane screenshot (PNG) |
| `POST` | `/sessions/{channel_id}/verbose` | Toggle verbose mode |
| `POST` | `/directories/browse` | List subdirectories. Body: `{path}` |
| `GET` | `/health` | Health check |

#### Quick Example

```bash
# Create a Claude session
curl -X POST http://localhost:8900/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"work_dir": "/tmp/project", "provider": "claude", "mode": "normal"}'
# → {"channel_id": "api:a1b2c3d4-...", "window_id": "@3", ...}

# Send input
curl -X POST http://localhost:8900/api/v1/sessions/api:a1b2c3d4-.../input \
  -H "Content-Type: application/json" \
  -d '{"text": "explain this codebase"}'

# List sessions
curl http://localhost:8900/api/v1/sessions

# Capture pane
curl http://localhost:8900/api/v1/sessions/api:a1b2c3d4-.../pane

# Close session
curl -X DELETE http://localhost:8900/api/v1/sessions/api:a1b2c3d4-...
```

### WebSocket Streaming

Connect to `ws://localhost:8900/api/v1/ws/{channel_id}` to receive real-time agent output and status events. Omit `channel_id` for a global listener.

**Client → Server messages** (JSON with `type` field):

```jsonc
{"type": "session.create", "work_dir": "/tmp", "provider": "claude", "mode": "normal"}
{"type": "input", "text": "hello", "enter": true, "literal": true}
{"type": "key", "key": "Escape"}
{"type": "capture.pane"}
{"type": "session.list"}
{"type": "session.close", "channel_id": "api:..."}
{"type": "ping"}
```

**Server → Client messages**:

```jsonc
{"type": "session.created", "channel_id": "api:...", "window_id": "@3", "provider": "claude", ...}
{"type": "agent.message", "channel_id": "api:...", "messages": [{"text": "...", "role": "assistant", "content_type": "text", "is_complete": true}]}
{"type": "agent.status", "channel_id": "api:...", "status": "working", "display_label": "Thinking..."}
{"type": "agent.status", "channel_id": "api:...", "status": "interactive", "interactive": true}
{"type": "window.change", "window_id": "@3", "change_type": "new", "provider": "claude"}
{"type": "hook.event", "window_id": "@3", "event_type": "SessionStart", ...}
{"type": "pong"}
{"type": "error", "message": "..."}
```

All messages support an optional `request_id` field for request-response correlation.

### Authentication

Set `ICC_API_KEY` to enable API key authentication:

```bash
export ICC_API_KEY=sk-your-secret-key
unified-icc server start
```

- REST: `Authorization: Bearer sk-your-secret-key` header
- WebSocket: `?token=sk-your-secret-key` query parameter

When `ICC_API_KEY` is not set, authentication is disabled (for local development).

### Relationship to the Unix Socket Daemon

The API server and the existing Unix socket daemon (`unified-icc gateway start`) are **parallel** ways to run the gateway. They share the same tmux session and cannot run simultaneously. Choose based on use case:

| Mode | Command | Use case |
|------|---------|----------|
| Unix socket daemon | `unified-icc gateway start` | CLI scripting, `unified-icc session` commands |
| API server | `unified-icc server start` | HTTP clients, web UIs, programmatic access |

---

## Module Reference

### `gateway.py` — UnifiedICC

The main public API. Instantiate once; call `start()` before use and `stop()` on shutdown.

```python
from unified_icc import UnifiedICC

gateway = UnifiedICC()
await gateway.start()
# ... use gateway ...
await gateway.stop()
```

Key methods:

| Method | Description |
|--------|-------------|
| `create_window(cwd, provider, mode)` | Launch a new tmux window with the given provider |
| `destroy_window(window_id)` | Kill a tmux window |
| `send_to_window(window_id, text, enter)` | Send text or control keys to a window |
| `bind_channel(channel_id, window_id)` | Bind a frontend channel to a tmux window |
| `unbind_channel(channel_id)` | Remove a channel binding |
| `kill_channel_windows(channel_id)` | Kill all windows bound to a channel (used by #new) |
| `on_message(callback)` | Register an `AgentMessageEvent` handler |
| `on_status(callback)` | Register a `StatusEvent` handler |
| `on_hook(callback)` | Register a `HookEvent` handler |
| `on_window_change(callback)` | Register a `WindowChangeEvent` handler |
| `list_windows()` | List all managed tmux windows |
| `get_channel(channel_id)` | Look up window_id for a channel |
| `list_orphaned_agent_windows()` | Live tmux windows with Claude/agent running but not tracked in state |

### `server/` — API Server

Standalone HTTP/WebSocket server that owns a `UnifiedICC` instance and exposes it via FastAPI.

```python
from unified_icc.server import create_app, run_server

# Programmatic start
run_server(host="0.0.0.0", port=8900)

# Or get the ASGI app for custom deployment
app = create_app()
```

Internal structure:

| File | Role |
|------|------|
| `app.py` | FastAPI app factory, gateway lifecycle (`lifespan`), callback wiring |
| `auth.py` | API key authentication (Bearer token + WS query param) |
| `connection_manager.py` | WebSocket connection tracking per channel_id |
| `ws_protocol.py` | JSON message type definitions (dataclasses) |
| `routes/sessions.py` | REST endpoints: CRUD, input, pane capture, browse |
| `routes/ws.py` | WebSocket endpoint: bidirectional message dispatch |

The server generates channel IDs with the `api:` prefix (e.g. `api:a1b2c3d4-e5f6-...`). These are opaque strings compatible with `ChannelRouter`.

### `channel_router.py` — ChannelRouter

Maps `channel_id` (frontend-specific string) to `window_id` (tmux `@N` notation).

```python
from unified_icc.channel_router import channel_router

channel_router.bind("feishu:oc_chat1:om_thread1", "@0")
window_id = channel_router.get_window("feishu:oc_chat1:om_thread1")
# window_id == "@0"
```

Channel ID format is defined by the frontend. Feishu uses `"feishu:{chat_id}:{thread_id}"`. Telegram would use `"telegram:{user_id}:{topic_id}"`.

### `session_monitor.py` — SessionMonitor

Internal component. Runs a 1s poll loop that:
1. Reads new hook events from `~/.cclark/events.jsonl`
2. Reads new transcript lines from each active window's transcript file
3. Dispatches typed events to registered callbacks

Do not instantiate directly; `UnifiedICC.start()` creates it internally.

### `tmux_manager.py` — TmuxManager

Async wrapper around libtmux. All operations run in `asyncio.to_thread()` to avoid blocking the event loop.

Key capabilities:
- Window lifecycle: `create_window`, `kill_window`, `list_windows`
- I/O: `send_keys`, `capture_pane` (plain and ANSI-colored)
- Vim mode detection: auto-enters INSERT mode before sending when Claude Code's `/vim` mode is active
- Pane-level operations: `send_keys_to_pane`, `capture_pane_by_id`

### `providers/` — Agent Providers

Each provider implements the `AgentProvider` protocol:

```python
class AgentProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def start(self, cwd: str, mode: str) -> WindowInfo:
        """Launch the agent in a new tmux window. Return window metadata."""
        ...

    def parse_transcript(self, lines: list[str]) -> list[AgentMessage]:
        """Parse transcript lines into AgentMessage objects."""
        ...

    def extract_session_id(self, session_map: dict) -> str | None:
        """Extract session_id from session_map.json entry."""
        ...
```

| Provider | Startup Command | Transcript | Session Discovery | Capabilities |
|----------|-----------------|------------|------------------|--------------|
| `claude` | `claude --permission-mode default` | JSONL (`events.jsonl`) + `session_map.json` | Hook → `session_map.json` | hooks, /continue, plan mode, resume |
| `codex` | `codex` | JSONL (`~/.codex/sessions/`) | Scan `~/.codex/sessions/` | resume, continue, status snapshot |
| `gemini` | `gemini` | JSONL | Scan `~/.gemini/chats/` | resume, continue |
| `pi` | `pi` | JSONL (`~/.pi/agent/sessions/`) | Scan `~/.pi/agent/sessions/` | resume, continue |
| `shell` | interactive shell | None | None | basic |

---

## FrontendAdapter Protocol

`unified-icc` never sends messages directly to users — it calls a `FrontendAdapter` implementation provided by the frontend. The protocol is defined in `unified_icc.adapter`:

```python
from unified_icc.adapter import (
    FrontendAdapter,
    CardPayload,
    Button,
    InteractivePrompt,
)

# Your adapter must implement:
adapter: FrontendAdapter = MyFeishuAdapter()

# Then wire it into the gateway:
gateway._adapter = adapter
```

### CardPayload

```python
@dataclass
class CardPayload:
    title: str = ""
    content: str = ""          # Markdown-formatted body text
    buttons: list[list[Button]] = []  # Rows of button rows
    footer: str = ""
    color: str = ""            # Accent color hex, e.g. "#4A90E2"
```

### Button

```python
@dataclass
class Button:
    id: str           # Callback identifier (passed back via callback_handler)
    label: str        # Display text
    emoji: str = ""   # Optional emoji prefix
    style: str = "default"  # "default" | "primary" | "danger"
```

### InteractivePrompt

```python
@dataclass
class InteractivePrompt:
    prompt_type: str   # "ask_user" | "permission" | "plan_mode" | "approval"
    title: str
    description: str
    options: list[str] = []    # For ask_user: list of choices
    detail: str = ""           # For permission: command/file being run
    plan_text: str = ""        # For plan_mode: the proposed plan
```

### FrontendAdapter Methods

| Method | Description |
|--------|-------------|
| `send_text(channel_id, text)` | Send plain text. Returns platform message_id. |
| `send_card(channel_id, card)` | Send interactive card. Returns card_id. |
| `update_card(channel_id, card_id, card)` | Patch an existing card in-place. |
| `send_image(channel_id, image_bytes, caption)` | Upload and send image. |
| `send_file(channel_id, file_path, caption)` | Upload and send file. |
| `show_prompt(channel_id, prompt)` | Show interactive prompt card. Returns card_id. |

The adapter also registers inbound handlers:

```python
adapter.register_message_handler(
    lambda channel_id, user_id, text: gateway.on_inbound_message(channel_id, user_id, text)
)
adapter.register_callback_handler(
    lambda channel_id, user_id, action_id, data: gateway.on_callback(channel_id, action_id, data)
)
```

---

## Event Types

All events are in `unified_icc.event_types`:

```python
from unified_icc.event_types import (
    AgentMessageEvent,
    StatusEvent,
    HookEvent,
    WindowChangeEvent,
)
```

### AgentMessageEvent

Emitted when the agent produces new output (text, thinking, tool calls, tool results).

```python
@dataclass
class AgentMessageEvent:
    window_id: str
    session_id: str
    messages: list[AgentMessage]    # Parsed transcript lines
    channel_ids: list[str]          # All channels bound to this window
```

`AgentMessage.content_type` is one of: `text`, `thinking`, `tool_use`, `tool_result`, `local_command`.

### StatusEvent

Emitted when the agent's terminal status line changes (idle, working, interactive, done, dead).

```python
@dataclass
class StatusEvent:
    window_id: str
    session_id: str
    status: str           # "idle" | "working" | "interactive" | "done" | "dead"
    display_label: str    # Human-readable: "idle", "Thinking...", "⏸ plan mode on"
    channel_ids: list[str]
```

### HookEvent

Forwarded hook event from the agent (e.g. Claude Code hook emits session start/end events).

```python
@dataclass
class HookEvent:
    window_id: str
    event_type: str       # e.g. "session_start", "session_end"
    session_id: str
    data: dict[str, Any]  # Hook-specific payload
```

### WindowChangeEvent

Emitted when a tmux window is created or destroyed by the gateway.

```python
@dataclass
class WindowChangeEvent:
    window_id: str
    change_type: str    # "new" | "removed" | "died"
    provider: str
    cwd: str
    display_name: str = ""
```

---

## Provider System

### ProviderCapabilities

Each provider declares which features it supports:

```python
@dataclass
class ProviderCapabilities:
    supports_jsonl: bool           # Structured JSONL transcript (vs plain text)
    supports_resume: bool         # /continue and session resume
    supports_plan_mode: bool       # Claude plan mode integration
    supports_hooks: bool          # Claude Code hook events (events.jsonl)
    supports_yolo: bool           # --dangerously-skip-permissions mode
    supports_idle_timeout: bool    # Idle detection
    supports_subagent_tracking: bool  # Sub-agent (task) tracking
```

### ProviderRegistry

```python
from unified_icc.providers import registry, list_providers

# Get provider by name
provider = registry.get("claude")

# List all available providers
for name in registry.list_names():
    p = registry.get(name)
    print(name, p.capabilities)
```

### Claude-specific notes

- `mode="standard"` launches `claude --permission-mode default`
- `mode="yolo"` launches `claude --dangerously-skip-permissions`
- Session resume: pass `resume_session_id=session_id` to `create_window`
- Plan mode: `send_to_window(window_id, "3", enter=False)` → then `send_to_window(window_id, feedback, enter=True)` (two-step for plan option 3 "Tell Claude what to change")

### Codex-specific notes

- No hook subsystem — session tracking relies on scanning `~/.codex/sessions/` for matching cwd
- `discover_transcript(cwd, window_key)` scans the sessions directory for the most recent transcript whose `session_meta.cwd` matches the given path (within 120 seconds of creation)
- Resume uses `resume <session_id>` subcommand syntax: `make_launch_args(resume_id="abc")` → `"resume abc"`
- Continue uses `resume --last`: `make_launch_args(use_continue=True)` → `"resume --last"`
- Transcript format: JSONL with `{timestamp, type, payload}` entries; entry types include `session_meta`, `response_item`, `input_item`, `event_msg`
- Builtin commands: `/clear`, `/compact`, `/init`, `/mcp`, `/mention`, `/mode`, `/model`, `/permissions`, `/plan`, `/status`
- Interactive prompts (edit confirmations, permission dialogs) are detected from raw pane text by `parse_terminal_status()` — no separate terminal parser dependency

---

## State & Persistence

### State Directory

`~/.cclark/` (configurable via `CCLARK_CONFIG_DIR`).

### state.json

Persisted channel↔window bindings. Restored on startup.

```json
{
  "bindings": {"feishu:oc_chat1:om_t1": "@0"},
  "display_names": {"@0": "Claude Code"},
  "channel_meta": {"feishu:oc_chat1:om_t1": {"cwd": "/home/user/project"}}
}
```

### session_map.json

Written by Claude Code hooks. Maps `"cclark:{window_id}"` → session metadata including `transcript_path` and `session_id`.

### events.jsonl

Append-only log of Claude Code hook events. `EventReader` tracks a byte offset per file and reads incrementally.

### monitor_state.json

Per-transcript byte offsets for the session monitor's poll loop. Key = transcript file path, value = last read byte position.

### window_state_store.json

Records which tmux windows were created by cclark (vs. existing windows). Used for orphan detection and startup cleanup.

### session_map.json (per window)

`~/.claude/sessions/{session_id}/meta.json` — Claude Code's own session metadata, used for session resume.

---

## CLI Commands

```bash
# Start the gateway daemon (long-running process)
unified-icc gateway start

# Start the API server (HTTP + WebSocket)
unified-icc server start --port 8900

# List active windows
unified-icc session list

# Send input to a window
unified-icc session send @0 "hello world"

# Destroy a window
unified-icc session close @0

# Show provider info
unified-icc provider list

# Configure
unified-icc config set tmux_session my_session
unified-icc config show
```

Run `unified-icc --help` for the full command reference.

---

## Configuration

All settings via environment variables or `GatewayConfig`:

```bash
# State directory (default: ~/.cclark)
export CCLARK_CONFIG_DIR=~/.cclark

# Default provider (default: claude)
export CCLARK_PROVIDER=claude

# tmux session name (default: cclark)
export TMUX_SESSION_NAME=cclark

# Monitor poll interval in seconds (default: 1.0)
export MONITOR_POLL_INTERVAL=1.0

# API server (default: disabled)
export ICC_API_HOST=0.0.0.0
export ICC_API_PORT=8900
export ICC_API_KEY=              # Set to enable authentication

# Log level (default: INFO)
export RUST_LOG=info
```

See `unified_icc.config` for the full `GatewayConfig` dataclass.

---

## Design Documents

| Document | Coverage |
|----------|----------|
| [dev-design.md](dev-design.md) | Project overview, ccgram analysis, gateway rationale |
| [design/module-gateway-core.md](design/module-gateway-core.md) | UnifiedICC API and internal wiring |
| [design/module-adapter-layer.md](design/module-adapter-layer.md) | FrontendAdapter protocol, UI components |
| [design/module-card-renderer.md](design/module-card-renderer.md) | Card rendering and verbose mode |
| [design/module-feishu-frontend.md](design/module-feishu-frontend.md) | Feishu-specific integration |
| [design/module-api-server.md](design/module-api-server.md) | HTTP/WebSocket API server architecture |
| [design/module-mvp.md](design/module-mvp.md) | MVP scope and implementation plan |
| `design/module-tmux-manager.md` | TmuxManager and window lifecycle (TBD) |
| `design/module-session-monitor.md` | Poll loop and event dispatch (TBD) |
| `design/module-providers.md` | Provider protocol and implementations (TBD) |
| `design/module-state-persistence.md` | State files and crash recovery (TBD) |

---

## Related Projects

| Project | Role |
|---------|------|
| **[cclark](https://github.com/Agony5757/cclark)** | Feishu frontend — implements `FrontendAdapter` for unified-icc |
| **[ccgram](https://github.com/alexei-led/ccgram)** | Original Telegram frontend (upstream reference) |
| **unified-icc** | This project — platform-agnostic gateway library |

---

## License

MIT
