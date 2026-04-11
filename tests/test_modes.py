"""Tests for three-tier mode system — mode detection, tool filtering, core tools."""

import os
from unittest.mock import patch

from aulinx.tools.registry import ToolRegistry


class TestModeToolFiltering:
    """Test that tool filtering works correctly per mode."""

    def test_core_mode_has_file_tools(self):
        registry = ToolRegistry(mode="core")
        assert "file_read" in registry
        assert "file_write" in registry
        assert "git_status" in registry

    def test_core_mode_excludes_gui_tools(self):
        registry = ToolRegistry(mode="core")
        assert "window_list" not in registry
        assert "atspi_get_tree" not in registry
        assert "display_brightness" not in registry
        assert "audio_set_volume" not in registry

    def test_core_mode_excludes_compositor_tools(self):
        registry = ToolRegistry(mode="core")
        assert "compositor_windows" not in registry
        assert "compositor_click" not in registry

    def test_core_mode_includes_server_tools(self):
        registry = ToolRegistry(mode="core")
        assert "journal_logs" in registry
        assert "docker_ps" in registry
        assert "port_list" in registry

    def test_desktop_mode_has_gui_tools(self):
        registry = ToolRegistry(mode="desktop")
        assert "window_list" in registry
        assert "atspi_get_tree" in registry
        assert "display_brightness" in registry

    def test_desktop_mode_excludes_compositor_tools(self):
        registry = ToolRegistry(mode="desktop")
        assert "compositor_windows" not in registry
        assert "compositor_click" not in registry

    def test_compositor_mode_has_everything(self):
        registry = ToolRegistry(mode="compositor")
        assert "file_read" in registry  # core
        assert "window_list" in registry  # desktop
        assert "compositor_windows" in registry  # compositor
        assert "compositor_click" in registry
        assert "compositor_spawn" in registry

    def test_mode_tool_counts(self):
        core = ToolRegistry(mode="core")
        desktop = ToolRegistry(mode="desktop")
        compositor = ToolRegistry(mode="compositor")

        # Each tier should have more tools than the previous
        assert len(core) < len(desktop)
        assert len(desktop) < len(compositor)

        # Sanity check minimums
        assert len(core) >= 80
        assert len(desktop) >= 120
        assert len(compositor) >= 150


class TestCoreTools:
    """Test that CORE_TOOLS (native tool calling set) is mode-aware."""

    def test_core_mode_core_tools_no_gui(self):
        registry = ToolRegistry(mode="core")
        core_tools = registry.CORE_TOOLS
        assert "file_read" in core_tools
        assert "git_status" in core_tools
        assert "journal_logs" in core_tools
        # No GUI tools
        assert "window_list" not in core_tools
        assert "atspi_get_tree" not in core_tools

    def test_desktop_mode_core_tools_has_gui(self):
        registry = ToolRegistry(mode="desktop")
        core_tools = registry.CORE_TOOLS
        assert "window_list" in core_tools
        assert "atspi_find_elements" in core_tools
        assert "input_type_text" in core_tools

    def test_compositor_mode_core_tools_has_compositor(self):
        registry = ToolRegistry(mode="compositor")
        core_tools = registry.CORE_TOOLS
        assert "compositor_windows" in core_tools
        assert "compositor_click" in core_tools
        assert "compositor_type" in core_tools
        assert "compositor_screenshot" in core_tools

    def test_ollama_tools_respect_mode(self):
        core = ToolRegistry(mode="core")
        compositor = ToolRegistry(mode="compositor")
        core_schemas = core.to_ollama_tools(core_only=True)
        comp_schemas = compositor.to_ollama_tools(core_only=True)
        assert len(comp_schemas) > len(core_schemas)


class TestModeDetection:
    """Test auto-detection logic."""

    def test_detect_core_no_display(self):
        from aulinx.cli import detect_mode
        with patch.dict(os.environ, {}, clear=True):
            # Remove display vars
            env = {k: v for k, v in os.environ.items()
                   if k not in ("WAYLAND_DISPLAY", "DISPLAY", "AULINX_SOCKET", "XDG_RUNTIME_DIR")}
            with patch.dict(os.environ, env, clear=True):
                mode = detect_mode()
                assert mode == "core"

    def test_detect_desktop_with_display(self):
        from aulinx.cli import detect_mode
        with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False):
            # Remove compositor socket
            env_clean = {k: v for k, v in os.environ.items() if k != "AULINX_SOCKET"}
            with patch.dict(os.environ, env_clean, clear=True):
                with patch.dict(os.environ, {"DISPLAY": ":0"}):
                    mode = detect_mode()
                    assert mode in ("desktop", "compositor")  # compositor if socket exists


class TestSystemPrompts:
    """Test mode-specific system prompts."""

    def test_prompts_exist_for_all_modes(self):
        from aulinx.agent import SYSTEM_PROMPTS
        assert "core" in SYSTEM_PROMPTS
        assert "desktop" in SYSTEM_PROMPTS
        assert "compositor" in SYSTEM_PROMPTS

    def test_core_prompt_mentions_headless(self):
        from aulinx.agent import SYSTEM_PROMPTS
        assert "HEADLESS" in SYSTEM_PROMPTS["core"]
        assert "CANNOT control GUI" in SYSTEM_PROMPTS["core"]

    def test_compositor_prompt_mentions_compositor(self):
        from aulinx.agent import SYSTEM_PROMPTS
        assert "compositor" in SYSTEM_PROMPTS["compositor"].lower()
        assert "compositor_*" in SYSTEM_PROMPTS["compositor"]
