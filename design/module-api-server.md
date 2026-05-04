# Module Design: API Server

**File**: `unified_icc/server/`
**Status**: Implemented

## Purpose

Expose the `UnifiedICC` gateway as a standalone HTTP/WebSocket API server, enabling any HTTP client to create and interact with AI coding agent sessions without a messaging frontend (Feishu, Telegram, etc.).

## Motivation

The gateway was originally designed as a library consumed by frontend adapters (cclark for Feishu, ccgram for Telegram). However, the core gateway is platform-agnostic and can serve as a standalone online agent. An HTTP/WebSocket API makes it accessible to:

- Web UIs and custom dashboards
- SDK integrations (Python, JS, etc.)
- CI/CD pipelines
- REPL/CLI tools via curl
- Any programmatic client

The existing Unix socket daemon (`cli/daemon.py`) proved the pattern of a standalone process owning the gateway, but its JSON-over-Unix-socket protocol is limited to simple request-response. The API server provides richer capabilities via REST + bidirectional WebSocket streaming.

## Architecture

```
Client (curl / SDK / Web UI)
       ↓ HTTP REST / WebSocket
  unified-icc API Server (FastAPI + uvicorn)
       ↓ owns single UnifiedICC instance
  tmux → AI agent (claude / codex / gemini / pi / shell)
```

The server is a thin layer over the gateway:
- **REST endpoints** call gateway methods directly (`create_window`, `send_input_to_window`, `capture_pane`, etc.)
- **WebSocket** receives gateway callbacks (`on_message`, `on_status`, `on_hook_event`, `on_window_change`) and pushes JSON events to subscribed connections

### Package Structure

```
server/
  __init__.py            # run_server(), create_app exports
  app.py                 # FastAPI app factory, lifespan context manager
  auth.py                # API key authentication
  connection_manager.py  # WebSocket connection tracking per channel_id
  ws_protocol.py         # JSON message type definitions (dataclasses)
  routes/
    __init__.py          # Route registration
    sessions.py          # REST endpoints
    ws.py                # WebSocket endpoint + message dispatch
```

## Gateway Lifecycle

The server owns a single `UnifiedICC` instance via FastAPI's `lifespan` context manager:

1. **Startup**: Create `UnifiedICC()`, call `await gateway.start()`, register 4 callbacks
2. **Runtime**: Gateway callbacks push events into `ConnectionManager`, which broadcasts to WebSocket connections
3. **Shutdown**: Call `await gateway.stop()`, clean up state

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _gateway = UnifiedICC()
    await _gateway.start()
    _gateway.on_message(_on_agent_message)
    _gateway.on_status(_on_agent_status)
    _gateway.on_hook_event(_on_hook_event)
    _gateway.on_window_change(_on_window_change)
    yield
    await _gateway.stop()
```

## REST API

### Session Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/sessions` | Create agent session |
| `GET` | `/api/v1/sessions` | List all sessions |
| `GET` | `/api/v1/sessions/{channel_id}` | Get session status |
| `DELETE` | `/api/v1/sessions/{channel_id}` | Close session |

Session creation generates a channel ID with the `api:` prefix:

```python
channel_id = f"api:{uuid.uuid4()}"
window = await gateway.create_window(work_dir, provider, mode)
gateway.bind_channel(channel_id, window.window_id)
```

### Agent Interaction

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{channel_id}/input` | Send text input |
| `POST` | `/sessions/{channel_id}/key` | Send special key |
| `GET` | `/sessions/{channel_id}/pane` | Capture pane text |
| `GET` | `/sessions/{channel_id}/screenshot` | Capture screenshot (PNG) |
| `POST` | `/sessions/{channel_id}/verbose` | Toggle verbose mode |

### Utilities

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/directories/browse` | List subdirectories |
| `GET` | `/health` | Health check |

## WebSocket Protocol

A single endpoint handles bidirectional communication:

```
ws://host:port/api/v1/ws/{channel_id}   # Subscribe to specific session
ws://host:port/api/v1/ws                 # Global listener
```

### Client → Server

All messages are JSON with a `type` field:

| Type | Fields | Description |
|------|--------|-------------|
| `session.create` | `work_dir`, `provider`, `mode`, `name` | Create new session |
| `session.list` | — | List all sessions |
| `session.close` | `channel_id` | Close a session |
| `input` | `text`, `enter`, `literal`, `raw` | Send text input |
| `input.raw` | `text` | Send raw key input |
| `key` | `key` | Send special key (Escape, Enter, etc.) |
| `capture.pane` | — | Request pane capture |
| `capture.screenshot` | — | Request screenshot |
| `verbose.set` | `enabled` | Toggle verbose |
| `wizard.browse` | `path` | List directory contents |
| `wizard.mkdir` | `name` | Create directory |
| `ping` | — | Heartbeat |

### Server → Client

| Type | When emitted |
|------|-------------|
| `session.created` | After `session.create` completes |
| `session.list` | Response to `session.list` |
| `session.closed` | After `session.close` completes |
| `agent.message` | Gateway `on_message` callback — agent output streaming |
| `agent.status` | Gateway `on_status` callback — status changes |
| `window.change` | Gateway `on_window_change` callback |
| `hook.event` | Gateway `on_hook_event` callback |
| `capture.pane` | Response to `capture.pane` request |
| `capture.screenshot` | Response to `capture.screenshot` request |
| `error` | On any error |
| `pong` | Response to `ping` |

All messages support an optional `request_id` field for request-response correlation.

## ConnectionManager

Tracks WebSocket connections per channel_id:

```python
class ConnectionManager:
    _subscriptions: dict[str, set[WebSocket]]  # channel_id → connections
    _global: set[WebSocket]                     # global listeners
```

Gateway callbacks resolve `channel_ids` from events and broadcast to subscribed connections. Dead connections are automatically cleaned up on send failure.

## Authentication

Static API key via `ICC_API_KEY` environment variable:

- **REST**: `Authorization: Bearer <key>` header (FastAPI `HTTPBearer` security)
- **WebSocket**: `?token=<key>` query parameter

When `ICC_API_KEY` is not set, authentication is disabled (local development).

## Channel ID Format

API sessions use `api:<uuid4>` as channel IDs (e.g. `api:a1b2c3d4-e5f6-7890-abcd-ef1234567890`). The `ChannelRouter` treats channel IDs as opaque strings, so this format is fully compatible with existing routing logic.

## Relationship to Unix Socket Daemon

The API server and the existing Unix socket daemon (`cli/daemon.py`) are **parallel** ways to run the gateway:

| Mode | Command | Protocol | Use case |
|------|---------|----------|----------|
| Unix socket daemon | `unified-icc gateway start` | JSON over Unix socket | CLI scripting |
| API server | `unified-icc server start` | HTTP REST + WebSocket | Programmatic access |

They share the same tmux session and state files (`~/.unified-icc/`), so they cannot run simultaneously. Each uses its own PID file (`gateway.pid` vs `server.pid`).

Existing daemon code is unchanged — the API server is an additive feature.

## CLI Integration

```bash
unified-icc server start [--host HOST] [--port PORT] [--detach]
unified-icc server stop
unified-icc server status
```

The `server` subcommand is registered alongside `gateway`, `session`, `provider`, and `config`.

## Dependencies

The server uses an optional dependency group (`[server]`) to avoid requiring FastAPI for users who only need the library:

```toml
[project.optional-dependencies]
server = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "websockets>=13.0",
]
```

Install with: `uv sync --extra server`

## Future Work

- **cclark migration**: In the long term, cclark could become a WebSocket client of the API server instead of importing `UnifiedICC` directly, enabling multiple frontends to share a single gateway process.
- **Multi-user auth**: JWT or token-based multi-user authentication.
- **Session history API**: Endpoint to retrieve past transcript entries.
- **Web UI**: Built-in dashboard for managing sessions.
