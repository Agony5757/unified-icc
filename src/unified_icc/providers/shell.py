"""Shell provider — generic shell session.

A minimal provider for raw shell windows (bash, zsh, etc.) that are not
running a dedicated agent CLI. Does not support hooks, mailbox delivery,
or command discovery.
"""

from __future__ import annotations


from unified_icc.providers._jsonl import JsonlProvider
from unified_icc.providers.base import ProviderCapabilities

KNOWN_SHELLS = frozenset({"bash", "zsh", "sh", "fish", "dash", "ksh", "csh", "tcsh"})

_SHELL_BUILTINS: dict[str, str] = {}


class ShellProvider(JsonlProvider):
    _CAPS = ProviderCapabilities(
        name="shell",
        launch_command="bash",
        supports_incremental_read=False,
        transcript_format="plain",
        supports_mailbox_delivery=False,
        chat_first_command_path=True,
    )
    _BUILTINS = _SHELL_BUILTINS
