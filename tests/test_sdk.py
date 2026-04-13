"""Tests for the Aulinx SDK module."""

import pytest

from aulinx.sdk import AulinxClient, RunResult


class TestRunResult:
    def test_default_fields(self):
        r = RunResult()
        assert r.response == ""
        assert r.tool_calls == []
        assert r.tool_results == []
        assert r.success is True
        assert r.duration_s == 0.0
        assert r.tokens_in == 0
        assert r.tokens_out == 0

    def test_custom_fields(self):
        r = RunResult(
            response="hello",
            tool_calls=[{"name": "date_now"}],
            tool_results=[{"name": "date_now", "result": {"local": "2025-01-01"}}],
            success=True,
            duration_s=1.5,
            tokens_in=100,
            tokens_out=50,
        )
        assert r.response == "hello"
        assert len(r.tool_calls) == 1
        assert r.tokens_in == 100
        assert r.tokens_out == 50

    def test_mutable_defaults_independent(self):
        """Each RunResult instance should have its own lists."""
        a = RunResult()
        b = RunResult()
        a.tool_calls.append({"name": "x"})
        assert b.tool_calls == []


class TestClientCreation:
    def test_default_client(self):
        client = AulinxClient()
        assert client._provider == "ollama"
        assert client._mode == "desktop"
        assert len(client._tools) > 0

    def test_core_mode_has_fewer_tools(self):
        desktop = AulinxClient(mode="desktop")
        core = AulinxClient(mode="core")
        assert len(core._tools) < len(desktop._tools)

    def test_compositor_mode(self):
        comp = AulinxClient(mode="compositor")
        assert len(comp._tools) > 0

    def test_openai_provider(self):
        client = AulinxClient(provider="openai", model="gpt-4o", api_key="test-key")
        assert client._provider == "openai"

    def test_anthropic_provider(self):
        client = AulinxClient(provider="anthropic", model="claude-sonnet-4-20250514", api_key="test-key")
        assert client._provider == "anthropic"

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            AulinxClient(provider="nonexistent")


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self):
        client = AulinxClient()
        tools = await client.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 90

    @pytest.mark.asyncio
    async def test_tool_dict_shape(self):
        client = AulinxClient()
        tools = await client.list_tools()
        t = tools[0]
        assert "name" in t
        assert "description" in t
        assert "tier" in t
        assert "parameters" in t

    @pytest.mark.asyncio
    async def test_list_tools_core_mode(self):
        client = AulinxClient(mode="desktop")
        core_tools = await client.list_tools(mode="core")
        desktop_tools = await client.list_tools()
        assert len(core_tools) < len(desktop_tools)


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_date_now(self):
        client = AulinxClient()
        result = await client.execute_tool("date_now")
        assert isinstance(result, dict)
        assert "local" in result
        assert "utc" in result
        assert "unix" in result

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        client = AulinxClient()
        result = await client.execute_tool("nonexistent_tool_xyz")
        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_updates_stats(self):
        client = AulinxClient()
        assert client.get_stats()["tool_calls"] == 0
        await client.execute_tool("date_now")
        assert client.get_stats()["tool_calls"] == 1


class TestGetStats:
    def test_initial_stats(self):
        client = AulinxClient()
        stats = client.get_stats()
        assert stats["runs"] == 0
        assert stats["tool_calls"] == 0
        assert stats["total_tokens_in"] == 0
        assert stats["total_tokens_out"] == 0
        assert stats["total_duration_s"] == 0.0

    def test_stats_returns_copy(self):
        client = AulinxClient()
        s1 = client.get_stats()
        s1["runs"] = 999
        assert client.get_stats()["runs"] == 0
