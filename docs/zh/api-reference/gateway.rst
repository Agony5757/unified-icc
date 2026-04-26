网关 API 参考
==============

UnifiedICC
-----------

编排所有子系统的主网关类。

.. code-block:: python

   from unified_icc import UnifiedICC

**初始化：**

.. code-block:: python

   gateway = UnifiedICC(gateway_config=None)

* ``gateway_config``（GatewayConfig | None）：可选的自定义配置。若为 None，则使用全局 ``config`` 单例。

生命周期方法
------------

start()
~~~~~~~

启动网关：连接到 tmux、加载状态、开始监控。

.. code-block:: python

   await gateway.start()

**过程：**

1. 确保 tmux 会话存在（``tmux_manager.ensure_session()``）
2. 从 ``~/.cclark/state.json`` 加载持久化状态
3. 将所有单例组件连接在一起
4. 启动 SessionMonitor 轮询循环

stop()
~~~~~~

停止网关：刷新状态、停止监控。

.. code-block:: python

   await gateway.stop()

**过程：**

1. 停止 SessionMonitor
2. 刷新所有待处理的状态写入
3. 记录最终状态

窗口管理
--------

create_window()
~~~~~~~~~~~~~~~

创建运行 AI 助手的新 tmux 窗口。

.. code-block:: python

   window = await gateway.create_window(
       work_dir="/path/to/project",
       provider="claude",
       mode="normal",  # 或 "yolo" 绕过审批
   )
   print(window.window_id)  # 例如 "cclark:1"
   print(window.provider)  # "claude"
   print(window.cwd)        # "/path/to/project"

**参数：**

* ``work_dir``（str）：新窗口的工作目录
* ``provider``（str）：AI 助手 Provider 名称（"claude"、"codex"、"gemini"、"pi"、"shell"）
* ``mode``（str）：审批模式（"normal" 或 "yolo"）

**返回：** 包含 window_id、display_name、provider、cwd 的 ``WindowInfo``

kill_window()
~~~~~~~~~~~~~

杀死 tmux 窗口并清理绑定。

.. code-block:: python

   await gateway.kill_window("cclark:1")

**过程：**

1. 解除窗口的所有频道绑定
2. 从状态存储中移除窗口
3. 杀死 tmux 窗口

list_windows()
~~~~~~~~~~~~~~

列出所有管理的窗口。

.. code-block:: python

   windows = await gateway.list_windows()
   for w in windows:
       print(f"{w.window_id}: {w.display_name} ({w.provider})")

**返回：** ``WindowInfo`` 对象列表

消息分发
--------

send_to_window()
~~~~~~~~~~~~~~~~

向 tmux 窗口发送文本输入。

.. code-block:: python

   await gateway.send_to_window("cclark:1", "你好，Claude！")

**参数：**

* ``window_id``（str）：目标窗口
* ``text``（str）：要发送的文本（自动附加换行符）

send_key()
~~~~~~~~~~

向 tmux 窗口发送特殊按键。

.. code-block:: python

   await gateway.send_key("cclark:1", "C-c")  # Ctrl+C
   await gateway.send_key("cclark:1", "C-d")  # Ctrl+D

**参数：**

* ``window_id``（str）：目标窗口
* ``key``（str）：按键组合（格式："C-x" 表示 Ctrl+x）

输出捕获
--------

capture_pane()
~~~~~~~~~~~~~~

捕获当前窗格内容。

.. code-block:: python

   content = await gateway.capture_pane("cclark:1")
   print(content)

**返回：** 包含窗格文本内容的字符串

capture_screenshot()
~~~~~~~~~~~~~~~~~~~~

将窗格捕获为 PNG 字节的截图。

.. code-block:: python

   image_bytes = await gateway.capture_screenshot("cclark:1")
   with open("screenshot.png", "wb") as f:
       f.write(image_bytes)

**返回：** 字节形式的 PNG 图像数据

事件订阅
--------

on_message()
~~~~~~~~~~~~

注册助手消息回调。

.. code-block:: python

   def handle_message(event: AgentMessageEvent):
       for msg in event.messages:
           print(f"[{msg.role}] {msg.text}")

   gateway.on_message(handle_message)

**参数：**

* ``callback``：接收 ``AgentMessageEvent`` 的函数

on_status()
~~~~~~~~~~~

注册状态变更回调。

.. code-block:: python

   def handle_status(event: StatusEvent):
       print(f"状态：{event.status}（{event.display_label}）")

   gateway.on_status(handle_status)

**参数：**

* ``callback``：接收 ``StatusEvent`` 的函数

on_hook_event()
~~~~~~~~~~~~~~~

注册钩子事件回调。

.. code-block:: python

   def handle_hook(event: HookEvent):
       print(f"钩子：{event.event_type}")

   gateway.on_hook_event(handle_hook)

**参数：**

* ``callback``：接收 ``HookEvent`` 的函数

on_window_change()
~~~~~~~~~~~~~~~~~~

注册窗口事件回调。

.. code-block:: python

   def handle_window(event: WindowChangeEvent):
       print(f"窗口 {event.change_type}：{event.window_id}")

   gateway.on_window_change(handle_window)

**参数：**

* ``callback``：接收 ``WindowChangeEvent`` 的函数

频道路由
--------

bind_channel()
~~~~~~~~~~~~~~

将频道绑定到窗口。

.. code-block:: python

   gateway.bind_channel("feishu:chat_123:thread_456", "cclark:1")

**参数：**

* ``channel_id``（str）：平台频道标识符
* ``window_id``（str）：tmux 窗口标识符

**注意：** 每个频道只能绑定一个窗口，每个窗口只能有一个主频道。

unbind_channel()
~~~~~~~~~~~~~~~~

移除频道绑定。

.. code-block:: python

   gateway.unbind_channel("feishu:chat_123:thread_456")

resolve_window()
~~~~~~~~~~~~~~~~

查找频道对应的窗口。

.. code-block:: python

   window_id = gateway.resolve_window("feishu:chat_123:thread_456")
   if window_id:
       await gateway.send_to_window(window_id, "消息")

**返回：** 窗口 ID，未绑定则返回 None

resolve_channels()
~~~~~~~~~~~~~~~~~~

查找窗口绑定的所有频道。

.. code-block:: python

   channels = gateway.resolve_channels("cclark:1")
   for channel in channels:
       await adapter.send_text(channel, "通知")

**返回：** 频道 ID 列表

Provider 访问
-------------

get_provider()
~~~~~~~~~~~~~~

获取窗口的 Provider。

.. code-block:: python

   provider = gateway.get_provider("cclark:1")
   print(provider.capabilities.name)  # "claude"

**返回：** 窗口 AI 助手的 Provider 实例

WindowInfo
----------

包含窗口信息的数据类。

.. code-block:: python

   from unified_icc import WindowInfo

**属性：**

* ``window_id``（str）：tmux 窗口标识符
* ``display_name``（str）：人类可读的名称
* ``provider``（str）：AI 助手 Provider 名称
* ``cwd``（str）：工作目录
* ``session_id``（str）：AI 助手会话 ID（若可用）
