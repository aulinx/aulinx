"""Base types for tools — Tool and Tier. Separate module to avoid circular imports."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Awaitable, Callable


class Tier(IntEnum):
    """Permission tiers for tool actions."""
    OBSERVE = 0      # Never confirm (read-only)
    LOW_RISK = 1     # Auto-allow with audit log
    MUTATE = 2       # Confirm first time per session
    DESTRUCTIVE = 3  # Always confirm
    IRREVERSIBLE = 4 # Always confirm + extra warning


class Tool:
    """A single tool the agent can call."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Awaitable[Any]],
        parameters: dict | None = None,
        tier: Tier = Tier.OBSERVE,
    ):
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters or {}
        self.tier = tier
