事件类型参考
=============

网关向前端适配器发出的所有事件。

.. code-block:: python

   from unified_icc import AgentMessageEvent, StatusEvent, HookEvent, WindowChangeEvent

AgentMessageEvent
-----------------

当 AI 助手产生新输出（助手消息、工具结果等）时发出。

.. code-block:: python

   @dataclass
   class AgentMessageEvent:
       window_id: str
       session_id: str
       messages: list[AgentMessage]
       channel_ids: list[str] = field(default_factory=list)

**属性：**

* ``window_id``（str）：产生消息的 tmux 窗口
* ``session_id``（str）：AI 助手会话 ID
* ``messages``（list[AgentMessage]）：从转录解析的消息
* ``channel_ids``（list[str]）：绑定到此窗口的频道

AgentMessage
~~~~~~~~~~~~

事件中的单条消息。

.. code-block:: python

   @dataclass(frozen=True, slots=True)
   class AgentMessage:
       text: str
       role: MessageRole  # "user" | "assistant"
       content_type: ContentType  # "text" | "thinking" | "tool_use" | "tool_result" | "local_command"
       is_complete: bool = True
       phase: str | None = None
       tool_use_id: str | None = None
       tool_name: str | None = None
       timestamp: str | None = None

**内容类型：**

* **text** — 普通文本输出
* **thinking** — Claude 的思考/推理输出
* **tool_use** — 工具调用（带 tool_name、tool_use_id）
* **tool_result** — 工具执行结果
* **local_command** — 如 /help、/clear 等 CLI 命令

**示例：**

.. code-block:: python

   def on_message(event: AgentMessageEvent):
       for msg in event.messages:
           if msg.content_type == "tool_use":
               print(f"运行工具：{msg.tool_name}")
           elif msg.content_type == "text":
               print(f"助手：{msg.text}")

StatusEvent
-----------

当 AI 助手状态变更时发出。

.. code-block:: python

   @dataclass
   class StatusEvent:
       window_id: str
       session_id: str
       status: str  # "working" | "idle" | "done" | "dead" | "interactive"
       display_label: str
       channel_ids: list[str] = field(default_factory=list)

**状态值：**

* **working** — AI 助手正在处理
* **idle** — AI 助手等待输入
* **done** — 任务成功完成
* **dead** — AI 助手进程死亡/崩溃
* **interactive** — AI 助手等待用户确认（权限提示）

**示例：**

.. code-block:: python

   def on_status(event: StatusEvent):
       status_emoji = {
           "working": "工作中",
           "idle": "空闲",
           "done": "完成",
           "dead": "死亡",
           "interactive": "交互中",
       }
       emoji = status_emoji.get(event.status, "?")
       print(f"{emoji} {event.display_label}：{event.status}")

HookEvent
---------

转发来自 AI 助手钩子系统的事件。

.. code-block:: python

   @dataclass
   class HookEvent:
       window_id: str
       event_type: str
       session_id: str
       data: dict[str, Any]

**常见事件类型：**

* **SessionStart** — 新 AI 助手会话已启动
* **Notification** — AI 助手要显示通知
* **Stop** — AI 助手停止
* **Task** — 任务状态更新

**示例：**

.. code-block:: python

   def on_hook(event: HookEvent):
       if event.event_type == "SessionStart":
           print(f"新会话：{event.session_id}")
       elif event.event_type == "Notification":
           print(f"通知：{event.data.get('message')}")

WindowChangeEvent
-----------------

当窗口被创建、移除或死亡时发出。

.. code-block:: python

   @dataclass
   class WindowChangeEvent:
       window_id: str
       change_type: str  # "new" | "removed" | "died"
       provider: str
       cwd: str
       display_name: str = ""

**变更类型：**

* **new** — 创建了新窗口
* **removed** — 窗口被显式移除
* **died** — 窗口进程崩溃

**示例：**

.. code-block:: python

   def on_window_change(event: WindowChangeEvent):
       if event.change_type == "new":
           print(f"新窗口：{event.window_id}（{event.provider}）")
           # 绑定到频道
           gateway.bind_channel("my_channel", event.window_id)

内部事件类型
------------

监控子系统内部使用的事件：

.. code-block:: python

   from unified_icc.monitor_events import NewMessage, NewWindowEvent, SessionInfo

* **NewMessage** — 来自转录读取器的内部消息表示
* **NewWindowEvent** — 来自会话生命周期的内部窗口事件
* **SessionInfo** — 来自项目扫描的会话信息
