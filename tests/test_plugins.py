"""Tests for plugin system."""

from unittest.mock import patch

import pytest

from aulinx.plugins import discover_plugins


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
