:orphan:

Gateway API Reference
=====================

UnifiedICC
----------

The main gateway class that orchestrates all subsystems.

.. code-block:: python

   from unified_icc import UnifiedICC

**Initialization:**

.. code-block:: python

   gateway = UnifiedICC(gateway_config=None)

* ``gateway_config`` (GatewayConfig | None): Optional custom configuration. If None, uses the global ``config`` singleton.

Lifecycle Methods
-----------------

start()
~~~~~~~

Start the gateway: connect to tmux, load state, begin monitoring.

.. code-block:: python

   await gateway.start()

**What happens:**

1. Ensures tmux session exists (``tmux_manager.ensure_session()``)
2. Loads persisted state from ``~/.cclark/state.json``
3. Wires together all singleton components
4. Starts the SessionMonitor poll loop

stop()
~~~~~~

Stop the gateway: flush state, stop monitoring.

.. code-block:: python

   await gateway.stop()

**What happens:**

1. Stops the SessionMonitor
2. Flushes any pending state writes
3. Logs final state

Window Management
-----------------

create_window()
~~~~~~~~~~~~~~~

Create a new tmux window running an agent.

.. code-block:: python

   window = await gateway.create_window(
       work_dir="/path/to/project",
       provider="claude",
       mode="normal",  # or "yolo" for approval bypass
   )
   print(window.window_id)  # e.g., "@1"
   print(window.provider)  # "claude"
   print(window.cwd)        # "/path/to/project"

**Parameters:**

* ``work_dir`` (str): Working directory for the new window
* ``provider`` (str): Agent provider name ("claude", "codex", "gemini", "pi", "shell")
* ``mode`` (str): Approval mode ("normal" or "yolo")

**Returns:** ``WindowInfo`` with window_id, display_name, provider, cwd

kill_window()
~~~~~~~~~~~~~

Kill a tmux window and clean up bindings.

.. code-block:: python

   await gateway.kill_window("@1")

**What happens:**

1. Unbinds all channels from the window
2. Removes window from state store
3. Kills the tmux window

list_windows()
~~~~~~~~~~~~~~

List all managed windows.

.. code-block:: python

   windows = await gateway.list_windows()
   for w in windows:
       print(f"{w.window_id}: {w.display_name} ({w.provider})")

**Returns:** List of ``WindowInfo`` objects

Message Dispatch
----------------

send_to_window()
~~~~~~~~~~~~~~~~

Send text input to a tmux window.

.. code-block:: python

   await gateway.send_to_window("@1", "Hello, Claude!")

**Parameters:**

* ``window_id`` (str): Target window
* ``text`` (str): Text to send (automatically appended with newline)

send_key()
~~~~~~~~~~

Send a special key to a tmux window.

.. code-block:: python

   await gateway.send_key("@1", "C-c")  # Ctrl+C
   await gateway.send_key("@1", "C-d")  # Ctrl+D

**Parameters:**

* ``window_id`` (str): Target window
* ``key`` (str): Key combination (format: "C-x" for Ctrl+x)

Output Capture
--------------

capture_pane()
~~~~~~~~~~~~~~

Capture the current pane content.

.. code-block:: python

   content = await gateway.capture_pane("@1")
   print(content)

**Returns:** String containing the pane's text content

capture_screenshot()
~~~~~~~~~~~~~~~~~~~~

Capture a screenshot of the pane as PNG bytes.

.. code-block:: python

   image_bytes = await gateway.capture_screenshot("@1")
   with open("screenshot.png", "wb") as f:
       f.write(image_bytes)

**Returns:** PNG image data as bytes

Event Subscription
------------------

on_message()
~~~~~~~~~~~~

Register a callback for agent messages.

.. code-block:: python

   def handle_message(event: AgentMessageEvent):
       for msg in event.messages:
           print(f"[{msg.role}] {msg.text}")

   gateway.on_message(handle_message)

**Parameters:**

* ``callback``: Function receiving ``AgentMessageEvent``

on_status()
~~~~~~~~~~~

Register a callback for status changes.

.. code-block:: python

   def handle_status(event: StatusEvent):
       print(f"Status: {event.status} ({event.display_label})")

   gateway.on_status(handle_status)

**Parameters:**

* ``callback``: Function receiving ``StatusEvent``

on_hook_event()
~~~~~~~~~~~~~~~

Register a callback for hook events.

.. code-block:: python

   def handle_hook(event: HookEvent):
       print(f"Hook: {event.event_type}")

   gateway.on_hook_event(handle_hook)

**Parameters:**

* ``callback``: Function receiving ``HookEvent``

on_window_change()
~~~~~~~~~~~~~~~~~~

Register a callback for window events.

.. code-block:: python

   def handle_window(event: WindowChangeEvent):
       print(f"Window {event.change_type}: {event.window_id}")

   gateway.on_window_change(handle_window)

**Parameters:**

* ``callback``: Function receiving ``WindowChangeEvent``

Channel Routing
---------------

bind_channel()
~~~~~~~~~~~~~~

Bind a channel to a window.

.. code-block:: python

   gateway.bind_channel("feishu:chat_123:thread_456", "@1")

**Parameters:**

* ``channel_id`` (str): Platform channel identifier
* ``window_id`` (str): tmux window identifier

**Note:** Only one window per channel, only one primary channel per window.

unbind_channel()
~~~~~~~~~~~~~~~~

Remove a channel binding.

.. code-block:: python

   gateway.unbind_channel("feishu:chat_123:thread_456")

resolve_window()
~~~~~~~~~~~~~~~~

Find the window for a channel.

.. code-block:: python

   window_id = gateway.resolve_window("feishu:chat_123:thread_456")
   if window_id:
       await gateway.send_to_window(window_id, "message")

**Returns:** Window ID or None if not bound

resolve_channels()
~~~~~~~~~~~~~~~~~~

Find all channels bound to a window.

.. code-block:: python

   channels = gateway.resolve_channels("@1")
   for channel in channels:
       await adapter.send_text(channel, "notification")

**Returns:** List of channel IDs

Provider Access
---------------

get_provider()
~~~~~~~~~~~~~~

Get the provider for a window.

.. code-block:: python

   provider = gateway.get_provider("@1")
   print(provider.capabilities.name)  # "claude"

**Returns:** Provider instance for the window's agent

WindowInfo
----------

Dataclass with window information.

.. code-block:: python

   from unified_icc import WindowInfo

**Attributes:**

* ``window_id`` (str): tmux window identifier
* ``display_name`` (str): Human-readable name
* ``provider`` (str): Agent provider name
* ``cwd`` (str): Working directory
* ``session_id`` (str): Agent session ID (if available)
