"""Tests for workflow memory system."""

from unittest.mock import patch

import pytest

from aulinx.tools import memory as mem_module


@pytest.fixture(autouse=True)
def temp_memory(tmp_path):
    """Redirect memory storage to a temp directory."""
    mem_file = tmp_path / "memory.json"
    with patch.object(mem_module, "MEMORY_DIR", tmp_path), \
         patch.object(mem_module, "MEMORY_FILE", mem_file):
        yield mem_file


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_store_and_get(self):
        await mem_module.memory_store("test", "key1", "value1")
        results = await mem_module.memory_get(namespace="test", key="key1")
        assert len(results) == 1
        assert results[0]["value"] == "value1"

    @pytest.mark.asyncio
    async def test_store_overwrites(self):
        await mem_module.memory_store("test", "key1", "old_value")
        result = await mem_module.memory_store("test", "key1", "new_value")
        assert result["previous_value"] == "old_value"

        results = await mem_module.memory_get(namespace="test", key="key1")
        assert results[0]["value"] == "new_value"

    @pytest.mark.asyncio
    async def test_multiple_namespaces(self):
        await mem_module.memory_store("ns1", "k", "v1")
        await mem_module.memory_store("ns2", "k", "v2")

        r1 = await mem_module.memory_get(namespace="ns1")
        r2 = await mem_module.memory_get(namespace="ns2")
        assert len(r1) == 1
        assert len(r2) == 1
        assert r1[0]["value"] == "v1"
        assert r2[0]["value"] == "v2"

    @pytest.mark.asyncio
    async def test_search_across_all(self):
        await mem_module.memory_store("project", "name", "aulinx")
        await mem_module.memory_store("prefs", "theme", "dark")

        results = await mem_module.memory_get(search="aulinx")
        assert len(results) == 1
        assert results[0]["key"] == "name"

    @pytest.mark.asyncio
    async def test_delete(self):
        await mem_module.memory_store("test", "to_delete", "goodbye")
        result = await mem_module.memory_delete("test", "to_delete")
        assert result["deleted"] is True

        results = await mem_module.memory_get(namespace="test")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        result = await mem_module.memory_delete("nope", "nope")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_namespaces(self):
        await mem_module.memory_store("alpha", "k", "v")
        await mem_module.memory_store("beta", "k1", "v1")
        await mem_module.memory_store("beta", "k2", "v2")

        namespaces = await mem_module.memory_list_namespaces()
        ns_map = {n["namespace"]: n["entries"] for n in namespaces}
        assert ns_map["alpha"] == 1
        assert ns_map["beta"] == 2

    @pytest.mark.asyncio
    async def test_empty_get(self):
        results = await mem_module.memory_get()
        assert results == []
