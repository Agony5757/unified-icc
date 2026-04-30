# Module: Session Lifecycle

> Single write authority for session state mutations: session creation, teardown, orphan detection, and hook event processing.

---

## 1. Purpose

`session_lifecycle.py` is the authority for all session-scoped state mutations. It detects when sessions appear, change, or disappear by diffing `session_map.json` snapshots, and propagates those changes to the idle tracker, task state, and window state store. It does not perform I/O itself — it reacts to data produced by other modules.

## 2. Architecture

```
session_lifecycle (singleton)
  │
  ├── reconcile(current_map, idle_tracker) → ReconcileResult
  │     Detects new/removed/replaced sessions
  │
  ├── handle_session_end(window_id)
  │     Clears task state, subagents, window session fields
  │
  ├── handle_subagent_start(window_id, subagent_id, name) → int
  │     Adds subagent to claude_task_state
  │
  ├── handle_subagent_stop(window_id, subagent_id) → tuple
  │     Removes subagent, returns name + index
  │
  ├── handle_task_completed(window_id, session_id, task_id, subject) → bool
  │     Marks task completed in claude_task_state
  │
  ├── handle_notification_wait(window_id, wait_header)
  │     Sets wait header for plan-mode / approval UI
  │
  ├── handle_stop_task_state(window_id)
  │     Clears wait header
  │
  └── resolve_session_id(window_id) → str | None
        Reverse lookup from window_id to session_id

ReconcileResult:
  sessions_to_remove: set[str]   — sessions that ended
  new_windows: dict[str, dict]   — newly discovered windows
  current_map: dict[str, dict]    — current session_map snapshot
```

## 3. Key Components

### 3.1 `SessionLifecycle`

Holds `_last_session_map` (the previous cycle's snapshot). `reconcile()` computes the diff against `current_map`.

### 3.2 `ReconcileResult`

Returned by `reconcile()`. Contains three disjoint sets:
- `sessions_to_remove`: sessions that were in the last map but are gone now (or whose `session_id` changed)
- `new_windows`: entries in `current_map` not present in `_last_session_map`
- `current_map`: passed through so callers don't need to re-load it

## 4. Data Flow

### Session Creation

```
gateway.create_window(work_dir="/project", provider="claude")
  → tmux_manager.create_window(launch_command="claude ...")
      → tmux new-window + pane.send_keys("claude ...")
  → window_store.mark_window_created(window_id)
  ↓
Claude Code starts → hook writes to session_map.json:
  {"cclark:@12": {"session_id": "abc-123", "cwd": "/project", ...}}
  ↓
_session_monitor._detect_and_cleanup_changes()
  → session_lifecycle.reconcile(current_map)
      last = {}   →   current = {"cclark:@12": {"session_id": "abc-123", ...}}
      old_windows = {}, current_windows = {"cclark:@12"}
      current_windows - old_windows = {"cclark:@12"}
      → result.new_windows["cclark:@12"] = {...}
      → _last_session_map = current_map
      ← ReconcileResult(new_windows={"cclark:@12": ...})
  ↓
On new window:
  → session_manager.set_window_provider(window_id, provider_name)
  → _new_window_callback(NewWindowEvent(window_id="@12", session_id="abc-123", ...))
  → window_store.get_window_state("@12").session_id = "abc-123"
  → _schedule_save()
```

### Session Teardown (explicit kill)

```
gateway.kill_window(window_id)
  → channel_router.unbind_window(window_id)
  → window_store.remove_created_window(window_id)
  → window_store.remove_window(window_id)
  → tmux_manager.kill_window(window_id)
      → tmux kill-window @N
  ↓
No further action needed — the session_map entry persists but the window is gone.
On next reconcile: window disappears from session_map → sessions_to_remove includes session_id.
```

### Orphan Detection

```
gateway.list_orphaned_agent_windows()
  → bound_wids = channel_router.bound_window_ids()
  → state_wids = set(window_store.iter_window_ids())
  → managed_wids = bound_wids | state_wids | window_store.get_created_windows()
  → for window in tmux_manager.list_windows():
        if window not in managed_wids and window.pane_current_command == "claude":
              → orphan
```

Orphans are windows that are **alive in tmux** but have **no channel binding and no state record**. They represent either:
- Windows started outside cclark
- Windows left orphaned after a crash

The gateway does not auto-kill orphans — it returns them for the frontend to present to the user.

### Startup Cleanup

```
UnifiedICC.start()
  → _startup_cleanup()
      1. For each window in window_store.get_created_windows():
             If not live in tmux → remove_created_window()
      2. For each bound window:
             If not live in tmux → unbind + remove_window
             If live → populate missing fields (cwd, provider, channel_id)
                         mark_window_created()
      3. For each window in window_states with no binding:
             → tmux_manager.kill_window(wid)
             → remove_window
             → remove_created_window
      This handles the case where cclark was killed while a session was active.
```

### Hook Event → Lifecycle Mutation

```
events.jsonl → read_new_events() → _hook_event_callback(HookEvent)
  ↓
session_lifecycle.handle_<event_type>(...)
  SessionEnd          → handle_session_end(window_id)
  SubagentStart       → handle_subagent_start(window_id, subagent_id, name)
  SubagentStop        → handle_subagent_stop(window_id, subagent_id)
  TaskCompleted       → handle_task_completed(window_id, session_id, task_id, subject)
  Notification+Wait   → handle_notification_wait(window_id, wait_header)
  Stop                → handle_stop_task_state(window_id)
```

## 5. State Files

| File | Written by | Read by |
|---|---|---|
| `~/.cclark/state.json` | `window_store`, `channel_router` | `_startup_cleanup` |
| `~/.cclark/session_map.json` | Claude Code hook, `session_map_sync` | `reconcile()` via `_load_current_session_map` |

`_last_session_map` is held in memory only — it is the "previous" snapshot for the next reconcile. It is not persisted; on restart it starts empty and is populated from `session_map.json`.

## 6. Error Handling

`reconcile()` is idempotent in the sense that missing keys in `_last_session_map` are treated as new windows (no error). All mutations are wrapped in try/except at the caller (`session_monitor._detect_and_cleanup_changes()`) so a single bad session does not crash the loop.

## 7. Design Decisions

### Why `_created_windows`?

`window_store._created_windows` tracks which windows cclark created via `create_window()`. This set guards two critical safety checks:

1. **Fallback scan guard**: The session monitor's fallback filesystem scan only links sessions to windows in `_created_windows`. Without this guard, the cclark development session itself could be matched to an unrelated session file, creating a feedback loop.

2. **Orphan detection**: `list_orphaned_agent_windows()` explicitly excludes `_created_windows` to avoid flagging cclark's own sessions as orphans.

### Why session ID changes trigger cleanup?

If a window's `session_id` changes (user ran `/exit` and started a new session in the same window), `reconcile()` adds the old session to `sessions_to_remove` and registers the new window as `new_windows`. The old session's idle tracker and task state are cleared, preventing stale data from leaking into the new session.

### Relationship with ChannelRouter

`SessionLifecycle` does not import or call `ChannelRouter` directly. It communicates session-to-window mappings through `window_store.get_window_state()` and `window_store.find_window_by_session()`. `ChannelRouter` is owned by the gateway layer.

### Related Documents

- `module-gateway-core.md` — `UnifiedICC.kill_window()`, `kill_channel_windows()`, `list_orphaned_agent_windows()` all delegate to this module
- `module-session-monitor.md` — calls `session_lifecycle.reconcile()` and processes `ReconcileResult`
- `module-state-persistence.md` — `window_store._created_windows` is persisted in `state.json`
