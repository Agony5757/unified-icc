"""Gateway configuration — no messaging platform tokens.

Loads tmux/monitoring paths and intervals from environment variables
(with .env support). No TELEGRAM_BOT_TOKEN or similar is required.

Key class: GatewayConfig (singleton instantiated as `config`).
"""

import structlog
import os
from pathlib import Path

from dotenv import load_dotenv

from ..utils.utils import unified_icc_dir

logger = structlog.get_logger()


def _env_with_fallback(new_name: str, old_name: str, older_name: str = "", default: str = "") -> str:
    """Read env var with fallback to legacy names."""
    val = os.getenv(new_name)
    if val is not None:
        return val
    if old_name:
        val = os.getenv(old_name)
        if val is not None:
            logger.debug("Using legacy env var %s, prefer %s", old_name, new_name)
            return val
    if older_name:
        val = os.getenv(older_name)
        if val is not None:
            logger.warning("Using deprecated env var %s, use %s instead", older_name, new_name)
            return val
    return default


class GatewayConfig:
    """Gateway configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.config_dir = unified_icc_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        for env_path in (Path(".env"), self.config_dir / ".env"):
            if env_path.is_file():
                load_dotenv(env_path)
                logger.debug("Loaded env from %s", env_path.resolve())

        # Tmux
        self.tmux_session_name = os.getenv("TMUX_SESSION_NAME", "cclark")
        self.tmux_main_window_name = "__main__"
        self.own_window_id: str | None = None
        self.tmux_external_patterns = os.getenv("TMUX_EXTERNAL_PATTERNS", "")

        # State files
        self.state_file = self.config_dir / "state.json"
        self.session_map_file = self.config_dir / "session_map.json"
        self.monitor_state_file = self.config_dir / "monitor_state.json"
        self.events_file = self.config_dir / "events.jsonl"
        self.mailbox_dir = self.config_dir / "mailbox"

        # Claude session monitoring
        _claude_config_dir = os.getenv("CLAUDE_CONFIG_DIR")
        self.claude_config_dir = Path(_claude_config_dir).expanduser() if _claude_config_dir else Path.home() / ".claude"
        self.claude_projects_path = self.claude_config_dir / "projects"
        self.monitor_poll_interval = max(0.5, float(os.getenv("MONITOR_POLL_INTERVAL", "1.0")))
        self.status_poll_interval = max(0.5, float(_env_with_fallback(
            "CCLARK_STATUS_POLL_INTERVAL", "CCGRAM_STATUS_POLL_INTERVAL", default="1.0"
        )))

        # Provider
        self.provider_name = _env_with_fallback(
            "CCLARK_PROVIDER", "CCGRAM_PROVIDER", "CCBOT_PROVIDER", default="claude"
        )

        # API server
        self.api_host = os.getenv("ICC_API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("ICC_API_PORT", "8900"))
        self.api_key = os.getenv("ICC_API_KEY", "")

        # Autoclose
        self.autoclose_done_minutes = int(os.getenv("AUTOCLOSE_DONE_MINUTES", "30"))
        self.autoclose_dead_minutes = int(os.getenv("AUTOCLOSE_DEAD_MINUTES", "10"))


config = GatewayConfig()
