:orphan:

Adapter Protocol Reference
===========================

FrontendAdapter
---------------

Protocol that each messaging platform adapter must implement.

.. code-block:: python

   from unified_icc import FrontendAdapter, CardPayload, InteractivePrompt
   from typing import Protocol, runtime_checkable

   @runtime_checkable
   class FrontendAdapter(Protocol):
       async def send_text(self, channel_id: str, text: str) -> str
       async def send_card(self, channel_id: str, card: CardPayload) -> str
       async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None
       async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str
       async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str
       async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str

Method Details
~~~~~~~~~~~~~~~

send_text
^^^^^^^^^

Send plain text message.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``text`` (str): Message text

**Returns:** Platform message ID

.. code-block:: python

   async def send_text(self, channel_id: str, text: str) -> str:
       return await self.client.send_message(channel_id, {"text": text})

send_card
^^^^^^^^^

Send a rich card/message with formatting.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``card`` (CardPayload): Rich card data

**Returns:** Platform message ID

.. code-block:: python

   async def send_card(self, channel_id: str, card: CardPayload) -> str:
       payload = self._format_card(card)
       return await self.client.send_message(channel_id, payload)

update_card
^^^^^^^^^^^

Update an existing card message in-place.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``card_id`` (str): Message ID of the card to update
* ``card`` (CardPayload): New card data

.. code-block:: python

   async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
       payload = self._format_card(card)
       await self.client.update_message(channel_id, card_id, payload)

send_image
^^^^^^^^^^

Send an image.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``image_bytes`` (bytes): PNG/JPEG image data
* ``caption`` (str): Optional image caption

**Returns:** Platform message ID

.. code-block:: python

   async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
       upload = await self.client.upload_media(channel_id, image_bytes, "image/png")
       return await self.client.send_message(channel_id, {
           "image_key": upload.key,
           "caption": caption,
       })

send_file
^^^^^^^^^

Send a file attachment.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``file_path`` (str): Path to file on disk
* ``caption`` (str): Optional file caption

**Returns:** Platform message ID

.. code-block:: python

   async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
       upload = await self.client.upload_file(channel_id, file_path)
       return await self.client.send_message(channel_id, {
           "file_key": upload.key,
           "caption": caption,
       })

show_prompt
^^^^^^^^^^^

Show an interactive prompt with buttons or selections.

**Parameters:**

* ``channel_id`` (str): Target channel identifier
* ``prompt`` (InteractivePrompt): Prompt data

**Returns:** Platform message ID

.. code-block:: python

   async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
       return await self.client.send_buttons(channel_id, {
           "title": prompt.title,
           "buttons": [{"text": opt["text"]} for opt in prompt.options],
       })

CardPayload
-----------

Dataclass for rich card/message content.

.. code-block:: python

   from unified_icc import CardPayload

**Attributes:**

===============  ====================  ============  ============
Attribute        Type                  Default       Description
===============  ====================  ============  ============
title            str                   ""            Card title
body             str                   ""            Card body text
fields           dict[str, str]        {}            Key-value fields
actions          list[dict[str, str]]  []            Action buttons
color            str                   ""            Accent color (hex)
===============  ====================  ============  ============

**Example:**

.. code-block:: python

   card = CardPayload(
       title="Claude Code",
       body="Working on feature implementation...",
       fields={
           "Status": "Running",
           "Provider": "claude",
       },
       actions=[
           {"text": "Stop", "action": "stop"},
           {"text": "Continue", "action": "continue"},
       ],
       color="#007AFF",
   )

InteractivePrompt
-----------------

Dataclass for interactive prompts.

.. code-block:: python

   from unified_icc import InteractivePrompt

**Attributes:**

===============  ====================  ============  ============
Attribute        Type                  Default       Description
===============  ====================  ============  ============
prompt_type      str                   (required)    Type: "question", "permission", "selection"
title            str                   (required)    Prompt title/text
options          list[dict[str, str]]  []            Button options
cancel_text      str                   "Cancel"       Cancel button text
===============  ====================  ============  ============

**Example:**

.. code-block:: python

   prompt = InteractivePrompt(
       prompt_type="permission",
       title="Claude wants to run rm -rf /?",
       options=[
           {"text": "Allow", "value": "allow"},
           {"text": "Deny", "value": "deny"},
       ],
       cancel_text="Cancel",
   )

Implementation Example
----------------------

.. code-block:: python

   import asyncio
   from unified_icc import FrontendAdapter, CardPayload, InteractivePrompt

   class MyPlatformAdapter(FrontendAdapter):
       def __init__(self, client):
           self.client = client
           self._sent_messages = {}  # card_id -> message_id

       async def send_text(self, channel_id: str, text: str) -> str:
           return await self.client.send_text(channel_id, text)

       async def send_card(self, channel_id: str, card: CardPayload) -> str:
           msg_id = await self.client.send_card(channel_id, {
               "title": card.title,
               "content": card.body,
               "fields": card.fields,
               "actions": card.actions,
               "color": card.color,
           })
           # Store for later updates
           cache_key = f"{channel_id}:{card.title}"
           self._sent_messages[cache_key] = msg_id
           return msg_id

       async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
           await self.client.update_message(card_id, {
               "title": card.title,
               "content": card.body,
               "fields": card.fields,
           })

       async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
           return await self.client.send_image(channel_id, image_bytes, caption)

       async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
           return await self.client.send_file(channel_id, file_path, caption)

       async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
           return await self.client.send_buttons(
               channel_id,
               prompt.title,
               [opt["text"] for opt in prompt.options],
           )

The adapter uses ``runtime_checkable`` to enable isinstance checks:

.. code-block:: python

   from typing import runtime_checkable

   @runtime_checkable
   class FrontendAdapter(Protocol):
       ...

   # Check if a class implements the protocol
   if isinstance(my_adapter, FrontendAdapter):
       print("Adapter is valid!")
