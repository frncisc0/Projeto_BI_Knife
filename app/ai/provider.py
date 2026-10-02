from typing import Protocol


class AIProvider(Protocol):
    """Future provider contract. Implementations must require explicit opt-in."""

    @property
    def enabled(self) -> bool: ...

    @property
    def name(self) -> str: ...


class NoAIProvider:
    """Default provider: no AI functionality and no network access."""

    enabled = False
    name = "none"
