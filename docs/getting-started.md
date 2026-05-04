# 快速上手

## 安装

```bash
git clone https://github.com/Agony5757/unified-icc.git
cd unified-icc
uv sync --extra server
```

> `--extra server` 安装 FastAPI 和 uvicorn，用于 API Server 模式。

## 配置

创建 `~/.unified-icc/config.yaml`：

```yaml
# 状态目录（默认 ~/.unified-icc）
state_dir: "~/.unified-icc"

# 默认 Provider（默认 claude）
default_provider: "claude"

# tmux 会话名（默认 cclark）
tmux_session: "cclark"

# API Server 配置
api_host: "0.0.0.0"
api_port: 8900
# api_key: "your-secret-key"  # 可选，设置后启用认证
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UNIFIED_ICC_DIR` | `~/.unified-icc` | 状态目录 |
| `CCLARK_PROVIDER` | `claude` | 默认 Provider |
| `TMUX_SESSION_NAME` | `cclark` | tmux 会话名 |
| `ICC_API_HOST` | `0.0.0.0` | API 监听地址 |
| `ICC_API_PORT` | `8900` | API 端口 |
| `ICC_API_KEY` | - | API 认证密钥 |

## 启动

### 方式一：API Server（推荐）

启动 HTTP + WebSocket API Server：

```bash
# 前台运行
unified-icc server start --port 8900

# 后台运行
unified-icc server start --port 8900 --detach

# 查看状态
unified-icc server status

# 停止
unified-icc server stop
```

### 方式二：程序化

```python
import asyncio
from unified_icc import UnifiedICC

async def main():
    gateway = UnifiedICC()
    await gateway.start()

    # 创建 Claude Code 会话
    window = await gateway.create_window(
        "/tmp/project",
        provider="claude",
        mode="standard"  # 或 "yolo"
    )

    # 绑定 channel
    gateway.bind_channel("feishu:oc_chat123", window.window_id)

    # 发送消息
    await gateway.send_to_window(window.window_id, "Hello!")

    await asyncio.sleep(60)
    await gateway.stop()

asyncio.run(main())
```

## 快速验证

```bash
# 健康检查
curl http://localhost:8900/health

# 创建会话
curl -X POST http://localhost:8900/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "test", "work_dir": "/tmp", "provider": "claude", "mode": "standard"}'

# 查看会话列表
curl http://localhost:8900/api/v1/sessions

# 发送输入
curl -X POST http://localhost:8900/api/v1/sessions/test/input \
  -H "Content-Type: application/json" \
  -d '{"text": "hello"}'

# 关闭会话
curl -X DELETE http://localhost:8900/api/v1/sessions/test
```

## 下一步

- [架构介绍](architecture.md) — 了解核心组件和数据流
- [Provider 系统](providers.md) — 选择合适的 Agent
- [API 参考](api.md) — 完整的 REST + WebSocket 文档
