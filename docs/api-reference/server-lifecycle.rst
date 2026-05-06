服务器生命周期
==============

描述 Unified ICC API 服务器从启动到关闭的完整过程。

实现位于 ``unified_icc.server.app``（FastAPI lifespan）和 ``unified_icc.server``（``run_server``）。

启动序列
--------

.. code-block:: text

   用户执行: unified-icc server start
        │
        ▼
   uvicorn 加载 FastAPI app
   FastAPI 调用 lifespan context manager
        │
        ▼
   lifespan.__aenter__():
     1. UnifiedICC() 网关实例化
     2. gateway.start() — 初始化 tmux、加载状态、启动轮询循环
     3. 网关注册回调:
        · gateway.on_message(_on_agent_message)
        · gateway.on_status(_on_agent_status)
        · gateway.on_hook_event(_on_hook_event)
        · gateway.on_window_change(_on_window_change)
        │
        ▼
   FastAPI 就绪，uvicorn 开始接受连接
   GET /health → {"status": "ok"}

网关回调 → ConnectionManager 事件流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   tmux 窗口 / transcript 文件变化
        │
        ▼
   UnifiedICC 网关内部事件
        │
        ├──► _on_agent_message()
        │         │
        │         ▼
        │    manager.broadcast_to_channel(cid, agent.message)
        │    manager.broadcast_global(agent.message)
        │
        ├──► _on_agent_status()
        │         │
        │         ▼
        │    manager.broadcast_to_channel(cid, agent.status)
        │    manager.broadcast_global(agent.status)
        │
        ├──► _on_hook_event()
        │         │
        │         ▼
        │    manager.broadcast_global(hook.event)
        │
        └──► _on_window_change()
                  │
                  ▼
             manager.broadcast_global(window.change)

**广播模型**:

- ``broadcast_to_channel(cid, msg)``: 发送给绑定到频道 ``cid`` 的 WebSocket 连接（私有消息）
- ``broadcast_global(msg)``: 发送给所有全局订阅的 WebSocket 连接（全局广播）

关闭序列
--------

.. code-block:: text

   SIGTERM / SIGINT / KeyboardInterrupt / unified-icc server stop
        │
        ▼
   FastAPI lifespan.__aexit__()
        │
        ▼
   gateway.stop():
     1. 停止 SessionMonitor 轮询循环
     2. 刷新所有待处理的状态写入
     3. 记录最终状态
        │
        ▼
   server.pid 文件删除（若由 start 命令创建）
        │
        ▼
   进程退出

CORS 配置
---------

服务器无条件添加允许所有来源的 CORS 中间件:

.. code-block:: python

   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

**安全注意**: 此配置允许任何来源的 JavaScript 向 API 服务器发起请求。若服务器面向公网，请限制 ``allow_origins`` 为受信任的前端域名。

ASGI 可挂载性
-------------

``create_app()`` 返回标准 FastAPI 实例，可以作为 ASGI 应用挂载到更大的应用中:

.. code-block:: python

   from unified_icc.server import create_app

   app = create_app()  # 可挂载到 FastAPI(middleware=[...]) 或 Starlette

环境变量与配置文件优先级
-------------------------

配置加载顺序（后者覆盖前者）:

1. ``~/.unified-icc/config.yaml``（配置文件）
2. 环境变量（如 ``ICC_API_KEY``、``ICC_API_PORT``）
3. 代码默认值

详见 :doc:`../configuration`。
