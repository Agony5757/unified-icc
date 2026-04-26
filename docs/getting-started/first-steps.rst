第一步
=========

本指南将引导你构建一个简单的消息前端适配器。

构建自定义前端适配器
--------------------

第一步：实现 FrontendAdapter 协议
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc import FrontendAdapter, CardPayload, InteractivePrompt
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from your_messaging_sdk import MessagingClient

   class MyPlatformAdapter(FrontendAdapter):
       def __init__(self, client: "MessagingClient"):
           self.client = client

       async def send_text(self, channel_id: str, text: str) -> str:
           return await self.client.send_message(channel_id, text)

       async def send_card(self, channel_id: str, card: CardPayload) -> str:
           formatted = self._format_card(card)
           return await self.client.send_card(channel_id, formatted)

       async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None:
           formatted = self._format_card(card)
           await self.client.update_message(channel_id, card_id, formatted)

       async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str:
           return await self.client.upload_image(channel_id, image_bytes, caption)

       async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str:
           return await self.client.upload_file(channel_id, file_path, caption)

       async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str:
           buttons = [opt["text"] for opt in prompt.options]
           return await self.client.send_buttons(channel_id, prompt.title, buttons)

       def _format_card(self, card: CardPayload) -> dict:
           # 将 CardPayload 转换为平台特定的卡片格式
           return {
               "title": card.title,
               "body": card.body,
               "fields": card.fields,
               "actions": card.actions,
               "color": card.color,
           }

第二步：连接事件处理器
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import asyncio
   from unified_icc import UnifiedICC

   async def main():
       gateway = UnifiedICC()
       await gateway.start()

       adapter = MyPlatformAdapter(messaging_client)

       # 将助手消息路由到前端
       def on_agent_message(event):
           # event.messages 包含解析后的 AgentMessage 对象
           for msg in event.messages:
               if msg.role == "assistant":
                   # 发送为卡片以获得富文本格式
                   card = CardPayload(
                       title="Claude",
                       body=msg.text,
                       color="#007AFF"
                   )
                   for channel_id in event.channel_ids:
                       asyncio.create_task(adapter.send_card(channel_id, card))

       gateway.on_message(on_agent_message)

       # 路由状态变更
       def on_status_change(event):
           status_text = f"状态：{event.status}"
           for channel_id in event.channel_ids:
               asyncio.create_task(adapter.send_text(channel_id, status_text))

       gateway.on_status(on_status_change)

       # 路由窗口事件
       def on_window_event(event):
           text = f"新窗口：{event.display_name}"
           asyncio.create_task(adapter.send_text("admin_channel", text))

       gateway.on_window_change(on_window_event)

       # 保持运行
       await asyncio.Event().wait()

   asyncio.run(main())

第三步：处理收到的消息
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   async def handle_incoming_message(channel_id: str, text: str):
       # 解析该频道对应的窗口
       window_id = gateway.resolve_window(channel_id)
       if not window_id:
           await adapter.send_text(channel_id, "该频道没有活跃会话")
           return

       # 发送给助手
       await gateway.send_to_window(window_id, text)

   # 在你的 webhook 处理器中：
   async def webhook_handler(request):
       payload = await request.json()
       channel_id = payload["channel_id"]
       text = payload["text"]
       await handle_incoming_message(channel_id, text)
       return {"status": "ok"}

第四步：运行你的应用
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # 同时运行网关和你的 Web 服务器
   async def run():
       gateway = UnifiedICC()
       await gateway.start()

       # 在后台启动你的 Web 服务器
       server = MyWebServer(webhook_handler)
       await server.start()

       try:
           await asyncio.Event().wait()
       finally:
           await gateway.stop()

   asyncio.run(run())

完整示例：简单的 CLI 前端
-------------------------

.. code-block:: python

   """简单的 CLI 前端，从 stdin 读取并写入 stdout。"""
   import asyncio
   import sys
   from unified_icc import UnifiedICC, CardPayload

   async def cli_frontend():
       gateway = UnifiedICC()
       await gateway.start()

       # 创建一个用于 CLI 交互的窗口
       window = await gateway.create_window("/tmp", provider="claude")
       gateway.bind_channel("cli:stdin", window.window_id)

       def on_message(event):
           for msg in event.messages:
               if msg.text:
                   print(f"\n[助手] {msg.text}\n> ", end="", flush=True)

       gateway.on_message(on_message)

       # 从 stdin 读取
       async def read_stdin():
           loop = asyncio.get_event_loop()
           while True:
               line = await loop.run_in_executor(None, sys.stdin.readline)
               if not line:
                   break
               await gateway.send_to_window(window.window_id, line.rstrip())

       await asyncio.gather(read_stdin())

   if __name__ == "__main__":
       asyncio.run(cli_frontend())

下一步
------

- 查阅 `API 参考 <../api-reference/index.rst>`_ 了解所有可用方法
- 参见 `Provider <../providers/index.rst>`_ 文档了解 Provider 特定细节
- 查看 `配置 <../configuration.rst>`_ 了解环境变量
