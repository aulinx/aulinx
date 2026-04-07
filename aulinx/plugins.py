"""Plugin system — auto-discovers and loads custom tools from user plugins directory.

Plugins are Python files in ~/.config/aulinx/plugins/ that define a TOOLS list,
exactly like built-in tool modules. They are loaded at startup and can be
hot-reloaded.

Example plugin (~/.config/aulinx/plugins/spotify.py):

    from aulinx.tools.base import Tool, Tier

    async def spotify_play(query: str = "") -> dict:
        import subprocess
        cmd = ["dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
               "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Play"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return {"playing": result.returncode == 0}

    TOOLS = [
        Tool(name="spotify_play", description="Play music on Spotify",
             fn=spotify_play, tier=Tier.LOW_RISK),
    ]
"""

import importlib.util
import sys
from pathlib import Path

from rich.console import Console

from aulinx.tools.base import Tool

console = Console()

PLUGINS_DIR = Path.home() / ".config/aulinx/plugins"


def discover_plugins() -> list[Tool]:
    """Discover and load all plugins from the plugins directory.

    Returns a list of Tool objects from all successfully loaded plugins.
    """
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        _create_example_plugin()
        return []

    tools = []
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            loaded = _load_plugin(path)
            tools.extend(loaded)
            if loaded:
                console.print(f"[dim]  Plugin: {path.name} ({len(loaded)} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]  Plugin error in {path.name}: {e}[/yellow]")

    return tools


def _load_plugin(path: Path) -> list[Tool]:
    """Load a single plugin file and return its TOOLS list."""
    spec = importlib.util.spec_from_file_location(f"aulinx_plugin_{path.stem}", str(path))
    if spec is None or spec.loader is None:
        return []

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    tools = getattr(module, "TOOLS", [])
    if not isinstance(tools, list):
        return []

    # Validate that all items are Tool instances
    valid = [t for t in tools if isinstance(t, Tool)]
    return valid


def reload_plugins() -> list[Tool]:
    """Reload all plugins (for hot-reload support)."""
    # Remove old plugin modules
    to_remove = [k for k in sys.modules if k.startswith("aulinx_plugin_")]
    for k in to_remove:
        del sys.modules[k]

    return discover_plugins()


def _create_example_plugin():
    """Create an example plugin file to help users get started."""
    example = PLUGINS_DIR / "_example.py"
    if example.exists():
        return

    example.write_text('''\
"""Example Aulinx plugin — rename this file (remove the underscore) to activate.

Plugins are Python files that define a TOOLS list with Tool objects.
See docs/adding-tools.md for the full guide.
"""

from aulinx.tools.base import Tier, Tool


async def hello_world(name: str = "World") -> dict:
    """A simple example tool."""
    return {"message": f"Hello, {name}! This is a custom plugin."}


TOOLS = [
    Tool(
        name="hello_world",
        description="A simple greeting tool (example plugin)",
        fn=hello_world,
        parameters={"name": "string (default: World)"},
        tier=Tier.OBSERVE,
    ),
]
''')
