贡献指南
=========

感谢你对 Unified ICC 贡献的兴趣！

开发环境设置
------------

1. Fork 并克隆
~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/YOUR_USERNAME/unified-icc.git
   cd unified-icc

2. 安装依赖
~~~~~~~~~~~~

.. code-block:: bash

   # 安装带开发依赖的包
   uv sync
   uv pip install -e ".[dev]"

3. 验证安装
~~~~~~~~~~~~

.. code-block:: bash

   uv run python -c "import unified_icc; print('OK')"

运行测试
--------

.. code-block:: bash

   # 运行所有测试
   uv run pytest

   # 带覆盖率运行
   uv run pytest --cov=unified_icc --cov-report=html

   # 运行特定测试文件
   uv run pytest tests/unit/test_channel_router.py

   # 带详细输出运行
   uv run pytest -v

   # 运行匹配模式的测试
   uv run pytest -k "test_channel"

代码质量
--------

代码检查
~~~~~~~~

.. code-block:: bash

   # 运行 ruff 检查器
   uv run ruff check

   # 自动修复问题
   uv run ruff check --fix

类型检查
~~~~~~~~

.. code-block:: bash

   # 运行 pyright
   uv run pyright

所有检查
~~~~~~~~

.. code-block:: bash

   # 运行所有质量检查
   uv run ruff check && uv run pyright && uv run pytest

项目结构
--------

::

   src/unified_icc/
   ├── __init__.py           # 公共 API 导出
   ├── gateway.py            # UnifiedICC 主类
   ├── adapter.py            # FrontendAdapter 协议
   ├── event_types.py        # 事件数据类
   ├── channel_router.py     # 频道↔窗口路由
   ├── config.py             # GatewayConfig
   ├── tmux_manager.py       # tmux 操作
   ├── session.py            # SessionManager
   ├── session_monitor.py    # 轮询循环协调器
   ├── session_lifecycle.py  # 会话映射对比
   ├── session_map.py        # 会话映射 I/O
   ├── state_persistence.py  # 去中心化 JSON 持久化
   ├── window_state_store.py # 窗口状态追踪
   ├── event_reader.py       # events.jsonl 读取器
   ├── transcript_reader.py  # 转录 I/O
   ├── transcript_parser.py  # 转录 → 消息
   ├── terminal_parser.py    # 终端 UI 检测
   ├── hook.py              # Claude 钩子事件
   ├── idle_tracker.py      # 空闲计时器
   ├── monitor_state.py      # 轮询状态
   ├── monitor_events.py     # 内部事件类型
   ├── window_resolver.py    # 窗口 ID 重映射
   ├── window_view.py        # 窗口快照
   ├── mailbox.py           # 助手间消息
   ├── cc_commands.py       # Claude 命令发现
   ├── expandable_quote.py  # 可展开文本块
   ├── topic_state_registry.py # 话题状态
   ├── claude_task_state.py # Claude 任务追踪
   ├── utils.py            # 工具函数
   └── providers/
       ├── __init__.py       # 注册表 + 辅助函数
       ├── base.py           # AgentProvider 协议
       ├── registry.py       # ProviderRegistry
       ├── _jsonl.py         # JSONL 基类
       ├── claude.py         # Claude Provider
       ├── codex.py          # Codex Provider
       ├── codex_format.py   # Codex 格式化
       ├── codex_status.py   # Codex 状态解析
       ├── gemini.py         # Gemini Provider
       ├── pi.py             # Pi Provider
       ├── pi_discovery.py   # Pi 发现
       ├── pi_format.py      # Pi 格式化
       ├── shell.py          # Shell Provider
       └── process_detection.py # 进程检测

添加新 Provider
---------------

1. 在 ``providers/`` 中创建 Provider 文件
2. 实现 ``AgentProvider`` 协议
3. 在 ``providers/__init__.py`` 中注册
4. 添加测试

示例：

.. code-block:: python

   # src/unified_icc/providers/myagent.py
   from .base import AgentProvider, ProviderCapabilities, ...

   class MyAgentProvider:
       @property
       def capabilities(self) -> ProviderCapabilities:
           return ProviderCapabilities(
               name="myagent",
               launch_command="myagent",
               # ... 其他能力
           )

       # 实现所有 AgentProvider 方法...

.. code-block:: python

   # src/unified_icc/providers/__init__.py
   from .myagent import MyAgentProvider

   registry.register("myagent", MyAgentProvider)

添加新前端适配器
----------------

参见 `第一步 <getting-started/first-steps.rst>`_ 指南了解如何实现自定义前端适配器。

提交变更
---------

1. 创建分支
~~~~~~~~~~

.. code-block:: bash

   git checkout -b feature/my-feature

2. 做变更
~~~~~~~~~

.. code-block:: bash

   # 编辑文件
   git add .
   git commit -m "feat: add my feature"

3. 推送并创建 PR
~~~~~~~~~~~~~~~~

.. code-block:: bash

   git push origin feature/my-feature
   # 在 GitHub 上创建 PR

提交信息格式
------------

::

   type(scope): 描述

类型：
- feat：新功能
- fix：错误修复
- docs：文档
- refactor：代码重构
- test：测试变更
- chore：维护

示例：

::

   feat(gateway): add send_key method
   fix(channel_router): handle empty bindings
   docs: update README

报告问题
--------

请附上：

- Python 版本（``python --version``）
- tmux 版本（``tmux -V``）
- unified-icc 版本
- 最小复现代码
- 调试输出的相关日志

行为准则
--------

- 尊重和包容
- 提供建设性反馈
- 遵循项目的代码风格
