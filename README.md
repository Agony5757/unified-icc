# Unified ICC

**ICC** = **I**nteractive **C**oding **CLI**（交互式编程命令行）—— 一个与平台无关的网关，通过 tmux 管理 AI 编程助手（Claude Code、Codex CLI、Gemini CLI、Pi 等）。

[![CI](https://github.com/Agony5757/unified-icc/actions/workflows/ci.yml/badge.svg)](https://github.com/Agony5757/unified-icc/actions)

Unified ICC 从 [ccgram](https://github.com/alexei-led/ccgram) 中提取核心逻辑为一个可复用的 Python 库，使任何消息前端（飞书、Telegram、Discord、Slack……）都能通过简洁的异步 API 驱动 AI 编程会话。

## 主要特性

- **平台无关**：核心库无任何消息平台依赖
- **多 Provider 支持**：无缝管理 Claude Code、Codex CLI、Gemini CLI、Pi 和 Shell 会话
- **异步优先**：为现代 Python 应用提供完整的 async/await API
- **事件驱动**：可订阅消息、状态变更、窗口事件和钩子
- **状态持久化**：带崩溃恢复的 JSON 持久化，记录窗口、频道绑定和 Claude session id
- **终端状态解析**：可从 tmux pane 中识别 Claude permission / plan 等交互状态并发出状态事件

## 安装

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv pip install -e .
```

## 快速开始

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    # 创建新的 Claude Code 窗口
    window = await gateway.create_window(
        "/path/to/project",
        provider="claude",
        mode="normal",
    )

    # 绑定消息频道
    gateway.bind_channel("feishu:chat_123:thread_456", window.window_id)

    # 订阅助手消息
    def on_message(event):
        for msg in event.messages:
            print(f"助手：{msg.text}")

    gateway.on_message(on_message)

    # 向助手发送输入
    await gateway.send_to_window(window.window_id, "你好！")

    await gateway.stop()

asyncio.run(main())
```

## 文档

| 章节 | 说明 |
|------|------|
| [快速开始](https://agony5757.github.io/unified-icc/index.html) | 安装、快速开始、入门 |
| [架构](https://agony5757.github.io/unified-icc/architecture.html) | 系统设计、组件、数据流 |
| [API 参考](https://agony5757.github.io/unified-icc/api-reference/index.html) | 完整 API 文档 |
| [Provider](https://agony5757.github.io/unified-icc/providers/index.html) | AI 助手 Provider 支持 |
| [事件](https://agony5757.github.io/unified-icc/events/index.html) | 事件系统和处理器 |
| [配置](https://agony5757.github.io/unified-icc/configuration.html) | 环境变量和配置项 |
| [故障排除](https://agony5757.github.io/unified-icc/troubleshooting.html) | 常见问题和解决方案 |
| [贡献指南](https://agony5757.github.io/unified-icc/contributing.html) | 开发指南 |

## 架构

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│  cclark     │  │  ccgram     │  │  未来接入     │
│  （飞书）    │  │  (Telegram) │  │  (Discord)   │
└──────┬──────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │
       │   FrontendAdapter API             │
       └────────────┬────┴────────────────┘
                    │
       ┌────────────┴────────────┐
       │    unified_icc          │
       │  ┌──────────────────┐   │
       │  │ UnifiedICC       │   │
       │  │ ChannelRouter    │   │
       │  │ SessionMonitor   │   │
       │  │ TmuxManager      │   │
       │  │ ProviderRegistry │   │
       │  └──────────────────┘   │
       └────────────┬────────────┘
                    │
       ┌────────────┴────────────┐
       │     tmux 会话           │
       │  ┌───┐ ┌───┐ ┌───┐     │
       │  │@0 │ │@1 │ │@2 │ ... │
       │  │CC │ │CX │ │GM │     │
       │  └───┘ └───┘ └───┘     │
       └─────────────────────────┘
```

## 支持的 Provider

| Provider | 启动命令 | 功能 |
|----------|----------|------|
| Claude Code | `claude --permission-mode default`（normal）或 `claude --dangerously-skip-permissions`（yolo） | 钩子事件、JSONL 转录、恢复会话、/continue、terminal prompt 解析 |
| Codex CLI | `codex` | 纯文本转录、yolo 模式 |
| Gemini CLI | `gemini` | JSONL 转录、yolo 模式 |
| Pi | `pi` | JSONL 转录 |
| Shell | interactive shell | 基础终端支持 |

## 配置

通过环境变量配置：

```bash
# 核心设置
CCLARK_CONFIG_DIR=~/.cclark
CCLARK_PROVIDER=claude

# Tmux
TMUX_SESSION_NAME=cclark

# 监控
MONITOR_POLL_INTERVAL=1.0
```

所有配置项详见[配置参考](https://agony5757.github.io/unified-icc/configuration.html)。

## 设计文档

| 文档 | 说明 |
|------|------|
| [dev-design.md](dev-design.md) | 主设计文档 — 项目概览、ccgram 分析、网关架构 |
| [design/module-gateway-core.md](design/module-gateway-core.md) | UnifiedICC 网关内部实现 |
| [design/module-adapter-layer.md](design/module-adapter-layer.md) | 前端适配器抽象层 |
| [design/module-feishu-frontend.md](design/module-feishu-frontend.md) | 飞书特定实现 |
| [design/module-card-renderer.md](design/module-card-renderer.md) | 卡片渲染 + 详细模式 |
| [design/module-mvp.md](design/module-mvp.md) | MVP 实现计划 |

## 相关项目

| 项目 | 仓库 | 说明 |
|------|------|------|
| **cclark** | [Agony5757/cclark](https://github.com/Agony5757/cclark) | 飞书前端，使用 unified-icc |
| **ccgram** | [alexei-led/ccgram](https://github.com/alexei-led/ccgram) | 原始 Telegram 前端（上游参考） |

## ICC 含义

**ICC = Interactive Coding CLI** — 以交互式终端会话运行的工具类别：

- **Claude Code** — Anthropic 的 AI 编程助手 CLI
- **Codex CLI** — OpenAI 的编程助手 CLI
- **未来助手** — 任何符合 tmux 兼容交互模式的新 CLI

Unified ICC 将每个 CLI 视为具有标准化协议（`AgentProvider`）的 "Provider"，使网关能够统一管理它们，无需关心各自的转录格式、钩子系统或恢复能力差异。

## cclark 集成要点

- `UnifiedICC.kill_channel_windows(channel_id)` 用于实现一个 Feishu chat 只保留一个托管 tmux-Claude session。
- `UnifiedICC.list_orphaned_agent_windows()` 可报告未被状态追踪的 live Claude tmux 窗口，但不会自动删除它们。
- `SessionMonitor.detect_session_id()` 会通过原始 tmux key 发送 `/status`，避免普通输入路径污染 Claude 输入框。
- 标准 Claude 会话应使用 `mode="normal"`，Provider 会注入 `--permission-mode default`；只有显式 yolo 才跳过权限。
- 前端如果要驱动 Claude plan mode 的 `Tell Claude what to change`，需要支持“不带 Enter 的选择输入”和“下一条反馈文本再提交”两步流程；`UnifiedICC.send_input_to_window(..., enter=False)` 用于这个场景。

## 许可证

MIT
