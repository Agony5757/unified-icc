"""Provider abstractions for multi-agent CLI backends.

Re-exports the protocol, event types, capability dataclass, and registry.
Provides ``get_provider()`` for accessing the active provider singleton,
and ``resolve_capabilities()`` for lightweight CLI commands that don't
require GatewayConfig (doctor, status).
"""

import structlog
import os

from unified_icc.providers.base import (
    AgentMessage,
    AgentProvider,
    DiscoveredCommand,
    ProviderCapabilities,
    SessionStartEvent,
    StatusUpdate,
)
from unified_icc.providers.registry import UnknownProviderError, registry

logger = structlog.get_logger()

_APPROVAL_MODE_NORMAL = "normal"
_APPROVAL_MODE_YOLO = "yolo"
_YOLO_FLAGS: dict[str, str] = {
    "claude": "--dangerously-skip-permissions",
    "codex": "--dangerously-bypass-approvals-and-sandbox",
    "gemini": "--yolo",
}


def has_yolo_mode(provider_name: str) -> bool:
    return provider_name in _YOLO_FLAGS


_active: AgentProvider | None = None
_registered = False


def _ensure_registered() -> None:
    global _registered
    if _registered:
        return
    from unified_icc.providers.claude import ClaudeProvider
    from unified_icc.providers.codex import CodexProvider
    from unified_icc.providers.gemini import GeminiProvider
    from unified_icc.providers.pi import PiProvider
    from unified_icc.providers.shell import ShellProvider

    registry.register("claude", ClaudeProvider)
    registry.register("codex", CodexProvider)
    registry.register("gemini", GeminiProvider)
    registry.register("pi", PiProvider)
    registry.register("shell", ShellProvider)
    _registered = True


def get_provider() -> AgentProvider:
    global _active
    if _active is None:
        _ensure_registered()
        from unified_icc.config import config

        try:
            _active = registry.get(config.provider_name)
        except UnknownProviderError:
            logger.warning("Unknown provider %r, falling back to 'claude'", config.provider_name)
            _active = registry.get("claude")
    return _active


def _reset_provider() -> None:
    global _active, _registered
    _active = None
    _registered = False


def get_provider_for_window(_window_id: str, provider_name: str | None = None) -> AgentProvider:
    _ensure_registered()
    if provider_name and registry.is_valid(provider_name):
        return registry.get(provider_name)
    return get_provider()


def detect_provider_from_command(pane_current_command: str) -> str:
    cmd = pane_current_command.strip().lower()
    if not cmd:
        return ""
    basename = os.path.basename(cmd.split()[0])
    for name in ("claude", "codex", "gemini", "pi"):
        if basename == name or basename.startswith(name + "-"):
            return name
    from .shell import KNOWN_SHELLS
    if basename in KNOWN_SHELLS or basename.lstrip("-") in KNOWN_SHELLS:
        return "shell"
    return ""


def detect_provider_from_transcript_path(transcript_path: str) -> str:
    normalized = transcript_path.strip().lower().replace("\\", "/")
    if not normalized:
        return ""
    if "/.codex/sessions/" in normalized:
        return "codex"
    if "/.claude/projects/" in normalized:
        return "claude"
    if "/.gemini/" in normalized and "/chats/" in normalized:
        return "gemini"
    if "/.pi/agent/sessions/" in normalized:
        return "pi"
    return ""


_TITLE_PREFIX = "icc:"
_LEGACY_TITLE_PREFIX = "ccgram:"


def detect_provider_from_runtime(pane_current_command: str, *, pane_title: str = "") -> str:
    detected = detect_provider_from_command(pane_current_command)
    if detected or not pane_title:
        return detected
    for prefix in (_TITLE_PREFIX, _LEGACY_TITLE_PREFIX):
        if pane_title.startswith(prefix):
            stamped = pane_title[len(prefix):].strip()
            _ensure_registered()
            if registry.is_valid(stamped):
                return stamped
    _ensure_registered()
    for name in registry.provider_names():
        provider = registry.get(name)
        if provider.detect_from_pane_title(pane_current_command, pane_title):
            return provider.capabilities.name
    return ""


def resolve_launch_command(provider_name: str, *, approval_mode: str = _APPROVAL_MODE_NORMAL) -> str:
    _ensure_registered()
    provider = provider_name.lower()
    new_env = f"CCLARK_{provider.upper()}_COMMAND"
    mid_env = f"CCGRAM_{provider.upper()}_COMMAND"
    old_env = f"CCBOT_{provider.upper()}_COMMAND"
    override = os.environ.get(new_env) or os.environ.get(mid_env) or os.environ.get(old_env)
    if override:
        command = override
    else:
        try:
            command = registry.get(provider).capabilities.launch_command
        except UnknownProviderError:
            provider = "claude"
            command = registry.get("claude").capabilities.launch_command

    if approval_mode.lower() != _APPROVAL_MODE_YOLO:
        return command
    yolo_flag = _YOLO_FLAGS.get(provider)
    if not yolo_flag or yolo_flag in command:
        return command
    return f"{command} {yolo_flag}"


def resolve_capabilities(provider_name: str | None = None) -> ProviderCapabilities:
    _ensure_registered()
    name = (
        provider_name
        if provider_name is not None
        else (
            os.environ.get("CCLARK_PROVIDER")
            or os.environ.get("CCGRAM_PROVIDER")
            or os.environ.get("CCBOT_PROVIDER", "claude")
        )
    )
    try:
        return registry.get(name).capabilities
    except UnknownProviderError:
        return registry.get("claude").capabilities


__all__ = [
    "AgentMessage", "AgentProvider", "DiscoveredCommand", "ProviderCapabilities",
    "SessionStartEvent", "StatusUpdate", "UnknownProviderError",
    "detect_provider_from_command", "detect_provider_from_transcript_path",
    "detect_provider_from_runtime", "get_provider", "get_provider_for_window",
    "has_yolo_mode", "registry", "resolve_capabilities", "resolve_launch_command",
]
