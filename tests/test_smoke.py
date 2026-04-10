"""Smoke tests — verify core components initialize without crashing."""

import pytest
from aulinx.tools.registry import ToolRegistry
from aulinx.cli import detect_mode


class TestSmoke:
    """Basic smoke tests for the Aulinx agent."""

    def test_registry_initializes_all_modes(self):
        """All three modes should initialize without errors."""
        for mode in ["core", "desktop", "compositor"]:
            registry = ToolRegistry(mode=mode)
            assert len(registry) > 0

    def test_registry_tools_have_functions(self):
        """Every registered tool should have a callable function."""
        registry = ToolRegistry(mode="compositor")
        for name, tool in registry._tools.items():
            assert callable(tool.fn), f"Tool {name} has no callable function"

    def test_mode_detection_returns_valid(self):
        """Mode detection should return one of the valid modes."""
        mode = detect_mode()
        assert mode in ("core", "desktop", "compositor")

    def test_agent_imports(self):
        """Agent module should import without errors."""
        from aulinx.agent import Agent, SYSTEM_PROMPTS
        assert Agent is not None
        assert len(SYSTEM_PROMPTS) == 3

    def test_context_imports(self):
        """Context module should import without errors."""
        from aulinx.context.desktop import DesktopContext
        ctx = DesktopContext()
        assert ctx is not None

    def test_doctor_imports(self):
        """Doctor module should import without errors."""
        from aulinx.doctor import run_doctor
        assert run_doctor is not None

    def test_config_loads(self):
        """Config should load without errors (even if no config file exists)."""
        from aulinx.config import load_config
        config = load_config()
        assert config is not None
        assert hasattr(config, 'llm')

    def test_cli_info_function(self):
        """The --info function should work without errors."""
        from aulinx.cli import _show_info
        # Just verify it doesn't crash
        _show_info()

    def test_server_tools_all_async(self):
        """All server tools should be async functions."""
        from aulinx.tools import server_tools
        import inspect
        for tool in server_tools.TOOLS:
            assert inspect.iscoroutinefunction(tool.fn), f"{tool.name} is not async"

    def test_compositor_tools_all_async(self):
        """All compositor tools should be async functions."""
        from aulinx.tools import compositor_tools
        import inspect
        for tool in compositor_tools.TOOLS:
            assert inspect.iscoroutinefunction(tool.fn), f"{tool.name} is not async"

    def test_tool_names_unique_across_modes(self):
        """Tool names should be unique within each mode."""
        for mode in ["core", "desktop", "compositor"]:
            registry = ToolRegistry(mode=mode)
            names = list(registry._tools.keys())
            assert len(names) == len(set(names)), f"Duplicate tool names in {mode} mode"

    def test_ollama_schemas_valid_json(self):
        """All tool schemas should be valid for Ollama."""
        import json
        for mode in ["core", "desktop", "compositor"]:
            registry = ToolRegistry(mode=mode)
            schemas = registry.to_ollama_tools(core_only=False)
            for schema in schemas:
                # Should be serializable
                json.dumps(schema)
                # Should have required fields
                assert "type" in schema
                assert "function" in schema
                assert "name" in schema["function"]
