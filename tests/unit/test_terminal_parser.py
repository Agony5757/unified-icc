from unified_icc.tmux.terminal_parser import extract_interactive_content


def test_extract_permission_prompt_for_create_file() -> None:
    pane = """
● Write(/tmp/cclark-permission-default-check.txt)

────────────────────────────────────────────────────────────────────────────────
 Create file
 ../../../../tmp/cclark-permission-default-check.txt
────────────────────────────────────────────────────────────────────────────────
  1 PERMISSION_DEFAULT_CHECK
────────────────────────────────────────────────────────────────────────────────
 Do you want to create cclark-permission-default-check.txt?
 ❯ 1. Yes
   2. Yes, allow all edits in tmp/ during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
"""

    content = extract_interactive_content(pane)

    assert content is not None
    assert content.name == "PermissionPrompt"
    assert "Do you want to create cclark-permission-default-check.txt?" in content.content
    assert "1. Yes" in content.content


def test_extract_permissions_panel_includes_escape_cancel_footer() -> None:
    pane = """
❯ /permissions

────────────────────────────────────────────────────────────────────────────────
  Permissions:  Recently denied   Allow   Ask   Deny   Workspace

  Claude Code won't ask before using allowed tools.
  ╭───────────────────────────────────────────────╮
  │ ⌕ Search…                                     │
  ╰───────────────────────────────────────────────╯

    1. Add a new rule…

   ←/→ tab switch · ↓ return · Esc cancel
"""

    content = extract_interactive_content(pane)

    assert content is not None
    assert content.name == "PermissionsPanel"
    assert "❯ /permissions" in content.content
    assert "Permissions:" in content.content
    assert "Esc cancel" in content.content


def test_extract_trust_workspace_prompt() -> None:
    pane = """
claude --permission-mode default
/status
────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:

 /home/agony/projects/larkcc-test/test-20260429-1156

 Quick safety check: Is this a project you created or one you trust? (Like your
  own code, a well-known open source project, or work from your team).

 Claude Code'll be able to read, edit, and execute files here.

 Security guide

 ❯ 1. Yes, I trust this folder
   2. No, exit

 Enter to confirm · Esc to cancel
"""

    content = extract_interactive_content(pane)

    assert content is not None
    assert content.name == "TrustWorkspacePrompt"
    assert "Quick safety check" in content.content
    assert "1. Yes, I trust this folder" in content.content
    assert "Enter to confirm" in content.content
