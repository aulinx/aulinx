"""AT-SPI tools — read and interact with application UIs."""

import json
from pathlib import Path
from aulinx.tools.registry import Tool, Tier


async def atspi_get_tree(app_name: str = "", max_depth: int = 3) -> dict | list:
    """Get the accessibility tree for an application."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)

        # Find the target app
        target = None
        for app in desktop:
            try:
                if app_name and app_name.lower() in (app.name or "").lower():
                    target = app
                    break
                elif not app_name:
                    # Use focused app
                    for win in app:
                        state = win.getState()
                        if state.contains(pyatspi.STATE_ACTIVE):
                            target = app
                            break
                    if target:
                        break
            except Exception:
                continue

        if not target:
            return {"error": f"App '{app_name}' not found" if app_name else "No focused app"}

        return _snapshot_node(target, 0, max_depth)

    except ImportError:
        return {"error": "pyatspi not available"}


def _snapshot_node(node, depth: int, max_depth: int) -> dict:
    """Recursively snapshot an accessible node."""
    if depth > max_depth or node is None:
        return {}

    try:
        state = node.getState()
        result = {
            "role": node.getRoleName(),
            "name": node.name or "",
        }

        # Only include showing elements
        if not state.contains(1 << 24):  # STATE_SHOWING approximation
            pass  # still include for now

        # Add text content
        try:
            text_iface = node.queryText()
            char_count = text_iface.characterCount
            if char_count > 0:
                result["text"] = text_iface.getText(0, min(char_count, 200))
        except (NotImplementedError, AttributeError):
            pass

        # Add actions
        try:
            action = node.queryAction()
            result["actions"] = [action.getName(i) for i in range(action.nActions)]
        except (NotImplementedError, AttributeError):
            pass

        # Recurse children
        children = []
        try:
            for child in node:
                if child is not None:
                    child_snap = _snapshot_node(child, depth + 1, max_depth)
                    if child_snap:
                        children.append(child_snap)
        except Exception:
            pass

        if children:
            result["children"] = children

        return result

    except Exception:
        return {}


async def atspi_find_elements(
    role: str = "", name: str = "", app_name: str = ""
) -> list[dict]:
    """Find UI elements by role and/or name."""
    try:
        import pyatspi

        ROLE_MAP = {
            "button": pyatspi.ROLE_PUSH_BUTTON,
            "text": pyatspi.ROLE_TEXT,
            "entry": pyatspi.ROLE_ENTRY,
            "menu": pyatspi.ROLE_MENU,
            "menu_item": pyatspi.ROLE_MENU_ITEM,
            "label": pyatspi.ROLE_LABEL,
            "link": pyatspi.ROLE_LINK,
            "table": pyatspi.ROLE_TABLE,
            "terminal": pyatspi.ROLE_TERMINAL,
        }

        target_role = ROLE_MAP.get(role)
        desktop = pyatspi.Registry.getDesktop(0)
        results = []

        for app in desktop:
            try:
                if app_name and app_name.lower() not in (app.name or "").lower():
                    continue
                _find_recursive(app, target_role, name.lower() if name else "", results, 0, 5)
            except Exception:
                continue

        return results[:20]

    except ImportError:
        return [{"error": "pyatspi not available"}]


def _find_recursive(node, target_role, name_filter: str, results: list, depth: int, max_depth: int):
    """Recursively search for matching elements."""
    if depth > max_depth or node is None or len(results) >= 20:
        return

    try:
        matches = True
        if target_role is not None and node.getRole() != target_role:
            matches = False
        if name_filter and name_filter not in (node.name or "").lower():
            matches = False

        if matches and (target_role is not None or name_filter):
            entry = {
                "role": node.getRoleName(),
                "name": node.name or "",
                "app": node.getApplication().name if node.getApplication() else "",
            }
            try:
                text = node.queryText()
                if text.characterCount > 0:
                    entry["text"] = text.getText(0, min(text.characterCount, 100))
            except (NotImplementedError, AttributeError):
                pass
            try:
                action = node.queryAction()
                entry["actions"] = [action.getName(i) for i in range(action.nActions)]
            except (NotImplementedError, AttributeError):
                pass
            results.append(entry)

        for child in node:
            if child is not None:
                _find_recursive(child, target_role, name_filter, results, depth + 1, max_depth)
    except Exception:
        pass


async def atspi_do_action(app_name: str, element_name: str, action: str = "click") -> str:
    """Perform an action on a UI element (click, activate, etc.)."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)

        for app in desktop:
            try:
                if app_name.lower() not in (app.name or "").lower():
                    continue
                result = _find_and_act(app, element_name.lower(), action, 0, 6)
                if result:
                    return result
            except Exception:
                continue

        return f"Element '{element_name}' not found in '{app_name}'"

    except ImportError:
        return "pyatspi not available"


def _find_and_act(node, name_filter: str, action_name: str, depth: int, max_depth: int) -> str | None:
    """Find an element and perform an action on it."""
    if depth > max_depth or node is None:
        return None

    try:
        if name_filter in (node.name or "").lower():
            try:
                action_iface = node.queryAction()
                for i in range(action_iface.nActions):
                    if action_name.lower() in action_iface.getName(i).lower():
                        action_iface.doAction(i)
                        return f"Performed '{action_iface.getName(i)}' on '{node.name}'"
                # If no matching action name, try the default (index 0)
                if action_iface.nActions > 0:
                    action_iface.doAction(0)
                    return f"Performed '{action_iface.getName(0)}' on '{node.name}'"
            except (NotImplementedError, AttributeError):
                return f"Element '{node.name}' found but has no actions"

        for child in node:
            if child is not None:
                result = _find_and_act(child, name_filter, action_name, depth + 1, max_depth)
                if result:
                    return result
    except Exception:
        pass

    return None


async def atspi_read_text(app_name: str, element_name: str = "") -> str:
    """Read text content from a UI element or the focused element."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)

        for app in desktop:
            try:
                if app_name.lower() not in (app.name or "").lower():
                    continue
                text = _find_text(app, element_name.lower() if element_name else "", 0, 6)
                if text:
                    return text
            except Exception:
                continue

        return f"No text found in '{app_name}'"

    except ImportError:
        return "pyatspi not available"


def _find_text(node, name_filter: str, depth: int, max_depth: int) -> str | None:
    """Find and read text from an element."""
    if depth > max_depth or node is None:
        return None

    try:
        if not name_filter or name_filter in (node.name or "").lower():
            try:
                text_iface = node.queryText()
                count = text_iface.characterCount
                if count > 0:
                    return text_iface.getText(0, min(count, 2000))
            except (NotImplementedError, AttributeError):
                pass

        for child in node:
            if child is not None:
                result = _find_text(child, name_filter, depth + 1, max_depth)
                if result:
                    return result
    except Exception:
        pass

    return None


async def atspi_set_text(app_name: str, element_name: str, text: str) -> str:
    """Set text content in an editable text field."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)

        for app in desktop:
            try:
                if app_name.lower() not in (app.name or "").lower():
                    continue
                result = _find_and_set_text(app, element_name.lower(), text, 0, 6)
                if result:
                    return result
            except Exception:
                continue

        return f"Editable element '{element_name}' not found in '{app_name}'"

    except ImportError:
        return "pyatspi not available"


def _find_and_set_text(node, name_filter: str, text: str, depth: int, max_depth: int) -> str | None:
    """Find an editable element and set its text."""
    if depth > max_depth or node is None:
        return None

    try:
        if name_filter in (node.name or "").lower():
            try:
                editable = node.queryEditableText()
                # Clear existing text
                text_iface = node.queryText()
                existing_len = text_iface.characterCount
                if existing_len > 0:
                    editable.deleteText(0, existing_len)
                # Insert new text
                editable.insertText(0, text, len(text))
                return f"Set text on '{node.name}': '{text[:50]}{'...' if len(text) > 50 else ''}'"
            except (NotImplementedError, AttributeError):
                pass

        for child in node:
            if child is not None:
                result = _find_and_set_text(child, name_filter, text, depth + 1, max_depth)
                if result:
                    return result
    except Exception:
        pass

    return None


async def window_screenshot(method: str = "grim") -> dict:
    """Take a screenshot of the screen or focused window. Returns the file path."""
    import subprocess
    import tempfile
    import time

    filename = f"aulinx-screenshot-{int(time.time())}.png"
    filepath = Path(tempfile.gettempdir()) / filename

    # Try multiple screenshot methods
    commands = {
        "grim": ["grim", str(filepath)],                          # Wayland (wlroots)
        "gnome-screenshot": ["gnome-screenshot", "-f", str(filepath)],  # GNOME
        "scrot": ["scrot", str(filepath)],                         # X11
        "import": ["import", "-window", "root", str(filepath)],   # ImageMagick X11
    }

    # Try preferred method first, then others
    order = [method] + [k for k in commands if k != method]

    for cmd_name in order:
        cmd = commands.get(cmd_name)
        if not cmd:
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and filepath.exists():
                size = filepath.stat().st_size
                return {
                    "path": str(filepath),
                    "size_bytes": size,
                    "method": cmd_name,
                }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return {"error": "No screenshot tool available (install grim, gnome-screenshot, or scrot)"}


TOOLS = [
    Tool(
        name="atspi_get_tree",
        description="Get the accessibility tree for an app (shows UI elements, text, actions)",
        fn=atspi_get_tree,
        parameters={"app_name": "string (optional, default: focused app)", "max_depth": "int (default 3)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="atspi_find_elements",
        description="Find UI elements by role (button/text/entry/menu/link/terminal) and/or name",
        fn=atspi_find_elements,
        parameters={"role": "string (optional)", "name": "string (optional)", "app_name": "string (optional)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="atspi_do_action",
        description="Click/activate a UI element by name in a specific app",
        fn=atspi_do_action,
        parameters={"app_name": "string", "element_name": "string", "action": "string (default: click)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="atspi_read_text",
        description="Read text content from a UI element in an app",
        fn=atspi_read_text,
        parameters={"app_name": "string", "element_name": "string (optional)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="atspi_set_text",
        description="Set text in an editable field (text entry, search bar, etc.)",
        fn=atspi_set_text,
        parameters={"app_name": "string", "element_name": "string", "text": "string"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="window_screenshot",
        description="Take a screenshot of the screen. Returns file path to the PNG.",
        fn=window_screenshot,
        parameters={"method": "grim|gnome-screenshot|scrot (default: grim)"},
        tier=Tier.OBSERVE,
    ),
]
