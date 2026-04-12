"""Tests for plugin system."""

import json
from unittest.mock import patch

import pytest

from aulinx.plugins import PluginManifest, discover_plugins, list_plugins


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a temp plugin directory."""
    with patch("aulinx.plugins.PLUGINS_DIR", tmp_path):
        yield tmp_path


class TestPluginDiscovery:
    def test_empty_dir(self, plugin_dir):
        tools = discover_plugins()
        assert tools == []

    def test_loads_valid_plugin(self, plugin_dir):
        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text('''
from aulinx.tools.base import Tool, Tier

async def my_tool() -> dict:
    return {"ok": True}

TOOLS = [
    Tool(name="my_tool", description="Test tool", fn=my_tool, tier=Tier.OBSERVE),
]
''')
        tools = discover_plugins()
        assert len(tools) == 1
        assert tools[0].name == "my_tool"

    def test_skips_underscore_files(self, plugin_dir):
        (plugin_dir / "_private.py").write_text("TOOLS = []")
        tools = discover_plugins()
        assert tools == []

    def test_skips_broken_plugin(self, plugin_dir):
        (plugin_dir / "broken.py").write_text("raise RuntimeError('broken')")
        tools = discover_plugins()
        assert tools == []

    def test_skips_no_tools_list(self, plugin_dir):
        (plugin_dir / "no_tools.py").write_text("x = 42")
        tools = discover_plugins()
        assert tools == []

    def test_multiple_plugins(self, plugin_dir):
        for i in range(3):
            (plugin_dir / f"plugin{i}.py").write_text(f'''
from aulinx.tools.base import Tool, Tier
async def tool_{i}() -> dict:
    return {{"n": {i}}}
TOOLS = [Tool(name="tool_{i}", description="Tool {i}", fn=tool_{i}, tier=Tier.OBSERVE)]
''')
        tools = discover_plugins()
        assert len(tools) == 3

    def test_disabled_via_manifest(self, plugin_dir):
        (plugin_dir / "disabled.py").write_text('''
from aulinx.tools.base import Tool, Tier
async def noop() -> dict:
    return {}
TOOLS = [Tool(name="noop", description="No-op", fn=noop, tier=Tier.OBSERVE)]
''')
        (plugin_dir / "disabled.json").write_text(json.dumps({
            "name": "disabled",
            "enabled": False,
        }))
        tools = discover_plugins()
        assert len(tools) == 0

    def test_manifest_metadata(self, plugin_dir):
        (plugin_dir / "rich.py").write_text('''
from aulinx.tools.base import Tool, Tier
async def rich_tool() -> dict:
    return {}
TOOLS = [Tool(name="rich_tool", description="Rich", fn=rich_tool, tier=Tier.OBSERVE)]
''')
        (plugin_dir / "rich.json").write_text(json.dumps({
            "name": "rich-plugin",
            "version": "2.1.0",
            "description": "A rich plugin",
            "author": "Test Author",
            "tools": ["rich_tool"],
        }))
        tools = discover_plugins()
        assert len(tools) == 1

        plugins = list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "rich-plugin"
        assert plugins[0].version == "2.1.0"
        assert plugins[0].author == "Test Author"


class TestPluginManifest:
    def test_from_json(self):
        m = PluginManifest.from_json({
            "name": "test",
            "version": "1.0",
            "description": "A test plugin",
            "tools": ["tool_a", "tool_b"],
        })
        assert m.name == "test"
        assert m.version == "1.0"
        assert len(m.tool_names) == 2

    def test_to_dict(self):
        m = PluginManifest(name="test", version="1.0", tool_names=["a"])
        d = m.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0"
        assert d["tools"] == ["a"]

    def test_defaults(self):
        m = PluginManifest(name="minimal")
        assert m.version == "0.0.0"
        assert m.enabled is True
        assert m.tool_names == []
