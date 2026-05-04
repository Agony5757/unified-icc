import os

os.environ.setdefault("UNIFIED_ICC_DIR", "/tmp/unified-icc-test-config")

import pytest

from unified_icc import channel_router, session_manager, StatePersistence, user_preferences, window_store


@pytest.fixture(autouse=True)
def isolate_persistent_singletons(tmp_path):
    """Keep unit tests from writing to the developer's real ~/.unified-icc state."""
    original_persistence = session_manager._persistence
    session_manager._persistence = StatePersistence(
        tmp_path / "state.json",
        session_manager._serialize_state,
    )

    window_store.reset()
    channel_router._bindings.clear()
    channel_router._reverse.clear()
    channel_router._display_names.clear()
    channel_router._channel_meta.clear()
    user_preferences.user_window_offsets.clear()
    user_preferences.user_dir_favorites.clear()

    yield

    if session_manager._persistence._save_timer is not None:
        session_manager._persistence._save_timer.cancel()
        session_manager._persistence._save_timer = None
    session_manager._persistence = original_persistence

    window_store.reset()
    channel_router._bindings.clear()
    channel_router._reverse.clear()
    channel_router._display_names.clear()
    channel_router._channel_meta.clear()
    user_preferences.user_window_offsets.clear()
    user_preferences.user_dir_favorites.clear()
