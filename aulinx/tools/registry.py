"""Tool registry — registers and executes desktop tools."""

from __future__ import annotations

import json
from enum import IntEnum
from typing import Any, Callable, Awaitable

from aulinx.tools import window, atspi_tools, files, apps, system, clipboard, notify, dbus_tools


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


class ToolRegistry:
    """Registry of tools the agent can call."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._confirmed_tools: set[str] = set()  # tools confirmed this session
        self._register_builtins()

    def _register_builtins(self):
        """Register all built-in tool modules."""
        for module in [window, atspi_tools, files, apps, system, clipboard, notify, dbus_tools]:
            for tool in module.TOOLS:
                self._tools[tool.name] = tool

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def needs_confirmation(self, name: str) -> bool:
        """Check if a tool needs user confirmation before execution."""
        tool = self._tools.get(name)
        if not tool:
            return True

        if tool.tier <= Tier.LOW_RISK:
            return False
        if tool.tier == Tier.MUTATE:
            # Confirm first time per session, then auto-allow
            if name in self._confirmed_tools:
                return False
            return True
        # DESTRUCTIVE and IRREVERSIBLE always confirm
        return True

    def mark_confirmed(self, name: str):
        """Mark a tool as confirmed for this session."""
        self._confirmed_tools.add(name)

    def describe(self) -> str:
        """Return tool descriptions for the LLM system prompt."""
        lines = []
        for tool in sorted(self._tools.values(), key=lambda t: t.name):
            params = ""
            if tool.parameters:
                params = " | params: " + ", ".join(
                    f"{k}: {v}" for k, v in tool.parameters.items()
                )
            tier_label = ["read", "low-risk", "mutate", "destructive", "irreversible"][tool.tier]
            lines.append(f"- {tool.name} [{tier_label}]: {tool.description}{params}")
        return "\n".join(lines)

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}

        # Mark as confirmed for session (for MUTATE tier)
        self.mark_confirmed(name)

        try:
            return await tool.fn(**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}
