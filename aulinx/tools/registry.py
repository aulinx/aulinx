"""Tool registry — registers and executes desktop tools."""

from __future__ import annotations

from typing import Any

# Re-export from base to maintain backwards compatibility
from aulinx.tools.base import Tier, Tool  # noqa: F401


    # Tools that require a GUI desktop (AT-SPI, screenshots, display control)
DESKTOP_ONLY_MODULES = {
    "window", "atspi_tools", "display", "audio", "bluetooth", "theme",
    "input_sim", "screen", "ocr", "desktop_utils",
}

# Tools that require the Aulinx compositor
COMPOSITOR_ONLY_MODULES = {"compositor_tools"}


class ToolRegistry:
    """Registry of tools the agent can call.

    Filters tools based on operating mode:
    - core: headless/server tools only (~75 tools)
    - desktop: core + GUI tools (~103 tools)
    - compositor: everything (~120+ tools)
    """

    def __init__(self, mode: str = "desktop"):
        self._tools: dict[str, Tool] = {}
        self._confirmed_tools: set[str] = set()
        self._mode = mode
        self._register_builtins()
        self._register_plugins()

    def _register_builtins(self):
        """Register built-in tool modules, filtered by mode."""
        from aulinx.tools import (
            ai_tools,
            apps,
            archive,
            atspi_tools,
            compositor_tools,
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
            server_tools,
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

        # Map module names to modules for filtering
        all_modules = {
            "window": window, "atspi_tools": atspi_tools, "files": files,
            "apps": apps, "system": system, "clipboard": clipboard,
            "notify": notify, "dbus_tools": dbus_tools, "process": process,
            "network": network, "audio": audio, "display": display,
            "power": power, "theme": theme, "memory": memory,
            "bluetooth": bluetooth, "workflow": workflow, "services": services,
            "input_sim": input_sim, "interact": interact,
            "long_memory_tools": long_memory_tools, "session": session,
            "packages": packages, "xdg": xdg, "timer": timer,
            "git": git, "text": text, "datetime_tools": datetime_tools,
            "ocr": ocr, "screen": screen, "web": web,
            "workflows_tools": workflows_tools, "ai_tools": ai_tools,
            "archive": archive, "calc": calc, "compositor_tools": compositor_tools,
            "server_tools": server_tools,
            "desktop_utils": desktop_utils, "disks": disks,
            "productivity": productivity, "schedule": schedule, "sysadmin": sysadmin,
        }

        for name, module in all_modules.items():
            # Skip desktop-only modules in core mode
            if self._mode == "core" and name in DESKTOP_ONLY_MODULES:
                continue
            # Skip compositor modules unless in compositor mode
            if name in COMPOSITOR_ONLY_MODULES and self._mode != "compositor":
                continue
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

    # Core tools included in native tool calling (mode-independent)
    _BASE_CORE_TOOLS = {
        "file_read", "file_write", "file_edit", "file_list", "file_search", "file_trash",
        "process_list", "process_kill",
        "system_info", "shell_exec",
        "who_am_i", "uptime", "disk_usage",
        "date_now", "calendar_show",
        "git_status", "git_log", "git_diff",
        "text_grep", "text_count",
        "clipboard_get", "clipboard_set",
        "network_status", "wifi_list",
        "memory_store", "memory_get",
        "xdg_open",
        "set_timer",
        "context_get",
        "journal_logs", "docker_ps", "port_list",
    }

    # Additional tools for desktop mode
    _DESKTOP_CORE_TOOLS = {
        "window_list", "window_get_focused", "window_screenshot",
        "atspi_get_tree", "atspi_find_elements", "atspi_do_action", "atspi_read_text", "atspi_set_text",
        "app_launch", "app_list_running",
        "notification_send",
        "audio_get_volume", "audio_set_volume",
        "power_status",
        "theme_get", "theme_set_dark",
        "bluetooth_status",
        "display_list", "display_brightness",
        "input_type_text", "input_key_combo",
    }

    # Additional tools for compositor mode (replace AT-SPI with compositor tools)
    _COMPOSITOR_CORE_TOOLS = {
        "compositor_summary", "compositor_suggest", "compositor_describe", "compositor_ascii", "compositor_status", "compositor_windows", "compositor_focused",
        "compositor_type", "compositor_key", "compositor_click",
        "compositor_screenshot", "compositor_annotated_screenshot",
        "compositor_spawn", "compositor_focus",
        "compositor_close", "compositor_wait_for", "compositor_diff",
        "compositor_set_ratio", "compositor_set_gap",
        "compositor_find_window", "compositor_run_and_type",
    }

    @property
    def CORE_TOOLS(self) -> set:
        tools = set(self._BASE_CORE_TOOLS)
        if self._mode in ("desktop", "compositor"):
            tools |= self._DESKTOP_CORE_TOOLS
        if self._mode == "compositor":
            tools |= self._COMPOSITOR_CORE_TOOLS
        return tools

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
