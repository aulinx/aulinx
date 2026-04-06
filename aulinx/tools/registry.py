"""Tool registry — registers and executes desktop tools."""

from __future__ import annotations

from typing import Any

# Re-export from base to maintain backwards compatibility
from aulinx.tools.base import Tier, Tool  # noqa: F401


class ToolRegistry:
    """Registry of tools the agent can call."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._confirmed_tools: set[str] = set()
        self._register_builtins()

    def _register_builtins(self):
        """Register all built-in tool modules."""
        from aulinx.tools import (
            apps,
            atspi_tools,
            audio,
            bluetooth,
            clipboard,
            datetime_tools,
            dbus_tools,
            display,
            files,
            git,
            input_sim,
            memory,
            network,
            notify,
            ocr,
            packages,
            power,
            process,
            services,
            session,
            system,
            text,
            theme,
            timer,
            window,
            workflow,
            xdg,
        )
        for module in [
            window, atspi_tools, files, apps, system, clipboard,
            notify, dbus_tools, process, network, audio, display,
            power, theme, memory, bluetooth, workflow, services,
            input_sim, session, packages, xdg, timer, git, text,
            datetime_tools, ocr,
        ]:
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
            if name in self._confirmed_tools:
                return False
            return True
        return True

    def mark_confirmed(self, name: str):
        """Mark a tool as confirmed for this session."""
        self._confirmed_tools.add(name)

    def describe(self, compact: bool = False) -> str:
        """Return tool descriptions for the LLM system prompt."""
        lines = []
        for tool in sorted(self._tools.values(), key=lambda t: t.name):
            if compact:
                # Short format to save tokens
                lines.append(f"- {tool.name}: {tool.description[:60]}")
            else:
                params = ""
                if tool.parameters:
                    params = " | params: " + ", ".join(
                        f"{k}: {v}" for k, v in tool.parameters.items()
                    )
                tier_label = ["read", "low-risk", "mutate", "destructive", "irreversible"][tool.tier]
                lines.append(f"- {tool.name} [{tier_label}]: {tool.description}{params}")
        return "\n".join(lines)

    def to_ollama_tools(self) -> list[dict]:
        """Return all tools as Ollama/OpenAI function calling schemas."""
        return [tool.to_ollama_schema() for tool in sorted(self._tools.values(), key=lambda t: t.name)]

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}

        self.mark_confirmed(name)

        try:
            return await tool.fn(**args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}
