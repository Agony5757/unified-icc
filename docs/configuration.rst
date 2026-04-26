配置参考
=========

Unified ICC 完全通过环境变量配置（支持 `.env` 文件）。核心库中无需任何平台令牌或 API 密钥。

配置加载顺序
-------------

配置按以下顺序加载（后者覆盖前者）：

1. 默认值
2. ``~/.cclark/.env`` 文件
3. ``./.env`` 文件（当前工作目录）
4. 环境变量

环境变量
--------

核心设置
~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 变量
     - 默认值
     - 说明
   * - ``CCLARK_CONFIG_DIR``
     - ``~/.cclark``
     - 配置目录
   * - ``CCLARK_PROVIDER``
     - ``claude``
     - 默认 AI 助手 Provider

兼容别名：``CCGRAM_CONFIG_DIR``、``CCBOT_CONFIG_DIR``

Tmux 设置
~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 变量
     - 默认值
     - 说明
   * - ``TMUX_SESSION_NAME``
     - ``cclark``
     - tmux 会话名称
   * - ``TMUX_EXTERNAL_PATTERNS``
     - （空）
     - 外部窗口发现模式

兼容别名：``CCGRAM_TMUX_SESSION``

监控设置
~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 变量
     - 默认值
     - 说明
   * - ``MONITOR_POLL_INTERVAL``
     - ``1.0``
     - 轮询间隔（秒，最小 0.5）
   * - ``CCLARK_STATUS_POLL_INTERVAL``
     - ``1.0``
     - 状态轮询间隔（秒）

兼容别名：``CCGRAM_STATUS_POLL_INTERVAL``

助手设置
~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 变量
     - 默认值
     - 说明
   * - ``CLAUDE_CONFIG_DIR``
     - ``~/.claude``
     - Claude 配置目录
   * - ``AUTOCLOSE_DONE_MINUTES``
     - ``30``
     - 完成后自动关闭（分钟）
   * - ``AUTOCLOSE_DEAD_MINUTES``
     - ``10``
     - 死亡会话自动关闭（分钟）

Provider 命令覆盖
~~~~~~~~~~~~~~~~

覆盖各 Provider 的启动命令：

.. list-table::
   :header-rows: 1

   * - 变量
     - 格式
   * - ``CCLARK_CLAUDE_COMMAND``
     - 覆盖 ``claude`` 命令
   * - ``CCLARK_CODEX_COMMAND``
     - 覆盖 ``codex`` 命令
   * - ``CCLARK_GEMINI_COMMAND``
     - 覆盖 ``gemini`` 命令
   * - ``CCLARK_PI_COMMAND``
     - 覆盖 ``pi`` 命令
   * - ``CCLARK_SHELL_COMMAND``
     - 覆盖 ``shell`` 命令

兼容别名：``CCGRAM_*``、``CCBOT_*``

示例 .env 文件
~~~~~~~~~~~~~~

.. code-block:: bash

   # 核心设置
   CCLARK_CONFIG_DIR=~/.cclark
   CCLARK_PROVIDER=claude

   # Tmux
   TMUX_SESSION_NAME=cclark

   # 监控
   MONITOR_POLL_INTERVAL=1.0

   # Provider 覆盖
   CCLARK_CLAUDE_COMMAND=/usr/local/bin/claude

GatewayConfig 类
----------------

.. code-block:: python

   from unified_icc import GatewayConfig, config

   # 访问全局配置
   print(config.tmux_session_name)  # "cclark"
   print(config.provider_name)     # "claude"

   # 或创建自定义配置
   custom_config = GatewayConfig()
   custom_config.tmux_session_name = "my-session"

GatewayConfig 属性
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - 属性
     - 类型
     - 说明
   * - ``config_dir``
     - ``Path``
     - 配置目录
   * - ``tmux_session_name``
     - ``str``
     - tmux 会话名称
   * - ``tmux_main_window_name``
     - ``str``
     - 主窗口名称
   * - ``own_window_id``
     - ``str | None``
     - 本网关所在窗口 ID
   * - ``tmux_external_patterns``
     - ``str``
     - 外部窗口发现模式
   * - ``state_file``
     - ``Path``
     - 主状态文件路径
   * - ``session_map_file``
     - ``Path``
     - 会话映射文件路径
   * - ``monitor_state_file``
     - ``Path``
     - 监控状态文件路径
   * - ``events_file``
     - ``Path``
     - 钩子事件文件路径
   * - ``mailbox_dir``
     - ``Path``
     - 邮箱目录路径
   * - ``claude_config_dir``
     - ``Path``
     - Claude 配置目录
   * - ``claude_projects_path``
     - ``Path``
     - Claude 项目路径
   * - ``monitor_poll_interval``
     - ``float``
     - 轮询间隔
   * - ``status_poll_interval``
     - ``float``
     - 状态轮询间隔
   * - ``provider_name``
     - ``str``
     - 默认 Provider
   * - ``autoclose_done_minutes``
     - ``int``
     - 完成状态自动关闭延迟
   * - ``autoclose_dead_minutes``
     - ``int``
     - 死亡状态自动关闭延迟

状态文件
--------

所有状态文件存储在 ``~/.cclark/``：

.. list-table::
   :header-rows: 1

   * - 文件
     - 说明
   * - ``state.json``
     - 网关状态（频道、窗口、显示名称）
   * - ``session_map.json``
     - tmux 窗口 ↔ AI 助手会话映射
   * - ``monitor_state.json``
     - 轮询偏移量和追踪中的会话
   * - ``events.jsonl``
     - 钩子事件日志（追加写入）

状态文件格式：state.json
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "channel_bindings": {
           "feishu:chat123:thread456": "cclark:1"
       },
       "channel_meta": {
           "feishu:chat123:thread456": {
               "user_id": "U123456"
           }
       },
       "display_names": {
           "cclark:1": "Claude Code"
       }
   }

状态文件格式：session_map.json
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "cclark:1": {
           "session_id": "abc123",
           "transcript_path": "/home/user/.claude/projects/myproj/.claude/history/session_abc123.jsonl",
           "cwd": "/home/user/projects/myproj",
           "window_name": "claude",
           "provider_name": "claude"
       }
   }

自定义配置示例
--------------

.. code-block:: python

   from unified_icc import UnifiedICC, GatewayConfig
   import os

   # 方式 1：环境变量
   os.environ["TMUX_SESSION_NAME"] = "my-session"
   os.environ["MONITOR_POLL_INTERVAL"] = "0.5"
   gateway = UnifiedICC()

   # 方式 2：自定义配置对象
   config = GatewayConfig()
   config.tmux_session_name = "my-session"
   config.monitor_poll_interval = 0.5
   config.state_file = Path("/tmp/my-state.json")
   gateway = UnifiedICC(gateway_config=config)

tmux 要求
---------

Unified ICC 要求：

- tmux 2.6 或更高版本
- 能够创建新会话/窗口
- 可访问 ``tmux`` 命令

tmux Socket
~~~~~~~~~~~

默认 unified-icc 使用默认 tmux socket。使用自定义 socket：

.. code-block:: bash

   export TMUX_SOCKET_PATH=/tmp/my-tmux-socket

窗口命名
~~~~~~~~

窗口自动命名。自定义显示名称：

.. code-block:: python

   # 在前端中设置显示名称
   from unified_icc import channel_router
   channel_router.set_display_name(window_id, "我的项目")

Provider 特定配置
-----------------

Claude
~~~~~~

Claude Code 如果 ``claude`` 在 PATH 中则自动检测。指定特定版本：

.. code-block:: bash

   export CCLARK_CLAUDE_COMMAND=/path/to/claude

Codex
~~~~~

.. code-block:: bash

   export CCLARK_CODEX_COMMAND=/path/to/codex

Gemini
~~~~~~

.. code-block:: bash

   export CCLARK_GEMINI_COMMAND=/path/to/gemini
