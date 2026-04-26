# Providers

Unified ICC supports multiple AI coding agent providers through a unified abstraction.

## Supported Providers

| Provider | Package | Launch Command |
|----------|---------|----------------|
| Claude | `claude-code` | `claude` |
| Codex | `codex` | `codex` |
| Gemini | `gemini` | `gemini` |
| Pi | `pi` | `pi` |
| Shell | — | interactive shell |

## Provider Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ProviderRegistry                        │
│  - get(provider_name) → AgentProvider                       │
│  - is_valid(provider_name) → bool                           │
│  - provider_names() → list[str]                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   AgentProvider Protocol                     │
│  (all providers implement this interface)                   │
│                                                              │
│  @property capabilities → ProviderCapabilities               │
│  make_launch_args() → str                                    │
│  parse_hook_payload() → SessionStartEvent | None            │
│  parse_transcript_line() → dict | None                      │
│  read_transcript_file() → (entries, offset)                  │
│  parse_transcript_entries() → (messages, pending_tools)      │
│  parse_terminal_status() → StatusUpdate | None              │
│  extract_bash_output() → str | None                         │
│  discover_transcript() → SessionStartEvent | None           │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ ClaudeProvider│      │ CodexProvider│      │ GeminiProvider│
│             │      │             │      │             │
│ JSONL       │      │ Plain text  │      │ JSONL       │
│ Session hooks│     │ No hooks    │      │ No hooks    │
└─────────────┘      └─────────────┘      └─────────────┘
```

## AgentProvider Protocol

```python
class AgentProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities:
        """What features this provider supports."""
        ...

    def make_launch_args(
        self,
        resume_id: str | None = None,
        use_continue: bool = False,
    ) -> str:
        """Build launch command arguments."""
        ...

    def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None:
        """Parse SessionStart hook payload."""
        ...

    def parse_transcript_line(self, line: str) -> dict[str, Any] | None:
        """Parse a single transcript line."""
        ...

    def read_transcript_file(
        self,
        file_path: str,
        last_offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Read new entries from transcript file."""
        ...

    def parse_transcript_entries(
        self,
        entries: list[dict[str, Any]],
        pending_tools: dict[str, Any],
        cwd: str | None = None,
    ) -> tuple[list[AgentMessage], dict[str, Any]]:
        """Convert parsed entries to AgentMessage objects."""
        ...

    def parse_terminal_status(
        self,
        pane_text: str,
        *,
        pane_title: str = "",
    ) -> StatusUpdate | None:
        """Parse status from terminal pane."""
        ...

    def extract_bash_output(
        self,
        pane_text: str,
        command: str,
    ) -> str | None:
        """Extract bash command output from pane."""
        ...

    def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool:
        """Check if entry is from user."""
        ...

    def discover_transcript(
        self,
        cwd: str,
        window_key: str,
        *,
        max_age: float | None = None,
    ) -> SessionStartEvent | None:
        """Find transcript for cwd."""
        ...

    def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]:
        """Discover available commands/skills."""
        ...

    def build_status_snapshot(
        self,
        transcript_path: str,
        *,
        display_name: str,
        session_id: str = "",
        cwd: str = "",
    ) -> str | None:
        """Build status line for snapshot."""
        ...
```

## ProviderCapabilities

Each provider declares its capabilities:

```python
@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    name: str                           # Provider name
    launch_command: str                 # CLI launch command
    supports_hook: bool = False         # Has hook integration
    supports_hook_events: bool = False   # Has hook event types
    hook_event_types: tuple[str, ...] = ()  # Available hook types
    supports_resume: bool = False       # Can resume sessions
    supports_continue: bool = False     # Has /continue command
    supports_structured_transcript: bool = False  # JSONL vs plain
    supports_incremental_read: bool = True  # Can read incrementally
    transcript_format: str = "jsonl"     # "jsonl" or "plain"
    uses_pane_title: bool = False        # Uses terminal title
    builtin_commands: tuple[str, ...] = ()   # Built-in commands
    supports_user_command_discovery: bool = False  # Can discover skills
    supports_status_snapshot: bool = False  # Can build status snapshot
    supports_mailbox_delivery: bool = True  # Mailbox support
    chat_first_command_path: bool = False  # /command path format
    has_yolo_confirmation: bool = False  # Has --dangerously-skip flag
    supports_task_tracking: bool = False  # Task tracking support
```

## Provider Comparison

| Feature | Claude | Codex | Gemini | Pi |
|---------|--------|-------|--------|-----|
| Hook events | ✅ | ❌ | ❌ | ❌ |
| JSONL transcript | ✅ | ❌ | ✅ | ✅ |
| Resume sessions | ✅ | ❌ | ❌ | ❌ |
| /continue | ✅ | ❌ | ❌ | ❌ |
| Status snapshot | ✅ | ❌ | ❌ | ❌ |
| Yolo mode | ✅ `--dangerously-skip-permissions` | ✅ `--dangerously-bypass` | ✅ `--yolo` | ❌ |
| Task tracking | ✅ | ❌ | ❌ | ❌ |
| Command discovery | ✅ | ❌ | ❌ | ❌ |

## Using Providers

### Get Provider by Name

```python
from unified_icc.providers import get_provider, registry

# Get default provider (from config)
provider = get_provider()
print(provider.capabilities.name)  # "claude"

# Get specific provider
claude = registry.get("claude")
codex = registry.get("codex")
```

### Check Provider Validity

```python
from unified_icc.providers import registry

if registry.is_valid("claude"):
    provider = registry.get("claude")
```

### List Available Providers

```python
from unified_icc.providers import registry

for name in registry.provider_names():
    caps = registry.get(name).capabilities
    print(f"{name}: {caps.launch_command}")
```

### Resolve Launch Command

```python
from unified_icc.providers import resolve_launch_command

# Normal mode
cmd = resolve_launch_command("claude")
# "claude"

# Yolo mode (skip permissions)
cmd = resolve_launch_command("claude", approval_mode="yolo")
# "claude --dangerously-skip-permissions"
```

### Detect Provider

```python
from unified_icc.providers import (
    detect_provider_from_command,
    detect_provider_from_transcript_path,
    detect_provider_from_runtime,
)

# From running command
provider = detect_provider_from_command("/usr/local/bin/claude")
# "claude"

# From transcript path
provider = detect_provider_from_transcript_path("/home/user/.claude/projects/myproj/.claude/history/2025-01-15_123456.jsonl")
# "claude"

# From pane command and title
provider = detect_provider_from_runtime(
    pane_current_command="claude",
    pane_title="icc:claude",
)
# "claude"
```

## Implementing a Custom Provider

```python
from dataclasses import dataclass
from typing import Any
from unified_icc.providers.base import (
    AgentProvider,
    AgentMessage,
    ProviderCapabilities,
    SessionStartEvent,
    StatusUpdate,
    DiscoveredCommand,
)

class MyAgentProvider:
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="myagent",
            launch_command="myagent",
            supports_hook=False,
            transcript_format="jsonl",
        )

    def make_launch_args(
        self,
        resume_id: str | None = None,
        use_continue: bool = False,
    ) -> str:
        if resume_id:
            return f"--resume {resume_id}"
        return ""

    def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None:
        return None  # No hook support

    def parse_transcript_line(self, line: str) -> dict[str, Any] | None:
        import json
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def parse_transcript_entries(
        self,
        entries: list[dict[str, Any]],
        pending_tools: dict[str, Any],
        cwd: str | None = None,
    ) -> tuple[list[AgentMessage], dict[str, Any]]:
        messages = []
        for entry in entries:
            messages.append(AgentMessage(
                text=entry.get("text", ""),
                role=entry.get("role", "assistant"),
                content_type=entry.get("type", "text"),
            ))
        return messages, {}

    def parse_terminal_status(
        self,
        pane_text: str,
        *,
        pane_title: str = "",
    ) -> StatusUpdate | None:
        return None

    def extract_bash_output(self, pane_text: str, command: str) -> str | None:
        return None

    def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool:
        return entry.get("role") == "user"

    def discover_transcript(
        self,
        cwd: str,
        window_key: str,
        *,
        max_age: float | None = None,
    ) -> SessionStartEvent | None:
        return None

    def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]:
        return []

    def build_status_snapshot(
        self,
        transcript_path: str,
        *,
        display_name: str,
        session_id: str = "",
        cwd: str = "",
    ) -> str | None:
        return None
```
