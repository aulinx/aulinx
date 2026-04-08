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
        self._register_plugins()

    def _register_builtins(self):
        """Register all built-in tool modules."""
        from aulinx.tools import (
            ai_tools,
            apps,
            archive,
            atspi_tools,
            audio,
            bluetooth,
            calc,
            clipboard,
            datetime_tools,
            dbus_tools,
            desktop_utils,
            disks,
            display,
            files,
            git,
            input_sim,
            interact,
            long_memory_tools,
            memory,
            network,
            notify,
            ocr,
            packages,
            power,
            process,
            productivity,
            schedule,
            screen,
            services,
            session,
            sysadmin,
            system,
            text,
            theme,
            timer,
            web,
            window,
            workflow,
            workflows_tools,
            xdg,
        )
        for module in [
            window, atspi_tools, files, apps, system, clipboard,
            notify, dbus_tools, process, network, audio, display,
            power, theme, memory, bluetooth, workflow, services,
            input_sim, interact, long_memory_tools, session, packages, xdg, timer,
            git, text, datetime_tools, ocr, screen, web, workflows_tools,
            ai_tools, archive, calc, desktop_utils, disks, productivity, schedule, sysadmin,
        ]:
            for tool in module.TOOLS:
                self._tools[tool.name] = tool

    def _register_plugins(self):
        """Load user plugins from ~/.config/aulinx/plugins/."""
        try:
            from aulinx.plugins import discover_plugins
            for tool in discover_plugins():
                self._tools[tool.name] = tool
        except Exception:
            pass

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

    # Core tools that are always included in native tool calling
    CORE_TOOLS = {
        "window_list", "window_get_focused",
        "atspi_get_tree", "atspi_find_elements", "atspi_do_action", "atspi_read_text", "atspi_set_text",
        "window_screenshot",
        "file_read", "file_write", "file_edit", "file_list", "file_search", "file_trash",
        "app_launch", "app_list_running",
        "process_list", "process_kill",
        "system_info", "shell_exec",
        "who_am_i", "uptime", "disk_usage",
        "date_now", "calendar_show",
        "git_status", "git_log", "git_diff",
        "text_grep", "text_count",
        "clipboard_get", "clipboard_set",
        "notification_send",
        "audio_get_volume", "audio_set_volume",
        "network_status", "wifi_list",
        "power_status",
        "theme_get", "theme_set_dark",
        "bluetooth_status",
        "display_list", "display_brightness",
        "memory_store", "memory_get",
        "input_type_text", "input_key_combo",
        "xdg_open",
        "set_timer",
        "context_get",
    }

    def to_ollama_tools(self, core_only: bool = True) -> list[dict]:
        """Return tools as Ollama/OpenAI function calling schemas.

        core_only=True (default): return ~50 most-used tools to fit in context window.
        core_only=False: return all 92 tools (may overflow small context windows).
        """
        tools = self._tools.values()
        if core_only:
            tools = [t for t in tools if t.name in self.CORE_TOOLS]
        return [tool.to_ollama_schema() for tool in sorted(tools, key=lambda t: t.name)]

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name. Strips unknown kwargs to prevent crashes."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}

        self.mark_confirmed(name)

        # Strip unknown kwargs — LLMs sometimes hallucinate extra parameters
        import inspect
        sig = inspect.signature(tool.fn)
        valid_params = set(sig.parameters.keys())
        cleaned_args = {k: v for k, v in args.items() if k in valid_params}

        try:
            return await tool.fn(**cleaned_args)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}
