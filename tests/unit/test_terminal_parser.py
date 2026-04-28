from unified_icc.terminal_parser import extract_interactive_content


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
