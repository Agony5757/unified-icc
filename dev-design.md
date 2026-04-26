# Unified ICC + CCLark Design Document

> **Unified ICC** (Interactive Coding CLI gateway) — a platform-agnostic engine for managing AI coding agents (Claude Code, Codex, etc.) via tmux.
> **CCLark** — a Feishu frontend consuming unified-icc, providing ccgram-equivalent UX on Feishu.

Design document index: [README.md](README.md)

---

## 1. Project Overview

### 1.1 Goals

CCLark aims to fully replicate ccgram's capabilities on Feishu, replacing Telegram as the messaging frontend. The core insight is that tmux management, session monitoring, and agent interaction are **platform-independent** — only the messaging UI layer changes between Telegram and Feishu.

### 1.2 Design Principles

1. **Gateway + Frontend separation** — core logic lives in a reusable gateway service; frontends (Feishu, Telegram) are thin adapters
2. **One session = one tmux window** — no multiplexing within a single conversation; multiple concurrent sessions use multiple Feishu bot accounts or group threads
3. **Feishu cards as primary UI** — use Feishu's Interactive Card system for rich output, tool results, approval flows
4. **Verbose mode** — `/verbose` toggle for detailed output streaming into Feishu cards
5. **Reuse ccgram core** — import or adapt ccgram's proven modules (providers, tmux, transcript parsing, hooks) rather than reimplementing

### 1.3 Deliverables

| Component | Description |
|---|---|
| **unified-icc** (`unified_icc`) | A Python gateway library/service exposing agent management via programmatic API |
| **cclark** | Feishu bot frontend consuming unified_icc, rendering to Feishu cards and messages |
| **Design docs** | This document + per-module specifications in `design/` |

---

## 2. CCGram Technical Stack Analysis

### 2.1 Architecture Layers

CCGram is organized in **6 distinct layers** with callback-based communication:

```
┌──────────────────────────────────────────────────────┐
│  Layer 1: Frontend (Telegram Bot)                    │
│  bot.py + handlers/ (50+ modules)                    │
│  - PTB handler registration, lifecycle               │
│  - Inline keyboards, entity formatting               │
│  - Topic routing, voice transcription                │
├──────────────────────────────────────────────────────┤
│  Layer 2: Message Pipeline                           │
│  message_queue.py → message_sender.py                │
│  - Per-user FIFO queue + worker                      │
│  - Message merging (3800 char), tool batching        │
│  - Rate limiting (1.1s/user), status coalescing      │
├──────────────────────────────────────────────────────┤
│  Layer 3: Session Monitoring                         │
│  session_monitor.py → transcript_reader.py           │
│  event_reader.py → session_lifecycle.py              │
│  - 1s poll loop, incremental JSONL reading           │
│  - Hook event dispatch (byte-offset)                 │
│  - Session lifecycle (new/dead/done)                 │
├──────────────────────────────────────────────────────┤
│  Layer 4: State Management                           │
│  session.py → thread_router.py → window_state_store  │
│  session_map.py → state_persistence.py               │
│  - Window↔session↔topic bindings                     │
│  - Debounced atomic JSON persistence                 │
│  - Per-window provider/mode settings                 │
├──────────────────────────────────────────────────────┤
│  Layer 5: Agent Provider Abstraction                 │
│  providers/base.py → claude.py, codex.py, etc.       │
│  - AgentProvider protocol + ProviderCapabilities     │
│  - Transcript parsing, status detection              │
│  - Launch command resolution, mode scraping          │
├──────────────────────────────────────────────────────┤
│  Layer 6: Infrastructure                             │
│  tmux_manager.py → config.py → hook.py               │
│  - Async tmux operations (libtmux + subprocess)      │
│  - Claude Code hook stdin processing                 │
│  - Configuration singleton (.env + env vars)         │
└──────────────────────────────────────────────────────┘
```

### 2.2 Layer Communication Patterns

**Inbound (user → agent):**
```
Telegram message → bot.py handler → thread_router (topic→window)
  → tmux_manager.send_keys(window_id, text) → Claude CLI
```

**Outbound (agent → user):**
```
Claude CLI writes JSONL → session_monitor (1s poll)
  → transcript_reader (incremental) → provider.parse_transcript_entries()
  → NewMessage callback → message_routing → message_queue
  → message_sender.rate_limit_send() → Telegram API
```

**Hook events (instant):**
```
Claude hook fires → hook.py (stdin JSON) → events.jsonl
  → event_reader (byte-offset) → hook_event_callback
  → dispatch_hook_event() → status/notification handlers
```

### 2.3 Coupling Analysis

| Module | Telegram Coupling | Reusability |
|---|---|---|
| `providers/` | None | Direct reuse |
| `tmux_manager.py` | None | Direct reuse |
| `transcript_parser.py` | None | Direct reuse |
| `session_monitor.py` | Callback-based | Reuse with new callbacks |
| `hook.py` | None | Direct reuse |
| `state_persistence.py` | None | Direct reuse |
| `config.py` | Minimal (token var names) | Adapt |
| `session.py` / `session_manager` | Thread binding concept | Adapt |
| `thread_router.py` | Telegram thread_id | Replace with generic channel map |
| `window_state_store.py` | None | Direct reuse |
| `message_queue.py` | Telegram message limits | Rewrite for Feishu |
| `handlers/*` | Heavy (PTB types) | Replace entirely |
| `bot.py` | Heavy (PTB framework) | Replace entirely |

### 2.4 Key Design Decisions from CCGram

| Decision | Rationale |
|---|---|
| Window ID-centric routing (`@0`, `@12`) | Unique within tmux server; names are display-only |
| Callback-based cross-layer communication | Decouples monitor from handlers without direct imports |
| Provider protocol with capability flags | Gates UX features without `if provider == "claude"` checks |
| File-based mailbox for inter-agent messaging | No database, no daemon, works offline |
| Entity-based formatting | No Telegram parse errors, auto fallback to plain text |
| 1s poll interval for monitoring | Balance between responsiveness and resource usage |

---

## 3. UnifiedICC Gateway Architecture

### 3.1 Vision

Extract ccgram's core logic into a **gateway library** that any frontend can consume. The gateway manages the tmux/agent layer and exposes a clean async API. Frontends (Feishu, Telegram, future Discord/Slack) become thin adapters.

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│  cclark      │  │  ccgram     │  │  future CC   │
│  (Feishu)    │  │  (Telegram) │  │  (Discord)   │
└──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │
       │  unified_icc gateway API           │
       └────────────┬────┴────────────────┘
                    │
       ┌────────────┴────────────┐
       │     UnifiedICC Gateway    │
       │  ┌──────────────────┐   │
       │  │ Session Manager   │   │
       │  │ Tmux Manager      │   │
       │  │ Session Monitor   │   │
       │  │ Provider Registry │   │
       │  │ Hook System       │   │
       │  │ State Persistence │   │
       │  └──────────────────┘   │
       └────────────┬────────────┘
                    │
       ┌────────────┴────────────┐
       │     tmux session         │
       │  ┌───┐ ┌───┐ ┌───┐     │
       │  │@0 │ │@1 │ │@2 │ ... │
       │  │CC │ │CC │ │SH │     │
       │  └───┘ └───┘ └───┘     │
       └─────────────────────────┘
```

### 3.2 Gateway API Design

The gateway exposes a programmatic Python API (not HTTP — the gateway runs in the same process as the frontend):

```python
class UnifiedICC:
    """Core gateway for managing AI coding agents via tmux."""

    # Lifecycle
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # Window management
    async def create_window(
        self, work_dir: str, provider: str = "claude", mode: str = "normal"
    ) -> WindowInfo: ...
    async def kill_window(self, window_id: str) -> None: ...
    async def list_windows(self) -> list[WindowInfo]: ...

    # Message dispatch
    async def send_to_window(self, window_id: str, text: str) -> None: ...
    async def send_key(self, window_id: str, key: str) -> None: ...

    # Output capture
    async def capture_pane(self, window_id: str) -> str: ...
    async def capture_screenshot(self, window_id: str) -> bytes: ...

    # Event subscription (callback-based, matching ccgram pattern)
    def on_message(self, callback: Callable[[AgentMessageEvent], Awaitable[None]]) -> None: ...
    def on_status(self, callback: Callable[[StatusEvent], Awaitable[None]]) -> None: ...
    def on_hook_event(self, callback: Callable[[HookEvent], Awaitable[None]]) -> None: ...
    def on_window_change(self, callback: Callable[[WindowChangeEvent], Awaitable[None]]) -> None: ...

    # Session resolution
    def resolve_window(self, channel_id: str) -> str | None: ...
    def bind_channel(self, channel_id: str, window_id: str) -> None: ...
    def unbind_channel(self, channel_id: str) -> None: ...

    # Provider management
    def get_provider(self, window_id: str) -> AgentProvider: ...
    def detect_provider(self, window_id: str) -> str: ...
```

### 3.3 Event Types (Frontend-Agnostic)

```python
@dataclass
class AgentMessageEvent:
    """A parsed message from the agent."""
    window_id: str
    session_id: str
    messages: list[AgentMessage]  # Reuse ccgram's AgentMessage
    channel_ids: list[str]  # Bound channel IDs for routing

@dataclass
class StatusEvent:
    """Agent status change (working, idle, done, dead)."""
    window_id: str
    status: str  # "working", "idle", "done", "dead", "interactive"
    display_label: str
    interactive_ui: InteractiveUI | None  # AskUserQuestion, ExitPlanMode, etc.

@dataclass
class HookEvent:
    """Claude Code hook event."""
    window_id: str
    event_type: str  # "Stop", "Notification", etc.
    data: dict

@dataclass
class WindowChangeEvent:
    """Window added or removed."""
    window_id: str
    change_type: str  # "new", "removed", "died"
    provider: str
    cwd: str
```

### 3.4 What Gets Extracted from CCGram

| ccgram module | unified_icc treatment |
|---|---|
| `providers/` (entire) | Direct import as dependency |
| `tmux_manager.py` | Import + adapt (remove Telegram-specific vim hacks if needed) |
| `session_monitor.py` | Extract core poll loop, decouple from ccgram's callback signatures |
| `transcript_reader.py` | Direct import |
| `event_reader.py` | Direct import |
| `session_lifecycle.py` | Direct import |
| `transcript_parser.py` | Direct import |
| `hook.py` | Direct import |
| `state_persistence.py` | Direct import |
| `window_state_store.py` | Direct import |
| `session_map.py` | Direct import |
| `session.py` | Extract core, generalize thread_router to channel_router |
| `thread_router.py` | Generalize: `thread_id` → `channel_id` |
| `config.py` | Split: gateway config vs frontend config |
| `window_resolver.py` | Direct import |
| `window_query.py` | Direct import |
| `session_query.py` | Direct import |
| `idle_tracker.py` | Direct import |
| `monitor_state.py` | Direct import |

### 3.5 Adapter Pattern

Each frontend implements a thin adapter:

```python
class FrontendAdapter(Protocol):
    """Interface that each messaging platform must implement."""

    async def send_text(self, channel_id: str, text: str) -> None: ...
    async def send_card(self, channel_id: str, card: CardPayload) -> None: ...
    async def update_card(self, channel_id: str, card_id: str, card: CardPayload) -> None: ...
    async def send_buttons(self, channel_id: str, text: str, buttons: list[Button]) -> None: ...
    async def send_image(self, channel_id: str, image: bytes) -> None: ...

    # Inbound: platform SDK calls these
    async def on_platform_message(self, channel_id: str, user_id: str, text: str) -> None: ...
    async def on_platform_callback(self, channel_id: str, user_id: str, action: str, data: dict) -> None: ...
```

---

## 4. CCLark Feishu Frontend Design

### 4.1 Feishu Platform Mapping

| CCGram (Telegram) | CCLark (Feishu) |
|---|---|
| Telegram Forum Group | Feishu Group (群组) |
| Forum Topic (thread) | Feishu Message Thread / Separate Group Chat |
| Inline Keyboard | Feishu Card Buttons |
| MessageEntity formatting | Feishu Rich Text / Card Markdown |
| Long polling (PTB) | Webhook event subscription |
| Voice message → Whisper | Voice message → Whisper (same) |
| `/send` file delivery | `/send` file delivery (Feishu file upload) |
| `/screenshot` PNG | `/screenshot` Feishu image message |
| `/toolbar` inline keyboard | `/toolbar` Feishu card with buttons |

### 4.2 Session Model

**Option A: Single Group + Threads (Recommended)**
- One Feishu group, each session is a message thread
- Similar to Telegram's topic model
- Clean 1:1 mapping

**Option B: Multiple Group Chats**
- Each session creates a new group chat
- Higher isolation, but more management overhead
- Aligns with "multiple bot accounts for multiplexing" requirement

**Decision: Option A by default, Option B for multi-bot setups.**

### 4.3 Feishu Card Design

Feishu Interactive Cards are the primary UI primitive:

```
┌─────────────────────────────────────┐
│ 🟢 claude-api                       │
│ ─────────────────────────────────── │
│ 📝 Writing tests for auth module    │
│                                     │
│ Tool: Edit → src/auth/login.py      │
│ ┌─────────────────────────────────┐ │
│ │ + def authenticate(user, pwd):  │ │
│ │ +     token = generate_jwt()    │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌──────┐ ┌──────┐ ┌──────┐        │
│ │📷    │ │⏹     │ │📺    │        │
│ │Screen│ │Ctrl-C│ │Live  │        │
│ └──────┘ └──────┘ └──────┘        │
│ ┌──────┐ ┌──────┐ ┌──────┐        │
│ │🔀    │ │💭    │ │⎋     │        │
│ │Mode  │ │Think │ │Esc   │        │
│ └──────┘ └──────┘ └──────┘        │
└─────────────────────────────────────┘
```

### 4.4 Verbose Mode (`/verbose`)

When verbose mode is active:

1. **All agent output** is captured and rendered in real-time
2. Tool calls, thinking blocks, and bash output are shown in Feishu cards
3. Cards are **updated in-place** as new output arrives (using card update API)
4. Non-verbose mode: only status updates and completion summaries

Implementation:
- Subscribe to `on_message` events from gateway
- Accumulate messages in a card buffer
- Debounce card updates (every 2-3 seconds, not per-line)
- Use card versioning for efficient updates

### 4.5 Command Set

| Command | Description |
|---|---|
| `/new` | Create new session (directory browser) |
| `/history` | Browse paginated message history |
| `/sessions` | Active sessions dashboard |
| `/toolbar` | Show action card (screenshot, ctrl-c, live, mode, etc.) |
| `/screenshot` | Capture current terminal as image |
| `/send [path]` | Send workspace file |
| `/verbose` | Toggle verbose output mode |
| `/sync` | Sync window state with tmux |
| `/resume` | Resume a past session |
| `/restore` | Recover a dead session |
| `/commands` | Show provider-specific slash commands |

### 4.6 Interactive UI Handling

Claude Code's `AskUserQuestion`, `ExitPlanMode`, and permission prompts are rendered as Feishu cards with interactive buttons:

- **AskUserQuestion**: Card with question text + option buttons
- **ExitPlanMode**: Card with plan summary + Approve/Revise buttons
- **Permission prompts**: Card with command/file details + Allow/Deny buttons

### 4.7 Technology Stack

| Component | Technology |
|---|---|
| Feishu SDK | `lark-oapi` (official Python SDK) |
| Async framework | `asyncio` (same as ccgram) |
| Gateway core | `unified_icc` (extracted from ccgram) |
| tmux integration | `libtmux` (reuse from ccgram) |
| Card rendering | `lark-oapi` card builder |
| Webhook server | `FastAPI` or `aiohttp` |
| Terminal screenshots | `Pillow` + `pyte` (reuse from ccgram) |
| Configuration | `python-dotenv` (reuse pattern from ccgram) |

---

## 5. Development Plan

### Phase 0: MVP Proof of Concept (Week 1)

**Goal**: Send a Feishu message → create tmux window with Claude → receive Claude output back in Feishu.

Minimal components:
1. Feishu webhook receiver (FastAPI endpoint)
2. Direct tmux window creation + send_keys
3. Simple transcript polling loop
4. Feishu message sender (text only)

**No gateway abstraction yet** — prove the end-to-end flow works.

### Phase 1: UnifiedICC Gateway Extraction (Week 2-3)

**Goal**: Extract ccgram core into importable `unified_icc` package.

1. Create `unified_icc` package structure
2. Import/adapt ccgram modules (providers, tmux, monitoring, state)
3. Generalize `thread_router` → `channel_router`
4. Define `UnifiedICC` API class with event callbacks
5. Write unit tests for gateway

### Phase 2: CCLark Feishu Frontend (Week 3-5)

**Goal**: Full Feishu frontend consuming unified_icc gateway.

1. Feishu bot setup (webhook, event subscription)
2. Channel binding (Feishu thread → tmux window)
3. Message routing (bidirectional)
4. Feishu card renderer for agent output
5. Interactive card buttons (toolbar, prompts)
6. Verbose mode with live card updates
7. Directory browser for session creation
8. `/send` file delivery
9. Terminal screenshots
10. Session recovery

### Phase 3: Polish & Advanced Features (Week 5-6)

1. Voice message transcription
2. Completion summaries (LLM-powered)
3. Inter-agent messaging
4. Session dashboard
5. Provider switching per-session
6. Multi-bot account support
7. Error handling and resilience

---

## 6. File Structure

```
unified-icc/
├── README.md                  # Project overview + document index
├── dev-design.md              # This document
├── design/
│   ├── module-gateway-core.md     # UnifiedICC gateway internals
│   ├── module-adapter-layer.md    # Frontend adapter abstraction
│   ├── module-feishu-frontend.md  # Feishu-specific implementation (cclark reference)
│   ├── module-card-renderer.md    # Feishu card rendering + verbose mode
│   └── module-mvp.md             # MVP implementation plan
├── src/
│   └── unified_icc/               # Gateway package
│       ├── __init__.py
│       ├── gateway.py         # UnifiedICC main API class
│       ├── channel_router.py  # Generic channel↔window mapping
│       ├── event_types.py     # Frontend-agnostic event types
│       ├── config.py          # Gateway configuration
│       └── ...                # Adapted from ccgram
├── tests/
│   └── unified_icc/               # Gateway tests
├── pyproject.toml
└── ...
```

> Note: `cclark` (Feishu frontend) lives in a separate repository: [Agony5757/cclark](https://github.com/Agony5757/cclark).
> It imports `unified_icc` as a dependency.

---

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Feishu card update rate limits | Debounce updates (2-3s), batch content |
| Feishu webhook reliability | Implement retry + health check endpoint |
| ccgram API instability during extraction | Pin ccgram version, maintain compatibility shim |
| Feishu topic/thread model differs from Telegram | Option A (threads) or Option B (groups) — validate in Phase 0 |
| Synchronous Feishu SDK vs async gateway | Wrap in `asyncio.to_thread()` or use httpx directly |
| Card payload size limits | Split large output across multiple cards or use file attachments |
