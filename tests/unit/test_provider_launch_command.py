from unified_icc.providers import resolve_launch_command


def test_claude_normal_mode_uses_permission_mode_default() -> None:
    assert resolve_launch_command("claude", approval_mode="normal") == (
        "claude --permission-mode default"
    )


def test_claude_yolo_mode_keeps_dangerous_flag() -> None:
    assert resolve_launch_command("claude", approval_mode="yolo") == (
        "claude --dangerously-skip-permissions"
    )
