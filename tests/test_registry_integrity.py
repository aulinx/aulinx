"""Registry integrity tests — verify all tools are properly configured.

These run on any platform (no Linux required).
"""

import asyncio

from aulinx.tools.base import Tier
from aulinx.tools.registry import ToolRegistry


class TestRegistryIntegrity:
    def test_all_tools_have_descriptions(self):
        registry = ToolRegistry()
        for name, tool in registry._tools.items():
            assert tool.description, f"{name} has no description"
            assert len(tool.description) > 5, f"{name} description too short"

    def test_all_tools_have_valid_tiers(self):
        registry = ToolRegistry()
        for name, tool in registry._tools.items():
            assert tool.tier in (Tier.OBSERVE, Tier.LOW_RISK, Tier.MUTATE, Tier.DESTRUCTIVE, Tier.IRREVERSIBLE), \
                f"{name} has invalid tier: {tool.tier}"

    def test_all_tools_are_async(self):
        registry = ToolRegistry()
        for name, tool in registry._tools.items():
            assert asyncio.iscoroutinefunction(tool.fn), f"{name} fn is not async"

    def test_tool_count_at_least_100(self):
        registry = ToolRegistry()
        assert len(registry) >= 100, f"Only {len(registry)} tools, expected 100+"

    def test_ollama_schemas_valid(self):
        registry = ToolRegistry()
        schemas = registry.to_ollama_tools(core_only=False)
        for schema in schemas:
            assert schema["type"] == "function"
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_core_tools_subset(self):
        registry = ToolRegistry()
        core = registry.to_ollama_tools(core_only=True)
        all_tools = registry.to_ollama_tools(core_only=False)
        assert len(core) < len(all_tools)
        assert len(core) >= 40

    def test_no_duplicate_tool_names(self):
        registry = ToolRegistry()
        names = list(registry._tools.keys())
        assert len(names) == len(set(names)), "Duplicate tool names found"
