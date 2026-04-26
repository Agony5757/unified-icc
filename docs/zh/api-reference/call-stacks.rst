函数调用栈
===========

本文档追踪 unified-icc 关键操作的函数调用链。

窗口创建
--------

创建新的 AI 助手窗口涉及多个子系统：

.. code-block:: text

   gateway.create_window(work_dir, provider, mode)
   |
   ├── resolve_launch_command(provider)
   |   ├── _ensure_registered()
   |   ├── registry.get(provider)
   |   └── return capabilities.launch_command
   |
   ├── tmux_manager.create_window()
   |   ├── tmux_manager.ensure_session()
   |   |   ├── libtmux.Server().has_session()
   |   |   └── libtmux.Session() if not exists
   |   |
   |   ├── libtmux.Window.create_window()
   |   |   ├── Session.create_window()
   |   |   └── Window.send_keys() for launch command
   |   |
   |   ├── window_store.add_window()
   |   |
   |   └── session_map_sync.update_session_map()
   |       └── StatePersistence.save()
   |
   ├── channel_router.get_display_name()
   |
   └── return WindowInfo(...)

**关键文件：**

* ``gateway.py:113-133`` — create_window
* ``tmux_manager.py:200-350`` — create_window 内部
* ``session_map.py`` — session map 更新

消息路由
--------

将前端收到的消息路由到助手：

.. code-block:: text

   frontend.handle_incoming_message(channel_id, text)
   |
   ├── channel_router.resolve_window(channel_id)
   |   └── return _bindings.get(channel_id)
   |
   ├── gateway.send_to_window(window_id, text)
   |   └── tmux_manager.send_to_window(window_id, text)
   |       └── Pane.send_keys(text + "\n")
   |
   └── Frontend 通过适配器发送响应

**关键文件：**

* ``channel_router.py:202-204`` — resolve_window
* ``gateway.py:158-160`` — send_to_window
* ``tmux_manager.py:400-450`` — send_to_window

输出捕获与触发
--------------

检测、解析 AI 助手输出并触发事件：

.. code-block:: text

   SessionMonitor._monitor_loop()
   |
   ├── _read_hook_events()
   |   ├── read_new_events() from events.jsonl
   |   └── _hook_event_callback(event) if registered
   |
   ├── _load_current_session_map()
   |   └── parse_session_map() from session_map.json
   |
   ├── _detect_and_cleanup_changes()
   |   └── SessionLifecycle.reconcile()
   |       ├── diff old vs new session_map
   |       └── emit NewWindowEvent if new windows
   |
   ├── check_for_updates(current_map)
   |   ├── _process_session_file() for each session
   |   |   ├── TranscriptReader._process_session_file()
   |   |   |   ├── _read_new_lines() from transcript
   |   |   |   ├── provider.parse_transcript_line()
   |   |   |   └── provider.parse_transcript_entries()
   |   |   |       ├── handle tool_use entries
   |   |   |       ├── handle tool_result entries
   |   |   |       ├── handle text entries
   |   |   |       └── return (messages, pending_tools)
   |   |   |
   |   |   └── IdleTracker.record_activity()
   |   |
   |   └── return new_messages
   |
   └── _message_callback(msg) for each new message
       └── Gateway._on_new_message()
           ├── AgentMessage(text, role, content_type, ...)
           ├── AgentMessageEvent(window_id, session_id, messages, channel_ids)
           └── user callbacks invoked

**关键文件：**

* ``session_monitor.py:305-386`` — _monitor_loop
* ``session_monitor.py:143-196`` — check_for_updates
* ``transcript_reader.py`` — TranscriptReader
* ``providers/*/parse_transcript_entries()`` — provider 解析

频道绑定
--------

将消息频道绑定到窗口：

.. code-block:: text

   gateway.bind_channel(channel_id, window_id)
   |
   ├── channel_router.bind()
   |   ├── _bindings[channel_id] = window_id
   |   ├── _reverse[window_id].append(channel_id)
   |   ├── _display_names[window_id] = display_name if provided
   |   ├── _channel_meta[channel_id] = {user_id, ...}
   |   |
   |   ├── evict old binding if channel was bound elsewhere
   |   ├── evict stale channels if window was bound elsewhere
   |   |
   |   └── _schedule_save() -> debounced write
   |
   └── StatePersistence.save() after 0.5s debounce

**关键文件：**

* ``channel_router.py:100-164`` — bind
* ``state_persistence.py`` — debounced writes

事件订阅与触发
--------------

.. code-block:: text

   gateway.on_message(callback)
   |
   └── _message_callbacks.append(callback)

   ...

   检测到 AI 助手输出
   |
   └── SessionMonitor._monitor_loop()
       |
       └── for msg in new_messages:
           |
           └── if _message_callback:
               |
               └── await _message_callback(msg)
                   |
                   └── Gateway._on_new_message(msg)
                       |
                       ├── agent_msg = AgentMessage(...)
                       ├── event = AgentMessageEvent(...)
                       └── for cb in _message_callbacks:
                           |
                           └── cb(event)
                               |
                               └── user_handler(event)

**关键文件：**

* ``gateway.py:178-179`` — on_message 注册
* ``gateway.py:213-234`` — _on_new_message 分发

状态持久化
----------

变更后保存状态：

.. code-block:: text

   channel_router.bind() -> _schedule_save()
   |
   ├── StatePersistence.schedule_save()
   |   ├── mark dirty
   |   └── schedule _write() in 0.5s
   |
   └── [0.5s debounce]

   StatePersistence._write()
   |
   ├── atomic_write_json() via utils.py
   |   ├── write to temp file
   |   └── os.rename() to target
   |
   └── clear dirty flag

**关键文件：**

* ``state_persistence.py`` — 完整实现
* ``utils.py:atomic_write_json()`` — 原子写入辅助函数

钩子事件处理
-----------

Claude 钩子事件从钩子模块流向用户回调：

.. code-block:: text

   hook.py（在随 Claude 一起运行的 tmux 窗格中）
   |
   ├── Claude 发出钩子事件
   |
   ├── hook.handle_hook() 从 stdin 读取
   |
   ├── hook.write_to_event_log()
   |   └── 追加到 events.jsonl
   |
   └── [单独监控网关进程]

   SessionMonitor._read_hook_events()
   |
   ├── read_new_events() from events.jsonl
   |   └── event_reader.read_new_events()
   |       ├── seek to offset
   |       ├── read new lines
   |       └── return (events, new_offset)
   |
   └── if _hook_event_callback:
       |
       └── await _hook_event_callback(event)
           |
           └── Gateway._on_hook_event()
               |
               └── HookEvent(window_id, event_type, session_id, data)
               |
               └── for cb in _hook_callbacks:
                   |
                   └── cb(hook_evt)

**关键文件：**

* ``hook.py`` — 钩子实现（在 tmux 窗格中运行）
* ``event_reader.py`` — events.jsonl 读取
* ``gateway.py:251-262`` — 钩子事件分发

截图捕获
--------

.. code-block:: text

   gateway.capture_screenshot(window_id)
   |
   └── tmux_manager.capture_screenshot()
       |
       ├── capture_pane() for fallback
       |
       ├── ImageMagick import command
       |   └── subprocess.run(["import", "-window", win_id, "png:-"])
       |
       └── return raw PNG bytes

**关键文件：**

* ``gateway.py:172-174``
* ``tmux_manager.py:capture_screenshot()`` — 使用 ImageMagick

窗口生命周期
-----------

窗口创建
~~~~~~~~

.. code-block:: text

   gateway.create_window()
   |
   ├── tmux_manager.create_window()
   |   ├── ensure_session()
   |   ├── Session.create_window()
   |   └── Window.send_keys(launch_command)
   |
   ├── window_store.add_window()
   |
   ├── session_map_sync.update_session_map()
   |
   └── [SessionMonitor 在下次轮询时检测]
       |
       └── NewWindowEvent emitted

窗口移除
~~~~~~~~

.. code-block:: text

   gateway.kill_window(window_id)
   |
   ├── channel_router.unbind_window()
   |   └── 移除所有频道绑定
   |
   ├── window_store.remove_window()
   |
   ├── tmux_manager.kill_window()
   |   └── Window.kill_window()
   |
   └── session_map_sync.remove_window()

**关键文件：**

* ``gateway.py:135-140`` — kill_window
* ``channel_router.py:181-196`` — unbind_window

Provider 检测
-------------

检测窗口中运行的是哪个 AI 助手：

.. code-block:: text

   detect_provider_from_transcript_path(transcript_path)
   |
   ├── check for known path patterns
   |   ├── "/.codex/sessions/" -> "codex"
   |   ├── "/.claude/projects/" -> "claude"
   |   ├── "/.gemini/" + "/chats/" -> "gemini"
   |   └── "/.pi/agent/sessions/" -> "pi"
   |
   └── return provider name or ""

**关键文件：**

* ``providers/__init__.py:102-114`` — detect_provider_from_transcript_path

转录解析
---------

处理新的转录内容：

.. code-block:: text

   TranscriptReader._process_session_file()
   |
   ├── _read_new_lines()
   |   ├── os.stat() for file mtime/size
   |   ├── seek to last_offset
   |   ├── read new lines
   |   └── update _file_mtimes
   |
   ├── for line in new_lines:
   |   |
   |   └── provider.parse_transcript_line(line)
   |       ├── try JSON parse
   |       └── return dict or None
   |
   └── provider.parse_transcript_entries()
       |
       ├── for entry in entries:
       |   |
       |   ├── if tool_use:
       |   |   └── AgentMessage(content_type="tool_use", tool_name=...)
       |   |
       |   ├── if tool_result:
       |   |   └── AgentMessage(content_type="tool_result", ...)
       |   |
       |   ├── if thinking:
       |   |   └── AgentMessage(content_type="thinking", ...)
       |   |
       |   └── if text:
       |       └── AgentMessage(content_type="text", ...)
       |
       └── return (messages, pending_tools)

**关键文件：**

* ``transcript_reader.py`` — 文件 I/O
* ``providers/_jsonl.py`` — 基础 JSONL 解析
* ``providers/claude.py`` — Claude 特定解析
