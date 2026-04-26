故障排除
=========

常见问题
--------

网关无法启动
~~~~~~~~~~~~

**症状**：``UnifiedICC().start()`` 卡住或失败

**可能原因**：

1. tmux 未安装或不在 PATH 中

   .. code-block:: bash

      tmux -V  # 应显示版本号

2. tmux 会话已存在但使用了不同的 socket

   .. code-block:: bash

      tmux list-sessions  # 检查已存在的会话

3. 状态文件权限问题

   .. code-block:: bash

      ls -la ~/.cclark/
      chmod 755 ~/.cclark/

**解决方案**：

.. code-block:: python

   # 检查 tmux 是否可用
   import subprocess
   result = subprocess.run(["tmux", "-V"], capture_output=True)
   print(result.stdout.decode())

   # 检查状态目录
   from unified_icc.utils import cclark_dir
   print(cclark_dir())  # 应存在且可写

---

消息未收到
~~~~~~~~~~

**症状**：``on_message`` 回调从未触发

**可能原因**：

1. 频道未绑定到窗口

   .. code-block:: python

      # 检查绑定
      from unified_icc import channel_router
      print(channel_router.bound_channel_ids())
      print(channel_router.bound_window_ids())

2. 会话监控器未运行

   .. code-block:: python

      # 验证监控器是否活跃
      from unified_icc.session_monitor import get_active_monitor
      monitor = get_active_monitor()
      print(monitor._running if monitor else "无监控器")

3. 转录文件未被读取

   .. code-block:: python

      # 检查转录路径
      from unified_icc.session_map import session_map_sync
      print(session_map_sync.current_map)

**解决方案**：

.. code-block:: python

   # 手动验证转录文件可读
   import asyncio
   from unified_icc import config

   async def check_transcripts():
       if config.session_map_file.exists():
           import json, aiofiles
           async with aiofiles.open(config.session_map_file) as f:
               content = await f.read()
           data = json.loads(content)
           print("会话映射：", data)

   asyncio.run(check_transcripts())

---

助手无响应
~~~~~~~~~~

**症状**：``send_to_window()`` 完成但助手无响应

**可能原因**：

1. 文本未到达 tmux 窗格

   .. code-block:: python

      # 验证窗格存在且可写
      await gateway.capture_pane(window_id)

2. AI 助手进程不在交互模式

   .. code-block:: python

      # 检查助手状态
      status = await gateway.get_provider(window_id).parse_terminal_status(
          await gateway.capture_pane(window_id)
      )
      print(status)

3. tmux 窗格未连接到正确窗口

   .. code-block:: python

      # 列出所有窗口
      windows = await gateway.list_windows()
      for w in windows:
          print(f"{w.window_id}: {w.display_name}")

**解决方案**：

.. code-block:: python

   # 调试发送操作
   import asyncio

   async def debug_send(window_id, text):
       # 先捕获当前状态
       before = await gateway.capture_pane(window_id)
       print(f"发送前：\n{before[-500:]}")

       # 发送
       await gateway.send_to_window(window_id, text)

       # 稍等
       await asyncio.sleep(0.5)

       # 捕获发送后状态
       after = await gateway.capture_pane(window_id)
       print(f"发送后：\n{after[-500:]}")

   asyncio.run(debug_send("cclark:1", "hello"))

---

状态未持久化
~~~~~~~~~~~~

**症状**：重启后绑定消失

**可能原因**：

1. 状态文件不可写

   .. code-block:: bash

      ls -la ~/.cclark/state.json
      # 若不存在，检查目录权限

2. 持久化未调度

   .. code-block:: python

      # 检查脏标记
      from unified_icc import channel_router
      # StatePersistence 使用去中心化，所以变更需要 0.5s 才保存

3. 关机时竞态条件

   .. code-block:: python

      # 始终优雅停止
      await gateway.stop()  # 这会刷新状态

**解决方案**：

.. code-block:: python

   # 手动触发持久化
   from unified_icc.state_persistence import persistence_manager

   # 做一次变更
   channel_router.bind("test:1", "cclark:1")

   # 强制保存
   if hasattr(persistence_manager, 'flush'):
       persistence_manager.flush()

   # 或等待去中心化
   import asyncio
   await asyncio.sleep(1.0)  # 去中心化延迟为 0.5s

---

Provider 未检测到
~~~~~~~~~~~~~~~~

**症状**：检测到错误的 Provider，或无 Provider

**可能原因**：

1. Provider 二进制文件不在 PATH 中

   .. code-block:: bash

      which claude  # 或 codex、gemini、pi

2. 转录路径不匹配模式

   .. code-block:: python

      from unified_icc.providers import detect_provider_from_transcript_path

      # 测试检测
      path = "~/.claude/projects/myproj/.claude/history/session.jsonl"
      provider = detect_provider_from_transcript_path(path)
      print(f"检测到：{provider}")

3. 窗格标题未正确设置

   .. code-block:: bash

      # 检查 tmux 窗口标题
      tmux display-message -t cclark:1 -p '#{window_name}'

**解决方案**：

.. code-block:: python

   # 创建窗口时显式指定 Provider
   window = await gateway.create_window(
       work_dir="/path",
       provider="claude"  # 显式指定
   )

   # 或在环境中设置默认
   import os
   os.environ["CCLARK_PROVIDER"] = "claude"

---

钩子事件未收到
~~~~~~~~~~~~~~

**症状**：``on_hook_event`` 回调从未触发（仅 Claude）

**可能原因**：

1. Claude 中未安装钩子

   .. code-block:: bash

      # 检查 Claude 配置
      cat ~/.claude/settings.json | grep hook

2. events.jsonl 不可写

   .. code-block:: bash

      ls -la ~/.cclark/events.jsonl

3. 钩子模块未加载

   .. code-block:: python

      # 验证钩子已安装
      from unified_icc import hook
      print(hook.__file__)

**解决方案**：

.. code-block:: python

   # 手动安装钩子
   from unified_icc.hook import install_hooks

   # 这会将钩子文件写入 ~/.claude/
   # 注意：需要重启 Claude 才能生效

---

截图捕获失败
~~~~~~~~~~~~

**症状**：``capture_screenshot()`` 报错

**可能原因**：

1. ImageMagick 未安装

   .. code-block:: bash

      convert --version  # 或
      import subprocess; subprocess.run(["import", "-version"])

2. DISPLAY 未设置（X11 环境下）

   .. code-block:: bash

      echo $DISPLAY  # 应为 :0 或类似值

3. tmux 捕获不工作

   .. code-block:: python

      # 测试基本捕获
      content = await gateway.capture_pane(window_id)
      print(f"捕获可用：{len(content)} 字符")

**解决方案**：

.. code-block:: python

   # 检查依赖
   import shutil
   print(f"ImageMagick：{shutil.which('import')}")
   print(f"DISPLAY：{import os; os.environ.get('DISPLAY')}")

   # 带错误处理尝试捕获
   try:
       image_bytes = await gateway.capture_screenshot(window_id)
   except Exception as e:
       print(f"截图失败：{e}")
       # 回退到文本捕获
       text = await gateway.capture_pane(window_id)

---

调试日志
--------

启用调试日志来追踪问题：

.. code-block:: python

   import structlog
   import logging

   # 配置 structlog
   structlog.configure(
       processors=[
           structlog.processors.TimeStamper(fmt="iso"),
           structlog.processors.add_log_level,
           structlog.dev.ConsoleRenderer(),
       ],
   )

   # 设置日志级别
   logging.getLogger("unified_icc").setLevel(logging.DEBUG)

或通过环境变量：

.. code-block:: bash

   export LOG_LEVEL=DEBUG

获取帮助
--------

如果仍然卡住：

1. 启用调试日志并捕获相关输出
2. 查看 `GitHub Issues <https://github.com/Agony5757/unified-icc/issues>`_
3. 附上：
   - Python 版本（``python --version``）
   - tmux 版本（``tmux -V``）
   - 相关日志
   - 最小复现代码
