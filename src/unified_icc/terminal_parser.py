"""Terminal output parser — detects Claude Code UI elements in pane text.

Parses captured tmux pane content to detect:
  - Interactive UIs (AskUserQuestion, ExitPlanMode, Permission Prompt,
    RestoreCheckpoint) via regex-based UIPattern matching.
  - Status line (spinner characters + working text) by scanning from bottom up.

Key functions: extract_interactive_content(), parse_status_line(),
strip_pane_chrome(), extract_bash_output().
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unified_icc.screen_buffer import ScreenBuffer


@dataclass
class InteractiveUIContent:
    """Content extracted from an interactive UI."""

    content: str
    name: str = ""


@dataclass(frozen=True)
class UIPattern:
    """A text-marker pair that delimits an interactive UI region."""

    name: str
    top: tuple[re.Pattern[str], ...]
    bottom: tuple[re.Pattern[str], ...]
    min_gap: int = 2
    context_above: int = 0


# ── UI pattern definitions (order matters — first match wins) ────────────

UI_PATTERNS: list[UIPattern] = [
    UIPattern(
        name="ExitPlanMode",
        top=(
            re.compile(r"^\s*Would you like to proceed\?"),
            re.compile(r"^\s*Claude has written up a plan"),
        ),
        bottom=(
            re.compile(r"^\s*ctrl-g to edit in "),
            re.compile(r"^\s*Esc to (cancel|exit)"),
        ),
    ),
    UIPattern(
        name="AskUserQuestion",
        top=(re.compile(r"^\s*←\s+[☐✔☒]"),),
        bottom=(),
        min_gap=1,
    ),
    UIPattern(
        name="AskUserQuestion",
        top=(re.compile(r"^\s*[☐✔☒]"),),
        bottom=(re.compile(r"^\s*Enter to select"),),
        min_gap=1,
    ),
    UIPattern(
        name="PermissionPrompt",
        top=(
            re.compile(r"^\s*Do you want to proceed\?"),
            re.compile(r"^\s*Do you want to make this edit"),
            re.compile(r"^\s*Do you want to (create|update|delete|modify) "),
            re.compile(r"^\s*Network request outside of sandbox"),
            re.compile(r"^\s*This command requires approval"),
            re.compile(r"^\s*Allow .+ to"),
        ),
        bottom=(re.compile(r"^\s*Esc to cancel"),),
    ),
    UIPattern(
        name="TrustWorkspacePrompt",
        top=(
            re.compile(r"^\s*Quick safety check: Is this a project you created or one you trust\?"),
            re.compile(r"^\s*Accessing workspace:"),
        ),
        bottom=(re.compile(r"^\s*Enter to confirm"),),
        context_above=3,
    ),
    UIPattern(
        name="RestoreCheckpoint",
        top=(re.compile(r"^\s*Restore the code"),),
        bottom=(re.compile(r"^\s*Enter to continue"),),
    ),
    UIPattern(
        name="Settings",
        top=(re.compile(r"^\s*Settings:"),),
        bottom=(
            re.compile(r"Esc to (cancel|exit)"),
            re.compile(r"^\s*Type to filter"),
        ),
    ),
    UIPattern(
        name="SelectModel",
        top=(re.compile(r"^\s*Select model"),),
        bottom=(
            re.compile(r"Enter to confirm"),
            re.compile(r"^\s*Esc to exit"),
        ),
    ),
    UIPattern(
        name="PermissionsPanel",
        top=(re.compile(r"^\s*Permissions:"),),
        bottom=(
            re.compile(r"Esc cancel"),
            re.compile(r"Esc to (cancel|exit)"),
        ),
        context_above=3,
    ),
    UIPattern(
        name="SelectionUI",
        top=(re.compile(r"^\s*[❯›]\s"),),
        bottom=(
            re.compile(r"^\s*Esc to (cancel|exit)"),
            re.compile(r"Esc cancel"),
            re.compile(r"^\s*Enter to (select|confirm|continue)"),
            re.compile(r"^\s*ctrl-g to edit"),
            re.compile(r"(?i)^\s*Press enter to (confirm|select|continue|submit)"),
            re.compile(r"(?i)^\s*enter to (submit|confirm|select)"),
            re.compile(r"^\s+\d+\.\s"),
        ),
        min_gap=1,
        context_above=10,
    ),
]

if UI_PATTERNS[-1].name != "SelectionUI":
    raise RuntimeError("catch-all SelectionUI pattern must be last in UI_PATTERNS")


# ── Post-processing ──────────────────────────────────────────────────────

_RE_LONG_DASH = re.compile(r"^─{5,}$")
_MIN_SEPARATOR_WIDTH = 20
_MAX_CHROME_LINE_LENGTH = 250


def _shorten_separators(text: str) -> str:
    return "\n".join(
        "─────" if _RE_LONG_DASH.match(line) else line for line in text.split("\n")
    )


# ── Core extraction ──────────────────────────────────────────────────────


def _context_start(lines: list[str], top_idx: int, context_above: int) -> int:
    if context_above <= 0:
        return top_idx
    for k in range(max(0, top_idx - context_above), top_idx):
        if lines[k].strip():
            return k
    return top_idx


def _try_extract(lines: list[str], pattern: UIPattern) -> InteractiveUIContent | None:
    top_idx: int | None = None
    bottom_idx: int | None = None

    for i, line in enumerate(lines):
        if top_idx is None:
            if any(p.search(line) for p in pattern.top):
                top_idx = i
        elif pattern.bottom and any(p.search(line) for p in pattern.bottom):
            bottom_idx = i
            break

    if top_idx is None:
        return None

    if not pattern.bottom:
        for i in range(len(lines) - 1, top_idx, -1):
            if lines[i].strip():
                bottom_idx = i
                break

    if bottom_idx is None or bottom_idx - top_idx < pattern.min_gap:
        return None

    display_start = _context_start(lines, top_idx, pattern.context_above)
    content = "\n".join(lines[display_start : bottom_idx + 1]).rstrip()
    return InteractiveUIContent(content=_shorten_separators(content), name=pattern.name)


# ── Bottom-up fallback ───────────────────────────────────────────────────

_ACTION_HINT_RE = re.compile(
    r"(?i)^\s*("
    r"Esc to (cancel|exit)"
    r"|.*Esc cancel"
    r"|Enter to (select|confirm|continue|submit)"
    r"|ctrl-g to edit"
    r"|Type to filter"
    r"|Press enter to (confirm|select|continue|submit)"
    r")"
)

_BOTTOM_UP_MAX_SCAN = 30
_BOTTOM_UP_MAX_DEPTH = 5
_SECTION_BREAK_BLANKS = 2
_BOTTOM_UP_MIN_GAP = 2

_CHECKBOX_CHARS_RE = re.compile(r"[☐✔☒]")
_CURSOR_CHARS_RE = re.compile(r"[❯›]\s")


def _infer_ui_name(lines: list[str]) -> str:
    for line in lines:
        if _CHECKBOX_CHARS_RE.search(line):
            return "AskUserQuestion"
        if _CURSOR_CHARS_RE.search(line):
            return "SelectionUI"
    return "InteractiveUI"


def _try_extract_bottom_up(lines: list[str]) -> InteractiveUIContent | None:
    bottom_idx: int | None = None
    non_blank_seen = 0
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            non_blank_seen += 1
            if non_blank_seen > _BOTTOM_UP_MAX_DEPTH:
                break
            if _ACTION_HINT_RE.search(lines[i]):
                bottom_idx = i
                break

    if bottom_idx is None:
        return None

    top_idx = bottom_idx
    consecutive_blank = 0
    scan_floor = max(0, bottom_idx - _BOTTOM_UP_MAX_SCAN)
    for i in range(bottom_idx - 1, scan_floor - 1, -1):
        if not lines[i].strip():
            consecutive_blank += 1
            if consecutive_blank >= _SECTION_BREAK_BLANKS:
                top_idx = i + consecutive_blank
                break
        else:
            consecutive_blank = 0
            top_idx = i

    if bottom_idx - top_idx < _BOTTOM_UP_MIN_GAP:
        return None

    content = "\n".join(lines[top_idx : bottom_idx + 1]).rstrip()
    name = _infer_ui_name(lines[top_idx : bottom_idx + 1])
    return InteractiveUIContent(content=_shorten_separators(content), name=name)


# ── Public API ───────────────────────────────────────────────────────────


def extract_interactive_content(
    pane_text: str | list[str],
    patterns: list[UIPattern] | None = None,
) -> InteractiveUIContent | None:
    """Extract content from an interactive UI in terminal output."""
    if not pane_text:
        return None

    lines = pane_text if isinstance(pane_text, list) else pane_text.strip().split("\n")
    for pattern in patterns or UI_PATTERNS:
        result = _try_extract(lines, pattern)
        if result:
            return result

    return _try_extract_bottom_up(lines)


def parse_from_screen(screen: ScreenBuffer) -> InteractiveUIContent | None:
    """Detect interactive UI content using pyte-rendered screen lines."""
    lines = screen.display
    cursor_row = screen.cursor_row

    end = max(cursor_row + 1, 1)
    for i in range(len(lines) - 1, cursor_row, -1):
        if lines[i].strip():
            end = i + 1
            break

    active_lines = lines[:end]
    if not active_lines:
        return None

    return extract_interactive_content(active_lines)


def parse_status_from_screen(screen: ScreenBuffer) -> str | None:
    """Extract status line using pyte-rendered screen lines."""
    lines = screen.display

    last_nonempty = len(lines) - 1
    while last_nonempty >= 0 and not lines[last_nonempty].strip():
        last_nonempty -= 1
    if last_nonempty < 0:
        return None

    active_lines = lines[: last_nonempty + 1]
    return parse_status_line("\n".join(active_lines), pane_rows=screen.rows)


def parse_status_block_from_screen(screen: ScreenBuffer) -> str | None:
    """Extract the status line plus visible checklist/progress lines."""
    lines = screen.display

    last_nonempty = len(lines) - 1
    while last_nonempty >= 0 and not lines[last_nonempty].strip():
        last_nonempty -= 1
    if last_nonempty < 0:
        return None

    active_lines = lines[: last_nonempty + 1]
    return parse_status_block("\n".join(active_lines), pane_rows=screen.rows)


# ── Status line parsing ─────────────────────────────────────────────────

STATUS_SPINNERS = frozenset(["·", "✻", "✽", "✶", "✳", "✢"])

_BRAILLE_START = 0x2800
_BRAILLE_END = 0x28FF
_NON_SPINNER_RANGES = ((0x2500, 0x257F),)
_NON_SPINNER_CHARS = frozenset("─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬>|+<=~")
_SPINNER_CATEGORIES = frozenset({"So", "Sm"})
_MAX_STATUS_PROGRESS_LINES = 8
_STATUS_PROGRESS_RE = re.compile(r"^\s*(?:⎿\s*)?[✔◼◻◔]\s+\S")


def is_likely_spinner(char: str) -> bool:
    if not char:
        return False
    if char in STATUS_SPINNERS:
        return True
    if char in _NON_SPINNER_CHARS:
        return False
    cp = ord(char)
    for start, end in _NON_SPINNER_RANGES:
        if start <= cp <= end:
            return False
    if _BRAILLE_START <= cp <= _BRAILLE_END:
        return True
    category = unicodedata.category(char)
    return category in _SPINNER_CATEGORIES


def parse_status_line(pane_text: str, *, pane_rows: int | None = None) -> str | None:
    """Extract the Claude Code status line from terminal output."""
    if not pane_text:
        return None

    lines = pane_text.strip().split("\n")

    if pane_rows is not None:
        scan_limit = max(int(pane_rows * 0.4), 16)
        scan_start = max(len(lines) - scan_limit, 0)
    else:
        scan_start = 0

    status_idx = _find_status_line_index(lines, scan_start)
    if status_idx is None:
        return None
    return lines[status_idx].strip()[1:].strip()


def parse_status_block(pane_text: str, *, pane_rows: int | None = None) -> str | None:
    """Extract the Claude status line together with visible checklist lines."""
    if not pane_text:
        return None

    lines = pane_text.strip().split("\n")
    scan_start = _status_scan_start(lines, pane_rows)

    status_idx = _find_status_line_index(lines, scan_start)
    if status_idx is None:
        return None

    status_line = lines[status_idx].strip()[1:].strip()
    progress_lines = _collect_status_progress_lines(lines, status_idx, scan_start)

    if not progress_lines:
        return status_line
    progress_lines.reverse()
    return "\n".join([status_line, *progress_lines])


def _status_scan_start(lines: list[str], pane_rows: int | None) -> int:
    if pane_rows is None:
        return 0
    scan_limit = max(int(pane_rows * 0.4), 16)
    return max(len(lines) - scan_limit, 0)


def _collect_status_progress_lines(
    lines: list[str], status_idx: int, scan_start: int
) -> list[str]:
    progress_lines: list[str] = []
    blanks_seen = 0
    for idx in range(status_idx - 1, scan_start - 1, -1):
        candidate = lines[idx].rstrip()
        stripped = candidate.strip()
        if not stripped:
            if progress_lines:
                blanks_seen += 1
                if blanks_seen >= 1:
                    break
            continue
        blanks_seen = 0
        if not _STATUS_PROGRESS_RE.match(candidate):
            break
        progress_lines.append(stripped.removeprefix("⎿ ").strip())
        if len(progress_lines) >= _MAX_STATUS_PROGRESS_LINES:
            break
    return progress_lines


def _find_status_line_index(lines: list[str], scan_start: int) -> int | None:
    for i in range(len(lines) - 1, scan_start - 1, -1):
        if not _is_separator(lines[i]):
            continue
        for offset in (1, 2):
            j = i - offset
            if j < scan_start:
                break
            candidate = lines[j].strip()
            if not candidate:
                continue
            if is_likely_spinner(candidate[0]):
                return j
            break
    return None


# ── Status display formatting ──────────────────────────────────────────

_STATUS_KEYWORDS: list[tuple[str, str, str]] = [
    ("think", "\U0001f9e0", "thinking…"),
    ("reason", "\U0001f9e0", "thinking…"),
    ("test", "\U0001f9ea", "testing…"),
    ("read", "\U0001f4d6", "reading…"),
    ("edit", "✏️", "editing…"),
    ("writ", "\U0001f4dd", "writing…"),
    ("search", "\U0001f50d", "searching…"),
    ("grep", "\U0001f50d", "searching…"),
    ("glob", "\U0001f4c2", "searching…"),
    ("install", "\U0001f4e6", "installing…"),
    ("runn", "⚡", "running…"),
    ("bash", "⚡", "running…"),
    ("execut", "⚡", "running…"),
    ("compil", "\U0001f3d7️", "building…"),
    ("build", "\U0001f3d7️", "building…"),
    ("lint", "\U0001f9f9", "linting…"),
    ("format", "\U0001f9f9", "formatting…"),
    ("deploy", "\U0001f680", "deploying…"),
    ("fetch", "\U0001f310", "fetching…"),
    ("download", "⬇️", "downloading…"),
    ("upload", "⬆️", "uploading…"),
    ("commit", "\U0001f4be", "committing…"),
    ("push", "⬆️", "pushing…"),
    ("pull", "⬇️", "pulling…"),
    ("clone", "\U0001f4cb", "cloning…"),
    ("debug", "\U0001f41b", "debugging…"),
    ("delet", "\U0001f5d1️", "deleting…"),
    ("creat", "✨", "creating…"),
    ("check", "✅", "checking…"),
    ("updat", "\U0001f504", "updating…"),
    ("analyz", "\U0001f52c", "analyzing…"),
    ("analys", "\U0001f52c", "analyzing…"),
    ("pars", "\U0001f50d", "parsing…"),
    ("verif", "✅", "verifying…"),
]

_DEFAULT_EMOJI = "⚙️"
_DEFAULT_STATUS = f"{_DEFAULT_EMOJI} working…"


def _match_status_keyword(raw_status: str) -> tuple[str, str] | None:
    lower = raw_status.lower()
    first_word = lower.split(maxsplit=1)[0] if lower else ""
    for keyword, emoji, verb in _STATUS_KEYWORDS:
        if keyword in first_word:
            return emoji, verb
    for keyword, emoji, verb in _STATUS_KEYWORDS:
        if keyword in lower:
            return emoji, verb
    return None


def status_emoji_prefix(raw_status: str) -> str:
    match = _match_status_keyword(raw_status)
    return match[0] if match else _DEFAULT_EMOJI


def format_status_display(raw_status: str) -> str:
    match = _match_status_keyword(raw_status)
    return f"{match[0]} {match[1]}" if match else _DEFAULT_STATUS


# ── Remote Control detection ──────────────────────────────────────────

_RC_MARKER = "Remote Control active"


def detect_remote_control(lines: list[str]) -> bool:
    boundary = find_chrome_boundary(lines)
    if boundary is None:
        return False
    return any(_RC_MARKER in line for line in lines[boundary:])


# ── Pane chrome stripping & bash output extraction ─────────────────────


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= _MIN_SEPARATOR_WIDTH and all(c == "─" for c in stripped)


def find_chrome_boundary(lines: list[str]) -> int | None:
    """Find the topmost separator row of Claude Code's bottom chrome."""
    if not lines:
        return None

    scan_start = max(len(lines) - 20, 0)

    separator_indices: list[int] = []
    for i in range(len(lines) - 1, scan_start - 1, -1):
        if _is_separator(lines[i]):
            separator_indices.append(i)

    if not separator_indices:
        return None

    boundary = separator_indices[0]

    for idx in separator_indices[1:]:
        gap_is_chrome = True
        for j in range(idx + 1, boundary):
            line = lines[j].strip()
            if not line:
                continue
            if len(line) > _MAX_CHROME_LINE_LENGTH:
                gap_is_chrome = False
                break
        if gap_is_chrome:
            boundary = idx
        else:
            break

    return boundary


def strip_pane_chrome(lines: list[str]) -> list[str]:
    """Strip Claude Code's bottom chrome (prompt area + status bar)."""
    boundary = find_chrome_boundary(lines)
    if boundary is not None:
        return lines[:boundary]
    return lines


def extract_bash_output(pane_text: str, command: str) -> str | None:
    """Extract ``!`` command output from a captured tmux pane."""
    lines = strip_pane_chrome(pane_text.splitlines())

    cmd_idx: int | None = None
    match_prefix = command[:10]
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped.startswith(f"! {match_prefix}") or stripped.startswith(
            f"!{match_prefix}"
        ):
            cmd_idx = i
            break

    if cmd_idx is None:
        return None

    raw_output = lines[cmd_idx:]

    while raw_output and not raw_output[-1].strip():
        raw_output.pop()

    if not raw_output:
        return None

    return "\n".join(raw_output).strip()
