"""Tests for tool registry — registration, tiers, confirmation logic."""

import pytest

from aulinx.tools.registry import Tier, Tool, ToolRegistry


def make_tool(name: str, tier: Tier = Tier.OBSERVE):
    async def noop(**kwargs):
        return {"ok": True, **kwargs}
    return Tool(name=name, description=f"Test {name}", fn=noop, tier=tier)


class TestToolRegistry:
    def test_builtin_tools_registered(self):
        registry = ToolRegistry()
        assert len(registry) > 0
        assert "window_list" in registry
        assert "file_read" in registry
        assert "shell_exec" in registry

    def test_tool_count(self):
        registry = ToolRegistry()
        assert len(registry) >= 50  # we have 55 as of now

    def test_describe_contains_all_tools(self):
        registry = ToolRegistry()
        desc = registry.describe()
        assert "window_list" in desc
        assert "atspi_get_tree" in desc
        assert "shell_exec" in desc

    def test_describe_includes_tiers(self):
        registry = ToolRegistry()
        desc = registry.describe()
        assert "[read]" in desc
        assert "[destructive]" in desc


class TestConfirmation:
    def test_observe_never_confirms(self):
        registry = ToolRegistry()
        assert not registry.needs_confirmation("window_list")
        assert not registry.needs_confirmation("file_read")
        assert not registry.needs_confirmation("system_info")

    def test_low_risk_never_confirms(self):
        registry = ToolRegistry()
        assert not registry.needs_confirmation("clipboard_set")
        assert not registry.needs_confirmation("audio_set_volume")

    def test_destructive_always_confirms(self):
        registry = ToolRegistry()
        assert registry.needs_confirmation("shell_exec")
        assert registry.needs_confirmation("process_kill")
        assert registry.needs_confirmation("file_trash")

    def test_mutate_confirms_first_time(self):
        registry = ToolRegistry()
        assert registry.needs_confirmation("app_launch")
        # After marking confirmed, should not need confirmation
        registry.mark_confirmed("app_launch")
        assert not registry.needs_confirmation("app_launch")

    def test_destructive_always_confirms_even_after_mark(self):
        registry = ToolRegistry()
        registry.mark_confirmed("shell_exec")
        assert registry.needs_confirmation("shell_exec")  # still True

    def test_unknown_tool_confirms(self):
        registry = ToolRegistry()
        assert registry.needs_confirmation("nonexistent_tool")


class TestExecution:
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert "error" in str(result).lower() or "Unknown" in str(result)

    @pytest.mark.asyncio
    async def test_execute_file_read_missing(self):
        registry = ToolRegistry()
        result = await registry.execute("file_read", {"path": "/tmp/aulinx_nonexistent_file_xyz"})
        assert "not found" in str(result).lower() or "error" in str(result).lower()
