# Module: Session Monitor

> The 1-second poll loop that reads hook events, monitors transcript files incrementally, detects new sessions, and dispatches `NewMessage` / `NewWindowEvent` events to registered callbacks.

---

## 1. Purpose

`session_monitor.py` is the live "eyes and ears" of the gateway. Every second, it:
1. Reads new entries from `events.jsonl` (hook events) and dispatches them
2. Reads new lines from every active session transcript (JSONL)
3. Reconciles the `session_map.json` against live tmux windows
4. Detects terminal-native interactive prompts (Permission, Plan, etc.)
5. Emits structured events to registered frontend callbacks

It delegates all heavy I/O to specialized modules (`event_reader`, `transcript_reader`, `session_lifecycle`) and is intentionally thin.

## 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   SessionMonitor                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ _monitor_loop()  — 1s poll                         │  │
│  │   ├── _read_hook_events()                          │  │
│  │   │     → event_reader.read_new_events()           │  │
│  │   │     → _hook_event_callback(event)              │  │
│  │   │                                                │  │
│  │   ├── _detect_and_cleanup_changes()                │  │
│  │   │     → session_map_sync.load_session_map()     │  │
│  │   │     → session_lifecycle.reconcile()            │  │
│  │   │     → _new_window_callback(NewWindowEvent)     │  │
│  │   │                                                │  │
│  │   ├── _check_terminal_statuses()                   │  │
│  │   │     → tmux_manager.capture_pane()             │  │
│  │   │     → provider.parse_terminal_status()         │  │
│  │   │     → _status_callback(window_id, StatusUpdate)│  │
│  │   │                                                │  │
│  │   ├── check_for_updates()                          │  │
│  │   │     → TranscriptReader._process_session_file() │  │
│  │   │     → _message_callback(NewMessage)            │  │
│  │   │                                                │  │
│  │   └── detect_missing_session_ids()                 │  │
│  │         → tmux_manager.send_keys("/status")        │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
       │                        │                    │
       ▼                        ▼                    ▼
  events.jsonl            session_map.json       transcript JSONL files
  (hook events)           (hook-written)        (~/.claude/projects/…)
```

## 3. Key Components

### 3.1 `SessionMonitor`

The main class. Call `start()` to launch the background poll loop; call `stop()` to shut it down cleanly.

```python
monitor = SessionMonitor(poll_interval=1.0)
monitor.set_message_callback(on_new_message)
monitor.set_new_window_callback(on_new_window)
monitor.set_status_callback(on_terminal_status)
monitor.set_hook_event_callback(on_hook_event)
monitor.start()
```

#### State

| Field | Type | Purpose |
|---|---|---|
| `state` | `MonitorState` | Per-transcript byte offsets; loaded/saved from `monitor_state.json` |
| `_transcript_reader` | `TranscriptReader` | Handles transcript file discovery, mtime caching, incremental reads |
| `_idle_tracker` | `IdleTracker` | Per-session idle timers |
| `_running` | `bool` | Controls the poll loop |
| `_fallback_scan_done` | `bool` | Prevents repeated fallback scans |

#### Key Methods

| Method | Description |
|---|---|
| `start()` / `stop()` | Manage the background asyncio task |
| `check_for_updates(current_map)` | Main entry point called each poll cycle |
| `detect_session_id(window_id)` | Actively probes `/status` in a window to extract session_id |
| `detect_missing_session_ids()` | Called at startup to fill session_ids for windows lacking them |
| `record_hook_activity(window_id)` | Called from hook event handler to reset idle timers |

### 3.2 `MonitorState`

Persists per-session byte offsets so the monitor never re-reads old transcript data on restart. Written to `~/.cclark/monitor_state.json`.

```python
@dataclass
class MonitorState:
    state_file: Path
    tracked_sessions: dict[str, TrackedSession]   # session_id → TrackedSession
    events_offset: int                            # byte offset in events.jsonl

@dataclass
class TrackedSession:
    session_id: str
    file_path: str
    last_byte_offset: int = 0
```

`save_if_dirty()` is called at the end of each poll cycle only when offsets have advanced.

### 3.3 `TranscriptReader`

Handles all transcript file I/O for the monitor. Key responsibilities:
- **mtime cache**: avoids re-opening files that have not changed
- **Incremental read**: seeks to `last_byte_offset` and reads only new bytes
- **Session file discovery**: scans `~/.claude/projects/` by session_id subdirectory
- **JSONL parsing**: parses each new line via `provider.parse_transcript_line()`

```python
class TranscriptReader:
    def __init__(self, state: MonitorState, idle_tracker: IdleTracker): ...

    async def _process_session_file(
        self, session_id, file_path, new_messages, window_id
    ): ...
```

### 3.4 `event_reader.py` — `read_new_events()`

Reads `events.jsonl` incrementally, starting from a stored byte offset.

```python
async def read_new_events(
    path: Path, current_offset: int
) -> tuple[list[HookEvent], int]:
    # Seeks to current_offset
    # Reads lines one by one
    # Parses JSON, skips malformed lines
    # Returns (events, new_offset)
```

### 3.5 `IdleTracker`

Per-session idle timers. When a hook event or transcript activity is recorded, the timer's clock resets. Used by `session_lifecycle` to detect when a session has gone quiet (and potentially died).

## 4. Data Flow

### Poll Cycle (every 1 second)

```
_monitor_loop():
  1. _read_hook_events()
       → read_new_events(config.events_file, state.events_offset)
       → state.events_offset = new_offset
       → for each HookEvent: _hook_event_callback(event)
       → session_lifecycle.handle_<event_type>(...)
         (SessionEnd, SubagentStart, SubagentStop, TaskCompleted, …)

  2. session_map_sync.load_session_map()
       → reads ~/.cclark/session_map.json
       → updates window_store WindowState entries

  3. _detect_and_cleanup_changes()
       → session_lifecycle.reconcile(current_map)
       → for new windows: _new_window_callback(NewWindowEvent)
       → for removed sessions: TranscriptReader.clear_session()

  4. detect_missing_session_ids()
       → for each window in _created_windows without a session_id:
       → detect_session_id(window_id)  [throttled to once per 5s per window]

  5. _check_terminal_statuses(all_windows)
       → for each bound/external window:
       → tmux_manager.capture_pane(window_id)
       → provider.parse_terminal_status(pane_text)
       → if interactive: _status_callback(window_id, StatusUpdate)

  6. check_for_updates(current_map)
       → for each session in session_map:
            → TranscriptReader._process_session_file(session_id, path, ...)
              → open transcript, seek to last_byte_offset
              → read new lines, parse via provider.parse_transcript_line()
              → provider.parse_transcript_entries()
              → emit NewMessage for each new assistant message
       → state.save_if_dirty()

  7. fallback scan (runs once when session_map is empty but created windows exist)
       → scan projects for session files
       → link by session_id to _created_windows only
       → process new sessions

  8. new_messages → _message_callback(NewMessage)
```

### Startup Sequence

```
gateway.start()
  → SessionMonitor()
       → state.load()   ← loads monitor_state.json
  → monitor.start()
       → _monitor_loop()
            → _cleanup_all_stale_sessions()
                 → reads session_map.json
                 → removes tracked sessions not in session_map
            → initial_map = _load_current_session_map()
            → session_lifecycle.initialize(initial_map)
            → detect_missing_session_ids()   ← fills session_ids from /status
```

### Hook Event Flow

```
Claude Code hook writes to events.jsonl:
  {"event": "SessionStart", "window_key": "cclark:@5", "session_id": "abc-123", "data": {...}}
  ↓
read_new_events() at next poll
  → HookEvent(event_type="SessionStart", window_key="cclark:@5", session_id="abc-123", ...)
  ↓
_hook_event_callback(event)
  → session_lifecycle.handle_session_start(...)
  → _idle_tracker.record_activity(session_id)
  → window_store.get_window_state(wid).session_id = session_id
  → _schedule_save()
```

## 5. State Files

| File | Owner | Contents |
|---|---|---|
| `~/.cclark/monitor_state.json` | `MonitorState` | Per-session byte offsets; events.jsonl read offset |
| `~/.cclark/session_map.json` | Claude Code hook / `session_map_sync` | window_key → session_id, cwd, transcript_path |
| `~/.cclark/events.jsonl` | Claude Code hook | Append-only hook event log |

## 6. Error Handling

- **Backoff**: On any `_LoopError` (`OSError`, `RuntimeError`, `JSONDecodeError`, `ValueError`), the loop backs off exponentially: 2s, 4s, 8s, … up to 30s. Unknown exceptions also trigger backoff but are logged at `exception` level.
- **Individual session failures**: `try/except` around each `_process_session_file` call — one bad transcript does not crash the loop.
- **Hook event callback failures**: Logged at `exception` level; do not propagate.
- **Monitor stop**: Calls `state.save()` synchronously to ensure offsets are flushed before exit.

## 7. Design Decisions

### Why Incremental (Byte-Offset) Reads?

Reading entire transcript files from offset 0 on every poll would be expensive for long sessions. Instead, `MonitorState` stores `last_byte_offset` per session. On each cycle, the file is opened, seeked to the offset, and only new bytes are read. The offset is persisted at the end of the cycle.

### Why Two-Step Session ID Detection?

`session_map.json` is written by the Claude Code hook, but the hook may not fire (e.g. if `--no-hook` was used). In that case, `detect_missing_session_ids()` runs at startup and sends `/status` to each cclark-created window that lacks a `session_id`. This is throttled to once per 5 seconds per window.

### Why the Fallback Scan?

When `session_map.json` is empty (hook was bypassed or a new session started outside cclark), `check_for_updates()` falls back to scanning the filesystem: `~/.claude/projects/<session_id>/transcript.jsonl`. It links sessions to windows **only** via exact `session_id` matches to `_created_windows`. This prevents unrelated sessions from being erroneously linked to cclark's own windows.

### Frontend Adapter Connection

`_message_callback(NewMessage)`, `_status_callback(window_id, StatusUpdate)`, `_new_window_callback(NewWindowEvent)`, and `_hook_event_callback(HookEvent)` are the four outbound channels. The `UnifiedICC` gateway wires these to its own public event callbacks (see `module-gateway-core.md`).

### Related Documents

- `module-gateway-core.md` — wires the four SessionMonitor callbacks to gateway public events
- `module-session-lifecycle.md` — `session_lifecycle.reconcile()` is called each cycle; handles SessionStart/End events
- `module-providers.md` — provider-specific `parse_transcript_line()` and `parse_terminal_status()` normalize provider output
- `module-state-persistence.md` — `MonitorState` is the `monitor_state.json` persistence layer
