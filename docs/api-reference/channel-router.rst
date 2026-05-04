频道路由器参考
==============

频道路由器管理平台频道和 tmux 窗口之间的双向映射。

.. code-block:: python

   from unified_icc import channel_router

概述
----

``ChannelRouter`` 管理：

1. **频道 -> 窗口绑定**：将平台频道 ID 映射到 tmux 窗口 ID
2. **窗口 -> 频道查找**：反向映射，查找窗口对应的频道
3. **显示名称**：窗口的人类可读名称
4. **频道元数据**：平台特定数据（用户 ID 等）

频道 ID 格式
------------

频道 ID 是平台特定的字符串：

.. code-block:: text

   "platform:primary:secondary"

**示例：**

.. list-table::
   :header-rows: 1

   * - 平台
     - 格式
   * - 飞书
     - ``feishu:chat_id:thread_id``
   * - Telegram
     - ``telegram:user_id:topic_id``
   * - Discord
     - ``discord:guild:channel``
   * - CLI
     - ``cli:stdin``

方法
----

bind()
~~~~~~

将频道绑定到窗口。

.. code-block:: python

   channel_router.bind(
       channel_id: str,
       window_id: str,
       *,
       user_id: str = "",
       display_name: str = "",
   ) -> None

**参数：**

* ``channel_id``：平台频道标识符
* ``window_id``：tmux 窗口标识符
* ``user_id``：频道的可选平台用户 ID
* ``display_name``：可选的人类可读名称

**约束：**

* 一个频道 -> 一个窗口
* 一个窗口 -> 一个主频道

.. code-block:: python

   # 将飞书线程绑定到 Claude 窗口
   channel_router.bind(
       channel_id="feishu:chat_abc:thread_xyz",
       window_id="@1",
       user_id="U123456",
       display_name="Claude",
   )

unbind()
~~~~~~~~

移除频道绑定。

.. code-block:: python

   channel_router.unbind(channel_id: str) -> None

unbind_window()
~~~~~~~~~~~~~~~

移除窗口的所有绑定。

.. code-block:: python

   channel_router.unbind_window(window_id: str) -> list[str]

**返回：** 已移除的频道 ID 列表

resolve_window()
~~~~~~~~~~~~~~~~

查找频道对应的窗口。

.. code-block:: python

   channel_router.resolve_window(channel_id: str) -> str | None

.. code-block:: python

   window_id = channel_router.resolve_window("feishu:chat_abc:thread_xyz")
   if window_id:
       await gateway.send_to_window(window_id, "你好！")

resolve_channels()
~~~~~~~~~~~~~~~~~~

查找窗口绑定的所有频道。

.. code-block:: python

   channel_router.resolve_channels(window_id: str) -> list[str]

resolve_channel_for_window()
~~~~~~~~~~~~~~~~~~~~~~~~~~~

查找窗口的主频道。

.. code-block:: python

   channel_router.resolve_channel_for_window(window_id: str) -> str | None

get_display_name()
~~~~~~~~~~~~~~~~~~

获取窗口的显示名称。

.. code-block:: python

   channel_router.get_display_name(window_id: str) -> str

set_display_name()
~~~~~~~~~~~~~~~~~~

设置窗口的显示名称。

.. code-block:: python

   channel_router.set_display_name(window_id: str, name: str) -> None

is_bound()
~~~~~~~~~~

检查频道是否已绑定。

.. code-block:: python

   channel_router.is_bound(channel_id: str) -> bool

is_window_bound()
~~~~~~~~~~~~~~~~~

检查是否有频道绑定到窗口。

.. code-block:: python

   channel_router.is_window_bound(window_id: str) -> bool

bound_window_ids()
~~~~~~~~~~~~~~~~~~

获取所有已绑定窗口的 ID。

.. code-block:: python

   channel_router.bound_window_ids() -> set[str]

bound_channel_ids()
~~~~~~~~~~~~~~~~~~~

获取所有已绑定频道的 ID。

.. code-block:: python

   channel_router.bound_channel_ids() -> set[str]

iter_channel_bindings()
~~~~~~~~~~~~~~~~~~~~~~~

遍历所有频道绑定。

.. code-block:: python

   channel_router.iter_channel_bindings() -> Iterator[tuple[str, str, str]]
   # 产出：(channel_id, user_id, window_id)

序列化
------

路由器自动持久化其状态：

.. code-block:: python

   # 状态格式
   {
       "channel_bindings": {"feishu:chat:thread": "@1"},
       "channel_meta": {"feishu:chat:thread": {"user_id": "U123"}},
       "display_names": {"@1": "Claude Code"},
   }

from_dict()
~~~~~~~~~~~

从字典加载状态（网关启动时调用）。

.. code-block:: python

   channel_router.from_dict(data: dict[str, Any]) -> None

处理从旧的 ``thread_bindings`` 格式（ccgram）的迁移。

to_dict()
~~~~~~~~~

序列化状态以持久化。

.. code-block:: python

   channel_router.to_dict() -> dict[str, Any]

兼容属性
--------

用于从 ccgram 的 ThreadRouter 迁移：

.. code-block:: python

   # ccgram 兼容
   channel_router.window_display_names  # _display_names 的别名
   channel_router.channel_bindings     # _bindings 的别名
   channel_router.group_chat_ids      # 空字典（特定于 Telegram）

示例：完整的前端集成
-------------------

.. code-block:: python

   from unified_icc import channel_router, gateway

   class FeishuAdapter:
       def __init__(self):
           self.gateway = gateway

       async def handle_message(self, chat_id: str, thread_id: str, text: str):
           channel_id = f"feishu:{chat_id}:{thread_id}"

           # 查找此频道对应的窗口
           window_id = channel_router.resolve_window(channel_id)
           if not window_id:
               # 创建新窗口
               window = await self.gateway.create_window("/tmp", provider="claude")
               channel_router.bind(
                   channel_id=channel_id,
                   window_id=window.window_id,
                   user_id=chat_id,
               )
               window_id = window.window_id

           # 发送消息给助手
           await self.gateway.send_to_window(window_id, text)

       async def handle_callback(self, callback_data: dict):
           action = callback_data["action"]
           window_id = callback_data["window_id"]

           if action == "stop":
               await self.gateway.kill_window(window_id)
           elif action == "continue":
               await self.gateway.send_key(window_id, "Enter")
