# 可扩展性

## 添加新 Provider

### 1. 实现 AgentProvider 协议

```python
# my_provider.py
from dataclasses import dataclass
from unified_icc.providers import AgentProvider, ProviderCapabilities, WindowInfo
from unified_icc.event_types import AgentMessage

@dataclass
class MyAgentMessage:
    text: str
    content_type: str  # "text", "thinking", "tool_use", "tool_result"
    is_complete: bool

class MyProvider(AgentProvider):
    name = "my-agent"
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
        cmd = ["my-agent", cwd]
        if resume_id:
            cmd.insert(1, f"resume {resume_id}")
        return cmd

    def parse_transcript(self, lines: list[str]) -> list[AgentMessage]:
        messages = []
        for line in lines:
            msg = AgentMessage(
                text=line,
                content_type="text",
                is_complete=True
            )
            messages.append(msg)
        return messages

    def extract_session_id(self, session_map: dict) -> str | None:
        # 从 session_map 中提取 session_id
        return None
```

### 2. 注册 Provider

```python
from unified_icc.providers import registry
from my_provider import MyProvider

registry.register(MyProvider())
```

### 3. 使用新 Provider

```python
window = await gateway.create_window(
    "/path/to/project",
    provider="my-agent",
    mode="standard"
)
```

## 添加新 Frontend

### 1. 实现 FrontendAdapter

```python
# my_adapter.py
from unified_icc.adapter import FrontendAdapter, CardPayload, Button, InteractivePrompt

class MyAdapter(FrontendAdapter):
    async def send_text(self, channel_id: str, text: str) -> str:
        # 发送到你的平台
        message_id = await my_platform.send_message(channel_id, text)
        return message_id

    async def send_card(self, channel_id: str, card: CardPayload) -> str:
        # 发送交互卡片
        card_id = await my_platform.send_card(channel_id, card)
        return card_id

    async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
        # 更新卡片
        await my_platform.update_card(card_id, card)

    async def send_image(self, channel_id: str, image_bytes: bytes, caption: str) -> str:
        ...

    async def send_file(self, channel_id: str, file_path: str, caption: str) -> str:
        ...

    async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
        # 显示权限/计划提示
        card = CardPayload(
            title=prompt.title,
            content=prompt.description,
            buttons=[[Button(id=str(i), label=opt) for i, opt in enumerate(prompt.options)]]
        )
        return await self.send_card(channel_id, card)

    def register_message_handler(self, handler):
        # 注册接收消息的回调
        my_platform.on_message(handler)

    def register_callback_handler(self, handler):
        # 注册按钮点击回调
        my_platform.on_callback(handler)
```

### 2. 连接到 Gateway

```python
from unified_icc import UnifiedICC
from my_adapter import MyAdapter

gateway = UnifiedICC()
gateway._adapter = MyAdapter()
await gateway.start()
```

## CardPayload 结构

```python
@dataclass
class CardPayload:
    title: str = ""           # 卡片标题
    content: str = ""         # Markdown 格式正文
    buttons: list[list[Button]] = []  # 按钮行
    footer: str = ""          # 底部说明
    color: str = ""           # 强调色 (#RRGGBB)
```

## InteractivePrompt 类型

```python
@dataclass
class InteractivePrompt:
    prompt_type: str   # "ask_user" | "permission" | "plan_mode" | "approval"
    title: str
    description: str
    options: list[str] = []    # ask_user 选项列表
    detail: str = ""           # permission 详情
    plan_text: str = ""        # plan_mode 计划文本
```

## WebSocket 扩展

API Server 支持通过 WebSocket 实时接收事件：

```javascript
const ws = new WebSocket('ws://localhost:8900/api/v1/ws/my-channel');

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'agent.message') {
        for (const m of msg.messages) {
            console.log(`[${m.content_type}] ${m.text}`);
        }
    }
};

// 发送消息
ws.send(JSON.stringify({
    type: 'input',
    channel_id: 'my-channel',
    text: 'hello',
    enter: true
}));
```

## 下一步

- [API 参考](api.md) — 完整的 REST + WebSocket 端点
