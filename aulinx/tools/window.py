"""Window management tools — list, focus, move, resize, close windows."""

import subprocess

from aulinx.tools.base import Tier, Tool


async def window_list() -> list[dict]:
    """List all open windows."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        windows = []
        for app in desktop:
            try:
                for win in app:
                    if win.getRoleName() in ("frame", "dialog"):
                        state = win.getState()
                        windows.append({
                            "app": app.name,
                            "title": win.name,
                            "role": win.getRoleName(),
                            "active": state.contains(pyatspi.STATE_ACTIVE),
                        })
            except Exception:
                continue
        return windows
    except ImportError:
        return [{"error": "pyatspi not available"}]


async def window_get_focused() -> dict | None:
    """Get the currently focused window."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            try:
                for win in app:
                    state = win.getState()
                    if state.contains(pyatspi.STATE_ACTIVE):
                        return {"app": app.name, "title": win.name}
            except Exception:
                continue
        return None
    except ImportError:
        return {"error": "pyatspi not available"}


async def window_focus(title: str) -> dict:
    """Focus/activate a window by title (partial match)."""
    try:
        result = subprocess.run(
            ["wmctrl", "-a", title],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"focused": True, "title": title}
    except FileNotFoundError:
        pass

    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title, "windowactivate"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"focused": True, "title": title, "via": "xdotool"}
    except FileNotFoundError:
        pass

    return {"error": f"Could not focus window '{title}'. Install wmctrl or xdotool."}


async def window_close(title: str) -> dict:
    """Close a window by title (partial match)."""
    try:
        result = subprocess.run(
            ["wmctrl", "-c", title],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"closed": True, "title": title}
    except FileNotFoundError:
        pass

    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title, "windowclose"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"closed": True, "title": title, "via": "xdotool"}
    except FileNotFoundError:
        pass

    return {"error": f"Could not close window '{title}'. Install wmctrl or xdotool."}


async def window_move_resize(title: str, x: int = -1, y: int = -1, width: int = -1, height: int = -1) -> dict:
    """Move and/or resize a window by title. Use -1 to keep current value."""
    try:
        result = subprocess.run(
            ["wmctrl", "-r", title, "-e", f"0,{x},{y},{width},{height}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"moved": True, "title": title, "x": x, "y": y, "width": width, "height": height}
        return {"error": result.stderr.strip() or "wmctrl failed"}
    except FileNotFoundError:
        return {"error": "wmctrl not installed. Run: sudo apt install wmctrl"}


async def window_minimize(title: str) -> dict:
    """Minimize a window by title."""
    try:
        # Get window ID
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            win_id = result.stdout.strip().splitlines()[0]
            subprocess.run(["xdotool", "windowminimize", win_id], capture_output=True, timeout=5)
            return {"minimized": True, "title": title}
    except FileNotFoundError:
        pass

    return {"error": "xdotool not installed"}


async def window_maximize(title: str) -> dict:
    """Maximize a window by title."""
    try:
        result = subprocess.run(
            ["wmctrl", "-r", title, "-b", "add,maximized_vert,maximized_horz"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"maximized": True, "title": title}
    except FileNotFoundError:
        pass

    return {"error": "wmctrl not installed"}


TOOLS = [
    Tool(
        name="window_list",
        description="List all open windows with app name, title, and active state",
        fn=window_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="window_get_focused",
        description="Get the currently focused window",
        fn=window_get_focused,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="window_focus",
        description="Focus/activate a window by title (e.g. 'Firefox', 'gedit')",
        fn=window_focus,
        parameters={"title": "string (window title, partial match)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="window_close",
        description="Close a window by title. May lose unsaved data.",
        fn=window_close,
        parameters={"title": "string (window title, partial match)"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="window_move_resize",
        description="Move and/or resize a window. Use -1 to keep current value.",
        fn=window_move_resize,
        parameters={
            "title": "string (window title)",
            "x": "int (x position, default -1 = keep)",
            "y": "int (y position, default -1 = keep)",
            "width": "int (default -1 = keep)",
            "height": "int (default -1 = keep)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="window_minimize",
        description="Minimize a window by title",
        fn=window_minimize,
        parameters={"title": "string"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="window_maximize",
        description="Maximize a window by title",
        fn=window_maximize,
        parameters={"title": "string"},
        tier=Tier.LOW_RISK,
    ),
]
