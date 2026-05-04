:orphan:

Contributing
============

Thank you for your interest in contributing to Unified ICC!

Development Setup
-----------------

1. Fork and Clone
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/YOUR_USERNAME/unified-icc.git
   cd unified-icc

2. Install Dependencies
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Install with dev dependencies
   uv sync
   uv pip install -e ".[dev]"

3. Verify Installation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   uv run python -c "import unified_icc; print('OK')"

Running Tests
-------------

.. code-block:: bash

   # Run all tests
   uv run pytest

   # Run with coverage
   uv run pytest --cov=unified_icc --cov-report=html

   # Run specific test file
   uv run pytest tests/unit/test_channel_router.py

   # Run with verbose output
   uv run pytest -v

   # Run tests matching pattern
   uv run pytest -k "test_channel"

Code Quality
------------

Linting
~~~~~~

.. code-block:: bash

   # Run ruff linter
   uv run ruff check

   # Auto-fix issues
   uv run ruff check --fix

Type Checking
~~~~~~~~~~~~~

.. code-block:: bash

   # Run pyright
   uv run pyright

All Checks
~~~~~~~~~~

.. code-block:: bash

   # Run all quality checks
   uv run ruff check && uv run pyright && uv run pytest

Project Structure
-----------------

.. code-block:: text

   src/unified_icc/
   ├── __init__.py           # Public API exports
   ├── gateway.py            # UnifiedICC main class
   ├── adapter.py            # FrontendAdapter protocol
   ├── event_types.py        # Event dataclasses
   ├── channel_router.py     # Channel to window routing
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
   ├── transcript_parser.py  # Transcript to messages
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
   ├── utils.py            # Utility functions
   └── providers/
       ├── __init__.py       # Registry + helpers
       ├── base.py           # AgentProvider protocol
       ├── registry.py       # ProviderRegistry
       ├── _jsonl.py         # JSONL base class
       ├── claude.py         # Claude provider
       ├── codex.py          # Codex provider
       ├── gemini.py         # Gemini provider
       ├── pi.py             # Pi provider
       ├── shell.py          # Shell provider
       └── process_detection.py # Process detection

Adding a New Provider
--------------------

1. Create provider file in ``providers/``
2. Implement ``AgentProvider`` protocol
3. Register in ``providers/__init__.py``
4. Add tests

Example:

.. code-block:: python

   # src/unified_icc/providers/myagent.py
   from .base import AgentProvider, ProviderCapabilities, ...

   class MyAgentProvider:
       @property
       def capabilities(self) -> ProviderCapabilities:
           return ProviderCapabilities(
               name="myagent",
               launch_command="myagent",
               # ... other capabilities
           )

       # Implement all AgentProvider methods...

.. code-block:: python

   # src/unified_icc/providers/__init__.py
   from .myagent import MyAgentProvider

   registry.register("myagent", MyAgentProvider)

Adding a New Frontend Adapter
-----------------------------

See the `First Steps <getting-started/first-steps.md>`_ guide for implementing a custom frontend adapter.

Submitting Changes
------------------

1. Create a Branch
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git checkout -b feature/my-feature

2. Make Changes
~~~~~~~~~~~~~~

.. code-block:: bash

   # Edit files
   git add .
   git commit -m "feat: add my feature"

3. Push and Create PR
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git push origin feature/my-feature
   # Create PR on GitHub

Commit Message Format
--------------------

::

   type(scope): description

   Types:
   - feat: New feature
   - fix: Bug fix
   - docs: Documentation
   - refactor: Code refactoring
   - test: Test changes
   - chore: Maintenance

   Examples:
   feat(gateway): add send_key method
   fix(channel_router): handle empty bindings
   docs: update README

Reporting Issues
----------------

Please include:

- Python version (``python --version``)
- tmux version (``tmux -V``)
- unified-icc version
- Minimal reproduction code
- Relevant logs with debug output

Code of Conduct
---------------

- Be respectful and inclusive
- Provide constructive feedback
- Follow the project's coding style
