欢迎使用 Unified ICC
=====================

ICC = Interactive Coding CLI（交互式编程命令行）—— 一个与平台无关的网关，用于通过 tmux 管理 AI 编程助手（Claude Code、Codex CLI 等）。

Unified ICC 将 `ccgram <https://github.com/alexei-led/ccgram>`_ 的核心逻辑提取为一个可复用的 Python 库，使任何消息前端（飞书、Telegram、Discord、Slack……）都能通过简洁的异步 API 来驱动 AI 编程会话。

主要特性
--------

- **平台无关**：核心库不依赖任何特定消息平台
- **多 Provider 支持**：无缝管理 Claude Code、Codex CLI、Gemini CLI、Pi 和 Shell 会话
- **异步优先**：为现代 Python 应用提供完整的 async/await API
- **事件驱动**：可订阅消息、状态变更、窗口事件和钩子事件
- **状态持久化**：带崩溃恢复的去中心化 JSON 持久化

文档章节
--------

.. toctree::
   :maxdepth: 2
   :caption: 目录

   getting-started/index
   getting-started/installation
   getting-started/first-steps
   architecture
   providers/index
   api-reference/index
   api-reference/gateway
   api-reference/adapter
   api-reference/events
   api-reference/channel-router
   api-reference/call-stacks
   events/index
   configuration
   troubleshooting
   contributing

快速示例
--------

.. code-block:: python

   import asyncio
   from unified_icc import UnifiedICC

   async def main():
       # 创建网关
       gateway = UnifiedICC()
       await gateway.start()

       # 创建一个 Claude Code 窗口
       window = await gateway.create_window("/path/to/project")

       # 将消息频道绑定到窗口
       gateway.bind_channel("feishu:chat_123:thread_456", window.window_id)

       # 订阅助手消息
       def on_message(event):
           print(f"助手：{event.messages[-1].text}")

       gateway.on_message(on_message)

       # 向助手发送输入
       await gateway.send_to_window(window.window_id, "你好，帮我在这个项目中做点事")

       await gateway.stop()

   asyncio.run(main())

相关项目
--------

.. list-table::
   :header-rows: 1

   * - 项目
     - 说明
   * - `cclark <https://github.com/Agony5757/cclark>`_
     - 飞书前端，依赖 unified-icc
   * - `ccgram <https://github.com/alexei-led/ccgram>`_
     - 原始 Telegram 前端（上游参考）

索引和表格
----------

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`
