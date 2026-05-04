# Module: State Persistence

> All on-disk persistence for the unified-icc system: channel↔window bindings, per-window metadata, monitor byte offsets, and the hook-written session map.

---

## 1. Purpose

`state_persistence.py` and related modules handle every JSON file that persists between process invocations. They provide crash recovery (state survives a restart), orphan detection (dead windows are identified by comparing live tmux windows against persisted state), and incremental reads (monitor offsets survive restarts).

## 2. Architecture

```
~/.unified-icc/  (or $UNIFIED_ICC_DIR/)
├── state.json              # ChannelRouter bindings + WindowStateStore + UserPreferences
│                           # Written by: StatePersistence (debounced)
│
├── monitor_state.json      # MonitorState: per-session byte offsets + events.jsonl offset
│                           # Written by: MonitorState.save_if_dirty()
│
├── session_map.json        # Hook-written: window_key → {session_id, cwd, transcript_path, …}
│                           # Written by: Claude Code hook (fcntl file lock)
│                           # Read by:   SessionMapSync, SessionMonitor
│
└── session_map.json.lock   # fcntl.LOCK_EX advisory lock for session_map writes

Key persistence classes:
  StatePersistence   — debounced atomic JSON writer (state.json)
  WindowStateStore   — _created_windows + window_states (state.json section)
  MonitorState       — tracked_sessions + events_offset (monitor_state.json)
  SessionMapSync     — session_map.json I/O and reconciliation
```

## 3. Key Components

### 3.1 `StatePersistence` (`state_persistence.py`)

Debounced, atomic JSON writer for `state.json`. Used by `SessionManager` to persist channel bindings, window states, and user preferences.

```python
class StatePersistence:
    def __init__(self, path: Path, serialize_fn: Callable[[], dict[str, Any]]): ...

    def schedule_save(self) -> None:
        # Sets _dirty = True
        # Cancels any pending timer
        # Schedules _do_save() to run in 0.5s

    def flush(self) -> None:
        # Cancels pending timer
        # Calls _do_save() immediately if dirty

    def load(self) -> dict[str, Any]:
        # Reads state.json, returns {} if absent or corrupt
```

**Atomic write**: `utils.atomic_write_json()` writes to a temp file then renames, ensuring readers never see a partial write.

**Debouncing**: `_do_save()` is scheduled 0.5 seconds after the first mutation. Any subsequent mutation within the window resets the timer. On shutdown, `flush()` forces an immediate save.

### 3.2 `WindowStateStore` (`window_state_store.py`)

Manages per-window metadata. The singleton `window_store` holds:

```python
@dataclass
class WindowState:
    session_id: str = ""
    cwd: str = ""
    window_name: str = ""
    transcript_path: str = ""
    notification_mode: str = "all"       # "all" | "errors_only" | "muted"
    provider_name: str = ""               # "claude" | "codex" | "gemini" | "pi" | "shell"
    approval_mode: str = "normal"          # "normal" | "yolo"
    batch_mode: str = "batched"           # "batched" | "verbose"
    external: bool = False                # True for emdash/external windows
    channel_id: str = ""                  # bound Feishu channel, for reverse routing

class WindowStateStore:
    window_states: dict[str, WindowState]           # window_id → WindowState
    _created_windows: dict[str, set[str]]           # app_name → set(window_id)
```

#### `_created_windows` Set

Tracks which windows cclark created via `create_window()`. Persisted in `state.json` under `_created_windows`. Guards the session monitor's fallback scan: only windows in this set can be linked to discovered sessions, preventing unrelated sessions from being matched to cclark's own windows.

```python
window_store.mark_window_created(window_id)    # called on create_window
window_store.is_created_window(window_id)      # called by fallback scan guard
window_store.remove_created_window(window_id)  # called on kill/unbind
window_store.get_created_windows()             # called by orphan detection
```

### 3.3 `MonitorState` (`monitor_state.py`)

Persists per-session byte offsets for the session monitor. Written to `monitor_state.json`.

```python
@dataclass
class MonitorState:
    state_file: Path
    tracked_sessions: dict[str, TrackedSession]   # session_id → {file_path, last_byte_offset}
    events_offset: int                             # byte offset in events.jsonl
```

`TrackedSession`:
```python
@dataclass
class TrackedSession:
    session_id: str
    file_path: str
    last_byte_offset: int = 0
```

`save_if_dirty()` is called at the end of each poll cycle only when offsets have advanced.

### 3.4 `SessionMapSync` (`session_map.py`)

Owns all reading and writing of `session_map.json`, including:

- **Async load**: `load_session_map()` reads the file and syncs `window_store` entries
- **File locking**: `write_hookless_session_map()` uses `fcntl.LOCK_EX` (consistent with the Claude Code hook)
- **Pruning**: `prune_session_map()` removes entries for dead tmux windows
- **Synthetic entries**: `write_hookless_session_map()` writes entries for Codex/Gemini/Pi (which lack hooks)

```python
session_map_sync = SessionMapSync()

# Called by hook event handler (async-safe):
session_map_sync.write_hookless_session_map(
    window_id, session_id, cwd, transcript_path, provider_name
)
# Called each poll cycle:
await session_map_sync.load_session_map()
# Called when a tmux window dies:
session_map_sync.prune_session_map(live_window_ids)
# Called on provider switch (no-hook providers):
session_map_sync.clear_session_map_entry(window_id)
```

### 3.5 `SessionManager._serialize_state()`

`SessionManager` (in `session.py`) owns the top-level `state.json` format. It composes all subsystems:

```python
def _serialize_state(self) -> dict[str, Any]:
    result = {"window_states": window_store.to_dict()}   # includes _created_windows
    result.update(user_preferences.to_dict())
    result.update(channel_router.to_dict())
    return result
```

`session_manager.flush_state()` is called by `UnifiedICC.stop()` to force a synchronous save on shutdown.

## 4. Data Flow

### Crash Recovery on Startup

```
UnifiedICC.start()
  → session_manager._load_state()
      → StatePersistence.load() → state.json dict
      → window_store.from_dict(state["window_states"])
      → channel_router.from_dict(state)
      → user_preferences.from_dict(state)
  ↓
  → _startup_cleanup()
      → For each created window:
           If not alive in tmux → remove_created_window()
           If not bound         → kill_window()
      → For each bound window:
           If alive → mark_window_created() + populate missing fields
      → For each orphaned window_state (no binding, not live):
           → tmux_manager.kill_window(wid) + remove_window
  ↓
  → SessionMonitor.start()
      → MonitorState.load() → monitor_state.json
      → _cleanup_all_stale_sessions()
           → removes tracked sessions not in session_map.json
      → detect_missing_session_ids()
           → sends /status to windows without session_id
```

### State Save on Mutation

```
gateway.send_to_window(window_id, "hello")
  → channel_router._schedule_save()   # wired by session_manager._wire_singletons()
      → StatePersistence.schedule_save()
          → _dirty = True
          → loop.call_later(0.5, _do_save)
  → ... 0.5s pass, no more mutations ...
  → _do_save()
      → _serialize_state() → dict
      → atomic_write_json(state_file, dict)
      → _dirty = False
```

### Monitor Offset Persistence

```
check_for_updates()
  → for each new transcript line:
       state.tracked_sessions[session_id].last_byte_offset = new_offset
       state._dirty = True
  → state.save_if_dirty()   # writes only if _dirty
```

### Hookless Provider Registration

```
Codex/Gemini/Pi: new session detected via filesystem scan
  → session_map_sync.write_hookless_session_map(
        window_id, session_id, cwd, transcript_path, provider_name
    )
      → fcntl.flock(LOCK_EX)
      → read existing session_map.json (with corrupt backup)
      → write new entry
      → atomic_write_json
      → flock(LOCK_UN)
```

## 5. State Files Detail

| File | Format | Owner | Written on | Read on |
|---|---|---|---|---|
| `~/.unified-icc/state.json` | JSON | `StatePersistence` | Debounced 0.5s after mutation | `SessionManager._load_state()` |
| `~/.unified-icc/monitor_state.json` | JSON | `MonitorState` | End of each poll cycle | `SessionMonitor.__init__()` |
| `~/.unified-icc/session_map.json` | JSON | Hook / `SessionMapSync` | Hook on session start; `write_hookless_session_map()` | Each poll cycle |
| `~/.unified-icc/session_map.json.lock` | lock file | `SessionMapSync` | During write | N/A |

### Config Directory

All files are stored under `~/.unified-icc/` by default. The `UNIFIED_ICC_DIR` environment variable overrides this, allowing multiple independent installations:

```python
config.config_dir   # ~/.unified-icc or $UNIFIED_ICC_DIR
config.state_file   # config_dir / "state.json"
config.monitor_state_file  # config_dir / "monitor_state.json"
config.session_map_file   # config_dir / "session_map.json"
config.events_file        # config_dir / "events.jsonl"
```

## 6. Error Handling

- **Corrupt state.json**: `StatePersistence.load()` catches `JSONDecodeError`, returns `{}`. The process starts fresh.
- **Corrupt monitor_state.json**: `MonitorState.load()` catches `JSONDecodeError`, returns `{}`.
- **Corrupt session_map.json**: `SessionMapSync.write_hookless_session_map()` backs it up to `.json.corrupt` before overwriting.
- **Missing state files**: all loaders check `path.exists()` first and return empty/default state.
- **File lock failure**: logged at `debug` level, write is skipped — prevents blocking on a locked file.
- **`atomic_write_json` failure**: caught by callers, logged, does not propagate.

## 7. Design Decisions

### Why Debounced Saves?

A single user message can trigger dozens of state mutations (multiple window updates, channel binding changes, etc.). Without debouncing, every mutation would trigger an immediate fsync. The 0.5s debounce window collapses all mutations from one user interaction into a single write.

### Why `atomic_write_json`?

On Linux, writing to a temp file then `os.rename()` is atomic at the filesystem level. This ensures that if the process is killed mid-write, `state.json` is either the old complete state or the new complete state — never a partial/corrupt blob.

### Why File Locking for session_map.json?

The Claude Code hook writes `session_map.json` concurrently with cclark. Without `fcntl.LOCK_EX`, cclark's read could race with the hook's write, reading a partial entry. `SessionMapSync.write_hookless_session_map()` uses the same locking pattern (`LOCK_EX`) for consistency.

### Why Persist `_created_windows`?

The set is critical for the fallback scan guard (see `module-session-lifecycle.md`). If it were not persisted, a process restart would lose the record of which windows cclark created, breaking orphan detection and the fallback scan safety guard.

### Why Two Separate Files?

`state.json` and `monitor_state.json` have different write patterns and audiences:
- `state.json`: written on every user interaction (debounced), read only at startup — needs to survive crashes quickly
- `monitor_state.json`: written only when transcript offsets advance, read at startup — stability matters more than latency

Splitting them avoids monitor offset advances from triggering channel binding saves (and vice versa).

### Related Documents

- `module-gateway-core.md` — `UnifiedICC.start()` triggers `_load_state()`; `stop()` calls `flush_state()`
- `module-session-lifecycle.md` — `_created_windows` guards orphan detection and fallback scan
- `module-session-monitor.md` — `MonitorState` is the persistence layer for `monitor_state.json`
- `module-tmux-manager.md` — tmux operations are the only non-persistence state
