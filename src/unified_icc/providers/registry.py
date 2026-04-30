"""Provider registry — maps provider names to classes, caches instances."""

import structlog

from unified_icc.providers.base import AgentProvider

logger = structlog.get_logger()


class UnknownProviderError(LookupError):
    """Raised when requesting a provider name that is not registered."""


class ProviderRegistry:
    """Maps provider name strings to AgentProvider classes.

    Supports lazy instantiation: get() creates and caches a singleton instance
    on first access. Used by providers/__init__.py to register claude, codex,
    gemini, pi, and shell providers.
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[AgentProvider]] = {}
        self._instances: dict[str, AgentProvider] = {}

    def register(self, name: str, provider_cls: type[AgentProvider]) -> None:
        """Register a provider class under *name*. Invalidates any cached instance."""
        self._providers[name] = provider_cls
        self._instances.pop(name, None)
        logger.debug("Registered provider %r", name)

    def provider_names(self) -> list[str]:
        return list(self._providers)

    def is_valid(self, name: str) -> bool:
        return name in self._providers

    def get(self, name: str) -> AgentProvider:
        if name in self._instances:
            return self._instances[name]
        cls = self._providers.get(name)
        if cls is None:
            available = ", ".join(sorted(self._providers)) or "(none)"
            raise UnknownProviderError(
                f"Unknown provider {name!r}. Available: {available}"
            )
        instance = cls()
        self._instances[name] = instance
        return instance


registry = ProviderRegistry()
