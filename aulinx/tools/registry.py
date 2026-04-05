"""Tool registry — registers and executes desktop tools."""

from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from aulinx.tools import window, atspi_tools, files, apps, system


class ToolRegistry:
    """Registry of tools the agent can call."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._register_builtins()

    def _register_builtins(self):
        """Register all built-in tool modules."""
        for module in [window, atspi_tools, files, apps, system]:
            for tool in module.TOOLS:
                self._tools[tool.name] = tool

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def describe(self) -> str:
        """Return tool descriptions for the LLM system prompt."""
        lines = []
        for tool in self._tools.values():
            params = json.dumps(tool.parameters) if tool.parameters else "{}"
            lines.append(f"- {tool.name}: {tool.description} | params: {params}")
        return "\n".join(lines)

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.fn(**args)
        except Exception as e:
            return f"Error executing {name}: {e}"


class Tool:
    """A single tool the agent can call."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Awaitable[Any]],
        parameters: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters or {}
