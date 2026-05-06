# Unified ICC API Reference

Unified ICC API 是统一网关的 HTTP/WebSocket 接口，用于在任何消息平台（飞书、Telegram、Discord…）与 AI 编程助手（Claude Code、Codex CLI、Gemini CLI…）之间建立桥梁。

所有 API 请求以 `/api/v1` 为前缀。API 兼容 OpenAPI 规范，Swagger UI 位于 `/docs`。

---

## Overview

API 服务器是一个 FastAPI 应用，运行于 `UnifiedICC` 网关之上：

```
  REST/WebSocket 客户端
           │
           ▼
    ┌─────────────┐
    │  FastAPI    │  HTTP + WebSocket
    │  Server     │
    └──────┬──────┘
           │  call / broadcast
    ┌──────▼──────┐
    │ UnifiedICC  │  Gateway — tmux + transcript
    │  Gateway    │  监控
    └─────────────┘
```

服务器**无状态**（HTTP 层），所有状态保存在 tmux 和 `~/.unified-icc/state.json`。

### Quick Start

```bash
# 1. 启动服务器
unified-icc server start --port 8900

# 2. 创建会话（REST）
curl -X POST http://localhost:8900/api/v1/sessions \
  -H "Authorization: Bearer $ICC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"work_dir": "/tmp/my-project", "provider": "claude"}'

# 3. 连接 WebSocket 监听事件
wscat -c "ws://localhost:8900/api/v1/ws/{channel_id}?token=$ICC_API_KEY"
```

---

## REST API

所有端点前缀 `/api/v1`。除 `GET /health` 外，均需认证。

### Sessions

#### POST /sessions — 创建会话

创建新的 AI 助手会话，并在 tmux 中启动对应的窗口。

**认证**: Bearer token（`ICC_API_KEY` 设置时）

**Request body**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `channel_id` | string | 否 | 自动生成 UUID | 外部频道标识符 |
| `work_dir` | string | 否 | 当前目录 | Agent 工作目录 |
| `provider` | string | 否 | `"claude"` | Provider 名称：`claude`, `codex`, `gemini`, `pi`, `shell` |
| `mode` | string | 否 | `"normal"` | 审批模式：`normal` 或 `yolo`（跳过权限确认） |
| `name` | string | 否 | `""` | 窗口显示名称（可选） |

**Response `200`**:

```json
{
  "channel_id": "api:3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "window_id": "@1",
  "provider": "claude",
  "mode": "normal",
  "cwd": "/tmp/my-project",
  "display_name": "my-project"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `channel_id` | string | 绑定到此会话的频道 ID |
| `window_id` | string | tmux 窗口 ID（如 `"@1"`） |
| `provider` | string | 使用的 Provider 名称 |
| `mode` | string | 审批模式（`normal` 或 `yolo`） |
| `cwd` | string | 工作目录 |
| `display_name` | string | 窗口显示名称 |

**curl 示例**:

```bash
curl -X POST http://localhost:8900/api/v1/sessions \
  -H "Authorization: Bearer $ICC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"work_dir": "/home/user/project", "provider": "claude", "mode": "normal"}'
```

---

#### GET /sessions — 列出会话

返回所有由网关管理的 tmux 窗口。

**认证**: Bearer token

**Response `200`**:

```json
{
  "sessions": [
    {
      "window_id": "@1",
      "display_name": "my-project",
      "provider": "claude",
      "cwd": "/tmp/my-project",
      "session_id": "abc-123",
      "channel_id": "feishu:oc_chat1"
    }
  ]
}
```

---

#### GET /sessions/{channel_id} — 获取会话

获取指定频道绑定的会话详情。

**认证**: Bearer token

**Response `200`**:

```json
{
  "channel_id": "feishu:oc_chat1",
  "window_id": "@1",
  "provider": "claude",
  "cwd": "/tmp/my-project",
  "session_id": "abc-123",
  "approval_mode": "normal",
  "batch_mode": "batched",
  "display_name": "my-project"
}
```

**Response `404`**: 无此频道对应的会话

```json
{"detail": "No session found for channel feishu:oc_chat1"}
```

---

#### DELETE /sessions/{channel_id} — 关闭会话

关闭指定频道绑定的会话，杀死对应的 tmux 窗口。

**认证**: Bearer token

**Response `200`**:

```json
{
  "channel_id": "feishu:oc_chat1",
  "killed_windows": 1
}
```

---

#### POST /sessions/{channel_id}/input — 发送输入

向 tmux 窗口发送文本输入（模拟键盘输入）。

**认证**: Bearer token

**Request body**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `text` | string | **是** | — | 要发送的文本 |
| `enter` | boolean | 否 | `true` | 发送文本后自动按回车 |
| `literal` | boolean | 否 | `true` | 逐字发送（保留特殊字符） |
| `raw` | boolean | 否 | `false` | 原始模式（绕过输入处理） |

**Response `200`**: `{"ok": true}`

**Response `404`**: 频道未绑定到任何窗口

---

#### POST /sessions/{channel_id}/key — 发送按键

向 tmux 窗口发送特殊按键（如 `Escape`、`Ctrl+C`）。

**认证**: Bearer token

**Request body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | **是** | 按键名称，如 `Escape`、`Enter`、`C-c`（Ctrl+C）|

**Response `200`**: `{"ok": true}`

**支持的按键**: `Escape`, `Enter`, `C-c`（Ctrl+C）, `C-d`（Ctrl+D）, `C-z`（Ctrl+Z）, `Up`, `Down` 等。

---

#### GET /sessions/{channel_id}/pane — 捕获窗格内容

以纯文本形式捕获 tmux 窗格当前内容。

**认证**: Bearer token

**Response `200`**:

```json
{
  "channel_id": "feishu:oc_chat1",
  "content": "user@host:~$ claude\n"
}
```

---

#### GET /sessions/{channel_id}/screenshot — 截取截图

将 tmux 窗格当前内容捕获为 PNG 图片。

**认证**: Bearer token

**Response `200`**: `Content-Type: image/png`（原始字节流）

**Response `404`**: 截图不可用

---

#### POST /sessions/{channel_id}/verbose — 切换 Verbose 模式

切换 thinking 内容展示模式（API 服务器端为占位 no-op，详细内容始终通过 WebSocket 事件下发）。

**认证**: Bearer token

**Request body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enabled` | boolean | **是** | `true` 启用详细输出，`false` 简化输出 |

**Response `200`**: `{"channel_id": "...", "verbose": true}`

---

### Directories

#### POST /directories/browse — 浏览目录

列出指定路径下的子目录（用于目录导航向导）。

**认证**: Bearer token

**Request body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | **是** | 要浏览的目录路径 |

**Response `200`**:

```json
{
  "path": "/home/user",
  "directories": ["Documents", "Downloads", "Projects"],
  "parent": "/home"
}
```

**Response `400`**: 路径不是目录

**Response `403`**: 权限不足

---

### Health

#### GET /health — 健康检查

返回服务器当前状态。此端点**无需认证**。

**Response `200`**:

```json
{"status": "ok"}
```

`status` 值:
- `"ok"` — 网关已初始化，服务器正常运行
- `"not_ready"` — 网关仍在启动中

---

## WebSocket API

WebSocket 提供双向通信，比 REST 更适合接收实时事件（Agent 输出、状态变更）。

### 连接

**频道订阅模式**（推荐）:
```
ws://localhost:8900/api/v1/ws/{channel_id}?token=<key>
```
连接到指定频道，接收该频道所有事件。

**全局监听模式**:
```
ws://localhost:8900/api/v1/ws?token=<key>
```
不绑定频道，仅接收全局广播事件（窗口变更、Hook 事件）。前端桥接层使用此模式来多路复用多个频道的事件。

**认证**: `?token=` 查询参数。无效时返回 `4001 Unauthorized` 并关闭连接。

**心跳**: 服务器**不自动发送 ping**。客户端应每 30 秒发送一次 `ping`，服务器返回 `pong`。若连接无数据流动，OS 会自动断开（TCP keepalive）。

---

### 客户端 → 服务器消息

所有消息为 JSON，`type` 字段决定消息类型。所有字段均为可选（除各消息类型所需的必填字段外）。

#### session.create — 创建会话

```json
{
  "type": "session.create",
  "request_id": "req-001",
  "channel_id": "feishu:oc_chat1",
  "work_dir": "/tmp/project",
  "provider": "claude",
  "mode": "normal",
  "name": "my-session"
}
```

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `request_id` | 否 | `""` | 请求 ID，用于关联响应 |
| `channel_id` | 否 | 自动 UUID | 频道标识符 |
| `work_dir` | 否 | cwd | 工作目录 |
| `provider` | 否 | `"claude"` | Provider |
| `mode` | 否 | `"normal"` | `normal` 或 `yolo` |
| `name` | 否 | `""` | 显示名称 |

**对应 REST**: `POST /sessions`

#### session.list — 列出会话

```json
{"type": "session.list", "request_id": "req-002"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `request_id` | 否 | 请求 ID |

**对应 REST**: `GET /sessions`

#### session.close — 关闭会话

```json
{"type": "session.close", "channel_id": "feishu:oc_chat1", "request_id": "req-003"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `channel_id` | **是** | 要关闭的频道 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `DELETE /sessions/{channel_id}`

#### input — 发送文本输入

```json
{
  "type": "input",
  "channel_id": "feishu:oc_chat1",
  "text": "hello",
  "enter": true,
  "literal": true,
  "raw": false,
  "request_id": "req-004"
}
```

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `channel_id` | **是** | — | 目标频道 |
| `text` | **是** | — | 要发送的文本 |
| `enter` | 否 | `true` | 发送后按回车 |
| `literal` | 否 | `true` | 逐字发送 |
| `raw` | 否 | `false` | 原始模式 |
| `request_id` | 否 | `""` | 请求 ID |

**对应 REST**: `POST /sessions/{channel_id}/input`

#### input.raw — 发送原始文本

```json
{"type": "input.raw", "channel_id": "feishu:oc_chat1", "text": "ls -la", "request_id": "req-005"}
```

等同于 `input`，但强制 `enter=true, literal=true, raw=true`。

#### key — 发送按键

```json
{"type": "key", "channel_id": "feishu:oc_chat1", "key": "Escape", "request_id": "req-006"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `channel_id` | **是** | 目标频道 |
| `key` | **是** | 按键名称 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `POST /sessions/{channel_id}/key`

#### capture.pane — 捕获窗格

```json
{"type": "capture.pane", "channel_id": "feishu:oc_chat1", "request_id": "req-007"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `channel_id` | **是** | 目标频道 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `GET /sessions/{channel_id}/pane`

#### capture.screenshot — 截取截图

```json
{"type": "capture.screenshot", "channel_id": "feishu:oc_chat1", "request_id": "req-008"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `channel_id` | **是** | 目标频道 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `GET /sessions/{channel_id}/screenshot`

#### verbose.set — 设置 Verbose 模式

```json
{"type": "verbose.set", "enabled": true, "request_id": "req-009"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `enabled` | **是** | `true` 启用详细模式 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `POST /sessions/{channel_id}/verbose`

#### wizard.browse — 浏览目录

```json
{"type": "wizard.browse", "path": "/home/user", "request_id": "req-010"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `path` | **是** | 目录路径 |
| `request_id` | 否 | 请求 ID |

**对应 REST**: `POST /directories/browse`

#### wizard.mkdir — 创建目录

```json
{"type": "wizard.mkdir", "name": "/tmp/new-dir", "request_id": "req-011"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | **是** | 目录名称（绝对或相对路径） |
| `request_id` | 否 | 请求 ID |

#### ping — 心跳

```json
{"type": "ping", "request_id": "req-012"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `request_id` | 否 | 请求 ID |

服务器返回 `{"type": "pong", "request_id": "req-012"}`。

---

### 服务器 → 客户端消息

#### session.created — 会话已创建

```json
{
  "type": "session.created",
  "request_id": "req-001",
  "channel_id": "feishu:oc_chat1",
  "window_id": "@1",
  "provider": "claude",
  "mode": "normal",
  "cwd": "/tmp/project",
  "display_name": "my-session"
}
```

#### session.list — 会话列表

```json
{
  "type": "session.list",
  "request_id": "req-002",
  "sessions": [...]
}
```

`sessions` 数组中每个对象包含: `window_id`, `display_name`, `provider`, `cwd`, `session_id`, `channel_id`（若有）。

#### session.closed — 会话已关闭

```json
{"type": "session.closed", "channel_id": "feishu:oc_chat1", "request_id": "req-003"}
```

#### agent.message — Agent 输出

由网关推送，当 Agent 有新输出时发送。

```json
{
  "type": "agent.message",
  "channel_id": "feishu:oc_chat1",
  "session_id": "abc-123",
  "messages": [
    {
      "text": "Hello! I'll help you...",
      "role": "assistant",
      "content_type": "text",
      "is_complete": true,
      "phase": null,
      "tool_use_id": null,
      "tool_name": null,
      "timestamp": null
    }
  ]
}
```

**AgentMessage 字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 消息文本 |
| `role` | string | `"user"` 或 `"assistant"` |
| `content_type` | string | `"text"`, `"thinking"`, `"tool_use"`, `"tool_result"`, `"local_command"` |
| `is_complete` | boolean | 消息是否完整 |
| `phase` | string\|null | Agent 阶段（如 `"planning"`） |
| `tool_use_id` | string\|null | 工具调用 ID |
| `tool_name` | string\|null | 工具名称 |
| `timestamp` | string\|null | 时间戳 |

#### agent.status — Agent 状态变更

```json
{
  "type": "agent.status",
  "channel_id": "feishu:oc_chat1",
  "session_id": "abc-123",
  "status": "working",
  "display_label": "Thinking...",
  "provider": "claude",
  "interactive": false,
  "prompt_state": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `channel_id` | string | 频道 ID |
| `session_id` | string | 会话 ID |
| `status` | string | `"idle"` \| `"working"` \| `"interactive"` \| `"done"` \| `"dead"` |
| `display_label` | string | 人类可读的当前状态描述 |
| `provider` | string | Provider 名称 |
| `interactive` | boolean | 是否处于交互模式 |
| `prompt_state` | object\|null | 交互提示详情（当 `interactive=true` 时） |

#### window.change — 窗口事件

**全局广播**（所有全局订阅者均会收到，无 `channel_id` 字段）:

```json
{
  "type": "window.change",
  "window_id": "@2",
  "change_type": "new",
  "provider": "claude",
  "cwd": "/tmp/project2",
  "display_name": "project2"
}
```

`change_type` 值: `"new"`（新创建）| `"removed"`（被移除）| `"died"`（异常退出）

#### hook.event — Hook 事件

**全局广播**，由 Claude Code Hook 触发:

```json
{
  "type": "hook.event",
  "window_id": "@1",
  "event_type": "SessionStart",
  "session_id": "abc-123",
  "data": {
    "cwd": "/tmp/project",
    "transcript_path": "/home/user/.claude/transcripts/..."
  }
}
```

#### capture.pane — 窗格捕获结果

```json
{
  "type": "capture.pane",
  "request_id": "req-007",
  "channel_id": "feishu:oc_chat1",
  "content": "user@host:~$ "
}
```

#### capture.screenshot — 截图结果

```json
{
  "type": "capture.screenshot",
  "request_id": "req-008",
  "channel_id": "feishu:oc_chat1",
  "image_base64": "iVBORw0KGgoAAAANS..."
}
```

`screenshot` 为 **base64 编码**的 PNG 数据，不是原始字节。

#### wizard.browse — 目录浏览结果

```json
{
  "type": "wizard.browse",
  "request_id": "req-010",
  "path": "/home/user",
  "directories": ["Documents", "Downloads"],
  "parent": "/home"
}
```

#### wizard.mkdir — 目录创建结果

```json
{"type": "wizard.mkdir", "request_id": "req-011", "path": "/tmp/new-dir"}
```

#### verbose.updated — Verbose 模式已更新

```json
{"type": "verbose.updated", "request_id": "req-009", "enabled": true}
```

#### error — 错误

```json
{"type": "error", "request_id": "req-007", "message": "No session for channel feishu:oc_chat1"}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 关联的请求 ID（若有） |
| `message` | string | 人类可读的错误描述 |

#### pong — 心跳响应

```json
{"type": "pong", "request_id": "req-012"}
```

---

## Event Types（网关事件）

网关对外暴露四种事件类型，通过 `gateway.on_*()` 注册回调，或通过 WebSocket 实时接收。

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
    status: str       # "idle" | "working" | "interactive" | "done" | "dead"
    display_label: str
    channel_ids: list[str]
    provider: str = ""
```

### HookEvent

```python
@dataclass
class HookEvent:
    window_id: str
    event_type: str   # 见下表
    session_id: str
    data: dict[str, Any]
```

### WindowChangeEvent

```python
@dataclass
class WindowChangeEvent:
    window_id: str
    change_type: str  # "new" | "removed" | "died"
    provider: str
    cwd: str
    display_name: str = ""
```

---

### Hook 事件类型（Claude Code）

以下事件由 Claude Code Hook 写入 `~/.unified-icc/events.jsonl`，由 SessionMonitor 读取后通过 `HookEvent` 转发:

| 事件类型 | 触发时机 | 主要 data 字段 |
|---------|---------|--------------|
| `SessionStart` | 新会话启动 | `cwd`, `transcript_path`, `window_name` |
| `Notification` | Agent 发送通知 | `tool_name`, `message` |
| `Stop` | Agent 停止 | `stop_reason`, `num_turns` |
| `StopFailure` | Agent 停止失败 | `error`, `error_details` |
| `SessionEnd` | 会话结束 | `reason` |
| `SubagentStart` | 子 Agent 启动 | `subagent_id`, `name`, `description` |
| `SubagentStop` | 子 Agent 退出 | `subagent_id`, `name`, `description` |
| `TeammateIdle` | 队友进入空闲 | `teammate_name`, `team_name` |
| `TaskCompleted` | 任务完成 | `task_id`, `task_subject`, `task_description` |

---

## Error Codes

### HTTP 状态码

| 状态码 | 含义 | 常见原因 |
|--------|------|---------|
| `200` | OK | 操作成功 |
| `400` | Bad Request | 无效的 provider、不存在的目录、JSON 格式错误 |
| `401` | Unauthorized | `ICC_API_KEY` 已设置但请求未提供或值错误 |
| `403` | Forbidden | 目录权限不足 |
| `404` | Not Found | 频道未绑定到任何会话 |
| `422` | Validation Error | 请求体不符合 Pydantic 模型（字段缺失或类型错误）|
| `503` | Service Unavailable | 网关尚未初始化（服务器启动中）|

### WebSocket 错误消息

服务器在 `error` 消息的 `message` 字段中返回详细描述:

| 消息 | 含义 |
|------|------|
| `Invalid JSON: <detail>` | JSON 解析失败 |
| `Unknown message type: <type>` | `type` 字段值不识别 |
| `Unknown provider: <name>` | Provider 名称无效 |
| `No session for channel <id>` | 频道未绑定到会话 |
| `channel_id required` | 缺少必填字段 |
| `Gateway not initialized` | 服务器启动中 |
| `Invalid or missing API key` | Token 无效或缺失 |
| `Not a directory: <path>` | 路径不是目录 |
| `Permission denied: <path>` | 权限不足 |
| `Failed to create directory: <err>` | 创建目录失败 |

---

## CLI Reference

`unified-icc server` 命令管理 API 服务器生命周期。

```bash
unified-icc server start [--host HOST] [--port PORT] [-d/--detach]
unified-icc server stop
unified-icc server status
```

### start

```
unified-icc server start --host 0.0.0.0 --port 8900 --detach
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 绑定地址 |
| `--port`, `-p` | `8900` | 绑定端口 |
| `--detach`, `-d` | `false` | 后台运行 |

`--detach` 时服务器 fork 到后台运行，PID 写入 `~/.unified-icc/server.pid`。

### stop

```
unified-icc server stop
```

发送 `SIGTERM`，若 5 秒内未退出则发送 `SIGKILL`。删除 PID 文件。

### status

```
unified-icc server status
```

输出示例:

```
API Server Status
=================
  Status    running
  PID       12345
  PID file  /home/user/.unified-icc/server.pid
```

---

## Configuration Reference

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ICC_API_HOST` | `0.0.0.0` | API 服务器绑定地址 |
| `ICC_API_PORT` | `8900` | API 服务器绑定端口 |
| `ICC_API_KEY` | `""` | API 认证密钥（空=禁用认证）|
| `TMUX_SESSION_NAME` | `unified-icc` | tmux 会话名称 |
| `MONITOR_POLL_INTERVAL` | `1.0` | Transcript 轮询间隔（秒）|
| `CCLARK_STATUS_POLL_INTERVAL` | `1.0` | 状态轮询间隔（秒）|
| `AUTOCLOSE_DONE_MINUTES` | `30` | 任务完成后自动关闭（分钟）|
| `AUTOCLOSE_DEAD_MINUTES` | `10` | 异常退出后自动关闭（分钟）|
| `CLAUDE_CONFIG_DIR` | `~/.claude` | Claude 配置目录 |
| `UNIFIED_ICC_DIR` | `~/.unified-icc` | 状态文件目录 |

### 状态文件

`~/.unified-icc/` 下的持久化文件:

| 文件 | 说明 |
|------|------|
| `state.json` | channel↔window 绑定关系 |
| `session_map.json` | window_key→session_id 映射 |
| `monitor_state.json` | transcript 文件轮询偏移量 |
| `events.jsonl` | append-only Hook 事件日志 |
| `server.pid` | 运行时 PID（仅服务器运行中存在）|

---

## 认证

设置 `ICC_API_KEY` 环境变量启用认证:

```bash
export ICC_API_KEY=sk-your-secret-key
unified-icc server start
```

**REST**: 在请求头中传递:
```bash
curl http://localhost:8900/api/v1/sessions \
  -H "Authorization: Bearer sk-your-secret-key"
```

**WebSocket**: 在 URL 查询参数中传递:
```javascript
const ws = new WebSocket('ws://localhost:8900/api/v1/ws?token=sk-your-secret-key');
```

**关闭认证**: 不设置 `ICC_API_KEY`（或设为空），所有端点均可匿名访问（**生产环境不推荐**）。

---

## 下一步

- [架构文档](architecture.md) — 系统组件与交互流程
- [Providers](providers.md) — 各 AI 助手的对比与能力
- [故障排除](troubleshooting.md) — 常见问题与解决方案
- [扩展指南](extending.md) — 添加自定义 Provider 或前端适配器
