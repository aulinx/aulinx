"""Window management tools — list, focus, close windows."""

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
]
