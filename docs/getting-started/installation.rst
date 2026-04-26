安装
========

使用 uv（推荐）
-----------------

.. code-block:: bash

   uv pip install unified-icc

或添加到你的项目中：

.. code-block:: bash

   uv add unified-icc

从源码安装
----------

.. code-block:: bash

   git clone https://github.com/Agony5757/unified-icc.git
   cd unified-icc
   uv pip install -e .

开发环境安装
------------

.. code-block:: bash

   git clone https://github.com/Agony5757/unified-icc.git
   cd unified-icc
   uv sync
   uv pip install -e ".[dev]"

系统要求
--------

- Python 3.12 或更高版本
- tmux 2.6 或更高版本
- 一个受支持的 AI 助手 CLI（Claude Code、Codex CLI、Gemini CLI 等）

快速开始
--------

1. 创建网关实例
~~~~~~~~~~~~~~

.. code-block:: python

   import asyncio
   from unified_icc import UnifiedICC

   async def main():
       gateway = UnifiedICC()
       await gateway.start()

       # 在这里写你的代码...

       await gateway.stop()

   asyncio.run(main())

2. 创建带助手的窗口
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   window = await gateway.create_window(
       work_dir="/path/to/project",
       provider="claude",  # 或 "codex"、"gemini"、"pi"、"shell"
   )
   print(f"已创建窗口：{window.window_id}")

3. 绑定消息频道
~~~~~~~~~~~~~~

.. code-block:: python

   gateway.bind_channel(
       channel_id="feishu:chat_123:thread_456",
       window_id=window.window_id,
   )

4. 订阅事件
~~~~~~~~~~

.. code-block:: python

   def handle_message(event):
       for msg in event.messages:
           print(f"[{msg.role}] {msg.text}")

   gateway.on_message(handle_message)

5. 向助手发送输入
~~~~~~~~~~~~~~~~~

.. code-block:: python

   await gateway.send_to_window(window.window_id, "你好！")

环境变量
--------

.. list-table::
   :header-rows: 1

   * - 变量
     - 默认值
     - 说明
   * - ``CCLARK_CONFIG_DIR``
     - ``~/.cclark``
     - 配置目录
   * - ``TMUX_SESSION_NAME``
     - ``cclark``
     - tmux 会话名称
   * - ``CCLARK_PROVIDER``
     - ``claude``
     - 默认 AI 助手 Provider
   * - ``MONITOR_POLL_INTERVAL``
     - ``1.0``
     - 轮询间隔（秒）
   * - ``CLAUDE_CONFIG_DIR``
     - ``~/.claude``
     - Claude 配置目录

为保持向后兼容，也支持旧版环境变量：

- ``CCGRAM_*``（ccgram 时期）
- ``CCBOT_*``（原始命名）

下一步
------

- 阅读 `架构概览 <../architecture.rst>`_ 深入了解系统
- 查阅 `API 参考 <../api-reference/index.rst>`_ 了解所有可用方法
- 学习 `Provider <../providers/index.rst>`_ 及其工作原理
- 查看 `配置 <../configuration.rst>`_ 了解所有选项
