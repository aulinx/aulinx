"""Tests for the compositor client import and tool registration."""

from aulinx.tools.registry import ToolRegistry


class TestCompositorClient:
    def test_client_importable_from_main_package(self):
        """The compositor client should be importable from aulinx package."""
        from aulinx.compositor_client import AulinxCompositor, connect
        assert AulinxCompositor is not None
        assert connect is not None

    def test_client_has_core_methods(self):
        from aulinx.compositor_client import AulinxCompositor
        client = AulinxCompositor()
        assert hasattr(client, 'connect')
        assert hasattr(client, 'close')
        assert hasattr(client, 'describe')
        assert hasattr(client, 'windows')
        assert hasattr(client, 'screenshot')
        assert hasattr(client, 'type_text')
        assert hasattr(client, 'click')
        assert hasattr(client, 'spawn')

    def test_compositor_tools_registered(self):
        registry = ToolRegistry(mode="compositor")
        assert "compositor_summary" in registry
        assert "compositor_describe" in registry
        assert "compositor_ascii" in registry
        assert "compositor_suggest" in registry
        assert "compositor_batch" in registry
        assert "compositor_annotated_screenshot" in registry
        assert "compositor_run_and_type" in registry

    def test_compositor_tools_count(self):
        registry = ToolRegistry(mode="compositor")
        comp_tools = [n for n in registry._tools if n.startswith("compositor_")]
        assert len(comp_tools) >= 28  # At least 28 compositor tools

    def test_compositor_tools_not_in_core_mode(self):
        registry = ToolRegistry(mode="core")
        comp_tools = [n for n in registry._tools if n.startswith("compositor_")]
        assert len(comp_tools) == 0

    def test_compositor_tools_not_in_desktop_mode(self):
        registry = ToolRegistry(mode="desktop")
        comp_tools = [n for n in registry._tools if n.startswith("compositor_")]
        assert len(comp_tools) == 0
