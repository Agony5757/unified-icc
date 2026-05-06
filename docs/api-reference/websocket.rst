WebSocket API 参考
===================

WebSocket 提供双向实时通信，比 REST 更适合接收 Agent 输出流、状态变更和窗口事件。

协议消息定义于 ``unified_icc.server.ws_protocol``，路由处理定义于 ``unified_icc.server.routes.ws``。

连接
----

两种连接模式:

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - 频道订阅模式（推荐）
     - 全局监听模式
   * - ``ws://host:port/api/v1/ws/{channel_id}?token=<key>``
     - ``ws://host:port/api/v1/ws?token=<key>``
   * - 接收该频道的 ``agent.message`` / ``agent.status`` 推送
     - 仅接收全局广播（``window.change``、``hook.event``）
   * - 前端直接与单会话交互
     - 前端桥接层多路复用多个频道

**认证**: ``?token=`` 查询参数。无效时返回 ``4001 Unauthorized`` 并关闭连接。

**心跳**: 服务器不自动发送 ping。客户端应每 30 秒发送一次 ``ping`` 消息，服务器返回 ``pong``。若连接无数据流动超过 OS 的 TCP keepalive 超时，连接会被断开。

**request_id**: 所有消息支持可选的 ``request_id`` 字段，服务器在响应中原样返回，用于请求/响应关联。

订阅模型
~~~~~~~~

WebSocket 连接通过 ``ConnectionManager`` 管理两种订阅:

- **频道订阅** (``manager.subscribe(channel_id, ws)``): 连接绑定到特定频道，接收该频道的私有消息（``agent.message``、``agent.status``）及全局广播
- **全局订阅** (``manager.subscribe_global(ws)``): 不绑定频道，仅接收全局广播事件，用于前端桥接层监听所有频道的事件

客户端 → 服务器消息
-------------------

所有消息为 JSON 对象，``type`` 字段决定消息类型。未列出的字段将被忽略。

session.create
~~~~~~~~~~~~~~

创建新的 AI 助手会话。

.. code-block:: json

   {
     "type": "session.create",
     "request_id": "req-001",
     "channel_id": "feishu:oc_chat1",
     "work_dir": "/tmp/project",
     "provider": "claude",
     "mode": "normal",
     "name": "my-session"
   }

.. list-table::
   :header-rows: 1
   :widths: 20 15 10 55

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``type``
     - string
     - **是**
     - 固定为 ``"session.create"``
   * - ``request_id``
     - string
     - 否
     - 请求 ID，关联响应
   * - ``channel_id``
     - string
     - 否
     - 频道标识符；空则自动生成 ``api:<uuid>``
   * - ``work_dir``
     - string
     - 否
     - 工作目录；空则使用当前目录
   * - ``provider``
     - string
     - 否
     - Provider 名称；默认为 ``"claude"``
   * - ``mode``
     - string
     - 否
     - ``"normal"``（需确认）或 ``"yolo"``
   * - ``name``
     - string
     - 否
     - 窗口显示名称

**服务器响应**: ``session.created``

**REST 等价**: ``POST /sessions``

session.list
~~~~~~~~~~~~

列出所有管理的会话。

.. code-block:: json

   {"type": "session.list", "request_id": "req-002"}

**服务器响应**: ``session.list``

**REST 等价**: ``GET /sessions``

session.close
~~~~~~~~~~~~~

关闭指定频道的会话。

.. code-block:: json

   {"type": "session.close", "channel_id": "feishu:oc_chat1", "request_id": "req-003"}

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``type``
     - string
     - 固定为 ``"session.close"``
   * - ``channel_id``
     - string
     - **必填** 要关闭的频道 ID
   * - ``request_id``
     - string
     - 请求 ID

**服务器响应**: ``session.closed``

**REST 等价**: ``DELETE /sessions/{channel_id}``

input
~~~~~

向 tmux 窗口发送文本输入。

.. code-block:: json

   {
     "type": "input",
     "channel_id": "feishu:oc_chat1",
     "text": "hello",
     "enter": true,
     "literal": true,
     "raw": false,
     "request_id": "req-004"
   }

.. list-table::
   :header-rows: 1
   :widths: 20 15 10 55

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``channel_id``
     - string
     - **是**
     - 目标频道 ID
   * - ``text``
     - string
     - **是**
     - 要发送的文本
   * - ``enter``
     - boolean
     - 否
     - 发送后按回车；默认 ``true``
   * - ``literal``
     - boolean
     - 否
     - 逐字发送；默认 ``true``
   * - ``raw``
     - boolean
     - 否
     - 原始模式；默认 ``false``

**REST 等价**: ``POST /sessions/{channel_id}/input``

input.raw
~~~~~~~~~

发送原始文本，等同于 ``input`` 但强制 ``enter=true, literal=true, raw=true``。

.. code-block:: json

   {"type": "input.raw", "channel_id": "feishu:oc_chat1", "text": "ls -la", "request_id": "req-005"}

key
~~~

向 tmux 窗口发送特殊按键。

.. code-block:: json

   {"type": "key", "channel_id": "feishu:oc_chat1", "key": "Escape", "request_id": "req-006"}

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``channel_id``
     - string
     - **必填** 目标频道 ID
   * - ``key``
     - string
     - **必填** 按键名称（如 ``Escape``、``Enter``、``C-c``）

**REST 等价**: ``POST /sessions/{channel_id}/key``

capture.pane
~~~~~~~~~~~~

捕获 tmux 窗格当前内容为纯文本。

.. code-block:: json

   {"type": "capture.pane", "channel_id": "feishu:oc_chat1", "request_id": "req-007"}

**服务器响应**: ``capture.pane``

**REST 等价**: ``GET /sessions/{channel_id}/pane``

capture.screenshot
~~~~~~~~~~~~~~~~~~

捕获 tmux 窗格当前内容为 PNG 图片（base64 编码）。

.. code-block:: json

   {"type": "capture.screenshot", "channel_id": "feishu:oc_chat1", "request_id": "req-008"}

**服务器响应**: ``capture.screenshot``（包含 ``image_base64`` 字段）

**REST 等价**: ``GET /sessions/{channel_id}/screenshot``

verbose.set
~~~~~~~~~~~

切换 verbose 模式（API 服务器端为 no-op，内容始终全量下发）。

.. code-block:: json

   {"type": "verbose.set", "enabled": true, "request_id": "req-009"}

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``enabled``
     - boolean
     - **必填** ``true`` 启用详细模式
   * - ``request_id``
     - string
     - 请求 ID

**服务器响应**: ``verbose.updated``

**REST 等价**: ``POST /sessions/{channel_id}/verbose``

wizard.browse
~~~~~~~~~~~~~

浏览目录，列出子目录。

.. code-block:: json

   {"type": "wizard.browse", "path": "/home/user", "request_id": "req-010"}

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``path``
     - string
     - **必填** 目录路径
   * - ``request_id``
     - string
     - 请求 ID

**服务器响应**: ``wizard.browse``

**REST 等价**: ``POST /directories/browse``

wizard.mkdir
~~~~~~~~~~~~

创建目录。

.. code-block:: json

   {"type": "wizard.mkdir", "name": "/tmp/new-dir", "request_id": "req-011"}

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``name``
     - string
     - **必填** 目录名（绝对或相对路径）
   * - ``request_id``
     - string
     - 请求 ID

**服务器响应**: ``wizard.mkdir``

ping
~~~~

心跳探测。服务器返回 ``pong``。

.. code-block:: json

   {"type": "ping", "request_id": "req-012"}

**服务器响应**: ``pong``

服务器 → 客户端消息
------------------

session.created
~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "type": "session.created",
     "request_id": "req-001",
     "channel_id": "feishu:oc_chat1",
     "window_id": "@1",
     "provider": "claude",
     "mode": "normal",
     "cwd": "/tmp/project",
     "display_name": "my-session"
   }

session.list
~~~~~~~~~~~~

.. code-block:: json

   {
     "type": "session.list",
     "request_id": "req-002",
     "sessions": [
       {
         "window_id": "@1",
         "display_name": "my-project",
         "provider": "claude",
         "cwd": "/tmp/my-project",
         "session_id": "abc-123",
         "channel_id": "feishu:oc_chat1"
       }
     ]
   }

session.closed
~~~~~~~~~~~~~~

.. code-block:: json

   {"type": "session.closed", "channel_id": "feishu:oc_chat1", "request_id": "req-003"}

agent.message
~~~~~~~~~~~~~

由网关推送，Agent 有新输出时发送（**私有消息**，仅频道订阅者收到）。

.. code-block:: json

   {
     "type": "agent.message",
     "channel_id": "feishu:oc_chat1",
     "session_id": "abc-123",
     "messages": [
       {
         "text": "Hello!",
         "role": "assistant",
         "content_type": "text",
         "is_complete": true,
         "phase": null,
         "tool_use_id": null,
         "tool_name": null,
         "timestamp": null
       }
     ]
   }

**AgentMessage 字段**:

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``text``
     - string
     - 消息文本内容
   * - ``role``
     - string
     - ``"user"`` 或 ``"assistant"``
   * - ``content_type``
     - string
     - ``"text"`` \| ``"thinking"`` \| ``"tool_use"`` \| ``"tool_result"`` \| ``"local_command"``
   * - ``is_complete``
     - boolean
     - 消息是否完整
   * - ``phase``
     - string\|null
     - Agent 阶段（如 ``"planning"``）
   * - ``tool_use_id``
     - string\|null
     - 工具调用 ID
   * - ``tool_name``
     - string\|null
     - 工具名称（如 ``Bash``、``Read``）
   * - ``timestamp``
     - string\|null
     - ISO 8601 时间戳

agent.status
~~~~~~~~~~~~

Agent 状态变更时推送（**私有消息**，仅频道订阅者收到）。

.. code-block:: json

   {
     "type": "agent.status",
     "channel_id": "feishu:oc_chat1",
     "session_id": "abc-123",
     "status": "working",
     "display_label": "Thinking...",
     "provider": "claude",
     "interactive": false,
     "prompt_state": null
   }

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``channel_id``
     - string
     - 频道 ID
   * - ``session_id``
     - string
     - 会话 ID
   * - ``status``
     - string
     - ``"idle"`` \| ``"working"`` \| ``"interactive"`` \| ``"done"`` \| ``"dead"``
   * - ``display_label``
     - string
     - 人类可读的当前状态描述
   * - ``provider``
     - string
     - Provider 名称
   * - ``interactive``
     - boolean
     - 是否处于交互模式（等待用户输入审批等）
   * - ``prompt_state``
     - object\|null
     - 交互提示详情对象（当 ``interactive=true`` 时才出现）

window.change
~~~~~~~~~~~~~~

窗口生命周期事件（**全局广播**，所有订阅者均收到）。

.. code-block:: json

   {
     "type": "window.change",
     "window_id": "@2",
     "change_type": "new",
     "provider": "claude",
     "cwd": "/tmp/project2",
     "display_name": "project2"
   }

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - 字段
     - 类型
     - 说明
   * - ``window_id``
     - string
     - tmux 窗口 ID
   * - ``change_type``
     - string
     - ``"new"``（新创建）\| ``"removed"``（被移除）\| ``"died"``（异常退出）
   * - ``provider``
     - string
     - Provider 名称
   * - ``cwd``
     - string
     - 工作目录
   * - ``display_name``
     - string
     - 窗口显示名称

hook.event
~~~~~~~~~~

Claude Code Hook 事件（**全局广播**，所有订阅者均收到）。

.. code-block:: json

   {
     "type": "hook.event",
     "window_id": "@1",
     "event_type": "SessionStart",
     "session_id": "abc-123",
     "data": {"cwd": "/tmp/project", "transcript_path": "..."}
   }

详见 :doc:`events` 中的 Hook 事件类型列表。

capture.pane
~~~~~~~~~~~~~

.. code-block:: json

   {
     "type": "capture.pane",
     "request_id": "req-007",
     "channel_id": "feishu:oc_chat1",
     "content": "user@host:~$ "
   }

capture.screenshot
~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "type": "capture.screenshot",
     "request_id": "req-008",
     "channel_id": "feishu:oc_chat1",
     "image_base64": "iVBORw0KGgoAAAANS..."
   }

**注意**: ``image_base64`` 是 base64 编码的 PNG 数据字符串，不是原始字节。需客户端解码为二进制。

verbose.updated
~~~~~~~~~~~~~~

.. code-block:: json

   {"type": "verbose.updated", "request_id": "req-009", "enabled": true}

wizard.browse
~~~~~~~~~~~~~

.. code-block:: json

   {
     "type": "wizard.browse",
     "request_id": "req-010",
     "path": "/home/user",
     "directories": ["Documents", "Downloads"],
     "parent": "/home"
   }

wizard.mkdir
~~~~~~~~~~~~

.. code-block:: json

   {"type": "wizard.mkdir", "request_id": "req-011", "path": "/tmp/new-dir"}

error
~~~~~

错误响应。

.. code-block:: json

   {"type": "error", "request_id": "req-007", "message": "No session for channel feishu:oc_chat1"}

详见 :doc:`errors`。

pong
~~~~

.. code-block:: json

   {"type": "pong", "request_id": "req-012"}
