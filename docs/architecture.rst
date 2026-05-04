架构概览
=========

Unified ICC 采用分层架构，在消息前端、网关核心和 AI 助手执行层（tmux）之间有清晰的职责划分。

系统层次
--------

**第 1 层：消息前端（外部）**

消息前端（飞书、Telegram、Discord 等）**不属于 unified-icc 的一部分**。每个前端通过实现 ``FrontendAdapter`` 协议来与网关通信。

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────┐
   │                     前端（例如 cclark）                        │
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ Webhook     │  │ 飞书        │  │ FeishuAdapter       ││
   │  │ 服务器      │  │ API 客户端  │  │ (FrontendAdapter)   ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   └────────────────────────────┬────────────────────────────────┘
                                │ FrontendAdapter API
                                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    unified_icc 网关                          │
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ UnifiedICC  │  │ChannelRouter│  │ 事件系统             ││
   │  │ （主 API）  │  │             │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ Session     │  │ TmuxManager │  │ SessionMonitor      ││
   │  │ Manager     │  │             │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ State       │  │ WindowState │  │ ProviderRegistry    ││
   │  │ Persistence │  │ Store       │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   └────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                       tmux 会话                             │
   │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────┐│
   │  │ @0        │  │ @1        │  │ @2        │  │ @main   ││
   │  │ (claude)  │  │ (codex)   │  │ (gemini)  │  │         ││
   │  └───────────┘  └───────────┘  └───────────┘  └─────────┘│
   └─────────────────────────────────────────────────────────────┘

组件职责
--------

**UnifiedICC（gateway.py）**

主要公共 API 类，编排所有子系统：

* **生命周期**：``start()`` / ``stop()`` — 初始化连接、加载状态、启动监控
* **窗口管理**：``create_window()``、``kill_window()``、``list_windows()``
* **消息分发**：``send_to_window()``、``send_key()``
* **输出捕获**：``capture_pane()``、``capture_screenshot()``
* **频道路由**：``bind_channel()``、``unbind_channel()``、``resolve_window()``
* **事件订阅**：``on_message()``、``on_status()``、``on_hook_event()``、``on_window_change()``

**ChannelRouter（channel_router.py）**

平台无关的双向频道-窗口映射：

* **bind()**：将 channel_id 与 window_id 关联
* **resolve_window()**：查找频道对应的窗口
* **resolve_channels()**：查找窗口绑定的所有频道
* **序列化**：``to_dict()`` / ``from_dict()`` 用于状态持久化

频道 ID 格式：``"platform:identifier:sub_identifier"``（例如 ``"feishu:chat_123:thread_456"``）

**SessionMonitor（session_monitor.py）**

异步轮询循环，监控所有 AI 助手会话：

1. 从 ``events.jsonl`` 读取钩子事件
2. 对比 session_map 变更
3. 通过 TranscriptReader 读取转录更新
4. 触发回调：NewMessage、NewWindowEvent、HookEvent

**TmuxManager（tmux_manager.py）**

封装 libtmux 实现底层 tmux 操作：

* 窗口创建/销毁
* 窗格捕获（文本和截图）
* 按键/输入发送
* 外部会话发现

**FrontendAdapter 协议（adapter.py）**

前端实现的契约：

.. code-block:: python

   class FrontendAdapter(Protocol):
       async def send_text(self, channel_id: str, text: str) -> str
       async def send_card(self, channel_id: str, card: CardPayload) -> str
       async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None
       async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str
       async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str
       async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str

数据流
------

**收消息流程（用户 -> 助手）**

1. 前端从消息平台收到消息
2. 前端通过 channel_router.resolve_window(channel_id) 解析 window_id
3. 前端通过 gateway.send_to_window(window_id, text) 发送文本
4. TmuxManager.send_to_window() 将文本送入 tmux 窗格
5. AI 助手进程收到输入并产生输出
6. SessionMonitor 检测到新的转录内容
7. 网关通过 on_message() 回调触发 AgentMessageEvent
8. 前端收到事件后格式化并发送到消息平台

**发消息流程（助手 -> 用户）**

1. AI 助手产生输出（输出到窗格）
2. SessionMonitor 轮询检测到新转录内容
3. TranscriptReader 按 Provider 格式解析新行
4. Provider.parse_transcript_entries() 转换为 AgentMessage 对象
5. 网关通过 on_message() 回调触发 AgentMessageEvent
6. 前端收到事件
7. 前端格式化消息（卡片、可展开块等）
8. 前端通过 FrontendAdapter 发送到消息平台

状态管理
--------

**状态文件**

* ``state.json``（``~/.unified-icc/``）— 主网关状态
* ``session_map.json``（``~/.unified-icc/``）— tmux 会话映射
* ``monitor_state.json``（``~/.unified-icc/``）— 轮询循环状态
* ``events.jsonl``（``~/.unified-icc/``）— 钩子事件日志

**持久化策略**

1. **去中心化写入**：StatePersistence 在变更后 0.5 秒调度写入
2. **原子写入**：先写临时文件，再 rename
3. **延迟加载**：状态在网关启动时加载
4. **迁移支持**：旧格式在加载时自动迁移

目录结构
--------

::

   src/unified_icc/
   ├── __init__.py           # 公共 API 导出
   ├── gateway.py            # UnifiedICC 主类
   ├── adapter.py            # FrontendAdapter 协议
   ├── event_types.py        # 事件数据类
   ├── channel_router.py     # 频道-窗口路由
   ├── config.py             # GatewayConfig
   ├── tmux_manager.py       # tmux 操作
   ├── session.py            # SessionManager
   ├── session_monitor.py    # 轮询循环协调器
   ├── session_lifecycle.py  # 会话映射对比
   ├── session_map.py        # 会话映射 I/O
   ├── state_persistence.py  # 去中心化 JSON 持久化
   ├── window_state_store.py # 窗口状态追踪
   ├── event_reader.py       # events.jsonl 读取器
   ├── transcript_reader.py  # 转录 I/O
   ├── transcript_parser.py  # 转录 -> 消息
   ├── terminal_parser.py    # 终端 UI 检测
   ├── hook.py              # Claude 钩子事件
   ├── idle_tracker.py      # 空闲计时器
   ├── monitor_state.py      # 轮询状态
   ├── monitor_events.py     # 内部事件类型
   ├── window_resolver.py    # 窗口 ID 重映射
   ├── window_view.py        # 窗口快照
   ├── mailbox.py           # 助手间消息
   ├── cc_commands.py       # Claude 命令发现
   ├── expandable_quote.py  # 可展开文本块
   ├── topic_state_registry.py # 话题状态
   ├── claude_task_state.py # Claude 任务追踪
   └── providers/
       ├── __init__.py       # 注册表 + 辅助函数
       ├── base.py           # AgentProvider 协议
       ├── registry.py       # ProviderRegistry
       ├── _jsonl.py         # JSONL 基类
       ├── claude.py         # Claude Provider
       ├── codex.py          # Codex Provider
       ├── gemini.py         # Gemini Provider
       ├── pi.py             # Pi Provider
       ├── shell.py          # Shell Provider
       └── process_detection.py # 进程检测
