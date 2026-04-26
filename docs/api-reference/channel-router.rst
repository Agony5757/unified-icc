Channel Router Reference
========================

The channel router manages bidirectional mappings between platform channels and tmux windows.

.. code-block:: python

   from unified_icc import channel_router

Overview
--------

The ``ChannelRouter`` manages:

1. **Channel -> Window bindings**: Maps platform channel IDs to tmux window IDs
2. **Window -> Channel lookup**: Reverse mapping to find channels for a window
3. **Display names**: Human-readable names for windows
4. **Channel metadata**: Platform-specific data (user IDs, etc.)

Channel ID Format
-----------------

Channel IDs are platform-specific strings:

.. code-block:: text

   "platform:primary:secondary"

**Examples:**

===========  ========================================
Platform     Format
===========  ========================================
Feishu       "feishu:chat_id:thread_id"
Telegram     "telegram:user_id:topic_id"
Discord      "discord:guild:channel"
CLI          "cli:stdin"
===========  ========================================

Methods
-------

bind()
~~~~~~

Bind a channel to a window.

.. code-block:: python

   channel_router.bind(
       channel_id: str,
       window_id: str,
       *,
       user_id: str = "",
       display_name: str = "",
   ) -> None

**Parameters:**

* ``channel_id``: Platform channel identifier
* ``window_id``: tmux window identifier
* ``user_id``: Optional platform user ID for the channel
* ``display_name``: Optional human-readable name

**Enforcement:**

* One channel -> one window
* One window -> one primary channel

.. code-block:: python

   # Bind a Feishu thread to a Claude window
   channel_router.bind(
       channel_id="feishu:chat_abc:thread_xyz",
       window_id="cclark:1",
       user_id="U123456",
       display_name="Claude",
   )

unbind()
~~~~~~~~

Remove a channel binding.

.. code-block:: python

   channel_router.unbind(channel_id: str) -> None

unbind_window()
~~~~~~~~~~~~~~~

Remove all bindings for a window.

.. code-block:: python

   channel_router.unbind_window(window_id: str) -> list[str]

**Returns:** List of removed channel IDs

resolve_window()
~~~~~~~~~~~~~~~~

Find window for a channel.

.. code-block:: python

   channel_router.resolve_window(channel_id: str) -> str | None

.. code-block:: python

   window_id = channel_router.resolve_window("feishu:chat_abc:thread_xyz")
   if window_id:
       await gateway.send_to_window(window_id, "Hello!")

resolve_channels()
~~~~~~~~~~~~~~~~~~

Find all channels for a window.

.. code-block:: python

   channel_router.resolve_channels(window_id: str) -> list[str]

resolve_channel_for_window()
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Find primary channel for a window.

.. code-block:: python

   channel_router.resolve_channel_for_window(window_id: str) -> str | None

get_display_name()
~~~~~~~~~~~~~~~~~~

Get display name for a window.

.. code-block:: python

   channel_router.get_display_name(window_id: str) -> str

set_display_name()
~~~~~~~~~~~~~~~~~~

Set display name for a window.

.. code-block:: python

   channel_router.set_display_name(window_id: str, name: str) -> None

is_bound()
~~~~~~~~~~

Check if a channel is bound.

.. code-block:: python

   channel_router.is_bound(channel_id: str) -> bool

is_window_bound()
~~~~~~~~~~~~~~~~~

Check if any channel is bound to a window.

.. code-block:: python

   channel_router.is_window_bound(window_id: str) -> bool

bound_window_ids()
~~~~~~~~~~~~~~~~~~

Get all bound window IDs.

.. code-block:: python

   channel_router.bound_window_ids() -> set[str]

bound_channel_ids()
~~~~~~~~~~~~~~~~~~~

Get all bound channel IDs.

.. code-block:: python

   channel_router.bound_channel_ids() -> set[str]

iter_channel_bindings()
~~~~~~~~~~~~~~~~~~~~~~~

Iterate over all channel bindings.

.. code-block:: python

   channel_router.iter_channel_bindings() -> Iterator[tuple[str, str, str]]
   # Yields: (channel_id, user_id, window_id)

Serialization
-------------

The router persists its state automatically:

.. code-block:: python

   # State format
   {
       "channel_bindings": {"feishu:chat:thread": "cclark:1"},
       "channel_meta": {"feishu:chat:thread": {"user_id": "U123"}},
       "display_names": {"cclark:1": "Claude Code"},
   }

from_dict()
~~~~~~~~~~~

Load state from dict (called during gateway startup).

.. code-block:: python

   channel_router.from_dict(data: dict[str, Any]) -> None

Handles migration from old ``thread_bindings`` format (ccgram).

to_dict()
~~~~~~~~~

Serialize state for persistence.

.. code-block:: python

   channel_router.to_dict() -> dict[str, Any]

Compatibility Properties
------------------------

For migration from ccgram's ThreadRouter:

.. code-block:: python

   # ccgram compatibility
   channel_router.window_display_names  # alias for _display_names
   channel_router.channel_bindings     # alias for _bindings
   channel_router.group_chat_ids       # empty dict (Telegram-specific)

Example: Full Frontend Integration
----------------------------------

.. code-block:: python

   from unified_icc import channel_router, gateway

   class FeishuAdapter:
       def __init__(self):
           self.gateway = gateway

       async def handle_message(self, chat_id: str, thread_id: str, text: str):
           channel_id = f"feishu:{chat_id}:{thread_id}"

           # Find window for this channel
           window_id = channel_router.resolve_window(channel_id)
           if not window_id:
               # Create new window
               window = await self.gateway.create_window("/tmp", provider="claude")
               channel_router.bind(
                   channel_id=channel_id,
                   window_id=window.window_id,
                   user_id=chat_id,
               )
               window_id = window.window_id

           # Send message to agent
           await self.gateway.send_to_window(window_id, text)

       async def handle_callback(self, callback_data: dict):
           action = callback_data["action"]
           window_id = callback_data["window_id"]

           if action == "stop":
               await self.gateway.kill_window(window_id)
           elif action == "continue":
               await self.gateway.send_key(window_id, "Enter")
