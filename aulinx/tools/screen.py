"""Screen tools — screenshot specific windows, record screen."""

import subprocess
import tempfile
import time
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def screenshot_window(app_name: str = "") -> dict:
    """Take a screenshot of a specific window by app name, or the focused window."""
    filepath = Path(tempfile.gettempdir()) / f"aulinx-win-{int(time.time())}.png"

    if app_name:
        # Try to find window ID and capture it
        try:
            # Get window ID via xdotool
            result = subprocess.run(
                ["xdotool", "search", "--name", app_name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                win_id = result.stdout.strip().splitlines()[0]
                # Capture with import (ImageMagick)
                cap = subprocess.run(
                    ["import", "-window", win_id, str(filepath)],
                    capture_output=True, text=True, timeout=10,
                )
                if cap.returncode == 0 and filepath.exists():
                    return {"path": str(filepath), "window": app_name, "size_bytes": filepath.stat().st_size}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Fallback: full screen screenshot
    for cmd in [
        ["gnome-screenshot", "-w", "-f", str(filepath)],  # GNOME focused window
        ["grim", str(filepath)],
        ["scrot", "-u", str(filepath)],  # focused window
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and filepath.exists():
                return {"path": str(filepath), "size_bytes": filepath.stat().st_size}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return {"error": "No screenshot tool available"}


async def workspace_switch(number: int) -> dict:
    """Switch to a virtual workspace/desktop by number (0-based)."""
    # Try wmctrl
    try:
        result = subprocess.run(
            ["wmctrl", "-s", str(number)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"switched": True, "workspace": number, "via": "wmctrl"}
    except FileNotFoundError:
        pass

    # Try xdotool
    try:
        result = subprocess.run(
            ["xdotool", "set_desktop", str(number)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"switched": True, "workspace": number, "via": "xdotool"}
    except FileNotFoundError:
        pass

    # Try GNOME D-Bus
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Shell",
             "--object-path", "/org/gnome/Shell",
             "--method", "org.gnome.Shell.Eval",
             f"global.workspace_manager.get_workspace_by_index({number}).activate(global.get_current_time())"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"switched": True, "workspace": number, "via": "gnome-shell"}
    except FileNotFoundError:
        pass

    return {"error": "No workspace switching tool available (install wmctrl or xdotool)"}


async def workspace_list() -> dict:
    """List available workspaces."""
    # Try wmctrl
    try:
        result = subprocess.run(
            ["wmctrl", "-d"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            workspaces = []
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    workspaces.append({
                        "number": int(parts[0]),
                        "active": parts[1] == "*",
                        "name": parts[-1] if len(parts) > 8 else f"Workspace {parts[0]}",
                    })
            return {"workspaces": workspaces, "count": len(workspaces)}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"error": "wmctrl not installed"}


TOOLS = [
    Tool(
        name="screenshot_window",
        description="Take a screenshot of a specific window by app name, or the focused window",
        fn=screenshot_window,
        parameters={"app_name": "string (optional, e.g. 'Firefox', 'gedit'. Omit for focused window)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="workspace_switch",
        description="Switch to a virtual workspace/desktop by number (0-based)",
        fn=workspace_switch,
        parameters={"number": "int (workspace number, 0-based)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="workspace_list",
        description="List all virtual workspaces and which one is active",
        fn=workspace_list,
        tier=Tier.OBSERVE,
    ),
]
