# Module: Providers

> The pluggable agent provider system: `AgentProvider` protocol, per-provider implementations, and the `ProviderRegistry`.

---

## 1. Purpose

Each supported AI coding agent CLI (Claude Code, Codex, Gemini, Pi, Shell) is wrapped by a provider class that implements the `AgentProvider` protocol. Providers normalize transcript formats, terminal status parsing, launch commands, and capability flags into a unified interface so the gateway and frontend adapters remain provider-agnostic.

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  ProviderRegistry (singleton)                 │
│   register(name, cls) / get(name) → AgentProvider            │
└──────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────┐
│                    AgentProvider (Protocol)                   │
│                                                              │
│   @property capabilities: ProviderCapabilities                │
│   make_launch_args(resume_id, use_continue) → str            │
│   parse_hook_payload(payload) → SessionStartEvent | None    │
│   parse_transcript_line(line) → dict | None                 │
│   parse_transcript_entries(entries, pending_tools, cwd)      │
│       → (list[AgentMessage], dict)                          │
│   parse_terminal_status(pane_text) → StatusUpdate | None     │
│   extract_bash_output(pane_text, command) → str | None        │
│   discover_commands(base_dir) → list[DiscoveredCommand]      │
│   ...                                                        │
└──────────────────────────────────────────────────────────────┘
          │
          ├──────────────────────────────┐
          ▼                              ▼
┌─────────────────────────┐  ┌─────────────────────────────────┐
│      ClaudeProvider     │  │        JsonlProvider (base)     │
│  Hook-based sessions    │  │  (subclass for Codex, Gemini, Pi)│
│  JSONL transcript       │  └─────────────────────────────────┘
│  Terminal status parse  │              │
│  /continue support      │              ├──────────────────────┐
│  Task tracking          │              ▼                      ▼
│  Mailbox delivery       │     ┌──────────────┐    ┌──────────────┐
└─────────────────────────┘     │ CodexProvider│    │GeminiProvider│
                                │  JSONL       │    │  JSONL       │
                                └──────────────┘    │  pane_title  │
                                                    └──────────────┘
                                                              │
                                ┌──────────────────────────────┘
                                ▼
                          ┌──────────────┐
                          │ PiProvider   │
                          │  JSONL       │
                          └──────────────┘

                    ┌────────────────────┐
                    │  ShellProvider     │
                    │  Plain transcript  │
                    │  no hook/mailbox   │
                    └────────────────────┘
```

## 3. Key Components

### 3.1 `AgentProvider` Protocol

Defined in `providers/base.py` as a Python `Protocol`. All providers must implement:

```python
class AgentProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def make_launch_args(
        self, resume_id: str | None = None, use_continue: bool = False
    ) -> str: ...

    def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None: ...

    def parse_transcript_line(self, line: str) -> dict[str, Any] | None: ...

    def read_transcript_file(
        self, file_path: str, last_offset: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def parse_transcript_entries(
        self, entries: list[dict[str, Any]], pending_tools: dict[str, Any],
        cwd: str | None = None,
    ) -> tuple[list[AgentMessage], dict[str, Any]]: ...

    def parse_terminal_status(
        self, pane_text: str, *, pane_title: str = ""
    ) -> StatusUpdate | None: ...

    def extract_bash_output(self, pane_text: str, command: str) -> str | None: ...

    def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool: ...

    def parse_history_entry(self, entry: dict[str, Any]) -> AgentMessage | None: ...

    def discover_transcript(
        self, cwd: str, window_key: str, *, max_age: float | None = None
    ) -> SessionStartEvent | None: ...

    def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]: ...

    def build_status_snapshot(
        self, transcript_path: str, *, display_name: str = "",
        session_id: str = "", cwd: str = ""
    ) -> str | None: ...

    async def scrape_current_mode(self, window_id: str) -> str | None: ...

    async def seed_task_state(
        self, window_id: str, session_id: str, transcript_path: str
    ) -> None: ...
```

### 3.2 `ProviderCapabilities` dataclass

Declared by each provider to advertise supported features:

```python
@dataclass
class ProviderCapabilities:
    name: str
    launch_command: str
    supports_hook: bool = False          # Claude Code: True
    supports_hook_events: bool = False  # SessionStart, Stop, TaskCompleted, …
    hook_event_types: tuple[str, ...] = ()
    supports_resume: bool = False        # --resume <id>
    supports_continue: bool = False      # /continue
    supports_structured_transcript: bool = False  # JSONL vs plain
    supports_incremental_read: bool = True        # byte-offset reads
    transcript_format: Literal["jsonl", "plain"] = "jsonl"
    uses_pane_title: bool = False        # Gemini sets terminal title for state
    builtin_commands: tuple[str, ...] = ()
    supports_user_command_discovery: bool = False
    supports_status_snapshot: bool = False
    supports_mailbox_delivery: bool = True
    chat_first_command_path: bool = False  # Shell: cwd must come before command
    has_yolo_confirmation: bool = False    # Provider has a --dangerously-skip flag
    supports_task_tracking: bool = False   # Claude Code: TaskCompleted events
```

### 3.3 `ProviderRegistry`

Maps provider name strings to provider classes. Instances are cached on first access.

```python
registry = ProviderRegistry()

registry.register("claude", ClaudeProvider)
registry.register("codex", CodexProvider)
registry.register("gemini", GeminiProvider)
registry.register("pi", PiProvider)
registry.register("shell", ShellProvider)

provider = registry.get("claude")  # returns cached instance
```

### 3.4 Provider Comparison

| Capability | Claude | Codex | Gemini | Pi | Shell |
|---|---|---|---|---|---|
| `supports_hook` | True | False | False | False | False |
| `supports_hook_events` | True | False | False | False | False |
| `supports_resume` | True | True | True | True | False |
| `supports_continue` | True | False | False | True | False |
| `supports_incremental_read` | True | True | False | True | False |
| `transcript_format` | JSONL | JSONL | JSONL | JSONL | plain |
| `uses_pane_title` | False | False | True | False | False |
| `supports_task_tracking` | True | False | False | False | False |
| `supports_mailbox_delivery` | True | False | False | False | False |
| `has_yolo_confirmation` | True | True | True | False | False |

## 4. Key Data Flows

### Launching Claude Code

```
gateway.create_window(provider="claude")
  → resolve_launch_command("claude", approval_mode="normal")
      "claude" + " --permission-mode default"
  → tmux_manager.create_window(
        launch_command="claude --permission-mode default",
        start_agent=True
    )
  → Claude starts → hook fires → session_map.json written
```

### Launching with YOLO Mode

```
resolve_launch_command("claude", approval_mode="yolo")
  → if "--dangerously-skip-permissions" not in command:
       return "claude --dangerously-skip-permissions"
```

### Detecting a Provider from Pane State

```
tmux_manager.list_windows()
  → window.pane_current_command = "claude"
  → detect_provider_from_command("claude")  → "claude"
  → detect_provider_from_transcript_path(path)  → "claude"
  → detect_provider_from_runtime(command, pane_title="icc:claude")  → "claude"
```

### Transcript Parsing

```
TranscriptReader._process_session_file()
  → provider.parse_transcript_line(line)   # raw JSON dict or None
  → provider.parse_transcript_entries(
        entries, pending_tools, cwd
    )   → (list[AgentMessage], updated_pending_tools)
  → for msg in AgentMessage:
        emit NewMessage(session_id, text, is_complete, content_type, ...)
```

### Terminal Status Parsing (Claude only)

```
tmux_manager.capture_pane(window_id)
  → provider.parse_terminal_status(pane_text)
      → extract_interactive_content(pane_text)   # Permission, AskUser, Plan, …
          → StatusUpdate(raw_text, display_label, is_interactive=True, ui_type=…)
      → parse_status_block(pane_text)           # Working / Thinking / ...
          → StatusUpdate(raw_text, display_label)
```

## 5. Provider-Specific Details

### ClaudeProvider

- **Hook**: writes `session_map.json` and `events.jsonl`
- **Transcript**: `~/.claude/projects/<project-id>/sessions/<session-id>/transcript.jsonl`
- **Session start**: `SessionStart` hook event with `session_id`, `cwd`, `transcript_path`, `window_key`
- **Status**: parses both interactive UI blocks (`[Permission]`, `[AskUser]`, `[Plan]`) and inline status lines
- **`/continue`**: implemented via `make_launch_args(use_continue=True)` returning `"--continue"`
- **Task tracking**: `handle_task_completed()` → `claude_task_state.mark_task_completed()`
- **Mailbox**: `providers/mailbox.py` delivers messages between sessions

### JsonlProvider (base for Codex, Gemini, Pi)

Abstract base providing JSONL parsing helpers. Subclasses override `_CAPS` and `_BUILTINS` and implement `discover_transcript()` if they support filesystem-based session discovery.

### CodexProvider

- **No hook**: sessions are registered via `write_hookless_session_map()` after filesystem discovery
- **Transcript**: `~/.codex/sessions/<session-id>/transcript.jsonl`
- **Detection**: pane command `codex`, transcript path `/.codex/sessions/`

### GeminiProvider

- **No hook**: sessions registered via `write_hookless_session_map()`
- **Pane title**: uses OSC escape sequences to broadcast state via `tmux display-message -p '#{pane_title}'`
- **`requires_pane_title_for_detection`**: returns `True` — pane title is the only detection signal
- **Transcript**: whole-file reads only (`supports_incremental_read = False`)

### PiProvider

- **No hook**: sessions registered via `write_hookless_session_map()`
- **Transcript**: `~/.pi/agent/sessions/<session-id>/transcript.jsonl`
- **Builtins**: `clear`, `help`, `resume`

### ShellProvider

- **Plain transcript**: no structured transcript file
- **Command path**: `chat_first_command_path = True` — the working directory must precede the command text
- **No mailbox**: `supports_mailbox_delivery = False`
- **No hook**

## 6. State Files

Providers do not directly own state files. Session metadata is stored in:
- `~/.unified-icc/session_map.json` — hook-written session metadata (Claude only)
- `~/.unified-icc/state.json` — provider_name stored per window in `WindowState`

## 7. Error Handling

- `parse_transcript_line()`: returns `None` for malformed JSON — caller skips the line silently
- `parse_transcript_entries()`: returns empty list on parse failure
- `discover_transcript()`: returns `None` when no session file is found
- `make_launch_args()`: raises `ValueError` for invalid `resume_id` format (UUID pattern check)

## 8. Design Decisions

### Why a Protocol, Not an ABC?

The `AgentProvider` is a `Protocol` (structural subtyping via `typing.Protocol`). This avoids a rigid inheritance hierarchy and makes it trivial to add a new provider: just implement the methods and `register()` it. No base class modification needed.

### Why `JsonlProvider` as a Concrete Base?

Codex, Gemini, and Pi share the same JSONL line format. Rather than repeating the parsing logic in each class, `JsonlProvider` provides concrete implementations for `parse_transcript_line()`, `parse_transcript_entries()`, `parse_history_entry()`, and `discover_commands()`. Each subclass only overrides `_CAPS` and `_BUILTINS`.

### Why `--permission-mode default`?

Claude Code blocks on a first-run consent prompt without it. The Feishu/Telegram frontend has no access to the terminal, so the prompt would hang the session silently. `--permission-mode default` auto-accepts the default response for all permission prompts.

### Why Session ID Detection via `/status`?

Claude Code's hook reliably writes `session_map.json`, but Codex, Gemini, and Pi have no hook. For these providers, `TranscriptReader._scan_projects_sync()` discovers sessions by scanning the filesystem. The `session_id` is extracted from the directory name.

### Related Documents

- `module-gateway-core.md` — `UnifiedICC.create_window()` calls `resolve_launch_command()`
- `module-session-monitor.md` — uses provider's `parse_transcript_line()`, `parse_terminal_status()`
- `module-session-lifecycle.md` — hook event handling calls provider-specific handlers
- `module-state-persistence.md` — `WindowState.provider_name` selects which provider instance is used
