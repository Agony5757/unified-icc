"""Provider protocol and shared event types for multi-agent CLI backends.

Pure definitions only — no imports from existing unified_icc modules to avoid
circular dependencies. Every agent provider (Claude, Codex, Gemini) must
satisfy the ``AgentProvider`` protocol.

Event types:
  - SessionStartEvent: emitted when a new session is detected
  - AgentMessage: a parsed message from the agent's transcript
  - StatusUpdate: a parsed terminal status line

Capability descriptor:
  - ProviderCapabilities: declares what features the provider supports
"""

import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

# ── Type aliases for AgentMessage fields ─────────────────────────────────
MessageRole = Literal["user", "assistant"]
ContentType = Literal["text", "thinking", "tool_use", "tool_result", "local_command"]

# ── Shared validation ────────────────────────────────────────────────────
RESUME_ID_RE = re.compile(r"^[\w-]+$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# ── Event types ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionStartEvent:
    """Emitted when a provider session starts or is detected via hook."""

    session_id: str
    cwd: str
    transcript_path: str
    window_key: str


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """A single parsed message from the agent's transcript.

    Attributes:
        text: The rendered text content.
        role: "user" or "assistant".
        content_type: "text", "thinking", "tool_use", "tool_result", "local_command".
        is_complete: Whether the message is fully rendered (vs streaming).
        tool_use_id: ID linking a tool_use to its result.
        tool_name: Name of the tool for tool_use entries.
    """

    text: str
    role: MessageRole
    content_type: ContentType
    is_complete: bool = True
    phase: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    """Parsed terminal status line from the agent's pane.

    Attributes:
        raw_text: The full raw status text.
        display_label: A short human-readable label.
        is_interactive: True when an interactive UI (ask, approve, plan) is shown.
        ui_type: Name of the UI type when interactive.
    """

    raw_text: str
    display_label: str
    is_interactive: bool = False
    ui_type: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredCommand:
    """A command/skill discovered by a provider."""

    name: str
    description: str
    source: Literal["builtin", "skill", "command"]


# ── Hook events ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HookEvent:
    """A structured event from the hook event log (events.jsonl)."""

    event_type: str
    window_key: str
    session_id: str
    data: dict[str, Any]
    timestamp: float


# ── Capabilities ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Declares which features a provider supports.

    Attributes:
        name: Provider name (e.g. "claude", "codex", "gemini").
        launch_command: CLI command used to start the agent.
        supports_hook: Whether the provider emits session_map.json entries.
        supports_incremental_read: Whether the transcript can be read byte-by-byte.
        transcript_format: "jsonl" or "plain".
        builtin_commands: Tuple of built-in slash commands.
        supports_task_tracking: Whether TaskCreate/TaskUpdate are parsed.
    """

    name: str
    launch_command: str
    supports_hook: bool = False
    supports_hook_events: bool = False
    hook_event_types: tuple[str, ...] = ()
    supports_resume: bool = False
    supports_continue: bool = False
    supports_structured_transcript: bool = False
    supports_incremental_read: bool = True
    transcript_format: Literal["jsonl", "plain"] = "jsonl"
    uses_pane_title: bool = False
    builtin_commands: tuple[str, ...] = ()
    supports_user_command_discovery: bool = False
    supports_status_snapshot: bool = False
    supports_mailbox_delivery: bool = True
    chat_first_command_path: bool = False
    has_yolo_confirmation: bool = False
    supports_task_tracking: bool = False


# ── Provider protocol ────────────────────────────────────────────────────


class AgentProvider(Protocol):
    """Protocol that every agent CLI provider must satisfy.

    Implementations (ClaudeProvider, CodexProvider, etc.) wrap provider-specific
    I/O (transcript files, pane captures) behind a uniform interface used by
    the gateway and monitor.
    """

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def make_launch_args(
        self,
        resume_id: str | None = None,
        use_continue: bool = False,
    ) -> str: ...

    def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None: ...

    def parse_transcript_line(self, line: str) -> dict[str, Any] | None: ...

    def read_transcript_file(
        self, file_path: str, last_offset: int
    ) -> tuple[list[dict[str, Any]], int]: ...

    def parse_transcript_entries(
        self,
        entries: list[dict[str, Any]],
        pending_tools: dict[str, Any],
        cwd: str | None = None,
    ) -> tuple[list[AgentMessage], dict[str, Any]]: ...

    def parse_terminal_status(
        self, pane_text: str, *, pane_title: str = ""
    ) -> StatusUpdate | None: ...

    def extract_bash_output(self, pane_text: str, command: str) -> str | None: ...

    def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool: ...

    def parse_history_entry(self, entry: dict[str, Any]) -> AgentMessage | None: ...

    def discover_transcript(
        self,
        cwd: str,
        window_key: str,
        *,
        max_age: float | None = None,
    ) -> SessionStartEvent | None: ...

    def requires_pane_title_for_detection(self, pane_current_command: str) -> bool: ...

    def detect_from_pane_title(
        self, pane_current_command: str, pane_title: str
    ) -> bool: ...

    def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]: ...

    def build_status_snapshot(
        self,
        transcript_path: str,
        *,
        display_name: str,
        session_id: str = "",
        cwd: str = "",
    ) -> str | None: ...

    def has_output_since(self, transcript_path: str, offset: int) -> bool: ...

    async def scrape_current_mode(self, window_id: str) -> str | None:  # noqa: ARG002
        return None

    async def seed_task_state(  # noqa: ARG002
        self,
        window_id: str,
        session_id: str,
        transcript_path: str,
    ) -> None: ...

    def apply_task_entries(  # noqa: ARG002
        self,
        window_id: str,
        session_id: str,
        entries: list[dict],
    ) -> None: ...
