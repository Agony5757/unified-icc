Architecture Overview
======================

Unified ICC is designed as a layered architecture with clear separation between the messaging frontend, the gateway core, and the agent execution substrate (tmux).

System Layers
-------------

**Layer 1: Messaging Frontend (External)**

The messaging frontend (Feishu, Telegram, Discord, etc.) is **not part of unified-icc**. Each frontend implements the ``FrontendAdapter`` protocol to communicate with the gateway.

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────┐
   │                     Frontend (e.g., cclark)                 │
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ Webhook     │  │ Feishu      │  │ FeishuAdapter       ││
   │  │ Server      │  │ API Client  │  │ (FrontendAdapter)   ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   └────────────────────────────┬────────────────────────────────┘
                                │ FrontendAdapter API
                                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    unified_icc Gateway                     │
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ UnifiedICC  │  │ChannelRouter│  │ Event System        ││
   │  │ (Main API)  │  │             │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ Session     │  │ TmuxManager │  │ SessionMonitor      ││
   │  │ Manager     │  │             │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
   │  │ State       │  │ WindowState │  │ ProviderRegistry    ││
   │  │ Persistence │  │ Store       │  │                     ││
   │  └─────────────┘  └─────────────┘  └─────────────────────┘│
   └────────────────────────────┬────────────────────────────────┘
                                │
                                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                       tmux Session                          │
   │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────┐│
   │  │ @0        │  │ @1        │  │ @2        │  │ @main   ││
   │  │ (claude)  │  │ (codex)    │  │ (gemini)  │  │         ││
   │  └───────────┘  └───────────┘  └───────────┘  └─────────┘│
   └─────────────────────────────────────────────────────────────┘

Component Responsibilities
--------------------------

**UnifiedICC (gateway.py)**

The main public API class. Orchestrates all subsystems:

* **Lifecycle**: ``start()`` / ``stop()`` — initializes connections, loads state, starts monitoring
* **Window management**: ``create_window()``, ``kill_window()``, ``list_windows()``
* **Message dispatch**: ``send_to_window()``, ``send_key()``
* **Output capture**: ``capture_pane()``, ``capture_screenshot()``
* **Channel routing**: ``bind_channel()``, ``unbind_channel()``, ``resolve_window()``
* **Event subscription**: ``on_message()``, ``on_status()``, ``on_hook_event()``, ``on_window_change()``

**ChannelRouter (channel_router.py)**

Platform-agnostic bidirectional mapping between channels and windows:

* **bind()**: Associate a channel_id with a window_id
* **resolve_window()**: Find window for a channel
* **resolve_channels()**: Find all channels for a window
* **Serialization**: ``to_dict()`` / ``from_dict()`` for state persistence

Channel ID format: ``"platform:identifier:sub_identifier"`` (e.g., ``"feishu:chat_123:thread_456"``)

**SessionMonitor (session_monitor.py)**

Async poll loop that monitors all agent sessions:

1. Reads hook events from ``events.jsonl``
2. Reconciles session_map changes
3. Reads transcript updates via TranscriptReader
4. Emits callbacks: NewMessage, NewWindowEvent, HookEvent

**TmuxManager (tmux_manager.py)**

Wraps libtmux for low-level tmux operations:

* Window creation/destruction
* Pane capture (text and screenshot)
* Key/input sending
* External session discovery

**FrontendAdapter Protocol (adapter.py)**

Contract for frontend implementations:

.. code-block:: python

   class FrontendAdapter(Protocol):
       async def send_text(self, channel_id: str, text: str) -> str
       async def send_card(self, channel_id: str, card: CardPayload) -> str
       async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None
       async def send_image(self, channel_id: str, image_bytes: bytes, caption: str = "") -> str
       async def send_file(self, channel_id: str, file_path: str, caption: str = "") -> str
       async def show_prompt(self, channel_id: str, prompt: InteractivePrompt) -> str

Data Flow
---------

**Incoming Message Flow (User -> Agent)**

1. Frontend receives message from messaging platform
2. Frontend resolves window_id via channel_router.resolve_window(channel_id)
3. Frontend sends text to gateway.send_to_window(window_id, text)
4. TmuxManager.send_to_window() pipes text to tmux pane
5. Agent process receives input, produces output
6. SessionMonitor detects new transcript content
7. Gateway emits AgentMessageEvent via on_message() callbacks
8. Frontend receives event, formats and sends to messaging platform

**Outgoing Message Flow (Agent -> User)**

1. Agent produces output (printed to pane)
2. SessionMonitor poll detects new transcript content
3. TranscriptReader parses new lines per provider format
4. Provider.parse_transcript_entries() converts to AgentMessage objects
5. Gateway emits AgentMessageEvent via on_message() callbacks
6. Frontend receives event
7. Frontend formats message (card, expandable blocks, etc.)
8. Frontend sends to messaging platform via FrontendAdapter

State Management
----------------

**State Files**

* ``state.json`` (``~/.cclark/``) - Main gateway state
* ``session_map.json`` (``~/.cclark/``) - tmux session mappings
* ``monitor_state.json`` (``~/.cclark/``) - Poll loop state
* ``events.jsonl`` (``~/.cclark/``) - Hook event log

**Persistence Strategy**

1. **Debounced writes**: StatePersistence schedules writes 0.5s after changes
2. **Atomic writes**: Write to temp file, then rename
3. **Lazy loading**: State loaded on gateway start
4. **Migration support**: Old formats auto-migrated on load

Directory Structure
-------------------

::

   src/unified_icc/
   ├── __init__.py           # Public API exports
   ├── gateway.py            # UnifiedICC main class
   ├── adapter.py            # FrontendAdapter protocol
   ├── event_types.py        # Event dataclasses
   ├── channel_router.py     # Channel-window routing
   ├── config.py             # GatewayConfig
   ├── tmux_manager.py       # tmux operations
   ├── session.py            # SessionManager
   ├── session_monitor.py    # Poll loop coordinator
   ├── session_lifecycle.py  # Session map diffing
   ├── session_map.py        # Session map I/O
   ├── state_persistence.py  # Debounced JSON persistence
   ├── window_state_store.py # Window state tracking
   ├── event_reader.py       # events.jsonl reader
   ├── transcript_reader.py  # Transcript I/O
   ├── transcript_parser.py  # Transcript -> messages
   ├── terminal_parser.py    # Terminal UI detection
   ├── hook.py              # Claude hook events
   ├── idle_tracker.py      # Idle timers
   ├── monitor_state.py      # Poll state
   ├── monitor_events.py     # Internal event types
   ├── window_resolver.py    # Window ID remapping
   ├── window_view.py        # Window snapshots
   ├── mailbox.py           # Agent-to-agent messages
   ├── cc_commands.py       # Claude command discovery
   ├── expandable_quote.py  # Expandable text blocks
   ├── topic_state_registry.py # Topic state
   ├── claude_task_state.py # Claude task tracking
   ├── providers/
   │   ├── __init__.py       # Registry + helpers
   │   ├── base.py           # AgentProvider protocol
   │   ├── registry.py       # ProviderRegistry
   │   ├── _jsonl.py         # JSONL base class
   │   ├── claude.py         # Claude provider
   │   ├── codex.py          # Codex provider
   │   ├── codex_format.py   # Codex formatting
   │   ├── codex_status.py   # Codex status parsing
   │   ├── gemini.py         # Gemini provider
   │   ├── pi.py             # Pi provider
   │   ├── pi_discovery.py   # Pi discovery
   │   ├── pi_format.py      # Pi formatting
   │   ├── shell.py          # Shell provider
   │   └── process_detection.py # Process detection
