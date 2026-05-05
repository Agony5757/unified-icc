"""Gateway configuration — no messaging platform tokens.

Loads tmux/monitoring paths and intervals from environment variables
(with .env support). No TELEGRAM_BOT_TOKEN or similar is required.

Key class: GatewayConfig (singleton instantiated as `config`).
Also supports loading from config.yaml via UnifiedConfig.
"""

from __future__ import annotations

import os
import structlog
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from ..channels.feishu.config import FeishuAppConfig
from ..utils.utils import unified_icc_dir

logger = structlog.get_logger()


# ── Feishu channel config (loaded from config.yaml) ───────────────────────────


@dataclass
class FeishuChannelConfig:
    """Configuration for the Feishu channel backend."""

    apps: list[FeishuAppConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "FeishuChannelConfig":
        """Parse from a dict loaded from YAML."""
        apps = [FeishuAppConfig.from_dict(app) for app in data.get("apps", [])]
        return cls(apps=apps)


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
        self.tmux_session = os.getenv("TMUX_SESSION_NAME", "unified-icc")
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

        # API server
        self.api_host = os.getenv("ICC_API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("ICC_API_PORT", "8900"))
        self.api_key = os.getenv("ICC_API_KEY", "")

        # Autoclose
        self.autoclose_done_minutes = int(os.getenv("AUTOCLOSE_DONE_MINUTES", "30"))
        self.autoclose_dead_minutes = int(os.getenv("AUTOCLOSE_DEAD_MINUTES", "10"))


config = GatewayConfig()


# ── UnifiedConfig: YAML + env fallback ─────────────────────────────────────────


class UnifiedConfig:
    """Unified configuration from config.yaml with env var fallback.

    Loads from ~/.unified-icc/config.yaml if present, otherwise falls back
    to GatewayConfig behavior (env vars only).

    Merges gateway settings (tmux, monitoring, API) with channel configs
    (e.g., Feishu apps).
    """

    def __init__(self) -> None:
        self.config_dir = unified_icc_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Load .env files
        for env_path in (Path(".env"), self.config_dir / ".env"):
            if env_path.is_file():
                load_dotenv(env_path)
                logger.debug("Loaded env from %s", env_path.resolve())

        self.config_file = self.config_dir / "config.yaml"
        self._yaml_data: dict[str, Any] = {}

        # Gateway defaults from YAML or env
        self._load_gateway_settings()

        # Channel configs from YAML
        self.feishu: FeishuChannelConfig | None = None
        if self.config_file.exists():
            self._load_yaml()
        else:
            # Fallback: single-app from env vars
            self._load_env_fallback()

    def _load_yaml(self) -> None:
        """Load configuration from config.yaml."""
        try:
            with open(self.config_file) as f:
                self._yaml_data = yaml.safe_load(f) or {}
        except Exception:
            logger.exception("Failed to load config.yaml, using env vars only")
            self._yaml_data = {}

        # Check for old format (apps at top level)
        if "apps" in self._yaml_data and "channels" not in self._yaml_data:
            warnings.warn(
                "config.yaml uses deprecated top-level 'apps' key. "
                "Please migrate to 'channels.feishu.apps' format.",
                DeprecationWarning,
            )
            # Wrap old format
            self._yaml_data = {
                "gateway": {},
                "channels": {"feishu": {"apps": self._yaml_data.pop("apps")}},
                "unified_icc_ws_url": self._yaml_data.pop("unified_icc_ws_url", None),
                "unified_icc_api_key": self._yaml_data.pop("unified_icc_api_key", None),
            }

        # Parse feishu channel config
        channels = self._yaml_data.get("channels", {})
        feishu_data = channels.get("feishu")
        if feishu_data:
            self.feishu = FeishuChannelConfig.from_dict(feishu_data)
        else:
            self.feishu = None

    def _load_gateway_settings(self) -> None:
        """Load gateway settings from YAML or env vars."""
        gateway_data = self._yaml_data.get("gateway", {})

        # Tmux
        self.tmux_session = gateway_data.get(
            "tmux_session", os.getenv("TMUX_SESSION_NAME", "unified-icc")
        )
        self.tmux_main_window_name = "__main__"
        self.own_window_id: str | None = None
        self.tmux_external_patterns = gateway_data.get(
            "tmux_external_patterns", os.getenv("TMUX_EXTERNAL_PATTERNS", "")
        )

        # State files
        self.state_file = self.config_dir / "state.json"
        self.session_map_file = self.config_dir / "session_map.json"
        self.monitor_state_file = self.config_dir / "monitor_state.json"
        self.events_file = self.config_dir / "events.jsonl"
        self.mailbox_dir = self.config_dir / "mailbox"

        # Claude session monitoring
        _claude_config_dir = os.getenv("CLAUDE_CONFIG_DIR")
        self.claude_config_dir = (
            Path(_claude_config_dir).expanduser()
            if _claude_config_dir
            else Path.home() / ".claude"
        )
        self.claude_projects_path = self.claude_config_dir / "projects"
        self.monitor_poll_interval = max(
            0.5,
            float(
                gateway_data.get(
                    "monitor_poll_interval", os.getenv("MONITOR_POLL_INTERVAL", "1.0")
                )
            ),
        )
        self.status_poll_interval = max(
            0.5,
            float(
                gateway_data.get(
                    "status_poll_interval",
                    os.getenv("CCLARK_STATUS_POLL_INTERVAL", "1.0"),
                )
            ),
        )

        # API server
        self.api_host = gateway_data.get("api_host", os.getenv("ICC_API_HOST", "0.0.0.0"))
        self.api_port = int(
            gateway_data.get("api_port", os.getenv("ICC_API_PORT", "8900"))
        )
        self.api_key = gateway_data.get("api_key", os.getenv("ICC_API_KEY", ""))

        # Autoclose
        self.autoclose_done_minutes = int(
            gateway_data.get("autoclose_done_minutes", os.getenv("AUTOCLOSE_DONE_MINUTES", "30"))
        )
        self.autoclose_dead_minutes = int(
            gateway_data.get("autoclose_dead_minutes", os.getenv("AUTOCLOSE_DEAD_MINUTES", "10"))
        )

    def _load_env_fallback(self) -> None:
        """Load single Feishu app from env vars (dev/fallback mode)."""
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")

        if app_id and app_secret:
            self.feishu = FeishuChannelConfig(
                apps=[
                    FeishuAppConfig(
                        name="default",
                        app_id=app_id,
                        app_secret=app_secret,
                        allowed_users=None,
                        tmux_session=self.tmux_session,
                    )
                ]
            )
        else:
            self.feishu = None


unified_config = UnifiedConfig()
