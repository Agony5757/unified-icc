API 参考
=========

核心类
------

.. toctree::
   :maxdepth: 1

   gateway
   adapter
   events
   channel-router

公共 API
--------

``unified_icc`` 包导出以下公共 API：

.. code-block:: python

   from unified_icc import (
       # 主网关
       UnifiedICC,
       WindowInfo,

       # 适配器协议
       FrontendAdapter,
       CardPayload,
       InteractivePrompt,

       # 事件
       AgentMessageEvent,
       StatusEvent,
       HookEvent,
       WindowChangeEvent,

       # 配置
       GatewayConfig,
       config,

       # 频道路由（单例）
       channel_router,
   )

模块索引
--------

**网关**

* ``gateway`` — UnifiedICC 主类
* ``config`` — GatewayConfig
* ``channel_router`` — ChannelRouter 单例

**事件**

* ``event_types`` — AgentMessageEvent、StatusEvent、HookEvent、WindowChangeEvent
* ``adapter`` — FrontendAdapter 协议、CardPayload、InteractivePrompt
* ``monitor_events`` — 内部事件类型（NewMessage、NewWindowEvent）

**会话管理**

* ``session`` — SessionManager
* ``session_monitor`` — SessionMonitor 轮询循环
* ``session_lifecycle`` — 会话映射对比
* ``session_map`` — 会话映射 I/O
* ``idle_tracker`` — 每会话空闲计时器

**状态**

* ``state_persistence`` — 去中心化 JSON 持久化
* ``window_state_store`` — 窗口状态追踪
* ``monitor_state`` — 轮询偏移量

**I/O**

* ``tmux_manager`` — tmux 操作
* ``transcript_reader`` — 转录 I/O
* ``transcript_parser`` — 转录 → 消息
* ``terminal_parser`` — 终端 UI 检测
* ``event_reader`` — events.jsonl 读取
* ``window_view`` — 窗口快照
* ``window_resolver`` — 窗口 ID 重映射

**钩子**

* ``hook`` — Claude 钩子事件

**工具**

* ``utils`` — 工具函数
* ``mailbox`` — 助手间消息
* ``cc_commands`` — Claude 命令发现
* ``expandable_quote`` — 可展开文本块
* ``topic_state_registry`` — 话题状态
* ``claude_task_state`` — Claude 任务追踪

**Provider**

* ``providers`` — Provider 注册表和辅助函数
* ``providers.base`` — AgentProvider 协议
* ``providers.registry`` — ProviderRegistry
* ``providers.claude`` — Claude Provider
* ``providers.codex`` — Codex Provider
* ``providers.gemini`` — Gemini Provider
* ``providers.pi`` — Pi Provider
* ``providers.shell`` — Shell Provider

函数调用栈
----------

关于关键操作的详细函数调用链，请参见 :doc:`call-stacks`。
