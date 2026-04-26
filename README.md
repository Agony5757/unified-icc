# Unified ICC

**ICC** = **I**nteractive **C**oding **CLI** — a platform-agnostic gateway for managing AI coding agents (Claude Code, Codex CLI, etc.) via tmux.

Unified ICC extracts the core logic from [ccgram](https://github.com/alexei-led/ccgram) into a reusable Python library, so that any messaging frontend (Feishu, Telegram, Discord, Slack...) can drive AI coding sessions through a clean async API.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│  cclark      │  │  ccgram     │  │  future      │
│  (Feishu)    │  │  (Telegram) │  │  (Discord)   │
└──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │
       │   unified-icc gateway API        │
       └────────────┬────┴────────────────┘
                    │
       ┌────────────┴────────────┐
       │    unified_icc           │
       │  ┌──────────────────┐   │
       │  │ Session Manager   │   │
       │  │ Tmux Manager      │   │
       │  │ Session Monitor   │   │
       │  │ Provider Registry │   │
       │  │ Hook System       │   │
       │  └──────────────────┘   │
       └────────────┬────────────┘
                    │
       ┌────────────┴────────────┐
       │     tmux session         │
       │  ┌───┐ ┌───┐ ┌───┐     │
       │  │@0 │ │@1 │ │@2 │ ... │
       │  │CC │ │CX │ │SH │     │
       │  └───┘ └───┘ └───┘     │
       └─────────────────────────┘
```

## Design Documents

| Document | Description |
|---|---|
| [dev-design.md](dev-design.md) | **Main design document** — project overview, ccgram analysis, gateway architecture, Feishu frontend design, development plan |
| [design/module-gateway-core.md](design/module-gateway-core.md) | UnifiedICC gateway internals — API, channel router, event dispatch, state persistence, import strategy |
| [design/module-adapter-layer.md](design/module-adapter-layer.md) | Frontend adapter abstraction — `FrontendAdapter` protocol, UI component adapters, message formatting pipeline |
| [design/module-feishu-frontend.md](design/module-feishu-frontend.md) | Feishu-specific implementation (cclark reference) — webhook server, FeishuAdapter, channel binding, interactive prompts |
| [design/module-card-renderer.md](design/module-card-renderer.md) | Feishu card rendering + verbose mode — card types, streaming algorithm, debounce strategy, content formatting |
| [design/module-mvp.md](design/module-mvp.md) | MVP implementation plan — 5-file proof of concept, validation checklist, transition roadmap |

## Quick Start (Reading Order)

1. Start with [dev-design.md](dev-design.md) for the full picture
2. Read [design/module-gateway-core.md](design/module-gateway-core.md) to understand the gateway API
3. Skim [design/module-adapter-layer.md](design/module-adapter-layer.md) for the adapter contract
4. Read [design/module-feishu-frontend.md](design/module-feishu-frontend.md) for the Feishu-specific design
5. Check [design/module-card-renderer.md](design/module-card-renderer.md) for verbose mode details
6. Review [design/module-mvp.md](design/module-mvp.md) for the implementation starting point

## Related Projects

| Project | Repo | Description |
|---|---|---|
| **cclark** | [Agony5757/cclark](https://github.com/Agony5757/cclark) | Feishu frontend consuming unified-icc |
| **ccgram** | [alexei-led/ccgram](https://github.com/alexei-led/ccgram) | Original Telegram frontend (upstream reference) |

## What ICC Stands For

**ICC = Interactive Coding CLI** — the class of tools that run as interactive terminal sessions:

- **Claude Code** — Anthropic's AI coding agent CLI
- **Codex CLI** — OpenAI's coding agent CLI
- **Future agents** — any new CLI that follows the tmux-compatible interactive pattern

Unified ICC treats each CLI as a "provider" with a standardized protocol (`AgentProvider`), so the gateway can manage them uniformly regardless of their specific transcript format, hook system, or resume capabilities.

## License

MIT
