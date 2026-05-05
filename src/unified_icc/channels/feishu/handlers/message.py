"""Inbound message handler — routes text messages to the gateway or starts new sessions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

from unified_icc.channels.feishu.adapter import FeishuAdapter
from unified_icc.channels.feishu.config import build_feishu_channel_id
from unified_icc.channels.feishu.event_parsers import FeishuMessageEvent

if TYPE_CHECKING:
    from unified_icc.core.gateway import UnifiedICC

logger = structlog.get_logger()

_NUMBERED_OPTION_RE = re.compile(r"^\s*(?:[❯›]\s*)?(\d+)\.\s+(.+?)\s*$")
_SELECTED_NUMBERED_OPTION_RE = re.compile(r"^\s*[❯›]\s*(\d+)\.\s+")


def classify_terminal_prompt(body: str) -> dict[str, str] | None:
    """Classify terminal UI text only when it expects a Feishu reply."""
    text = body or ""
    options = extract_numbered_prompt_options(text)
    selected = extract_selected_prompt_option(text)
    if (
        "has written up a plan" in text
        or (
            "Would you like to proceed?" in text
            and "what to change" in text
        )
    ):
        return {
            "type": "plan_decision",
            "phase": "choice",
            "options": ",".join(options),
            "selected": selected,
        }

    permission_markers = (
        "Do you want to proceed?",
        "Do you want to make this edit",
        "Do you want to create ",
        "Do you want to update ",
        "Do you want to delete ",
        "Do you want to modify ",
        "Network request outside of sandbox",
        "This command requires approval",
    )
    if any(marker in text for marker in permission_markers) or (
        "Allow " in text and " to " in text
    ):
        return {
            "type": "permission",
            "phase": "choice",
            "options": ",".join(options),
            "selected": selected,
        }

    selection_markers = (
        "Enter to select",
        "Enter to confirm",
        "Press enter to select",
        "Press enter to confirm",
        "Type to filter",
    )
    if any(marker in text for marker in selection_markers) and any(
        marker in text for marker in ("☐", "✔", "☒", "❯", "›")
    ):
        return {
            "type": "selection",
            "phase": "choice",
            "options": ",".join(options),
            "selected": selected,
        }

    return None


def extract_numbered_prompt_options(body: str) -> list[str]:
    """Return every visible numbered choice from a Claude terminal prompt."""
    options: list[str] = []
    seen: set[str] = set()
    for line in (body or "").splitlines():
        match = _NUMBERED_OPTION_RE.match(line)
        if not match:
            continue
        value = match.group(1)
        if value in seen:
            continue
        seen.add(value)
        options.append(value)
    return options


def extract_selected_prompt_option(body: str) -> str:
    """Return the numbered option currently focused by Claude's cursor."""
    for line in (body or "").splitlines():
        match = _SELECTED_NUMBERED_OPTION_RE.match(line)
        if match:
            return match.group(1)
    return ""


def build_terminal_prompt_reply_guidance(body: str, state: dict[str, str], provider_name: str = "claude") -> str:
    """Build prompt-specific Feishu guidance for the current terminal UI."""
    options = extract_numbered_prompt_options(body)
    if options:
        choices = ", ".join(f"`{option}`" for option in options)
        guidance = f"Reply with one of the listed numbers: {choices}."
    else:
        guidance = f"Reply with the number shown in {provider_name.title()}."

    if state.get("type") == "plan_decision" and "3" in options:
        guidance += (
            "\nFor plan option `3`, reply `3` first, then send the feedback text."
        )

    return guidance


def set_terminal_prompt_state(states: dict[str, dict[str, str]], channel_id: str, body: str) -> bool:
    """Classify and record the latest actionable terminal prompt for a channel."""
    state = classify_terminal_prompt(body)
    if state is None:
        clear_terminal_prompt_state(states, channel_id)
        return False
    states[channel_id] = state
    return True


def clear_terminal_prompt_state(states: dict[str, dict[str, str]], channel_id: str) -> None:
    """Clear the stored terminal prompt state for a channel."""
    states.pop(channel_id, None)


class MessageCommandHandler:
    """Handles inbound Feishu messages: # commands, session creation, forwarding."""

    def __init__(self, gateway: UnifiedICC, adapter: FeishuAdapter, app_name: str) -> None:
        self._gateway = gateway
        self._adapter = adapter
        self._app_name = app_name
        self._terminal_prompt_states: dict[str, dict[str, str]] = {}

    async def handle_message(self, event: FeishuMessageEvent) -> None:
        """Top-level handler for an inbound Feishu text message."""
        logger.info("handle_message: text=%r chat_id=%s", event.text, event.chat_id)
        channel_id = build_feishu_channel_id(
            self._app_name, event.chat_id, event.thread_id
        )
        text = event.text

        global_cmd = text.split(maxsplit=1)[0].lower() if text.strip() else ""
        if global_cmd == "#new":
            await self._handle_hash_new(event, channel_id)
            return
        if global_cmd == "#help":
            await self._handle_help(channel_id)
            return

        # Check session creation wizard
        from unified_icc.channels.feishu.handlers.session_creation import handle_session_input
        if await handle_session_input(event, channel_id, self._gateway, self._adapter, self._app_name):
            return

        # # prefix commands
        if text.startswith("#"):
            await self._handle_hash_command(event, channel_id, text)
            return

        # Forward to agent
        window_id = self._gateway.channel_router.resolve_window(channel_id)
        if window_id is None:
            await self._handle_new_channel(channel_id)
            return

        if await self._handle_terminal_prompt_reply(channel_id, window_id, text):
            return

        try:
            await self._advance_channel_turn(channel_id)
            await self._gateway.send_to_window(window_id, text)
        except Exception:
            logger.exception("Failed to send to window %s", window_id)
            await self._adapter.send_text(channel_id, "Failed to send message to session.")

    async def _advance_channel_turn(self, channel_id: str) -> int:
        """Finalize any open thinking card and advance the channel's turn index."""
        from unified_icc.channels.feishu.state import advance_turn_index, get_verbose_state

        state = get_verbose_state(channel_id)
        if state.streaming_thinking_active:
            from unified_icc.channels.feishu.cards.thinking import finalize_active_thinking_card
            try:
                await finalize_active_thinking_card(self._adapter, channel_id)
            except Exception:
                logger.exception("ThinkingCardStreamer finalize failed channel=%s", channel_id)

        return advance_turn_index(channel_id)

    async def _handle_terminal_prompt_reply(
        self,
        channel_id: str,
        window_id: str,
        text: str,
    ) -> bool:
        """Handle numbered replies to permission/plan/selection prompts."""
        state = self._terminal_prompt_states.get(channel_id)
        if not state:
            return False

        stripped = text.strip()
        allowed_options = {
            option for option in (state.get("options") or "").split(",") if option
        }
        if state.get("type") == "plan_decision":
            if state.get("phase") == "choice" and stripped == "3":
                await self._gateway.send_input_to_window(
                    window_id,
                    "3",
                    enter=False,
                    literal=True,
                    raw=True,
                )
                state["phase"] = "awaiting_feedback"
                await self._adapter.send_text(
                    channel_id,
                    "Plan option 3 selected. Send the feedback text next.",
                )
                return True

            if state.get("phase") == "awaiting_feedback":
                await self._advance_channel_turn(channel_id)
                await self._gateway.send_to_window(window_id, text)
                clear_terminal_prompt_state(self._terminal_prompt_states, channel_id)
                return True

        if state.get("type") == "selection" and stripped.isdigit():
            if allowed_options and stripped not in allowed_options:
                await self._send_invalid_prompt_option(channel_id, stripped, allowed_options)
                return True

            if await self._select_terminal_option_by_navigation(window_id, stripped, state):
                await self._advance_channel_turn(channel_id)
                clear_terminal_prompt_state(self._terminal_prompt_states, channel_id)
                return True

        if stripped.isdigit() and allowed_options and stripped not in allowed_options:
            await self._send_invalid_prompt_option(channel_id, stripped, allowed_options)
            return True

        if stripped.isdigit() and (not allowed_options or stripped in allowed_options):
            await self._advance_channel_turn(channel_id)
            await self._gateway.send_to_window(window_id, stripped)
            clear_terminal_prompt_state(self._terminal_prompt_states, channel_id)
            return True

        return False

    async def _send_invalid_prompt_option(
        self,
        channel_id: str,
        stripped: str,
        allowed_options: set[str],
    ) -> None:
        choices = ", ".join(f"`{option}`" for option in sorted(allowed_options, key=int))
        await self._adapter.send_text(
            channel_id,
            f"`{stripped}` is not a visible option. Reply with one of: {choices}.",
        )

    async def _select_terminal_option_by_navigation(
        self,
        window_id: str,
        target: str,
        state: dict[str, str],
    ) -> bool:
        selected = state.get("selected") or ""
        options = [option for option in (state.get("options") or "").split(",") if option]
        if not selected or target not in options or selected not in options:
            return False

        current_idx = options.index(selected)
        target_idx = options.index(target)
        delta = target_idx - current_idx
        key = "Down" if delta > 0 else "Up"
        for _ in range(abs(delta)):
            await self._gateway.send_key(window_id, key)
        await self._gateway.send_key(window_id, "Enter")
        return True

    async def _handle_new_channel(self, channel_id: str) -> None:
        await self._adapter.send_text(
            channel_id,
            "No active session is bound to this chat.\n\n" + _build_help_text(),
        )

    async def _handle_hash_command(
        self,
        event: FeishuMessageEvent,
        channel_id: str,
        text: str,
    ) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "#new":
            await self._handle_hash_new(event, channel_id)
        elif cmd == "#session":
            await self._handle_session_command(channel_id, arg)
        elif cmd == "#status":
            await self._handle_status(channel_id)
        elif cmd == "#help":
            await self._handle_help(channel_id)
        elif cmd == "#mkdir":
            await self._adapter.send_text(
                channel_id,
                "Use #new first, then send #mkdir <name> during directory selection.",
            )
        elif cmd == "#screenshot":
            await self._handle_screenshot(channel_id)
        elif cmd == "#verbose":
            await self._handle_verbose_toggle(channel_id, arg)
        else:
            await self._adapter.send_text(
                channel_id,
                f"Unknown command: {cmd}\nSend #help for available commands.",
            )

    async def _handle_hash_new(self, event: FeishuMessageEvent, channel_id: str) -> None:
        from unified_icc.channels.feishu.handlers.session_creation import (
            clear_session_creation,
            start_session_creation,
        )
        from unified_icc.channels.feishu.state import reset_channel_state

        logger.info("_handle_hash_new: user_id=%s channel_id=%s", event.user_id, channel_id)
        clear_session_creation(event.user_id)

        killed = await self._gateway.kill_channel_windows(channel_id)
        if killed:
            await self._adapter.send_text(
                channel_id,
                "Closed previous session window(s): " + ", ".join(killed),
            )

        orphans = await self._gateway.list_orphaned_agent_windows()
        if orphans:
            lines = [
                "Warning: found tmux-agent window(s) that are no longer tracked:",
            ]
            for w in orphans:
                lines.append(f"  {w.window_id} | {w.display_name} | {w.cwd or 'unknown cwd'}")
            lines.append("They were not killed because ownership cannot be proven.")
            await self._adapter.send_text(channel_id, "\n".join(lines))

        reset_channel_state(channel_id)
        clear_terminal_prompt_state(self._terminal_prompt_states, channel_id)
        await start_session_creation(event, channel_id, self._gateway, self._adapter, self._app_name)

    async def _handle_session_command(self, channel_id: str, arg: str) -> None:
        sub = arg.strip().lower()
        if sub == "list":
            await self._handle_session_list(channel_id)
        elif sub.startswith("close "):
            target = sub[len("close "):].strip()
            await self._handle_session_close(channel_id, target)
        elif sub == "close":
            await self._adapter.send_text(channel_id, "Usage: #session close <window_id>")
        else:
            await self._adapter.send_text(channel_id, "Usage: #session list | #session close <window_id>")

    async def _handle_session_list(self, channel_id: str) -> None:
        windows = await self._gateway.list_windows()
        if not windows:
            await self._adapter.send_text(channel_id, "No active sessions.")
            return

        lines = ["Active sessions:"]
        for w in windows:
            wid = getattr(w, "window_id", str(w))
            provider = getattr(w, "provider", "unknown")
            cwd = getattr(w, "cwd", "")
            session_short = (getattr(w, "session_id", "") or "")[:8]
            bound = self._gateway.resolve_channels(wid)
            ch_info = ""
            if bound:
                ch_parts = [c.rsplit(":", 1)[-1] for c in bound]
                ch_info = " → " + ", ".join(ch_parts)
            lines.append(f"  [{session_short}] {wid} | {provider} | {cwd}{ch_info}")

        await self._adapter.send_text(channel_id, "\n".join(lines))

    async def _handle_session_close(self, channel_id: str, target_wid: str) -> None:
        target_wid = target_wid.strip()
        if not target_wid:
            await self._adapter.send_text(channel_id, "Usage: #session close <window_id>")
            return

        windows = await self._gateway.list_windows()
        valid_ids = {getattr(w, "window_id", str(w)) for w in windows}
        if target_wid not in valid_ids:
            await self._adapter.send_text(channel_id, f"Unknown window id: {target_wid}")
            return

        await self._gateway.kill_window(target_wid)
        await self._adapter.send_text(channel_id, f"Session {target_wid} closed.")

    async def _handle_status(self, channel_id: str) -> None:
        window_id = self._gateway.channel_router.resolve_window(channel_id)
        if window_id is None:
            await self._adapter.send_text(channel_id, "No active session on this channel.")
            return

        from unified_icc.channels.feishu.state import get_verbose_state
        from unified_icc.tmux.window_state_store import window_store

        ws = window_store.get_window_state(window_id)
        vs = get_verbose_state(channel_id)
        verbose = getattr(vs, "_verbose_enabled", False)
        session_short = (ws.session_id or "")[:8]

        lines = [
            f"Window: {window_id}",
            f"Session: {session_short}… ({ws.session_id})",
            f"Provider: {ws.provider_name or 'unknown'}",
            f"CWD: {ws.cwd or '—'}",
            f"Mode: {ws.approval_mode or '—'}",
            f"Verbose: {'on' if verbose else 'off'}",
            f"Thinking card: {vs.streaming_thinking_card_id if vs.streaming_thinking_active else 'none'}",
        ]
        await self._adapter.send_text(channel_id, "\n".join(lines))

    async def _handle_help(self, channel_id: str) -> None:
        await self._adapter.send_text(channel_id, _build_help_text())

    async def _handle_screenshot(self, channel_id: str) -> None:
        from unified_icc.channels.feishu.handlers.screenshot import handle_screenshot_request
        await handle_screenshot_request(channel_id, self._gateway, self._adapter)

    async def _handle_verbose_toggle(self, channel_id: str, arg: str) -> None:
        from unified_icc.channels.feishu.state import get_verbose_state
        state = get_verbose_state(channel_id)
        if arg == "on":
            new = True
        elif arg == "off":
            new = False
        else:
            new = not getattr(state, "_verbose_enabled", False)
        setattr(state, "_verbose_enabled", new)
        verb = "enabled" if new else "disabled"
        await self._adapter.send_text(
            channel_id,
            f"Verbose mode {verb}. Thinking will {'be' if new else 'not be'} shown.",
        )


    # ── Gateway callbacks (outbound: gateway → Feishu) ───────────────────────────

    async def on_agent_message(self, event: Any) -> None:
        """Gateway callback: agent produced output."""
        from unified_icc.tmux.window_state_store import window_store

        channel_ids: list[str] = list(getattr(event, "channel_ids", []) or [])
        if not channel_ids:
            session_id = getattr(event, "session_id", "")
            if session_id:
                direct = window_store.find_channel_by_session(session_id)
                if direct:
                    channel_ids = [direct]

        if not channel_ids:
            channel_ids = self._gateway.channel_router.resolve_channels(event.window_id)

        if not channel_ids:
            return

        messages: list = getattr(event, "messages", [])
        for channel_id in channel_ids:
            try:
                await self._dispatch_agent_messages(channel_id, messages)
            except Exception:
                logger.exception("on_agent_message failed for channel %s", channel_id)

    async def on_agent_status(self, event: Any) -> None:
        """Gateway callback: agent status changed."""
        from unified_icc.adapter import CardPayload
        from unified_icc.channels.feishu.cards.thinking import finalize_active_thinking_card

        channel_ids: list[str] = list(getattr(event, "channel_ids", []) or [])
        if not channel_ids:
            channel_ids = self._gateway.channel_router.resolve_channels(event.window_id)

        for channel_id in channel_ids:
            try:
                status = getattr(event, "status", "")
                if status == "interactive":
                    body = str(getattr(event, "display_label", "") or "").strip()
                    await finalize_active_thinking_card(self._adapter, channel_id)
                    provider_name = getattr(event, "provider", "") or "claude"
                    terminal_states: dict[str, dict[str, str]] = {}

                    prompt_state = classify_terminal_prompt(body)
                    if prompt_state and set_terminal_prompt_state(terminal_states, channel_id, body):
                        if body:
                            body = f"{body}\n\n{build_terminal_prompt_reply_guidance(body, prompt_state, provider_name)}"
                        await self._adapter.send_card(
                            channel_id,
                            CardPayload(
                                title=f"{provider_name.title()} needs input",
                                body=body,
                                color="orange",
                            ),
                        )
                else:
                    text = (
                        f"[status] Session {status} — "
                        f"{getattr(event, 'provider', '') or 'unknown'} | "
                        f"{getattr(event, 'working_dir', '') or ''}"
                    )
                    await self._adapter.send_text(channel_id, text)
            except Exception:
                logger.exception("on_agent_status failed for channel %s", channel_id)

    async def on_agent_hook(self, event: Any) -> None:
        """Gateway callback: hook event."""
        channel_ids = self._gateway.channel_router.resolve_channels(event.window_id)
        for channel_id in channel_ids:
            try:
                await self._adapter.send_text(
                    channel_id,
                    f"[hook] {getattr(event, 'hook_name', '')}: {getattr(event, 'message', '')}",
                )
            except Exception:
                logger.exception("on_agent_hook failed for channel %s", channel_id)

    async def _dispatch_agent_messages(
        self,
        channel_id: str,
        messages: list[Any],
    ) -> None:
        """Dispatch agent messages to the Feishu channel."""
        from unified_icc.channels.feishu.cards.streaming import VerboseCardStreamer
        from unified_icc.channels.feishu.cards.thinking import finalize_active_thinking_card, ThinkingCardStreamer
        from unified_icc.channels.feishu.state import get_current_turn_index, get_verbose_state
        from unified_icc.tmux.window_state_store import window_store

        _STX = "\x02"  # noqa: N806
        EXP_START = "\x02EXPQUOTE_START\x02"  # noqa: N806
        EXP_END = "\x02EXPQUOTE_END\x02"  # noqa: N806

        def _clean_text(raw: str) -> str:
            return raw.replace(EXP_START, "").replace(EXP_END, "").replace(_STX, "")

        def _looks_like_thinking(m: Any) -> bool:
            ct = getattr(m, "content_type", "text") or "text"
            if ct == "thinking":
                return True
            if ct != "text":
                return False
            text = getattr(m, "text", "") or ""
            return EXP_START in text or EXP_END in text

        thinking, regular = [], []
        for m in messages:
            if getattr(m, "role", "") == "user":
                continue
            if _looks_like_thinking(m):
                thinking.append(m)
            else:
                regular.append(m)

        verbose_on = getattr(get_verbose_state(channel_id), "_verbose_enabled", False)
        window_id = self._gateway.channel_router.resolve_window(channel_id)
        provider = ""
        if window_id:
            ws = window_store.get_window_state(window_id)
            provider = ws.provider_name or ""

        if thinking:
            streamer = ThinkingCardStreamer(self._adapter, channel_id, placeholder_only=not verbose_on)
            for m in thinking:
                text = _clean_text(getattr(m, "text", "") or "")
                is_complete = getattr(m, "is_complete", True)
                try:
                    await streamer.push_thinking(text, is_complete=is_complete)
                except Exception:
                    logger.exception("ThinkingCardStreamer failed channel=%s", channel_id)

        if regular:
            await finalize_active_thinking_card(self._adapter, channel_id)
            combined = "\n".join(
                _clean_text(getattr(m, "text", "") or "")
                for m in regular
                if getattr(m, "text", "") and not _looks_like_thinking(m)
            )
            if combined:
                streamer = VerboseCardStreamer(
                    client=self._adapter._client,
                    channel_id=channel_id,
                    user_id="__channel__",
                    provider=provider,
                )
                try:
                    await streamer.push(combined, turn_index=get_current_turn_index(channel_id))
                    await streamer.flush()
                except Exception:
                    logger.exception("verbose card send failed channel=%s", channel_id)


def _build_help_text() -> str:
    """Return the formatted help text listing all commands."""
    return (
        "cclark commands:\n"
        "#new — Start a fresh agent workspace for this chat.\n"
        "#mkdir <name> — During #new directory selection, create a new child directory.\n"
        "#status — Show the session bound to this chat.\n"
        "#verbose on|off — Show or hide streaming/thinking details.\n"
        "#session list — List active tmux sessions.\n"
        "#session close <window_id> — Close a specific managed tmux session.\n"
        "#screenshot — Send a screenshot of the current tmux window.\n"
        "#help — Show this help.\n"
        "\n"
        "To begin: send #new, choose a directory, send ok, choose a provider, then choose mode.\n"
        "After a session starts, normal text and slash commands are forwarded to the agent."
    )
