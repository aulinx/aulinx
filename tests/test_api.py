"""Tests for the web dashboard API."""

import pytest

from aulinx.api import handle_api_request


class TestAPI:
    @pytest.mark.asyncio
    async def test_tools_endpoint(self):
        result = await handle_api_request("/api/tools")
        assert "tools" in result
        assert "count" in result
        assert result["count"] > 90

    @pytest.mark.asyncio
    async def test_stats_endpoint(self):
        result = await handle_api_request("/api/stats")
        assert "tools" in result
        assert result["tools"] > 90

    @pytest.mark.asyncio
    async def test_config_endpoint(self):
        result = await handle_api_request("/api/config")
        assert "model" in result
        assert "base_url" in result
        assert "temperature" in result

    @pytest.mark.asyncio
    async def test_audit_endpoint(self):
        result = await handle_api_request("/api/audit")
        assert "entries" in result

    @pytest.mark.asyncio
    async def test_history_endpoint(self):
        result = await handle_api_request("/api/history")
        assert "sessions" in result

    @pytest.mark.asyncio
    async def test_unknown_path(self):
        result = await handle_api_request("/api/nonexistent")
        assert "error" in result
