# 故障排除

## 常见问题

### Server 启动失败

**问题**：`Address already in use`

**解决**：
1. 检查是否有其他进程占用端口
   ```bash
   lsof -i :8900
   ```
2. 或使用其他端口
   ```bash
   unified-icc server start --port 8901
   ```

### 无法创建 tmux 窗口

**问题**：`tmux: need IPv6`

**解决**：确保 tmux 已安装并可用
```bash
tmux -V
```

### Session 创建超时

**问题**：创建会话后窗口为空

**解决**：
1. 检查 Agent 是否已安装（`claude --version`, `codex --version`）
2. 检查工作目录是否存在
3. 查看 server 日志

### 认证失败

**问题**：`401 Unauthorized`

**解决**：
1. 确认设置了 `ICC_API_KEY` 环境变量
2. 请求中是否包含正确的 Bearer token
3. WebSocket 是否携带了 `?token=...` 参数

### Channel 绑定失败

**问题**：`Channel already bound`

**解决**：
```python
# 先解绑旧的
gateway.kill_channel_windows(channel_id)
# 再创建新的
window = await gateway.create_window(...)
```

## 日志

### 查看日志

```bash
# 如果前台运行，日志直接输出到 stdout

# 如果后台运行
journalctl -u unified-icc
```

### 调试模式

```bash
export RUST_LOG=debug
unified-icc server start
```

## 状态清理

### 重置状态

```bash
# 停止所有服务
unified-icc server stop

# 删除状态文件（谨慎！）
rm -rf ~/.unified-icc/state.json
rm -rf ~/.unified-icc/session_map.json

# 重启服务
unified-icc server start --port 8900
```

### 清理孤儿窗口

```bash
# 列出所有窗口
tmux list-windows -t cclark

# 杀死特定窗口
tmux kill-window -t cclark:2
```

## 性能问题

### 轮询延迟

SessionMonitor 默认 1 秒轮询间隔。可通过配置调整：

```yaml
# ~/.unified-icc/config.yaml
monitor_poll_interval: 0.5  # 秒
```

### 内存占用

长时间运行后，events.jsonl 可能很大。定期清理：

```bash
truncate -s 0 ~/.unified-icc/events.jsonl
```

## 寻求帮助

- 查看 [GitHub Issues](https://github.com/Agony5757/unified-icc/issues)
