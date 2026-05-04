# API 参考

## REST API

所有端点前缀 `/api/v1`。

### Sessions

#### 创建会话

```bash
POST /sessions
Content-Type: application/json

{
    "channel_id": "feishu:oc_chat",
    "work_dir": "/tmp/project",
    "provider": "claude",
    "mode": "standard"
}
```

响应：
```json
{
    "channel_id": "feishu:oc_chat",
    "window_id": "@3",
    "provider": "claude",
    "cwd": "/tmp/project",
    "mode": "standard"
}
```

#### 列出会话

```bash
GET /sessions
```

响应：
```json
{
    "sessions": [
        {
            "channel_id": "feishu:oc_chat",
            "window_id": "@3",
            "provider": "claude",
            "cwd": "/tmp/project"
        }
    ]
}
```

#### 获取会话

```bash
GET /sessions/{channel_id}
```

#### 删除会话

```bash
DELETE /sessions/{channel_id}
```

#### 发送输入

```bash
POST /sessions/{channel_id}/input
Content-Type: application/json

{
    "text": "hello",
    "enter": true,
    "literal": false
}
```

参数：
- `text`: 要发送的文本
- `enter`: 是否发送回车（默认 true）
- `literal`: 是否逐字发送（默认 false）

#### 发送按键

```bash
POST /sessions/{channel_id}/key
Content-Type: application/json

{
    "key": "Escape"
}
```

支持的按键：`Escape`, `Enter`, `Ctrl+C`, `Ctrl+D` 等。

#### 捕获窗格

```bash
GET /sessions/{channel_id}/pane
```

响应：纯文本

#### 截取截图

```bash
GET /sessions/{channel_id}/screenshot
```

响应：PNG 图片

#### 切换 verbose

```bash
POST /sessions/{channel_id}/verbose
```

### Directories

#### 浏览目录

```bash
POST /directories/browse
Content-Type: application/json

{
    "path": "/home/user"
}
```

### Health

```bash
GET /health
```

## WebSocket API

连接：`ws://localhost:8900/api/v1/ws/{channel_id}`

### 客户端 → 服务器

```json
// 创建会话
{"type": "session.create", "channel_id": "my-channel", "work_dir": "/tmp", "provider": "claude", "mode": "standard"}

// 发送输入
{"type": "input", "channel_id": "my-channel", "text": "hello", "enter": true}

// 发送按键
{"type": "key", "channel_id": "my-channel", "key": "Escape"}

// 捕获窗格
{"type": "capture.pane", "channel_id": "my-channel"}

// 列出会话
{"type": "session.list"}

// 关闭会话
{"type": "session.close", "channel_id": "my-channel"}

// 心跳
{"type": "ping"}
```

### 服务器 → 客户端

```json
// 会话创建
{"type": "session.created", "channel_id": "my-channel", "window_id": "@3", "provider": "claude", ...}

// Agent 消息
{"type": "agent.message", "channel_ids": ["my-channel"], "messages": [
    {"text": "Hello!", "role": "assistant", "content_type": "text", "is_complete": true}
]}

// Agent 状态
{"type": "agent.status", "channel_ids": ["my-channel"], "status": "working", "display_label": "Thinking..."}
{"type": "agent.status", "channel_ids": ["my-channel"], "status": "interactive", "interactive": true}

// 窗口变化
{"type": "window.change", "window_id": "@3", "change_type": "new", "provider": "claude"}

// Hook 事件
{"type": "hook.event", "window_id": "@3", "event_type": "session_start", ...}

// 窗格捕获
{"type": "pane.capture", "channel_id": "my-channel", "text": "..."}

// 心跳响应
{"type": "pong"}

// 错误
{"type": "error", "message": "..."}
```

## 认证

设置 `ICC_API_KEY` 环境变量启用认证：

```bash
export ICC_API_KEY=sk-your-secret-key
unified-icc server start
```

### REST

```bash
curl http://localhost:8900/api/v1/sessions \
  -H "Authorization: Bearer sk-your-secret-key"
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8900/api/v1/ws?token=sk-your-secret-key');
```

## Event Types

### AgentMessageEvent

```python
@dataclass
class AgentMessageEvent:
    window_id: str
    session_id: str
    messages: list[AgentMessage]
    channel_ids: list[str]
```

### StatusEvent

```python
@dataclass
class StatusEvent:
    window_id: str
    session_id: str
    status: str  # "idle" | "working" | "interactive" | "done" | "dead"
    display_label: str
    channel_ids: list[str]
```

### HookEvent

```python
@dataclass
class HookEvent:
    window_id: str
    event_type: str  # "session_start", "session_end"
    session_id: str
    data: dict
```

## 下一步

- [故障排除](troubleshooting.md) — 常见问题与解决方案
