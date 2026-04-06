"""Tests for session info tools."""

import pytest

from aulinx.tools.session import env_get, who_am_i


class TestWhoAmI:
    @pytest.mark.asyncio
    async def test_returns_dict(self):
        result = await who_am_i()
        assert isinstance(result, dict)
        assert "user" in result
        assert "home" in result
        assert "shell" in result or "desktop" in result


class TestEnvGet:
    @pytest.mark.asyncio
    async def test_get_specific_var(self):
        result = await env_get("PATH")
        assert "value" in result
        assert len(result["value"]) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        result = await env_get("AULINX_TEST_NONEXISTENT_VAR_XYZ")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_common_vars(self):
        result = await env_get()
        assert isinstance(result, dict)
        # At least PATH should be present on any system
        assert "PATH" in result
