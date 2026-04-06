"""Application management tools."""

import shutil
import subprocess

from aulinx.tools.base import Tier, Tool


async def app_launch(app: str) -> str:
    """Launch an application by name or command."""
    # Try common launch methods
    for cmd in [
        ["gtk-launch", app],
        ["xdg-open", app] if "/" in app or "." in app else None,
        [app],
    ]:
        if cmd is None:
            continue
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Launched: {app}"
        except Exception:
            continue

    return f"Could not launch: {app}"


async def app_list_running() -> list[str]:
    """List running GUI applications via AT-SPI."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        return [app.name for app in desktop if app.name]
    except ImportError:
        return ["pyatspi not available"]


TOOLS = [
    Tool(
        name="app_launch",
        description="Launch an application by name (e.g. 'firefox', 'nautilus', 'gnome-terminal')",
        fn=app_launch,
        parameters={"app": "string"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="app_list_running",
        description="List all running GUI applications",
        fn=app_list_running,
        tier=Tier.OBSERVE,
    ),
]
