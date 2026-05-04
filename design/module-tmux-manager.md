# Module: Tmux Manager

> Thin async wrapper around libtmux for creating, inspecting, and killing tmux windows, and sending keystrokes to their panes.

---

## 1. Purpose

`tmux_manager.py` provides the only tmux I/O surface in the codebase. All other modules interact with tmux exclusively through this module. It wraps libtmux with async shims, handles pane-level keystroke delivery (including vim and shell mode quirks), and discovers external AI-agent windows running in other tmux sessions.

## 2. Architecture

```
┌──────────────────────────────────────────────┐
│              TmuxManager                     │
│                                              │
│  tmux session "cclark" (configurable)        │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ new_window  │  │ kill_window          │  │
│  │ rename      │  │ list_windows         │  │
│  └─────────────┘  └──────────────────────┘  │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ capture_pane│  │ send_keys             │  │
│  │ (plain/ANSI)│  │ (literal/raw/vim-fix)│  │
│  └─────────────┘  └──────────────────────┘  │
│  ┌─────────────────────────────────────────┐ │
│  │ discover_external_sessions              │ │
│  │ (scans all tmux sessions for agents)   │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
          │
          ▼
  libtmux.Server / tmux CLI subprocess
          │
          ▼
  tmux server → session → windows → panes
```

## 3. Key Components

### 3.1 `TmuxManager`

The central class. One instance (`tmux_manager`) is created at module load time using the configured session name.

```python
tmux_manager = TmuxManager()  # uses config.tmux_session_name
```

All blocking libtmux calls are wrapped with `asyncio.to_thread()`. Operations that are natively subprocess-based (e.g. ANSI capture, foreign-session send-keys) use `asyncio.create_subprocess_exec` directly.

#### Core Methods

| Method | Description |
|---|---|
| `ensure_session()` | Creates the tmux session if it does not already exist |
| `get_or_create_session()` | Returns existing session or creates a new one |
| `create_window(...)` | Creates a new tmux window; optionally launches an agent CLI |
| `kill_window(window_id)` | Kills a tmux window by ID |
| `list_windows()` | Returns `list[TmuxWindow]` for all windows in the session |
| `find_window_by_id(window_id)` | Looks up a single window by ID (handles foreign sessions) |
| `find_window_by_name(name)` | Looks up a single window by name |
| `capture_pane(window_id, with_ansi=False)` | Reads visible pane text |
| `capture_pane_scrollback(window_id, history=200)` | Reads pane text including scrollback |
| `capture_pane_raw(window_id)` | Returns raw ANSI text + pane dimensions |
| `send_keys(window_id, text, enter=True, literal=True, raw=False)` | Sends keystrokes |
| `rename_window(window_id, name)` | Renames a window |
| `discover_external_sessions()` | Scans all tmux sessions for AI agent windows |
| `stamp_pane_title(window_id, provider)` | Sets the pane title to `icc:<provider>` |

### 3.2 `TmuxWindow` dataclass

```python
@dataclass
class TmuxWindow:
    window_id: str           # e.g. "@0", "@12"
    window_name: str
    cwd: str                 # pane_current_path of the active pane
    pane_current_command: str # foreground process: "claude", "bash", etc.
    pane_tty: str            # TTY device, e.g. /dev/ttys003
    pane_width: int
    pane_height: int
```

### 3.3 `PaneInfo` dataclass

Returned by `list_panes(window_id)` for multi-pane inspection.

### 3.4 Window ID Model

Windows are identified by their **tmux window ID** (e.g. `@0`, `@12`), not by name. Window IDs are stable across tmux server restarts. Names can be changed by the user at any time and must never be used as keys.

Foreign windows — those belonging to external tmux sessions such as emdash — use a **qualified ID** of the form `session_name:@N` (e.g. `emdash-claude-main-abc:@0`). `window_resolver.is_foreign_window()` distinguishes these from native windows.

### 3.5 Vim Mode Handling

When Claude Code is running in a vim-enhanced terminal (e.g. via a vim plugin that overrides navigation keys), the pane may be in **NORMAL mode** instead of INSERT mode. Sending text directly would execute vim commands rather than inserting text.

`_ensure_vim_insert_mode()` detects this by:
1. Checking a per-window `_vim_state` cache (`True`/`False`/`None` = unknown)
2. If `False`: returns immediately (no vim, zero overhead)
3. If `True` or `None`: captures the pane and looks for `-- INSERT --` in the last 3 lines
4. If not found and state is `None` or was `True`: sends `i` (enter INSERT), waits 120ms, re-checks
5. If INSERT appeared: state = `True`, done
6. If still no INSERT: state = `False`, sends Backspace to undo the stray `i`

All vim-probe and send operations on the same window are serialized by a per-window `asyncio.Lock` (`_vim_locks`) to prevent interleaving.

### 3.6 `!` Command Mode

When a user command starts with `!`, `_send_literal_then_enter_locked()` sends `!` first to exit Claude Code's TUI back to the shell, waits 1 second for the shell to activate, then sends the rest of the command.

### 3.7 Foreign Window Support

Windows in external tmux sessions (emdash, other tools) are handled via subprocess calls to `tmux` rather than libtmux, since libtmux only operates on the local server. `_find_foreign_window()` queries `tmux list-windows` directly; `_pane_send_subprocess()` uses `tmux send-keys -t <qualified_id>`.

## 4. Data Flow

### Creating a Window

```
gateway.create_window(work_dir="/project", provider="claude")
  → tmux_manager.create_window(work_dir, launch_command="claude --permission-mode default")
      → ensure_session() / get_or_create_session()
      → session.new_window(window_name, start_directory=work_dir)
      → pane.send_keys("export ICC_WINDOW_ID=...")
      → pane.send_keys("export EDITOR=true VISUAL=true")
      → pane.send_keys("claude --permission-mode default", enter=True)
      ← returns (success, message, window_name, window_id)
```

`ICC_WINDOW_ID` is exported into the pane so that the launched agent can self-identify its window.

### Sending Text to a Window

```
gateway.send_to_window(window_id, "fix the login bug")
  → tmux_manager.find_window_by_id(window_id)
  → tmux_manager.send_keys(window_id, "fix the login bug")
      → _send_literal_then_enter(window_id, text)
          → _ensure_vim_insert_mode(window_id)   [cached, fast path]
          → pane.send_keys(text, enter=False, literal=True)
          → asyncio.sleep(0.5)                    [TUI settle delay]
          → pane.send_keys("", enter=True, literal=False)
      ← True / False
```

### Capturing Pane Text

```
gateway.capture_pane(window_id)
  → tmux_manager.capture_pane(window_id, with_ansi=False)
      → _capture_pane_plain(window_id) via asyncio.to_thread
          → libtmux: session.windows.get(window_id).active_pane.capture_pane()
      ← str or None
```

## 5. State Files

No state is persisted directly in `tmux_manager.py`. It only reads from and writes to the live tmux server. The session name comes from `config.tmux_session_name`. The `icc:<provider>` pane title is stamped on created windows but is not read back — it exists purely for human readability.

## 6. Error Handling

All `LibTmuxException`, `OSError`, and `subprocess.CalledProcessError` exceptions are caught and logged at `debug` or `warning` level. Operations return `False` or `None` on failure — they do not raise. This keeps the monitor loop robust against transient tmux unavailability.

```
TmuxManager._reset_server()   # sets _server = None to force reconnect on next use
```

The server handle is reset after any exception during pane capture or key-sending to avoid stale-object errors.

## 7. Design Decisions

### Async Wrapper over libtmux

libtmux is synchronous. Rather than importing it at the top level, every operation that touches tmux runs in `asyncio.to_thread()`. This keeps the gateway fully async and avoids blocking the event loop, even during slow tmux operations.

### Literal vs Raw Sending

`sender_keys(literal=True)` sends characters as-is (safe for user text). `literal=False` interprets tmux key names (`Up`, `Down`, `Escape`, `C-u`, `BSpace`) — needed for control sequences sent by the session monitor when probing status.

`raw=True` bypasses all TUI workarounds (vim detection, `!` prefix splitting, Enter delay) and is used exclusively for sending control keys in the monitor loop.

### Pane Title Stamping

`stamp_pane_title()` uses `tmux select-pane -T` instead of `send-keys` to set the title. This avoids injecting the title string into the agent's input buffer.

### External Session Discovery

`discover_external_sessions()` runs on every poll cycle and caches results for 10 seconds to avoid spawning N subprocess calls per cycle. It scans **all** tmux sessions (not just the configured one) for windows whose active pane runs a known AI agent process (`claude`, `codex`, `gemini`, `pi`). This enables the monitor to observe sessions started outside cclark.

### Related Documents

- `module-gateway-core.md` — `UnifiedICC` calls `tmux_manager` for all window operations
- `module-session-lifecycle.md` — window creation is the first step of session creation; orphan detection calls `list_windows()`
- `module-session-monitor.md` — uses `capture_pane()` to read terminal status and `discover_external_sessions()` to find external windows
