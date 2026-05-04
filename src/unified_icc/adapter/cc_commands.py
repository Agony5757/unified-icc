"""Discover Claude Code commands — platform-agnostic command discovery.

Scans filesystem sources to build the command list:
  1. Built-in CC commands (always present)
  2. User-invocable skills from ~/.claude/skills/
  3. Custom commands from ~/.claude/commands/

Key class: CCCommand.
Key function: discover_cc_commands().
"""

import structlog
from dataclasses import dataclass
from pathlib import Path

logger = structlog.get_logger()

CC_BUILTINS: dict[str, str] = {
    "clear": "Clear conversation history",
    "compact": "Compact conversation context",
    "effort": "Set thinking effort level",
    "help": "Show Claude Code help",
    "init": "Initialize CLAUDE.md in project",
    "mcp": "List MCP servers and tools",
    "memory": "Edit CLAUDE.md",
    "model": "Select model and thinking effort",
    "permissions": "Manage tool permissions",
    "plan": "Switch to plan mode",
    "rc": "Start remote control (alias)",
    "remote-control": "Start remote control session",
    "status": "Show session status",
    "tasks": "Manage background tasks",
}


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    frontmatter = text[3:end].strip()
    result: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


@dataclass(frozen=True, slots=True)
class CCCommand:
    """A discoverable Claude Code command or skill.

    Attributes:
        name: Command name (e.g. "compact", "help").
        description: Short description from frontmatter or docstring.
        source: "builtin" (always available), "skill" (from ~/.claude/skills/),
            or "command" (from ~/.claude/commands/).
    """

    name: str
    description: str
    source: str  # "builtin", "skill", "command"


def _discover_skills(claude_dir: Path) -> list[CCCommand]:
    """Discover user-invocable skills from ~/.claude/skills/."""
    commands: list[CCCommand] = []
    skills_dir = claude_dir / "skills"
    if not skills_dir.is_dir():
        return commands
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md)
        if fm.get("user_invocable", "").lower() not in ("true", "yes", "1"):
            continue
        name = skill_dir.name
        desc = fm.get("description", fm.get("short_description", ""))
        commands.append(CCCommand(name=name, description=desc, source="skill"))
    return commands


def _discover_custom_commands(claude_dir: Path) -> list[CCCommand]:
    """Discover custom commands from ~/.claude/commands/."""
    commands: list[CCCommand] = []
    commands_dir = claude_dir / "commands"
    if not commands_dir.is_dir():
        return commands
    for group_dir in commands_dir.iterdir():
        if group_dir.is_dir():
            for cmd_file in group_dir.glob("*.md"):
                fm = parse_frontmatter(cmd_file)
                name = f"{group_dir.name}:{cmd_file.stem}"
                desc = fm.get("description", "")
                commands.append(CCCommand(name=name, description=desc, source="command"))
        elif group_dir.suffix == ".md":
            fm = parse_frontmatter(group_dir)
            name = group_dir.stem
            desc = fm.get("description", "")
            commands.append(CCCommand(name=name, description=desc, source="command"))
    return commands


def discover_cc_commands(claude_dir: Path | None = None) -> list[CCCommand]:
    """Scan filesystem for CC commands."""
    if claude_dir is None:
        from ..utils.config import config
        claude_dir = config.claude_config_dir

    commands: list[CCCommand] = []

    for name, desc in CC_BUILTINS.items():
        commands.append(CCCommand(name=name, description=desc, source="builtin"))

    commands.extend(_discover_skills(claude_dir))
    commands.extend(_discover_custom_commands(claude_dir))

    return commands
