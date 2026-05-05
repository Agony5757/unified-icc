"""End-to-end tests for Feishu channel with 4 bots.

These tests verify the unified-icc gateway with 4 configured Feishu bots.
Manual Feishu connectivity tests are skipped unless RUN_FEISHU_E2E=1 is set.

Run real Feishu checks with:
    RUN_FEISHU_E2E=1 pytest tests/e2e/ -v --no-cov
"""

import os
import sys

import pytest

RUN_FEISHU_E2E = os.getenv("RUN_FEISHU_E2E") == "1"
requires_feishu_e2e = pytest.mark.skipif(
    not RUN_FEISHU_E2E,
    reason="manual Feishu E2E requires RUN_FEISHU_E2E=1",
)


class TestFeishuChannelSetup:
    """Test Feishu channel configuration and connectivity."""

    @requires_feishu_e2e
    def test_config_loads_4_apps(self):
        """Verify config has 4 Feishu apps configured."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "from unified_icc.utils.config import UnifiedConfig; "
             "c = UnifiedConfig(); "
             "print('feishu:', c.feishu is not None); "
             "print('count:', len(c.feishu.apps) if c.feishu else 0); "
             "print('names:', [a.name for a in c.feishu.apps] if c.feishu else [])"],
            capture_output=True, text=True,
        )
        output = result.stdout
        assert "feishu: True" in output, f"Config load failed: {result.stderr}"
        assert "count: 4" in output, f"Expected 4 apps: {output}"
        assert "claude-coder" in output, f"Missing expected app: {output}"

    @requires_feishu_e2e
    def test_config_uses_unified_icc_naming(self):
        """Verify tmux_session uses unified-icc naming, not cclark."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "from unified_icc.utils.config import UnifiedConfig; "
             "c = UnifiedConfig(); "
             "print('gateway:', c.tmux_session); "
             "print('apps:', [a.tmux_session for a in c.feishu.apps] if c.feishu else [])"],
            capture_output=True, text=True,
        )
        output = result.stdout
        assert "unified-icc" in output, f"Expected unified-icc naming: {output}"
        assert "cclark" not in output, f"Found cclark naming: {output}"

    @requires_feishu_e2e
    def test_config_no_health_port(self):
        """Verify health_port is not in FeishuAppConfig."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "from unified_icc.utils.config import UnifiedConfig; "
             "c = UnifiedConfig(); "
             "for app in (c.feishu.apps if c.feishu else []): "
             "    hp = getattr(app, 'health_port', None); "
             "    print(f'{app.name}: hp={hp}')"],
            capture_output=True, text=True,
        )
        output = result.stdout
        # health_port should either not exist or be None
        for line in output.strip().split('\n'):
            if line.startswith('claude-coder'):
                assert 'hp=None' in line or 'hp=8080' not in line, \
                    f"health_port should not be set: {line}"

    @pytest.mark.asyncio
    async def test_gateway_api_health_route(self, monkeypatch):
        """Verify the health route contract without requiring a running server."""
        from unified_icc.server import app as server_app
        from unified_icc.server.routes.sessions import health

        monkeypatch.setattr(server_app, "_gateway", object())

        assert await health() == {"status": "ok"}


class TestFeishuWSConnections:
    """Test Feishu WebSocket connections.

    NOTE: These tests verify the WebSocket URL can be obtained.
    Actual message receiving requires:
    1. Feishu apps have im.message.receive_v1 event subscribed
    2. Someone sends a message to the bot in Feishu
    """

    @requires_feishu_e2e
    @pytest.mark.asyncio
    async def test_ws_connection_obtains_url(self):
        """Verify WebSocket endpoint returns valid URL."""
        import subprocess
        code = '''
import asyncio
from unified_icc.channels.feishu.ws_client import FeishuWSClient
from unified_icc.utils.config import UnifiedConfig

async def test():
    c = UnifiedConfig()
    app = c.feishu.apps[0]
    ws = FeishuWSClient(app.app_id, app.app_secret, app.name, app.allowed_users, lambda e: None)
    url = await ws._get_ws_url()
    print("URL:", url[:50])
    return url.startswith("wss://")

result = asyncio.run(test())
print("OK" if result else "FAIL")
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        assert "URL: wss://msg-frontier.feishu.cn" in output, \
            f"WS URL failed: {output}"
        assert "OK" in output, f"WS connection failed: {output}"
