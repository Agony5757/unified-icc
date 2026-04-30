:orphan:

Configuration Reference
======================

Unified ICC is configured entirely through environment variables (with ``.env`` file support). There are no required platform tokens or API keys in the core library.

Configuration Loading
----------------------

Configuration is loaded in this order (later sources override earlier):

1. Default values
2. ``~/.cclark/.env`` file
3. ``./.env`` file (current working directory)
4. Environment variables

Environment Variables
--------------------

Core Settings
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Variable
     - Default
     - Description
   * - ``CCLARK_CONFIG_DIR``
     - ``~/.cclark``
     - Configuration directory
   * - ``CCLARK_PROVIDER``
     - ``claude``
     - Default agent provider

Legacy equivalents: ``CCGRAM_CONFIG_DIR``, ``CCBOT_CONFIG_DIR``

Tmux Settings
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Variable
     - Default
     - Description
   * - ``TMUX_SESSION_NAME``
     - ``cclark``
     - tmux session name
   * - ``TMUX_EXTERNAL_PATTERNS``
     - (empty)
     - Patterns for external window discovery

Legacy equivalent: ``CCGRAM_TMUX_SESSION``

Monitoring Settings
~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Variable
     - Default
     - Description
   * - ``MONITOR_POLL_INTERVAL``
     - ``1.0``
     - Poll interval in seconds (min 0.5)
   * - ``CCLARK_STATUS_POLL_INTERVAL``
     - ``1.0``
     - Status poll interval in seconds

Legacy equivalent: ``CCGRAM_STATUS_POLL_INTERVAL``

Agent Settings
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Variable
     - Default
     - Description
   * - ``CLAUDE_CONFIG_DIR``
     - ``~/.claude``
     - Claude configuration directory
   * - ``AUTOCLOSE_DONE_MINUTES``
     - ``30``
     - Auto-close done sessions after N minutes
   * - ``AUTOCLOSE_DEAD_MINUTES``
     - ``10``
     - Auto-close dead sessions after N minutes

Provider Command Overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~

Override the launch command for each provider:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Format
   * - ``CCLARK_CLAUDE_COMMAND``
     - Override ``claude`` command
   * - ``CCLARK_CODEX_COMMAND``
     - Override ``codex`` command
   * - ``CCLARK_GEMINI_COMMAND``
     - Override ``gemini`` command
   * - ``CCLARK_PI_COMMAND``
     - Override ``pi`` command
   * - ``CCLARK_SHELL_COMMAND``
     - Override ``shell`` command

Legacy equivalents: ``CCGRAM_*``, ``CCBOT_*``

Example .env File
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Core settings
   CCLARK_CONFIG_DIR=~/.cclark
   CCLARK_PROVIDER=claude

   # Tmux
   TMUX_SESSION_NAME=cclark

   # Monitoring
   MONITOR_POLL_INTERVAL=1.0

   # Provider overrides
   CCLARK_CLAUDE_COMMAND=/usr/local/bin/claude

GatewayConfig Class
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc import GatewayConfig, config

   # Access the global config
   print(config.tmux_session_name)  # "cclark"
   print(config.provider_name)     # "claude"

   # Or create a custom config
   custom_config = GatewayConfig()
   custom_config.tmux_session_name = "my-session"

GatewayConfig Attributes
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 10 60

   * - Attribute
     - Type
     - Description
   * - ``config_dir``
     - ``Path``
     - Configuration directory
   * - ``tmux_session_name``
     - ``str``
     - tmux session name
   * - ``tmux_main_window_name``
     - ``str``
     - Main window name
   * - ``own_window_id``
     - ``str | None``
     - This gateway's window ID
   * - ``tmux_external_patterns``
     - ``str``
     - External window patterns
   * - ``state_file``
     - ``Path``
     - Main state file path
   * - ``session_map_file``
     - ``Path``
     - Session map file path
   * - ``monitor_state_file``
     - ``Path``
     - Monitor state file path
   * - ``events_file``
     - ``Path``
     - Hook events file path
   * - ``mailbox_dir``
     - ``Path``
     - Mailbox directory path
   * - ``claude_config_dir``
     - ``Path``
     - Claude config directory
   * - ``claude_projects_path``
     - ``Path``
     - Claude projects path
   * - ``monitor_poll_interval``
     - ``float``
     - Poll interval
   * - ``status_poll_interval``
     - ``float``
     - Status poll interval
   * - ``provider_name``
     - ``str``
     - Default provider
   * - ``autoclose_done_minutes``
     - ``int``
     - Auto-close delay for done
   * - ``autoclose_dead_minutes``
     - ``int``
     - Auto-close delay for dead

State Files
-----------

All state files are stored in ``~/.cclark/``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - File
     - Description
   * - ``state.json``
     - Gateway state (channels, windows, display names)
   * - ``session_map.json``
     - tmux window to agent session mappings
   * - ``monitor_state.json``
     - Poll loop offsets and tracked sessions
   * - ``events.jsonl``
     - Hook event log (append-only)

State File Format: state.json
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "channel_bindings": {
           "feishu:chat123:thread456": "@1"
       },
       "channel_meta": {
           "feishu:chat123:thread456": {
               "user_id": "U123456"
           }
       },
       "display_names": {
           "@1": "Claude Code"
       }
   }

State File Format: session_map.json
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "@1": {
           "session_id": "abc123",
           "transcript_path": "/home/user/.claude/projects/myproj/.claude/history/session_abc123.jsonl",
           "cwd": "/home/user/projects/myproj",
           "window_name": "claude",
           "provider_name": "claude"
       }
   }

Custom Configuration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from unified_icc import UnifiedICC, GatewayConfig
   import os

   # Option 1: Environment variables
   os.environ["TMUX_SESSION_NAME"] = "my-session"
   os.environ["MONITOR_POLL_INTERVAL"] = "0.5"
   gateway = UnifiedICC()

   # Option 2: Custom config object
   config = GatewayConfig()
   config.tmux_session_name = "my-session"
   config.monitor_poll_interval = 0.5
   config.state_file = Path("/tmp/my-state.json")
   gateway = UnifiedICC(gateway_config=config)

tmux Requirements
-----------------

Unified ICC requires:

- tmux version 2.6 or higher
- The ability to create new sessions/windows
- Access to the ``tmux`` command

tmux Socket
~~~~~~~~~~~

By default, unified-icc uses the default tmux socket. To use a custom socket:

.. code-block:: bash

   export TMUX_SOCKET_PATH=/tmp/my-tmux-socket

Window Naming
~~~~~~~~~~~~~

Windows are named automatically. To customize:

.. code-block:: python

   # In your frontend, set display names
   from unified_icc import channel_router
   channel_router.set_display_name(window_id, "My Project")

Provider-Specific Configuration
-------------------------------

Claude
~~~~~~

Claude Code is auto-detected if ``claude`` is in your PATH. To use a specific version:

.. code-block:: bash

   export CCLARK_CLAUDE_COMMAND=/path/to/claude

Codex
~~~~~

.. code-block:: bash

   export CCLARK_CODEX_COMMAND=/path/to/codex

Gemini
~~~~~~

.. code-block:: bash

   export CCLARK_GEMINI_COMMAND=/path/to/gemini
