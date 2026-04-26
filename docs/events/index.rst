# Events System

Unified ICC uses an event-driven architecture where the gateway emits events that frontends can subscribe to.

## Event Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionMonitor                            │
│                                                              │
│  Poll Loop ──► Detect Changes ──► Emit Events              │
│      │                                           │            │
│      │                                           ▼            │
│      │                              ┌───────────────────┐   │
│      │                              │ Event Callbacks    │   │
│      │                              │ (on_message, etc.)│   │
│      │                              └───────────────────┘   │
│      │                                           │            │
│      ▼                                           ▼            │
│  TranscriptReader                    FrontendAdapter         │
│  (parses output)                     (sends to platform)    │
└─────────────────────────────────────────────────────────────┘
```

## Subscribing to Events

```python
from unified_icc import UnifiedICC

gateway = UnifiedICC()

# Register callbacks
gateway.on_message(my_message_handler)
gateway.on_status(my_status_handler)
gateway.on_hook_event(my_hook_handler)
gateway.on_window_change(my_window_handler)
```

## Event Types

### AgentMessageEvent

Emitted when the agent produces output.

```python
def my_message_handler(event):
    for msg in event.messages:
        print(f"[{msg.role}] {msg.text}")
```

### StatusEvent

Emitted when agent status changes.

```python
def my_status_handler(event):
    print(f"Status: {event.status}")
```

### HookEvent

Emitted for hook events (SessionStart, Notification, etc.).

```python
def my_hook_handler(event):
    if event.event_type == "SessionStart":
        print(f"New session: {event.session_id}")
```

### WindowChangeEvent

Emitted when windows are created or removed.

```python
def my_window_handler(event):
    print(f"Window {event.change_type}: {event.window_id}")
```

## Internal Event Flow

### Transcript → AgentMessageEvent

```
1. TranscriptReader._process_session_file()
   ↓
2. TranscriptReader._read_new_lines() reads new lines
   ↓
3. Provider.parse_transcript_line() parses each line
   ↓
4. Provider.parse_transcript_entries() converts to AgentMessage
   ↓
5. SessionMonitor._transcript_reader._process_session_file() receives messages
   ↓
6. NewMessage objects collected
   ↓
7. SessionMonitor.check_for_updates() returns new messages
   ↓
8. SessionMonitor._monitor_loop() calls _message_callback
   ↓
9. Gateway._on_new_message() wraps in AgentMessageEvent
   ↓
10. User callbacks invoked
```

### Session Lifecycle → WindowChangeEvent

```
1. SessionMonitor._monitor_loop() runs poll
   ↓
2. SessionMonitor._load_current_session_map() reads session_map.json
   ↓
3. SessionLifecycle.reconcile() diffs old vs new
   ↓
4. New windows detected → result.new_windows populated
   ↓
5. SessionMonitor._detect_and_cleanup_changes() fires callback
   ↓
6. NewWindowEvent created
   ↓
7. Gateway._on_new_window() wraps in WindowChangeEvent
   ↓
8. User callbacks invoked
```

## Handling Events in Frontends

### Simple Text Relay

```python
async def relay_messages(event):
    for msg in event.messages:
        if msg.text and msg.is_complete:
            for channel in event.channel_ids:
                await adapter.send_text(channel, msg.text)

gateway.on_message(relay_messages)
```

### Rich Card Formatting

```python
from unified_icc import CardPayload

async def format_as_card(event):
    for msg in event.messages:
        if msg.content_type == "tool_use":
            card = CardPayload(
                title=f"Tool: {msg.tool_name}",
                body=msg.text[:500],
                color="#FF6B6B",
            )
        else:
            card = CardPayload(
                title="Claude",
                body=msg.text[:2000],
                color="#007AFF",
            )

        for channel in event.channel_ids:
            await adapter.send_card(channel, card)

gateway.on_message(format_as_card)
```

### Streaming Updates

```python
from unified_icc import CardPayload

# Track sent messages for updates
_sent_messages: dict[str, str] = {}  # session_id -> card_id

async def stream_messages(event):
    for msg in event.messages:
        if not msg.is_complete:
            # Partial update
            channel = event.channel_ids[0] if event.channel_ids else None
            if channel and event.session_id in _sent_messages:
                card_id = _sent_messages[event.session_id]
                card = CardPayload(title="Claude", body=msg.text)
                await adapter.update_card(channel, card_id, card)
        else:
            # Final message
            for channel in event.channel_ids:
                card = CardPayload(title="Claude", body=msg.text)
                card_id = await adapter.send_card(channel, card)
                _sent_messages[event.session_id] = card_id

gateway.on_message(stream_messages)
```

### Error Handling

```python
def safe_handler(event):
    try:
        process_event(event)
    except Exception as e:
        logger.exception(f"Error handling event: {e}")
        # Notify admin
        asyncio.create_task(adapter.send_text("admin", f"Error: {e}"))

gateway.on_message(safe_handler)
```

## Hook Events

Hook events come from the agent's hook system (primarily Claude):

```python
from unified_icc import HookEvent

# Hook event types
HOOK_EVENTS = {
    "SessionStart": "New session started",
    "Notification": "Agent notification",
    "Stop": "Agent stopped",
    "Task": "Task state update",
}
```

### Handling SessionStart

```python
async def on_session_start(event):
    if event.event_type == "SessionStart":
        session_id = event.data.get("session_id")
        cwd = event.data.get("cwd", "")
        print(f"Session {session_id} started in {cwd}")

        # Auto-bind to a channel if needed
        # channel_router.bind("feishu:chat:thread", window_id)

gateway.on_hook_event(on_session_start)
```

### Handling Notifications

```python
async def on_notification(event):
    if event.event_type == "Notification":
        message = event.data.get("message", "")
        level = event.data.get("level", "info")  # info, warning, error

        for channel in event.channel_ids:
            await adapter.send_text(channel, f"[{level.upper()}] {message}")

gateway.on_hook_event(on_notification)
```

## Status Events

Status changes indicate the agent's current state:

```python
from unified_icc import StatusEvent

STATUS_HANDLERS = {
    "working": handle_working,
    "idle": handle_idle,
    "done": handle_done,
    "dead": handle_dead,
    "interactive": handle_interactive,
}

def on_status_change(event):
    handler = STATUS_HANDLERS.get(event.status, handle_unknown)
    handler(event)

gateway.on_status(on_status_change)
```

## Window Events

```python
async def on_window_event(event):
    if event.change_type == "new":
        # New window created
        print(f"New {event.provider} window: {event.window_id}")
        # Bind to default channel
        gateway.bind_channel("default_channel", event.window_id)

    elif event.change_type == "removed":
        # Window explicitly killed
        print(f"Window removed: {event.window_id}")
        # Clean up any state

    elif event.change_type == "died":
        # Window crashed
        print(f"Window died: {event.window_id}")
        # Notify user
        for channel in gateway.resolve_channels(event.window_id):
            await adapter.send_text(channel, "⚠️ Agent crashed!")

gateway.on_window_change(on_window_event)
```
