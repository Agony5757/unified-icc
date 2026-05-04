"""Tests for ProviderRegistry."""
from __future__ import annotations

import pytest

from unified_icc.providers.base import AgentProvider, ProviderCapabilities
from unified_icc.providers.registry import ProviderRegistry, UnknownProviderError


class DummyProvider(AgentProvider):
    capabilities = ProviderCapabilities(
        name="dummy",
        launch_command="dummy",
        supports_resume=False,
        supports_continue=False,
        supports_structured_transcript=False,
        supports_incremental_read=False,
        transcript_format="",
        supports_hook=True,
        supports_status_snapshot=False,
        builtin_commands=[],
    )

    def detect_from_pane_title(self, command: str, title: str) -> bool:
        return False


class AnotherProvider(AgentProvider):
    capabilities = ProviderCapabilities(
        name="another",
        launch_command="another",
        supports_resume=False,
        supports_continue=False,
        supports_structured_transcript=False,
        supports_incremental_read=False,
        transcript_format="",
        supports_hook=True,
        supports_status_snapshot=False,
        builtin_commands=[],
    )

    def detect_from_pane_title(self, command: str, title: str) -> bool:
        return False


def test_register_adds_provider() -> None:
    reg = ProviderRegistry()
    reg.register("dummy", DummyProvider)
    assert reg.is_valid("dummy") is True
    assert "dummy" in reg.provider_names()


def test_register_invalidates_cached_instance() -> None:
    reg = ProviderRegistry()
    reg.register("dummy", DummyProvider)
    instance1 = reg.get("dummy")
    instance2 = reg.get("dummy")
    assert instance1 is instance2  # cached

    reg.register("dummy", DummyProvider)  # re-register
    instance3 = reg.get("dummy")
    assert instance3 is not instance1  # new instance


def test_get_returns_instance_of_registered_class() -> None:
    reg = ProviderRegistry()
    reg.register("dummy", DummyProvider)
    inst = reg.get("dummy")
    assert isinstance(inst, DummyProvider)


def test_get_unknown_provider_raises_with_available_list() -> None:
    reg = ProviderRegistry()
    with pytest.raises(UnknownProviderError) as exc_info:
        reg.get("nonexistent")
    assert "nonexistent" in str(exc_info.value)
    assert "Available:" in str(exc_info.value)


def test_get_unknown_provider_shows_empty_list_when_no_providers() -> None:
    reg = ProviderRegistry()
    with pytest.raises(UnknownProviderError) as exc_info:
        reg.get("anything")
    assert "(none)" in str(exc_info.value)


def test_provider_names_returns_all_registered() -> None:
    reg = ProviderRegistry()
    reg.register("a", DummyProvider)
    reg.register("b", AnotherProvider)
    assert set(reg.provider_names()) == {"a", "b"}


def test_is_valid_returns_false_for_unregistered() -> None:
    reg = ProviderRegistry()
    assert reg.is_valid("unknown") is False


def test_multiple_providers_cached_separately() -> None:
    reg = ProviderRegistry()
    reg.register("dummy", DummyProvider)
    reg.register("another", AnotherProvider)
    inst1 = reg.get("dummy")
    inst2 = reg.get("another")
    assert isinstance(inst1, DummyProvider)
    assert isinstance(inst2, AnotherProvider)
    assert inst1 is not inst2


def test_unregister_is_not_supported() -> None:
    """ProviderRegistry only supports register, not unregister."""
    reg = ProviderRegistry()
    reg.register("dummy", DummyProvider)
    assert reg.is_valid("dummy") is True
    # No unregister method - re-registering same name should work
    reg.register("dummy", AnotherProvider)
    assert reg.is_valid("dummy") is True
    inst = reg.get("dummy")
    assert isinstance(inst, AnotherProvider)
