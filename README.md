# Unified ICC

**平台无关的 AI 编程助手网关** — 管理 tmux 上的 Claude Code、Codex CLI、Gemini CLI 等会话，通过统一 API 暴露给任意前端。

```
飞书 (cclark)  →  unified-icc  →  tmux  →  Claude Code
Telegram        →  unified-icc  →  tmux  →  Codex CLI
HTTP/WS 客户端 →  unified-icc  →  tmux  →  Gemini CLI
```

[![CI](https://github.com/Agony5757/unified-icc/actions/workflows/ci.yml/badge.svg)](https://github.com/Agony5757/unified-icc/actions)

## 核心特性

- **平台无关** — 核心代码无消息平台依赖，前端通过 `FrontendAdapter` 协议接入
- **多 Agent 支持** — 内置 Claude Code、Codex CLI、Gemini CLI、Pi、Shell
- **会话管理** — tmux 窗口生命周期、transcript 监控、crash recovery
- **API Server** — HTTP + WebSocket API，支持任意 HTTP 客户端访问
- **异步设计** — 完整的 async/await API

## 快速导航

| 文档 | 说明 |
|------|------|
| [快速上手](docs/getting-started.md) | 安装、配置、启动 |
| [架构介绍](docs/architecture.md) | 组件、数据流、状态管理 |
| [Provider 系统](docs/providers.md) | 内置 Agent 及能力对比 |
| [可扩展性](docs/extending.md) | 添加新 Provider 或前端 |
| [API 参考](docs/api.md) | REST + WebSocket 端点 |
| [故障排除](docs/troubleshooting.md) | 常见问题与解决方案 |

## 快速开始

```bash
# 安装
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv sync --extra server

# 启动 API Server
unified-icc server start --port 8900

# 创建会话
curl -X POST http://localhost:8900/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "test", "work_dir": "/tmp", "provider": "claude", "mode": "standard"}'
```

## 相关项目

| 项目 | 说明 |
|------|------|
| [cclark](https://github.com/Agony5757/cclark) | 飞书前端 |
| [ccgram](https://github.com/alexei-led/ccgram) | Telegram 前端（上游参考） |

## License

MIT
