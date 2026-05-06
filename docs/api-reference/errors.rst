错误码参考
==========

API 服务器返回的错误分为两类：HTTP 状态码（REST）和 WebSocket ``error`` 消息。

HTTP 状态码
-----------

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - 状态码
     - 含义
     - 常见原因
   * - ``200``
     - OK
     - 操作成功
   * - ``400``
     - Bad Request
     - 无效的 Provider 名称、不存在的目录、路径不是目录
   * - ``401``
     - Unauthorized
     - ``ICC_API_KEY`` 已设置但请求未提供或值错误
   * - ``403``
     - Forbidden
     - 目录权限不足（无法读取或列出）
   * - ``404``
     - Not Found
     - 频道未绑定到任何会话
   * - ``422``
     - Validation Error
     - 请求体字段缺失或类型不匹配（Pydantic 验证失败）
   * - ``503``
     - Service Unavailable
     - 网关尚未初始化（服务器刚启动时短暂出现）

REST 错误响应格式
~~~~~~~~~~~~~~~~~

.. code-block:: json

   {"detail": "Human-readable error message"}

WebSocket 错误消息
------------------

所有 WebSocket 错误均为 JSON 消息:

.. code-block:: json

   {"type": "error", "request_id": "optional-correlation-id", "message": "Human-readable error message"}

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - 消息内容
     - 含义
   * - ``Invalid JSON: <jsonDecodeError detail>``
     - 接收到的文本不是有效 JSON
   * - ``Unknown message type: <type>``
     - ``type`` 字段值不在已知消息类型列表中
   * - ``Unknown provider: <name>``
     - Provider 名称不在已注册列表中（claude/codex/gemini/pi/shell）
   * - ``No session for channel <id>``
     - 指定频道未绑定到任何 tmux 窗口
   * - ``channel_id required``
     - 消息缺少必填的 ``channel_id`` 字段
   * - ``Gateway not initialized``
     - 网关仍在启动中，尚未就绪
   * - ``Invalid or missing API key``
     - WebSocket 连接的 ``?token=`` 参数无效或缺失
   * - ``Not a directory: <path>``
     - ``wizard.browse`` 或 ``wizard.mkdir`` 的路径不是目录
   * - ``Permission denied: <path>``
     - 对目录没有读权限
   * - ``Failed to create directory: <oserror detail>``
     - 创建目录失败（权限不足、磁盘满等）
   * - ``Unhandled message type: <type>``
     - 消息类型已知但处理器未处理（通常为代码 bug）

FastAPI Validation Error (422)
-------------------------------

当 REST 请求体不符合 Pydantic 模型时，FastAPI 返回 422，响应体包含详细的字段级错误:

.. code-block:: json

   {
     "detail": [
       {
         "loc": ["body", "text"],
         "msg": "Field required",
         "type": "missing"
       }
     ]
   }

``loc`` 数组表示错误字段路径（如 ``["body", "text"]`` 表示请求体的 ``text`` 字段）。

调试方法
--------

**检查服务器日志**: 服务器输出到 stdout（前台模式）或系统日志（后台模式）。查看是否有异常堆栈。

**验证 PID 存活**:

.. code-block:: bash

   cat ~/.unified-icc/server.pid
   kill -0 $(cat ~/.unified-icc/server.pid) && echo "alive" || echo "dead"

**常见配置错误**:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 症状
     - 排查方向
   * - ``401 Unauthorized`` 但已设置正确的 key
     - 请求头格式应为 ``Authorization: Bearer <key>``，注意大小写和空格
   * - WebSocket 连接被关闭（4001）
     - 确认 ``ICC_API_KEY`` 环境变量与连接 URL 中的 ``?token=`` 参数一致
   * - ``503 Service Unavailable``
     - 服务器刚启动，网关尚未初始化；等待 1-2 秒后重试
   * - 连接不上服务器
     - 确认服务器绑定地址（``0.0.0.0`` 允许外部连接，``127.0.0.1`` 仅本地）
   * - ``404 Not Found`` on REST but session exists
     - REST 路径使用 ``channel_id``，确认与创建会话时使用的 ID 一致
