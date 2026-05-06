REST API 参考
==============

所有 REST 端点前缀 ``/api/v1``，由 FastAPI 实现，OpenAPI 文档位于 ``/docs``。

除 ``GET /health`` 外，所有端点均需认证（见 :doc:`../api` 认证章节）。

请求/响应模型（Pydantic）定义于 ``unified_icc.server.routes.sessions``。

Sessions
--------

POST /sessions — 创建会话
~~~~~~~~~~~~~~~~~~~~~~~~~~

创建一个新的 AI 助手会话，启动对应的 tmux 窗口。

**认证**: Bearer token（``ICC_API_KEY`` 设置时）

**Request body** (``CreateSessionRequest``):

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``channel_id``
     - string
     - 否
     - 外部频道标识符；空则自动生成 ``api:<uuid>``
   * - ``work_dir``
     - string
     - 否
     - Agent 工作目录；空则使用当前目录
   * - ``provider``
     - string
     - 否
     - Provider 名称；默认为 ``"claude"``；可选: ``claude``, ``codex``, ``gemini``, ``pi``, ``shell``
   * - ``mode``
     - string
     - 否
     - 审批模式；默认为 ``"normal"``；``"normal"``（需确认）或 ``"yolo"``（跳过权限）
   * - ``name``
     - string
     - 否
     - tmux 窗口显示名称

**Response ``200 OK``**:

.. code-block:: json

   {
     "channel_id": "api:3fa85f64-5717-4562-b3fc-2c963f66afa6",
     "window_id": "@1",
     "provider": "claude",
     "mode": "normal",
     "cwd": "/tmp/my-project",
     "display_name": "my-project"
   }

**Response ``400 Bad Request``**: 无效 provider 或目录不存在

.. code-block:: json

   {"detail": "Unknown provider: invalid-provider"}

**curl 示例**:

.. code-block:: bash

   curl -X POST http://localhost:8900/api/v1/sessions \
     -H "Authorization: Bearer $ICC_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"work_dir": "/home/user/project", "provider": "claude", "mode": "normal"}'

**WebSocket 等价**: ``session.create`` 消息

---

GET /sessions — 列出会话
~~~~~~~~~~~~~~~~~~~~~~~~~

返回所有由网关管理的 tmux 窗口（不限于 API 创建的会话）。

**认证**: Bearer token

**Response ``200 OK``**:

.. code-block:: json

   {
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

**curl 示例**:

.. code-block:: bash

   curl http://localhost:8900/api/v1/sessions \
     -H "Authorization: Bearer $ICC_API_KEY"

**WebSocket 等价**: ``session.list`` 消息

---

GET /sessions/{channel_id} — 获取会话详情
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

获取指定频道绑定的会话的完整状态信息。

**认证**: Bearer token

**Response ``200 OK``**:

.. code-block:: json

   {
     "channel_id": "feishu:oc_chat1",
     "window_id": "@1",
     "provider": "claude",
     "cwd": "/tmp/my-project",
     "session_id": "abc-123",
     "approval_mode": "normal",
     "batch_mode": "batched",
     "display_name": "my-project"
   }

**Response ``404 Not Found``**: 频道未绑定到任何会话

.. code-block:: json

   {"detail": "No session found for channel feishu:oc_chat1"}

---

DELETE /sessions/{channel_id} — 关闭会话
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

关闭指定频道的会话，杀死对应的 tmux 窗口并清理所有绑定。

**认证**: Bearer token

**Response ``200 OK``**:

.. code-block:: json

   {"channel_id": "feishu:oc_chat1", "killed_windows": 1}

**WebSocket 等价**: ``session.close`` 消息

---

POST /sessions/{channel_id}/input — 发送输入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

向 tmux 窗口发送文本，模拟键盘输入。

**认证**: Bearer token

**Request body** (``InputRequest``):

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``text``
     - string
     - **是**
     - 要发送的文本内容
   * - ``enter``
     - boolean
     - 否
     - 发送文本后自动按回车；默认为 ``true``
   * - ``literal``
     - boolean
     - 否
     - 逐字发送（保留特殊字符）；默认为 ``true``
   * - ``raw``
     - boolean
     - 否
     - 原始模式；默认为 ``false``

**Response ``200 OK``**: ``{"ok": true}``

**Response ``404 Not Found``**: 频道未绑定到任何会话

**WebSocket 等价**: ``input`` 消息

---

POST /sessions/{channel_id}/key — 发送按键
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

向 tmux 窗口发送特殊按键（Escape、Ctrl+C 等）。

**认证**: Bearer token

**Request body** (``KeyRequest``):

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``key``
     - string
     - **是**
     - 按键名称；如 ``Escape``、``Enter``、``C-c``（Ctrl+C）

**Response ``200 OK``**: ``{"ok": true}``

**支持的按键**: ``Escape``、``Enter``、``C-c``（Ctrl+C）、``C-d``（Ctrl+D）、``C-z``、``Up``、``Down``、``Left``、``Right``、``PageUp``、``PageDown`` 等。

**WebSocket 等价**: ``key`` 消息

---

GET /sessions/{channel_id}/pane — 捕获窗格内容
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以纯文本形式捕获 tmux 窗格的当前可见内容。

**认证**: Bearer token

**Response ``200 OK``**:

.. code-block:: json

   {"channel_id": "feishu:oc_chat1", "content": "user@host:~$ claude\n"}

**Response ``404 Not Found``**: 频道未绑定到任何会话

**WebSocket 等价**: ``capture.pane`` 消息

---

GET /sessions/{channel_id}/screenshot — 截取截图
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

将 tmux 窗格当前内容捕获为 PNG 图片（原始字节流）。

**认证**: Bearer token

**Response ``200 OK``**: ``Content-Type: image/png``（原始字节流）

**Response ``404 Not Found``**: 截图不可用

**WebSocket 等价**: ``capture.screenshot`` 消息（返回 base64 编码）

---

POST /sessions/{channel_id}/verbose — 切换 Verbose 模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

切换 thinking 内容的展示详细程度。此端点在 API 服务器端为占位 no-op，详细内容始终通过 WebSocket 事件全量下发。

**认证**: Bearer token

**Request body** (``VerboseRequest``):

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``enabled``
     - boolean
     - **是**
     - ``true`` 启用详细输出；``false`` 简化输出

**Response ``200 OK``**:

.. code-block:: json

   {"channel_id": "feishu:oc_chat1", "verbose": true}

**WebSocket 等价**: ``verbose.set`` 消息

Directories
-----------

POST /directories/browse — 浏览目录
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

列出指定路径下的子目录，用于目录导航向导。

**认证**: Bearer token

**Request body** (``BrowseRequest``):

.. list-table::
   :header-rows: 1
   :widths: 20 10 10 60

   * - 字段
     - 类型
     - 必填
     - 说明
   * - ``path``
     - string
     - **是**
     - 要浏览的目录绝对路径

**Response ``200 OK``**:

.. code-block:: json

   {
     "path": "/home/user",
     "directories": ["Documents", "Downloads", "Projects"],
     "parent": "/home"
   }

**Response ``400 Bad Request``**: 路径不是目录

.. code-block:: json

   {"detail": "Not a directory: /etc/passwd"}

**Response ``403 Forbidden``**: 权限不足

.. code-block:: json

   {"detail": "Permission denied: /root"}

**WebSocket 等价**: ``wizard.browse`` 消息

Health
------

GET /health — 健康检查
~~~~~~~~~~~~~~~~~~~~~~~

返回网关初始化状态。此端点**无需认证**。

**Response ``200 OK``**:

.. code-block:: json

   {"status": "ok"}

``status`` 字段:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 值
     - 含义
   * - ``"ok"``
     - 网关已初始化，服务器正常运行
   * - ``"not_ready"``
     - 网关仍在启动中（服务器刚启动时短暂出现）
