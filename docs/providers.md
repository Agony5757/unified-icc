# Provider 系统

## 内置 Provider

| Provider | 命令 | 说明 |
|----------|------|------|
| `claude` | `claude --permission-mode default` | Anthropic Claude Code |
| `codex` | `codex` | OpenAI Codex CLI |
| `gemini` | `gemini` | Google Gemini CLI |
| `pi` | `pi` | Brevian Pi |
| `shell` | `bash` / `zsh` | 交互式 Shell |

## 能力对比

| 能力 | Claude | Codex | Gemini | Pi | Shell |
|------|--------|-------|--------|-----|-------|
| JSONL transcript | ✓ | ✓ | ✓ | ✓ | ✗ |
| 会话恢复 | ✓ | ✓ | ✓ | ✓ | ✗ |
| Plan mode | ✓ | ✓ | ✗ | ✗ | ✗ |
| Hook events | ✓ | ✗ | ✗ | ✗ | ✗ |
| Yolo mode | ✓ | ✗ | ✗ | ✗ | ✗ |
| 子任务跟踪 | ✓ | ✗ | ✗ | ✗ | ✗ |

## ProviderCapabilities

每个 Provider 声明其支持的功能：

```python
@dataclass
class ProviderCapabilities:
    supports_jsonl: bool           # 结构化 JSONL transcript
    supports_resume: bool          # /continue 和会话恢复
    supports_plan_mode: bool       # Plan mode 集成
    supports_hooks: bool           # Hook 事件
    supports_yolo: bool           # --dangerously-skip-permissions
    supports_idle_timeout: bool    # 空闲检测
    supports_subagent_tracking: bool # 子任务跟踪
```

## 会话发现

### Claude Code

Claude Code 通过 hook 写入 `session_map.json`：

```json
{
  "cclark:@0": {
    "session_id": "abc123",
    "transcript_path": "~/.claude/sessions/abc123/transcript.json",
    "cwd": "/home/user/project"
  }
}
```

`SessionLifecycle` 监听文件变化，检测新会话。

### Codex / Gemini / Pi

扫描各自的 sessions 目录：

- Codex: `~/.codex/sessions/`
- Gemini: `~/.gemini/chats/`
- Pi: `~/.pi/agent/sessions/`

按 `cwd` 匹配最新会话。

## 启动模式

### standard 模式

```python
# Claude
"claude --permission-mode default"

# 权限提示需要用户审批
```

### yolo 模式

```python
# Claude
"claude --dangerously-skip-permissions"

# 所有操作自动批准
```

## Plan Mode

Claude Code 的 Plan Mode 是一个两步流程：

```python
# 选项 1 或 2：直接提交
await gateway.send_to_window(window_id, "1", enter=True)

# 选项 3：先选 3，再发反馈
await gateway.send_to_window(window_id, "3", enter=False)
# 等待用户输入反馈
await gateway.send_to_window(window_id, feedback_text, enter=True)
```

## 添加自定义 Provider

1. 实现 `AgentProvider` 协议：

```python
from unified_icc.providers import AgentProvider, ProviderCapabilities, WindowInfo

class MyProvider(AgentProvider):
    name = "my-provider"
    capabilities = ProviderCapabilities(
        supports_jsonl=True,
        supports_resume=True,
        supports_plan_mode=False,
        supports_hooks=False,
        supports_yolo=False,
        supports_idle_timeout=True,
        supports_subagent_tracking=False,
    )

    def make_launch_args(self, cwd: str, mode: str, resume_id: str | None = None) -> list[str]:
        return ["my-cli", cwd]

    def parse_transcript(self, lines: list[str]) -> list[AgentMessage]:
        # 解析 transcript 行
        ...

    def extract_session_id(self, session_map: dict) -> str | None:
        ...
```

2. 注册到 ProviderRegistry：

```python
from unified_icc.providers import registry

registry.register(MyProvider())
```

## 下一步

- [API 参考](api.md) — 完整的 API 端点
- [可扩展性](extending.md) — 添加新 Frontend
