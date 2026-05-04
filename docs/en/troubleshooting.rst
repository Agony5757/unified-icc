:orphan:

Troubleshooting
===============

Common Issues
-------------

Gateway Won't Start
~~~~~~~~~~~~~~~~~~

**Symptom:** ``UnifiedICC().start()`` hangs or fails

**Possible causes:**

1. tmux not installed or not in PATH

   .. code-block:: bash

      tmux -V  # Should show version

2. tmux session already exists with different socket

   .. code-block:: bash

      tmux list-sessions  # Check existing sessions

3. Permission issues with state files

   .. code-block:: bash

      ls -la ~/.unified-icc/
      chmod 755 ~/.unified-icc/

**Solution:**

.. code-block:: python

   # Check tmux is available
   import subprocess
   result = subprocess.run(["tmux", "-V"], capture_output=True)
   print(result.stdout.decode())

   # Check state directory
   from unified_icc.utils import unified_icc_dir
   print(unified_icc_dir())  # Should exist and be writable


Messages Not Being Received
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``on_message`` callbacks never fire

**Possible causes:**

1. Channel not bound to window

   .. code-block:: python

      # Check bindings
      from unified_icc import channel_router
      print(channel_router.bound_channel_ids())
      print(channel_router.bound_window_ids())

2. Session monitor not running

   .. code-block:: python

      # Verify monitor is active
      from unified_icc.session_monitor import get_active_monitor
      monitor = get_active_monitor()
      print(monitor._running if monitor else "No monitor")

3. Transcript file not being read

   .. code-block:: python

      # Check transcript path
      from unified_icc.session_map import session_map_sync
      print(session_map_sync.current_map)

**Solution:**

.. code-block:: python

   # Manually verify transcript is readable
   import asyncio
   from unified_icc import config

   async def check_transcripts():
       if config.session_map_file.exists():
           import json, aiofiles
           async with aiofiles.open(config.session_map_file) as f:
               content = await f.read()
           data = json.loads(content)
           print("Session map:", data)

   asyncio.run(check_transcripts())


Agent Not Responding to Input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``send_to_window()`` completes but agent doesn't respond

**Possible causes:**

1. Text not reaching tmux pane

   .. code-block:: python

      # Verify pane exists and is writable
      await gateway.capture_pane(window_id)

2. Agent process is not in interactive mode

   .. code-block:: python

      # Check agent status
      status = await gateway.get_provider(window_id).parse_terminal_status(
          await gateway.capture_pane(window_id)
      )
      print(status)

3. tmux pane not attached to correct window

   .. code-block:: python

      # List all windows
      windows = await gateway.list_windows()
      for w in windows:
          print(f"{w.window_id}: {w.display_name}")

**Solution:**

.. code-block:: python

   # Debug send operation
   import asyncio

   async def debug_send(window_id, text):
       # First capture current state
       before = await gateway.capture_pane(window_id)
       print(f"Before:\n{before[-500:]}")

       # Send
       await gateway.send_to_window(window_id, text)

       # Wait briefly
       await asyncio.sleep(0.5)

       # Capture after state
       after = await gateway.capture_pane(window_id)
       print(f"After:\n{after[-500:]}")

   asyncio.run(debug_send("@1", "hello"))


State Not Persisting
~~~~~~~~~~~~~~~~~~~~

**Symptom:** Bindings disappear after restart

**Possible causes:**

1. State file not writable

   .. code-block:: bash

      ls -la ~/.unified-icc/state.json
      # If doesn't exist, check directory permissions

2. Persistence not scheduled

   .. code-block:: python

      # Check dirty flag
      from unified_icc import channel_router
      # StatePersistence uses debouncing, so changes take 0.5s to save

3. Race condition during shutdown

   .. code-block:: python

      # Always stop gracefully
      await gateway.stop()  # This flushes state

**Solution:**

.. code-block:: python

   # Manually trigger persistence
   from unified_icc.state_persistence import persistence_manager

   # Make a change
   channel_router.bind("test:1", "@1")

   # Force save
   if hasattr(persistence_manager, 'flush'):
       persistence_manager.flush()

   # Or wait for debounce
   import asyncio
   await asyncio.sleep(1.0)  # Debounce is 0.5s


Provider Not Detected
~~~~~~~~~~~~~~~~~~~~~

**Symptom:** Wrong provider detected, or no provider

**Possible causes:**

1. Provider binary not in PATH

   .. code-block:: bash

      which claude  # or codex, gemini, pi

2. Transcript path doesn't match patterns

   .. code-block:: python

      from unified_icc.providers import detect_provider_from_transcript_path

      # Test detection
      path = "~/.claude/projects/myproj/.claude/history/session.jsonl"
      provider = detect_provider_from_transcript_path(path)
      print(f"Detected: {provider}")

3. Pane title not set correctly

   .. code-block:: bash

      # Check tmux window title
      tmux display-message -t @1 -p '#{window_name}'

**Solution:**

.. code-block:: python

   # Explicitly specify provider when creating window
   window = await gateway.create_window(
       work_dir="/path",
       provider="claude"  # Explicit provider
   )

   # Or set default in environment
   import os
   os.environ["CCLARK_PROVIDER"] = "claude"


Hook Events Not Received
~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``on_hook_event`` callbacks never fire (Claude only)

**Possible causes:**

1. Hook not installed in Claude

   .. code-block:: bash

      # Check Claude config
      cat ~/.claude/settings.json | grep hook

2. events.jsonl not writable

   .. code-block:: bash

      ls -la ~/.unified-icc/events.jsonl

3. Hook module not loaded

   .. code-block:: python

      # Verify hook is installed
      from unified_icc import hook
      print(hook.__file__)

**Solution:**

.. code-block:: python

   # Install hook manually
   from unified_icc.hook import install_hooks

   # This writes hook files to ~/.claude/
   # Note: Requires Claude restart to take effect


Screenshot Capture Fails
~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom:** ``capture_screenshot()`` raises error

**Possible causes:**

1. ImageMagick not installed

   .. code-block:: bash

      convert --version  # or
      import subprocess; subprocess.run(["import", "-version"])

2. DISPLAY not set (for X11)

   .. code-block:: bash

      echo $DISPLAY  # Should be :0 or similar

3. tmux capture not working

   .. code-block:: python

      # Test basic capture
      content = await gateway.capture_pane(window_id)
      print(f"Capture works: {len(content)} chars")

**Solution:**

.. code-block:: python

   # Check dependencies
   import shutil
   print(f"ImageMagick: {shutil.which('import')}")
   print(f"DISPLAY: {import os; os.environ.get('DISPLAY')}")

   # Try capture with error handling
   try:
       image_bytes = await gateway.capture_screenshot(window_id)
   except Exception as e:
       print(f"Screenshot failed: {e}")
       # Fall back to text capture
       text = await gateway.capture_pane(window_id)


Debug Logging
-------------

Enable debug logging to trace issues:

.. code-block:: python

   import structlog
   import logging

   # Configure structlog
   structlog.configure(
       processors=[
           structlog.processors.TimeStamper(fmt="iso"),
           structlog.processors.add_log_level,
           structlog.dev.ConsoleRenderer(),
       ],
   )

   # Set log level
   logging.getLogger("unified_icc").setLevel(logging.DEBUG)

Or via environment:

.. code-block:: bash

   export LOG_LEVEL=DEBUG

Getting Help
------------

If you're still stuck:

1. Enable debug logging and capture relevant output
2. Check the `GitHub Issues <https://github.com/Agony5757/unified-icc/issues>`_
3. Include:

   - Python version (``python --version``)
   - tmux version (``tmux -V``)
   - Relevant logs
   - Minimal reproduction code
