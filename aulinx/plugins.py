"""Plugin system — auto-discovers and loads custom tools from user plugins directory.

Plugins are Python files in ~/.config/aulinx/plugins/ that define a TOOLS list,
exactly like built-in tool modules. They are loaded at startup and can be
hot-reloaded.

Plugins can optionally include a plugin.json manifest:

    {
        "name": "spotify",
        "version": "1.0.0",
        "description": "Spotify media control",
        "author": "Your Name",
        "tools": ["spotify_play", "spotify_pause", "spotify_next"]
    }

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

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from aulinx.tools.base import Tool

console = Console()

PLUGINS_DIR = Path.home() / ".config/aulinx/plugins"


@dataclass
class PluginManifest:
    """Metadata about a plugin, loaded from plugin.json or inferred from the module."""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    tool_names: list[str] = field(default_factory=list)
    path: str = ""
    enabled: bool = True

    @staticmethod
    def from_json(data: dict, path: str = "") -> PluginManifest:
        return PluginManifest(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            tool_names=data.get("tools", []),
            path=path,
            enabled=data.get("enabled", True),
        )

    @staticmethod
    def from_module(name: str, tools: list[Tool], path: str = "") -> PluginManifest:
        return PluginManifest(
            name=name,
            tool_names=[t.name for t in tools],
            path=path,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tools": self.tool_names,
            "enabled": self.enabled,
        }


def discover_plugins() -> list[Tool]:
    """Discover and load all plugins from the plugins directory.

    Returns a list of Tool objects from all successfully loaded plugins.
    Supports both single-file plugins (foo.py) and directory plugins
    (foo/ with plugin.json + __init__.py).
    """
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        _create_example_plugin()
        return []

    tools = []

    # Load single-file plugins (*.py)
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue

        # Check for adjacent manifest
        manifest = _load_manifest(path.with_suffix(".json"))
        if manifest and not manifest.enabled:
            continue

        try:
            loaded = _load_plugin(path)
            tools.extend(loaded)
            if loaded:
                console.print(f"[dim]  Plugin: {path.name} ({len(loaded)} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]  Plugin error in {path.name}: {e}[/yellow]")

    # Load directory plugins (dir/plugin.json + dir/__init__.py)
    for d in sorted(PLUGINS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        init_file = d / "__init__.py"
        manifest_file = d / "plugin.json"
        if not init_file.exists():
            continue

        manifest = _load_manifest(manifest_file)
        if manifest and not manifest.enabled:
            continue

        try:
            loaded = _load_plugin(init_file)
            tools.extend(loaded)
            if loaded:
                name = manifest.name if manifest else d.name
                console.print(f"[dim]  Plugin: {name} ({len(loaded)} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]  Plugin error in {d.name}: {e}[/yellow]")

    return tools


def _load_manifest(path: Path) -> PluginManifest | None:
    """Load a plugin.json manifest file."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PluginManifest.from_json(data, str(path))
    except (json.JSONDecodeError, OSError):
        return None


def list_plugins() -> list[PluginManifest]:
    """List all installed plugins with their metadata."""
    if not PLUGINS_DIR.exists():
        return []

    manifests = []

    # Single-file plugins
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        manifest = _load_manifest(path.with_suffix(".json"))
        if manifest:
            manifests.append(manifest)
        else:
            # Infer from module
            try:
                tools = _load_plugin(path)
                manifests.append(PluginManifest.from_module(path.stem, tools, str(path)))
            except Exception:
                manifests.append(PluginManifest(name=path.stem, path=str(path), enabled=False))

    # Directory plugins
    for d in sorted(PLUGINS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        manifest_file = d / "plugin.json"
        manifest = _load_manifest(manifest_file)
        if manifest:
            manifests.append(manifest)
        elif (d / "__init__.py").exists():
            try:
                tools = _load_plugin(d / "__init__.py")
                manifests.append(PluginManifest.from_module(d.name, tools, str(d)))
            except Exception:
                manifests.append(PluginManifest(name=d.name, path=str(d), enabled=False))

    return manifests


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
