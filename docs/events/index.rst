事件系统
=========

Unified ICC 采用事件驱动架构，网关发出事件，前端可以订阅这些事件。

事件流
------

::

   ┌─────────────────────────────────────────────────────────────┐
   │                    SessionMonitor                            │
   │                                                              │
   │  轮询循环 ──► 检测变更 ──► 触发事件                        │
   │      │                                           │            │
   │      │                                           ▼            │
   │      │                              ┌───────────────────┐   │
   │      │                              │ 事件回调           │   │
   │      │                              │ (on_message 等)    │   │
   │      │                              └───────────────────┘   │
   │      │                                           │            │
   │      ▼                                           ▼            │
   │  TranscriptReader                    FrontendAdapter         │
   │  （解析输出）                     （发送到平台）             │
   └─────────────────────────────────────────────────────────────┘

订阅事件
--------

.. code-block:: python

   from unified_icc import UnifiedICC

   gateway = UnifiedICC()

   # 注册回调
   gateway.on_message(my_message_handler)
   gateway.on_status(my_status_handler)
   gateway.on_hook_event(my_hook_handler)
   gateway.on_window_change(my_window_handler)

事件类型
--------

AgentMessageEvent
~~~~~~~~~~~~~~~~~~

当 AI 助手产生输出时触发。

.. code-block:: python

   def my_message_handler(event):
       for msg in event.messages:
           print(f"[{msg.role}] {msg.text}")

StatusEvent
~~~~~~~~~~~

当 AI 助手状态变更时触发。

.. code-block:: python

   def my_status_handler(event):
       print(f"状态：{event.status}")

HookEvent
~~~~~~~~~

当有钩子事件（SessionStart、Notification 等）时触发。

.. code-block:: python

   def my_hook_handler(event):
       if event.event_type == "SessionStart":
           print(f"新会话：{event.session_id}")

WindowChangeEvent
~~~~~~~~~~~~~~~~~~

当窗口被创建或移除时触发。

.. code-block:: python

   def my_window_handler(event):
       print(f"窗口 {event.change_type}：{event.window_id}")

内部事件流
----------

转录 → AgentMessageEvent
~~~~~~~~~~~~~~~~~~~~~~~~

::

   1. TranscriptReader._process_session_file()
      ↓
   2. TranscriptReader._read_new_lines() 读取新行
      ↓
   3. Provider.parse_transcript_line() 解析每一行
      ↓
   4. Provider.parse_transcript_entries() 转换为 AgentMessage
      ↓
   5. SessionMonitor._transcript_reader._process_session_file() 接收消息
      ↓
   6. 收集 NewMessage 对象
      ↓
   7. SessionMonitor.check_for_updates() 返回新消息
      ↓
   8. SessionMonitor._monitor_loop() 调用 _message_callback
      ↓
   9. Gateway._on_new_message() 包装为 AgentMessageEvent
      ↓
   10. 调用用户回调

会话生命周期 → WindowChangeEvent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   1. SessionMonitor._monitor_loop() 运行轮询
      ↓
   2. SessionMonitor._load_current_session_map() 读取 session_map.json
      ↓
   3. SessionLifecycle.reconcile() 对比新旧状态
      ↓
   4. 检测到新窗口 → result.new_windows 填充
      ↓
   5. SessionMonitor._detect_and_cleanup_changes() 触发回调
      ↓
   6. 创建 NewWindowEvent
      ↓
   7. Gateway._on_new_window() 包装为 WindowChangeEvent
      ↓
   8. 调用用户回调

在前端中处理事件
----------------

简单文本转发
~~~~~~~~~~~~

.. code-block:: python

   async def relay_messages(event):
       for msg in event.messages:
           if msg.text and msg.is_complete:
               for channel in event.channel_ids:
                   await adapter.send_text(channel, msg.text)

   gateway.on_message(relay_messages)

富卡片格式化
~~~~~~~~~~~~

.. code-block:: python

   from unified_icc import CardPayload

   async def format_as_card(event):
       for msg in event.messages:
           if msg.content_type == "tool_use":
               card = CardPayload(
                   title=f"工具：{msg.tool_name}",
                   body=msg.text[:500],
                   color="#FF6B6B",
               )
           else:
               card = CardPayload(
                   title="Claude",
                   body=msg.text[:2000],
                   color="#007AFF",
               )

           for channel in event.channel_ids:
               await adapter.send_card(channel, card)

   gateway.on_message(format_as_card)

流式更新
~~~~~~~~

.. code-block:: python

   from unified_icc import CardPayload

   # 追踪已发送的消息以便更新
   _sent_messages: dict[str, str] = {}  # session_id -> card_id

   async def stream_messages(event):
       for msg in event.messages:
           if not msg.is_complete:
               # 部分更新
               channel = event.channel_ids[0] if event.channel_ids else None
               if channel and event.session_id in _sent_messages:
                   card_id = _sent_messages[event.session_id]
                   card = CardPayload(title="Claude", body=msg.text)
                   await adapter.update_card(channel, card_id, card)
           else:
               # 最终消息
               for channel in event.channel_ids:
                   card = CardPayload(title="Claude", body=msg.text)
                   card_id = await adapter.send_card(channel, card)
                   _sent_messages[event.session_id] = card_id

   gateway.on_message(stream_messages)

错误处理
~~~~~~~~

.. code-block:: python

   def safe_handler(event):
       try:
           process_event(event)
       except Exception as e:
           logger.exception(f"处理事件时出错：{e}")
           # 通知管理员
           asyncio.create_task(adapter.send_text("admin", f"错误：{e}"))

   gateway.on_message(safe_handler)

钩子事件
--------

钩子事件来自 AI 助手的钩子系统（主要是 Claude）：

.. code-block:: python

   from unified_icc import HookEvent

   # 钩子事件类型
   HOOK_EVENTS = {
       "SessionStart": "新会话已启动",
       "Notification": "AI 助手通知",
       "Stop": "AI 助手停止",
       "Task": "任务状态更新",
   }

处理 SessionStart
~~~~~~~~~~~~~~~~~

.. code-block:: python

   async def on_session_start(event):
       if event.event_type == "SessionStart":
           session_id = event.data.get("session_id")
           cwd = event.data.get("cwd", "")
           print(f"会话 {session_id} 在 {cwd} 中启动")

           # 如有需要，自动绑定到频道
           # channel_router.bind("feishu:chat:thread", window_id)

   gateway.on_hook_event(on_session_start)

处理通知
~~~~~~~~

.. code-block:: python

   async def on_notification(event):
       if event.event_type == "Notification":
           message = event.data.get("message", "")
           level = event.data.get("level", "info")  # info、warning、error

           for channel in event.channel_ids:
               await adapter.send_text(channel, f"[{level.upper()}] {message}")

   gateway.on_hook_event(on_notification)

状态事件
--------

状态变更表示 AI 助手的当前状态：

.. code-block:: python

   from unified_icc import StatusEvent

   STATUS_HANDLERS = {
       "working": handle_working,
       "idle": handle_idle,
       "done": handle_done,
       "dead": handle_dead,
       "interactive": handle_interactive,
   }

   def on_status_change(event):
       handler = STATUS_HANDLERS.get(event.status, handle_unknown)
       handler(event)

   gateway.on_status(on_status_change)

窗口事件
--------

.. code-block:: python

   async def on_window_event(event):
       if event.change_type == "new":
           # 创建了新窗口
           print(f"新 {event.provider} 窗口：{event.window_id}")
           # 绑定到默认频道
           gateway.bind_channel("default_channel", event.window_id)

       elif event.change_type == "removed":
           # 窗口被显式杀死
           print(f"窗口已移除：{event.window_id}")
           # 清理任何状态

       elif event.change_type == "died":
           # 窗口崩溃
           print(f"窗口死亡：{event.window_id}")
           # 通知用户
           for channel in gateway.resolve_channels(event.window_id):
               await adapter.send_text(channel, "⚠️ AI 助手崩溃了！")

   gateway.on_window_change(on_window_event)
