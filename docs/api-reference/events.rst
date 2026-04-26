Event Types Reference
=====================

All events emitted by the gateway to frontend adapters.

.. code-block:: python

   from unified_icc import AgentMessageEvent, StatusEvent, HookEvent, WindowChangeEvent

AgentMessageEvent
-----------------

Emitted when the agent produces new output (assistant messages, tool results, etc.).

.. code-block:: python

   @dataclass
   class AgentMessageEvent:
       window_id: str
       session_id: str
       messages: list[AgentMessage]
       channel_ids: list[str] = field(default_factory=list)

**Attributes:**

* ``window_id`` (str): tmux window that produced the message
* ``session_id`` (str): Agent session ID
* ``messages`` (list[AgentMessage]): Parsed messages from the transcript
* ``channel_ids`` (list[str]): Channels bound to this window

AgentMessage
~~~~~~~~~~~~

Individual message within an event.

.. code-block:: python

   @dataclass(frozen=True, slots=True)
   class AgentMessage:
       text: str
       role: MessageRole  # "user" | "assistant"
       content_type: ContentType  # "text" | "thinking" | "tool_use" | "tool_result" | "local_command"
       is_complete: bool = True
       phase: str | None = None
       tool_use_id: str | None = None
       tool_name: str | None = None
       timestamp: str | None = None

**Content Types:**

* **text** - Regular text output
* **thinking** - Claude's thinking/reasoning output
* **tool_use** - Tool invocation (with tool_name, tool_use_id)
* **tool_result** - Tool execution result
* **local_command** - CLI commands like /help, /clear

**Example:**

.. code-block:: python

   def on_message(event: AgentMessageEvent):
       for msg in event.messages:
           if msg.content_type == "tool_use":
               print(f"Running tool: {msg.tool_name}")
           elif msg.content_type == "text":
               print(f"Agent: {msg.text}")

StatusEvent
-----------

Emitted when agent status changes.

.. code-block:: python

   @dataclass
   class StatusEvent:
       window_id: str
       session_id: str
       status: str  # "working" | "idle" | "done" | "dead" | "interactive"
       display_label: str
       channel_ids: list[str] = field(default_factory=list)

**Status Values:**

* **working** - Agent is actively processing
* **idle** - Agent is waiting for input
* **done** - Task completed successfully
* **dead** - Agent process died/crashed
* **interactive** - Agent is waiting for user confirmation (permission prompt)

**Example:**

.. code-block:: python

   def on_status(event: StatusEvent):
       status_emoji = {
           "working": "working",
           "idle": "idle",
           "done": "done",
           "dead": "dead",
           "interactive": "interactive",
       }
       emoji = status_emoji.get(event.status, "?")
       print(f"{emoji} {event.display_label}: {event.status}")

HookEvent
---------

Forwarded hook event from the agent's hook system.

.. code-block:: python

   @dataclass
   class HookEvent:
       window_id: str
       event_type: str
       session_id: str
       data: dict[str, Any]

**Common Event Types:**

* **SessionStart** - New agent session started
* **Notification** - Agent wants to show a notification
* **Stop** - Agent stopped
* **Task** - Task state update

**Example:**

.. code-block:: python

   def on_hook(event: HookEvent):
       if event.event_type == "SessionStart":
           print(f"New session: {event.session_id}")
       elif event.event_type == "Notification":
           print(f"Notification: {event.data.get('message')}")

WindowChangeEvent
-----------------

Emitted when a window is created, removed, or dies.

.. code-block:: python

   @dataclass
   class WindowChangeEvent:
       window_id: str
       change_type: str  # "new" | "removed" | "died"
       provider: str
       cwd: str
       display_name: str = ""

**Change Types:**

* **new** - New window created
* **removed** - Window explicitly removed
* **died** - Window process crashed

**Example:**

.. code-block:: python

   def on_window_change(event: WindowChangeEvent):
       if event.change_type == "new":
           print(f"New window: {event.window_id} ({event.provider})")
           # Bind to channel
           gateway.bind_channel("my_channel", event.window_id)

Internal Event Types
--------------------

These are used internally by the monitoring subsystem:

.. code-block:: python

   from unified_icc.monitor_events import NewMessage, NewWindowEvent, SessionInfo

* **NewMessage** - Internal message representation from transcript reader
* **NewWindowEvent** - Internal window event from session lifecycle
* **SessionInfo** - Session information from projects scan
