"""Manual helper for validating four independent Feishu bots.

This module is skipped by default. To run it locally:

    RUN_FEISHU_E2E=1 FEISHU_E2E_CHAT_IDS=oc_...,oc_...,oc_...,oc_... pytest tests/e2e/test_4_bots.py -s
"""

import os
import subprocess
import time

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FEISHU_E2E") != "1",
    reason="manual Feishu E2E requires RUN_FEISHU_E2E=1",
)

BOT_NAMES = ("claude-coder", "claude-coder-2", "claude-coder-3", "claude-coder-4")


def _chat_ids() -> list[str]:
    raw = os.getenv("FEISHU_E2E_CHAT_IDS", "")
    chat_ids = [item.strip() for item in raw.split(",") if item.strip()]
    if len(chat_ids) != len(BOT_NAMES):
        pytest.skip("FEISHU_E2E_CHAT_IDS must contain four comma-separated chat IDs")
    return chat_ids


def send_message(chat_id: str, text: str) -> bool:
    result = subprocess.run(
        [
            "lark-cli",
            "im",
            "+messages-send",
            "--as",
            "user",
            "--chat-id",
            chat_id,
            "--text",
            text,
        ],
        capture_output=True,
        check=False,
        env={**os.environ, "LARK_CLI_NO_PROXY": "1"},
        text=True,
    )
    return result.returncode == 0


def test_four_feishu_bots_accept_help_messages() -> None:
    for name, chat_id in zip(BOT_NAMES, _chat_ids(), strict=True):
        assert send_message(chat_id, "#help"), f"failed to send #help to {name}"
        time.sleep(1)
