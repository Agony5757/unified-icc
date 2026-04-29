Provider
=========

Unified ICC 通过统一抽象支持多种 AI 编程助手 Provider。

支持的 Provider
---------------

.. list-table::
   :header-rows: 1

   * - Provider
     - 包
     - 启动命令
   * - Claude
     - ``claude-code``
     - normal: ``claude --permission-mode default``；yolo: ``claude --dangerously-skip-permissions``
   * - Codex
     - ``codex``
     - ``codex``
   * - Gemini
     - ``gemini``
     - ``gemini``
   * - Pi
     - ``pi``
     - ``pi``
   * - Shell
     - —
     - 交互式 shell

Provider 架构
--------------

::

   ┌─────────────────────────────────────────────────────────────┐
   │                      ProviderRegistry                        │
   │  - get(provider_name) → AgentProvider                       │
   │  - is_valid(provider_name) → bool                            │
   │  - provider_names() → list[str]                             │
   └─────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                   AgentProvider Protocol                      │
   │  （所有 Provider 都实现此接口）                               │
   │                                                              │
   │  @property capabilities → ProviderCapabilities                 │
   │  make_launch_args() → str                                   │
   │  parse_hook_payload() → SessionStartEvent | None             │
   │  parse_transcript_line() → dict | None                       │
   │  read_transcript_file() → (entries, offset)                 │
   │  parse_transcript_entries() → (messages, pending_tools)      │
   │  parse_terminal_status() → StatusUpdate | None             │
   │  extract_bash_output() → str | None                          │
   │  discover_transcript() → SessionStartEvent | None            │
   │  ...                                                         │
   └─────────────────────────────────────────────────────────────┘
                                 │
              ┌─────────────────┼─────────────────┐
              ▼                  ▼                  ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │ClaudeProvider│      │CodexProvider│      │GeminiProvider│
   │             │      │             │      │             │
   │ JSONL       │      │ 纯文本     │      │ JSONL       │
   │ 会话钩子    │      │ 无钩子     │      │ 无钩子      │
   └─────────────┘      └─────────────┘      └─────────────┘

AgentProvider 协议
------------------

.. code-block:: python

   class AgentProvider(Protocol):
       @property
       def capabilities(self) -> ProviderCapabilities:
           """此 Provider 支持哪些功能。"""
           ...

       def make_launch_args(
           self,
           resume_id: str | None = None,
           use_continue: bool = False,
       ) -> str:
           """构建启动命令参数。"""
           ...

       def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None:
           """解析 SessionStart 钩子载荷。"""
           ...

       def parse_transcript_line(self, line: str) -> dict[str, Any] | None:
           """解析单行转录内容。"""
           ...

       def read_transcript_file(
           self,
           file_path: str,
           last_offset: int,
       ) -> tuple[list[dict[str, Any]], int]:
           """从转录文件读取新条目。"""
           ...

       def parse_transcript_entries(
           self,
           entries: list[dict[str, Any]],
           pending_tools: dict[str, Any],
           cwd: str | None = None,
       ) -> tuple[list[AgentMessage], dict[str, Any]]:
           """将解析的条目转换为 AgentMessage 对象。"""
           ...

       def parse_terminal_status(
           self,
           pane_text: str,
           *,
           pane_title: str = "",
       ) -> StatusUpdate | None:
           """从终端窗格解析状态。"""
           ...

       def extract_bash_output(
           self,
           pane_text: str,
           command: str,
       ) -> str | None:
           """从窗格中提取 bash 命令输出。"""
           ...

       def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool:
           """检查条目是否来自用户。"""
           ...

       def discover_transcript(
           self,
           cwd: str,
           window_key: str,
           *,
           max_age: float | None = None,
       ) -> SessionStartEvent | None:
           """为工作目录查找转录。"""
           ...

       def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]:
           """发现可用的命令/技能。"""
           ...

       def build_status_snapshot(
           self,
           transcript_path: str,
           *,
           display_name: str,
           session_id: str = "",
           cwd: str = "",
       ) -> str | None:
           """为快照构建状态行。"""
           ...

ProviderCapabilities
--------------------

每个 Provider 声明其能力：

.. code-block:: python

   @dataclass(frozen=True, slots=True)
   class ProviderCapabilities:
       name: str                           # Provider 名称
       launch_command: str                 # CLI 启动命令
       supports_hook: bool = False         # 有钩子集成
       supports_hook_events: bool = False   # 有钩子事件类型
       hook_event_types: tuple[str, ...] = ()  # 可用钩子类型
       supports_resume: bool = False        # 可恢复会话
       supports_continue: bool = False     # 有 /continue 命令
       supports_structured_transcript: bool = False  # JSONL vs 纯文本
       supports_incremental_read: bool = True  # 可增量读取
       transcript_format: str = "jsonl"     # "jsonl" 或 "plain"
       uses_pane_title: bool = False        # 使用终端标题
       builtin_commands: tuple[str, ...] = ()   # 内置命令
       supports_user_command_discovery: bool = False  # 可发现技能
       supports_status_snapshot: bool = False  # 可构建状态快照
       supports_mailbox_delivery: bool = True  # 邮箱支持
       chat_first_command_path: bool = False  # /command 路径格式
       has_yolo_confirmation: bool = False  # 有 --dangerously-skip 标志
       supports_task_tracking: bool = False  # 任务追踪支持

Provider 功能对比
------------------

.. list-table::
   :header-rows: 1

   * - 功能
     - Claude
     - Codex
     - Gemini
     - Pi
   * - 钩子事件
     - ✅
     - ❌
     - ❌
     - ❌
   * - JSONL 转录
     - ✅
     - ❌
     - ✅
     - ✅
   * - 恢复会话
     - ✅
     - ❌
     - ❌
     - ❌
   * - /continue
     - ✅
     - ❌
     - ❌
     - ❌
   * - 状态快照
     - ✅
     - ❌
     - ❌
     - ❌
   * - Yolo 模式
     - ✅ ``--dangerously-skip-permissions``
     - ✅ ``--dangerously-bypass``
     - ✅ ``--yolo``
     - ❌
   * - 任务追踪
     - ✅
     - ❌
     - ❌
     - ❌
   * - 命令发现
     - ✅
     - ❌
     - ❌
     - ❌

Claude 权限模式
----------------

``normal`` / ``standard`` 会话启动 Claude 时会显式传入 ``--permission-mode default``。
这用于覆盖本机用户配置中可能存在的 ``permissions.defaultMode = bypassPermissions``，让 Claude 重新显示权限确认 UI。

``yolo`` 会话才会使用 ``--dangerously-skip-permissions``。

Claude terminal prompt
----------------------

Claude 的权限确认和 plan-mode 决策首先出现在 tmux terminal UI 中。
Provider 的 ``parse_terminal_status()`` 会从 pane 文本中识别这些交互状态，并通过 gateway 状态事件交给前端。
前端可以把该状态渲染为卡片、按钮或文本提示；当前 cclark 使用飞书卡片展示，并通过普通回复 ``1`` / ``2`` / ``3`` 驱动焦点中的 Claude UI。

使用 Provider
-------------

按名称获取 Provider
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc.providers import get_provider, registry

   # 获取默认 Provider（来自配置）
   provider = get_provider()
   print(provider.capabilities.name)  # "claude"

   # 获取特定 Provider
   claude = registry.get("claude")
   codex = registry.get("codex")

检查 Provider 有效性
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc.providers import registry

   if registry.is_valid("claude"):
       provider = registry.get("claude")

列出可用 Provider
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc.providers import registry

   for name in registry.provider_names():
       caps = registry.get(name).capabilities
       print(f"{name}: {caps.launch_command}")

解析启动命令
~~~~~~~~~~~~

.. code-block:: python

   from unified_icc.providers import resolve_launch_command

   # 普通模式
   cmd = resolve_launch_command("claude")
   # "claude --permission-mode default"

   # Yolo 模式（跳过权限）
   cmd = resolve_launch_command("claude", approval_mode="yolo")
   # "claude --dangerously-skip-permissions"

检测 Provider
~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc.providers import (
       detect_provider_from_command,
       detect_provider_from_transcript_path,
       detect_provider_from_runtime,
   )

   # 从运行命令检测
   provider = detect_provider_from_command("/usr/local/bin/claude")
   # "claude"

   # 从转录路径检测
   provider = detect_provider_from_transcript_path("/home/user/.claude/projects/myproj/.claude/history/2025-01-15_123456.jsonl")
   # "claude"

   # 从窗格命令和标题检测
   provider = detect_provider_from_runtime(
       pane_current_command="claude",
       pane_title="icc:claude",
   )
   # "claude"

实现自定义 Provider
--------------------

.. code-block:: python

   from dataclasses import dataclass
   from typing import Any
   from unified_icc.providers.base import (
       AgentProvider,
       AgentMessage,
       ProviderCapabilities,
       SessionStartEvent,
       StatusUpdate,
       DiscoveredCommand,
   )

   class MyAgentProvider:
       @property
       def capabilities(self) -> ProviderCapabilities:
           return ProviderCapabilities(
               name="myagent",
               launch_command="myagent",
               supports_hook=False,
               transcript_format="jsonl",
           )

       def make_launch_args(
           self,
           resume_id: str | None = None,
           use_continue: bool = False,
       ) -> str:
           if resume_id:
               return f"--resume {resume_id}"
           return ""

       def parse_hook_payload(self, payload: dict[str, Any]) -> SessionStartEvent | None:
           return None  # 无钩子支持

       def parse_transcript_line(self, line: str) -> dict[str, Any] | None:
           import json
           try:
               return json.loads(line)
           except json.JSONDecodeError:
               return None

       def parse_transcript_entries(
           self,
           entries: list[dict[str, Any]],
           pending_tools: dict[str, Any],
           cwd: str | None = None,
       ) -> tuple[list[AgentMessage], dict[str, Any]]:
           messages = []
           for entry in entries:
               messages.append(AgentMessage(
                   text=entry.get("text", ""),
                   role=entry.get("role", "assistant"),
                   content_type=entry.get("type", "text"),
               ))
           return messages, {}

       def parse_terminal_status(
           self,
           pane_text: str,
           *,
           pane_title: str = "",
       ) -> StatusUpdate | None:
           return None

       def extract_bash_output(self, pane_text: str, command: str) -> str | None:
           return None

       def is_user_transcript_entry(self, entry: dict[str, Any]) -> bool:
           return entry.get("role") == "user"

       def discover_transcript(
           self,
           cwd: str,
           window_key: str,
           *,
           max_age: float | None = None,
       ) -> SessionStartEvent | None:
           return None

       def discover_commands(self, base_dir: str) -> list[DiscoveredCommand]:
           return []

       def build_status_snapshot(
           self,
           transcript_path: str,
           *,
           display_name: str,
           session_id: str = "",
           cwd: str = "",
       ) -> str | None:
           return None
