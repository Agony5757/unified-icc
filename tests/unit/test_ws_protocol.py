from __future__ import annotations

from unified_icc.server.ws_protocol import (
    InputMsg,
    SessionCreateMsg,
    parse_client_message,
)


def test_session_create_accepts_external_channel_id() -> None:
    msg = parse_client_message(
        {
            "type": "session.create",
            "request_id": "r1",
            "channel_id": "feishu:oc_chat",
            "work_dir": "/tmp/project",
            "provider": "codex",
            "mode": "standard",
        }
    )

    assert isinstance(msg, SessionCreateMsg)
    assert msg.channel_id == "feishu:oc_chat"
    assert msg.provider == "codex"


def test_input_accepts_channel_id_and_raw_flag() -> None:
    msg = parse_client_message(
        {
            "type": "input",
            "request_id": "r2",
            "channel_id": "feishu:oc_chat",
            "text": "3",
            "enter": False,
            "literal": True,
            "raw": True,
        }
    )

    assert isinstance(msg, InputMsg)
    assert msg.channel_id == "feishu:oc_chat"
    assert msg.enter is False
    assert msg.raw is True
