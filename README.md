# Unified ICC

**ICC** = **I**nteractive **C**oding **CLI**（交互式编程命令行）—— 一个与平台无关的网关，通过 tmux 管理 AI 编程助手（Claude Code、Codex CLI、Gemini CLI、Pi 等）。

[![CI](https://github.com/Agony5757/unified-icc/actions/workflows/ci.yml/badge.svg)](https://github.com/Agony5757/unified-icc/actions)

Unified ICC 从 [ccgram](https://github.com/alexei-led/ccgram) 中提取核心逻辑为一个可复用的 Python 库，使任何消息前端（飞书、Telegram、Discord、Slack……）都能通过简洁的异步 API 驱动 AI 编程会话。

## 主要特性

- **平台无关**：核心库无任何消息平台依赖
- **多 Provider 支持**：无缝管理 Claude Code、Codex CLI、Gemini CLI、Pi 和 Shell 会话
- **异步优先**：为现代 Python 应用提供完整的 async/await API
- **事件驱动**：可订阅消息、状态变更、窗口事件和钩子
- **状态持久化**：带崩溃恢复的去中心化 JSON 持久化

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
    window = await gateway.create_window("/path/to/project", provider="claude")

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
| [快速开始](https://unified-icc.readthedocs.io/zh/index.html) | 安装、快速开始、入门 |
| [架构](https://unified-icc.readthedocs.io/zh/architecture.html) | 系统设计、组件、数据流 |
| [API 参考](https://unified-icc.readthedocs.io/zh/api-reference/index.html) | 完整 API 文档 |
| [Provider](https://unified-icc.readthedocs.io/zh/providers/index.html) | AI 助手 Provider 支持 |
| [事件](https://unified-icc.readthedocs.io/zh/events/index.html) | 事件系统和处理器 |
| [配置](https://unified-icc.readthedocs.io/zh/configuration.html) | 环境变量和配置项 |
| [故障排除](https://unified-icc.readthedocs.io/zh/troubleshooting.html) | 常见问题和解决方案 |
| [贡献指南](https://unified-icc.readthedocs.io/zh/contributing.html) | 开发指南 |

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
| Claude Code | `claude` | 钩子事件、JSONL 转录、恢复会话、/continue |
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

所有配置项详见[配置参考](https://unified-icc.readthedocs.io/zh/configuration.html)。

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

## 许可证

MIT
