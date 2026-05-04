适配器协议参考
==============

FrontendAdapter
----------------

每个消息平台适配器必须实现的协议。

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

方法详情
~~~~~~~~~

send_text
^^^^^^^^^

发送纯文本消息。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``text``（str）：消息文本

**返回：** 平台消息 ID

.. code-block:: python

   async def send_text(self, channel_id: str, text: str) -> str:
       return await self.client.send_message(channel_id, {"text": text})

send_card
^^^^^^^^^

发送带格式的富文本卡片/消息。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``card``（CardPayload）：富卡片数据

**返回：** 平台消息 ID

.. code-block:: python

   async def send_card(self, channel_id: str, card: CardPayload) -> str:
       payload = self._format_card(card)
       return await self.client.send_message(channel_id, payload)

update_card
^^^^^^^^^^^

就地更新现有卡片消息。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``card_id``（str）：要更新的卡片消息 ID
* ``card``（CardPayload）：新卡片数据

.. code-block:: python

   async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
       payload = self._format_card(card)
       await self.client.update_message(channel_id, card_id, payload)

send_image
^^^^^^^^^^

发送图片。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``image_bytes``（bytes）：PNG/JPEG 图片数据
* ``caption``（str）：可选图片说明

**返回：** 平台消息 ID

.. code-block:: python

   async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
       upload = await self.client.upload_media(channel_id, image_bytes, "image/png")
       return await self.client.send_message(channel_id, {
           "image_key": upload.key,
           "caption": caption,
       })

send_file
^^^^^^^^^

发送文件附件。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``file_path``（str）：磁盘上的文件路径
* ``caption``（str）：可选文件说明

**返回：** 平台消息 ID

.. code-block:: python

   async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
       upload = await self.client.upload_file(channel_id, file_path)
       return await self.client.send_message(channel_id, {
           "file_key": upload.key,
           "caption": caption,
       })

show_prompt
^^^^^^^^^^^

显示带按钮或选项的交互式提示。

**参数：**

* ``channel_id``（str）：目标频道标识符
* ``prompt``（InteractivePrompt）：提示数据

**返回：** 平台消息 ID

.. code-block:: python

   async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
       return await self.client.send_buttons(channel_id, {
           "title": prompt.title,
           "buttons": [{"text": opt["text"]} for opt in prompt.options],
       })

CardPayload
-----------

用于富卡片/消息内容的数据类。

.. code-block:: python

   from unified_icc import CardPayload

**属性：**

.. list-table::
   :header-rows: 1

   * - 属性
     - 类型
     - 默认
     - 说明
   * - ``title``
     - ``str``
     - ``""``
     - 卡片标题
   * - ``body``
     - ``str``
     - ``""``
     - 卡片正文
   * - ``fields``
     - ``dict[str, str]``
     - ``{}``
     - 键值对字段
   * - ``actions``
     - ``list[dict[str, str]]``
     - ``[]``
     - 操作按钮
   * - ``color``
     - ``str``
     - ``""``
     - 强调色（十六进制）

**示例：**

.. code-block:: python

   card = CardPayload(
       title="Claude Code",
       body="正在实现功能...",
       fields={
           "状态": "运行中",
           "Provider": "claude",
       },
       actions=[
           {"text": "停止", "action": "stop"},
           {"text": "继续", "action": "continue"},
       ],
       color="#007AFF",
   )

InteractivePrompt
-----------------

用于交互式提示的数据类。

.. code-block:: python

   from unified_icc import InteractivePrompt

**属性：**

.. list-table::
   :header-rows: 1

   * - 属性
     - 类型
     - 默认
     - 说明
   * - ``prompt_type``
     - ``str``
     - （必填）
     - 类型："question"、"permission"、"selection"
   * - ``title``
     - ``str``
     - （必填）
     - 提示标题/文本
   * - ``options``
     - ``list[dict[str, str]]``
     - ``[]``
     - 按钮选项
   * - ``cancel_text``
     - ``str``
     - ``"取消"``
     - 取消按钮文本

**示例：**

.. code-block:: python

   prompt = InteractivePrompt(
       prompt_type="permission",
       title="Claude 想要运行 rm -rf /？",
       options=[
           {"text": "允许", "value": "allow"},
           {"text": "拒绝", "value": "deny"},
       ],
       cancel_text="取消",
   )

实现示例
--------

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
           # 存储以供后续更新
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

适配器使用 ``runtime_checkable`` 来启用 isinstance 检查：

.. code-block:: python

   from typing import runtime_checkable

   @runtime_checkable
   class FrontendAdapter(Protocol):
       ...

   # 检查类是否实现了该协议
   if isinstance(my_adapter, FrontendAdapter):
       print("适配器有效！")
