"""Claude Code provider — wraps existing modules behind AgentProvider protocol.

Wraps transcript_parser, terminal_parser, and claude_task_state to satisfy
the AgentProvider protocol. Supports hooks, task tracking, and incremental
JSONL transcript reads.
"""

from __future__ import annotations

from typing import Any

import structlog

from unified_icc.cc_commands import CC_BUILTINS
from unified_icc.providers.base import UUID_RE
from unified_icc.providers.base import (
    AgentMessage,
    DiscoveredCommand,
    ProviderCapabilities,
    SessionStartEvent,
    StatusUpdate,
)
from unified_icc.terminal_parser import (
    extract_bash_output,
    extract_interactive_content,
    format_status_display,
    parse_status_block,
)

_log = structlog.get_logger(__name__)


class ClaudeProvider:
    """Claude Code provider implementation."""

    _CAPS = ProviderCapabilities(
        name="claude",
        launch_command="claude",
        supports_hook=True,
        supports_hook_events=True,
        hook_event_types=(
            "SessionStart", "Notification", "Stop", "StopFailure",
            "SessionEnd", "SubagentStart", "SubagentStop",
            "TeammateIdle", "TaskCompleted",
        ),
        supports_resume=True,
        supports_continue=True,
        supports_structured_transcript=True,
        supports_incremental_read=True,
        transcript_format="jsonl",
        uses_pane_title=False,
        builtin_commands=tuple(CC_BUILTINS.keys()),
        supports_user_command_discovery=True,
        supports_status_snapshot=True,
        supports_mailbox_delivery=True,
        supports_task_tracking=True,
    )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._CAPS

    def make_launch_args(self, resume_id: str | None = None, use_continue: bool = False) -> str:
        if use_continue:
            return "--continue"
        if resume_id:
            if not UUID_RE.match(resume_id):
                raise ValueError(f"Invalid resume_id: {resume_id!r}")
            return f"--resume {resume_id}"
        return ""

    def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None:
        session_id = payload.get("session_id", "")
        if not session_id or not UUID_RE.match(session_id):
            return None
        cwd = payload.get("cwd", "")
        transcript_path = payload.get("transcript_path", "")
        window_key = payload.get("window_key", "")
        if not window_key:
            return None
        return SessionStartEvent(
            session_id=session_id,
            cwd=cwd,
            transcript_path=transcript_path,
            window_key=window_key,
        )

    def parse_transcript_line(self, line: str) -> dict[str, Any] | None:
        from unified_icc.transcript_parser import TranscriptParser
        return TranscriptParser.parse_line(line)

    def read_transcript_file(self, file_path: str, last_offset: int) -> tuple[list[dict[str, Any]], int]:
        from unified_icc.transcript_parser import TranscriptParser
        return TranscriptParser.read_file(file_path, last_offset)  # type: ignore[return-value]

    def parse_transcript_entries(
        self, entries: list[dict[str, Any]], pending_tools: dict[str, Any],
        cwd: str | None = None,
    ) -> tuple[list[AgentMessage], dict[str, Any]]:
        from unified_icc.transcript_parser import TranscriptParser
        return TranscriptParser.parse_entries(entries, pending_tools, cwd=cwd)  # type: ignore[return-value]

    def parse_terminal_status(self, pane_text: str, *, pane_title: str = "") -> StatusUpdate | None:
        content = extract_interactive_content(pane_text)
        if content:
            return StatusUpdate(
                raw_text=content.content,
                display_label=content.name,
                is_interactive=True,
                ui_type=content.name,
            )
        status_block = parse_status_block(pane_text)
        if status_block:
            return StatusUpdate(
                raw_text=status_block,
                display_label=format_status_display(status_block),
            )
        return None

    def extract_bash_output(self, pane_text: str, command: str) -> str | None:
        return extract_bash_output(pane_text, command)

    def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool:
        return entry.get("type") == "user"

    def parse_history_entry(self, entry: dict[str, Any]) -> AgentMessage | None:
        from unified_icc.transcript_parser import TranscriptParser
        return TranscriptParser.parse_history_entry(entry)

    def discover_transcript(self, cwd: str, window_key: str, *, max_age: float | None = None) -> SessionStartEvent | None:  # noqa: ARG002
        return None

    def requires_pane_title_for_detection(self, pane_current_command: str) -> bool:  # noqa: ARG002
        return False

    def detect_from_pane_title(self, pane_current_command: str, pane_title: str) -> bool:  # noqa: ARG002
        return False

    def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]:  # noqa: ARG002
        return [DiscoveredCommand(name=name, description=desc, source="builtin") for name, desc in CC_BUILTINS.items()]

    def build_status_snapshot(self, transcript_path: str, *, display_name: str = "", session_id: str = "", cwd: str = "") -> str | None:  # noqa: ARG002
        return None

    def has_output_since(self, transcript_path: str, offset: int) -> bool:  # noqa: ARG002
        return False

    async def scrape_current_mode(self, window_id: str) -> str | None:  # noqa: ARG002
        return None

    async def seed_task_state(self, window_id: str, session_id: str, transcript_path: str) -> None:
        from unified_icc.claude_task_state import claude_task_state
        entries_data = self.read_transcript_file(transcript_path, 0)[0]
        claude_task_state.rebuild_from_entries(window_id, session_id, entries_data)

    def apply_task_entries(self, window_id: str, session_id: str, entries: list[dict]) -> None:
        from unified_icc.claude_task_state import claude_task_state
        claude_task_state.apply_entries(window_id, session_id, entries)
