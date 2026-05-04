# 架构介绍

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend (cclark)                   │
│   ws_client → handlers → adapter → ICCWebSocketGateway     │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ FrontendAdapter (async)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    UnifiedICC Gateway                       │
│                                                             │
│   gateway.py ──► ChannelRouter ──► SessionMonitor          │
│   (公开 API)      (channel↔window)    (1s poll)           │
│                        ↓                 ↓                   │
│                   state.json         event_types.py         │
│                                                             │
│   tmux_manager.py ← SessionLifecycle ← ProviderRegistry     │
│   (tmux 操作)      (会话发现)          (claude/codex/...)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        tmux session                         │
│                                                             │
│   @0 (claude)    @1 (codex)    @2 (gemini)    @3 (pi)    │
│   transcript.json stdout.txt   transcript.json transcript.json│
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### Gateway (`gateway.py`)

公开 API 入口，管理 tmux 窗口和 channel 绑定：

```python
# 创建窗口
window = await gateway.create_window(cwd, provider, mode)

# 绑定 channel
gateway.bind_channel(channel_id, window_id)

# 发送消息
await gateway.send_to_window(window_id, text, enter=True)

# 事件回调
gateway.on_message(callback)      # AgentMessageEvent
gateway.on_status(callback)        # StatusEvent
gateway.on_hook(callback)          # HookEvent
gateway.on_window_change(callback) # WindowChangeEvent
```

### ChannelRouter (`channel_router.py`)

维护 channel_id ↔ window_id 的双向映射：

- 每个 channel 最多绑定一个 window
- 每个 window 可以被多个 channel 监听
- 持久化到 `state.json`

```python
channel_router.bind("feishu:oc_chat1", "@0")
window_id = channel_router.get_window("feishu:oc_chat1")
```

### SessionMonitor (`session_monitor.py`)

内部组件，1 秒轮询循环：

1. 读取 `~/.unified-icc/events.jsonl`（Claude hooks）
2. 读取各窗口的 transcript 文件
3. 解析并分发事件到回调

### TmuxManager (`tmux_manager.py`)

异步 libtmux 封装：

- 窗口生命周期：`create_window`, `kill_window`, `list_windows`
- I/O：`send_keys`, `capture_pane`
- Vim 模式检测：自动进入 INSERT 模式后再发送

### ProviderRegistry (`providers/`)

Agent Provider 协议和实现：

```python
class AgentProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def start(self, cwd: str, mode: str) -> WindowInfo
    def parse_transcript(self, lines: list[str]) -> list[AgentMessage]
    def extract_session_id(self, session_map: dict) -> str | None
```

## 数据流

### 入站（Frontend → Agent）

```
Frontend adapter.on_inbound_message(channel_id, text)
    │
    ▼
gateway.send_to_window(window_id, text)
    │
    ▼
tmux send-keys
    │
    ▼
Agent 接收输入
```

### 出站（Agent → Frontend）

```
tmux transcript / events.jsonl
    │
    ▼
SessionMonitor.poll() → 解析 transcript
    │
    ▼
AgentMessageEvent / StatusEvent / HookEvent
    │
    ▼
gateway.on_message() → adapter.send_card()
    │
    ▼
Frontend 渲染卡片
```

## 状态持久化

### 状态目录

`~/.unified-icc/`（可通过 `UNIFIED_ICC_DIR` 配置）

### 文件

| 文件 | 说明 |
|------|------|
| `state.json` | channel↔window 绑定、显示名 |
| `session_map.json` | Claude hooks 写入的 session→window 映射 |
| `events.jsonl` | Claude hooks 事件日志 |
| `monitor_state.json` | transcript 读取偏移量 |

### Crash Recovery

启动时自动恢复 `state.json` 中的绑定，SessionMonitor 继续监控已有的 tmux 窗口。

## FrontendAdapter 协议

`unified-icc` 不直接发送消息给用户，而是调用前端提供的 `FrontendAdapter`：

```python
class FrontendAdapter(Protocol):
    async def send_text(self, channel_id: str, text: str) -> str
    async def send_card(self, channel_id: str, card: CardPayload) -> str
    async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None
    async def send_image(self, channel_id: str, image_bytes: bytes, caption: str) -> str
    async def send_file(self, channel_id: str, file_path: str, caption: str) -> str
    async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str

    def register_message_handler(self, handler)
    def register_callback_handler(self, handler)
```

## 下一步

- [Provider 系统](providers.md) — 了解内置 Agent 的能力差异
- [可扩展性](extending.md) — 添加新的 Provider 或 Frontend
