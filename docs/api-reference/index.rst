API Reference
=============

Core Classes
------------

.. toctree::
   :maxdepth: 1

   gateway
   adapter
   events
   channel-router

Public API
----------

The ``unified_icc`` package exports the following public API:

.. code-block:: python

   from unified_icc import (
       # Main gateway
       UnifiedICC,
       WindowInfo,

       # Adapter protocol
       FrontendAdapter,
       CardPayload,
       InteractivePrompt,

       # Events
       AgentMessageEvent,
       StatusEvent,
       HookEvent,
       WindowChangeEvent,

       # Configuration
       GatewayConfig,
       config,

       # Channel routing (singleton)
       channel_router,
   )

Module Index
------------

**Gateway**

* ``gateway`` - UnifiedICC main class
* ``config`` - GatewayConfig
* ``channel_router`` - ChannelRouter singleton

**Events**

* ``event_types`` - AgentMessageEvent, StatusEvent, HookEvent, WindowChangeEvent
* ``adapter`` - FrontendAdapter protocol, CardPayload, InteractivePrompt
* ``monitor_events`` - Internal event types (NewMessage, NewWindowEvent)

**Session Management**

* ``session`` - SessionManager
* ``session_monitor`` - SessionMonitor poll loop
* ``session_lifecycle`` - Session map diffing
* ``session_map`` - Session map I/O
* ``idle_tracker`` - Per-session idle timers

**State**

* ``state_persistence`` - Debounced JSON persistence
* ``window_state_store`` - Window state tracking
* ``monitor_state`` - Poll loop offsets

**I/O**

* ``tmux_manager`` - tmux operations
* ``transcript_reader`` - Transcript I/O
* ``transcript_parser`` - Transcript -> messages
* ``terminal_parser`` - Terminal UI detection
* ``event_reader`` - events.jsonl reading
* ``window_view`` - Window snapshots
* ``window_resolver`` - Window ID remapping

**Hooks**

* ``hook`` - Claude hook events

**Utilities**

* ``utils`` - Utility functions
* ``mailbox`` - Agent-to-agent messages
* ``cc_commands`` - Claude command discovery
* ``expandable_quote`` - Expandable text blocks
* ``topic_state_registry`` - Topic state
* ``claude_task_state`` - Claude task tracking

**Providers**

* ``providers`` - Provider registry and helpers
* ``providers.base`` - AgentProvider protocol
* ``providers.registry`` - ProviderRegistry
* ``providers.claude`` - Claude provider
* ``providers.codex`` - Codex provider
* ``providers.gemini`` - Gemini provider
* ``providers.pi`` - Pi provider
* ``providers.shell`` - Shell provider

Call Stacks
-----------

For detailed function call chains, see :doc:`call-stacks`.
