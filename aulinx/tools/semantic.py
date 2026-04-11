"""Semantic desktop tools — AI-native desktop understanding.

Connects to the aulinx semantic daemon or compositor via Unix socket
and provides tools for querying the scene graph, finding elements,
activating controls, and subscribing to desktop events.

These tools replace screenshot-based perception with structured
semantic queries — 100x cheaper and real-time.
"""

import json
import os
import socket
from typing import Optional

from .base import Tier, Tool

# Persistent connection to the semantic socket
_connection: Optional[socket.socket] = None
_request_id = 0


def _get_socket_path() -> str:
    """Get the semantic IPC socket path."""
    if "AULINX_SOCKET" in os.environ:
        return os.environ["AULINX_SOCKET"]
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg:
        return os.path.join(xdg, "aulinx", "semantic.sock")
    return "/tmp/aulinx-semantic.sock"


def _connect() -> socket.socket:
    """Get or create a connection to the semantic daemon."""
    global _connection
    if _connection is not None:
        return _connection
    path = _get_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    sock.settimeout(5.0)
    _connection = sock
    return sock


def _send(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request and return the result."""
    global _request_id
    _request_id += 1

    sock = _connect()
    request = {
        "jsonrpc": "2.0",
        "id": _request_id,
        "method": method,
        "params": params or {},
    }
    line = json.dumps(request) + "\n"
    sock.sendall(line.encode())

    # Read response
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("Semantic daemon disconnected")
        data += chunk

    response = json.loads(data.decode().strip())
    if "error" in response and response["error"]:
        raise RuntimeError(f"Semantic error: {response['error']['message']}")
    return response.get("result", {})


def _is_available() -> bool:
    """Check if the semantic daemon/compositor is running."""
    path = _get_socket_path()
    return os.path.exists(path)


# ---- Tools ----


@Tool(
    description="List all windows on the desktop with semantic info",
    tier=Tier.OBSERVE,
)
async def scene_windows() -> dict:
    """Get all visible windows with titles, app IDs, geometry, and focus state."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return {"windows": _send("scene.windows")}


@Tool(
    description="Get the full semantic scene graph",
    tier=Tier.OBSERVE,
)
async def scene_graph() -> dict:
    """Get the complete semantic scene graph including all elements."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return {"graph": _send("scene.graph")}


@Tool(
    description="Get a single window's semantic tree",
    tier=Tier.OBSERVE,
)
async def scene_window(window_id: int) -> dict:
    """Get detailed semantic data for a specific window."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return {"window": _send("scene.window", {"window_id": window_id})}


@Tool(
    description="Find UI elements by text (button labels, titles)",
    tier=Tier.OBSERVE,
)
async def scene_find(query: str) -> dict:
    """Find elements whose labels or titles contain the query text."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return {"results": _send("scene.find", {"query": query})}


@Tool(
    description="Find UI elements by role (button, text_field, etc.)",
    tier=Tier.OBSERVE,
)
async def scene_find_by_role(role: str) -> dict:
    """Find all elements of a given role type."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return {"results": _send("scene.find_by_role", {"role": role})}


@Tool(
    description="Get the currently focused window and element",
    tier=Tier.OBSERVE,
)
async def scene_focused() -> dict:
    """Get which window and element currently has input focus."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("scene.focused")


@Tool(
    description="Click/activate a UI element by its node ID",
    tier=Tier.MUTATE,
)
async def element_activate(node_id: int) -> dict:
    """Activate (click/press) an element found via scene_find."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("element.activate", {"node_id": node_id})


@Tool(
    description="Set the text value of an input field",
    tier=Tier.MUTATE,
)
async def element_set_value(node_id: int, value: str) -> dict:
    """Set the text value of a text field or input element."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("element.set_value", {"node_id": node_id, "value": value})


@Tool(
    description="Focus a window by its ID",
    tier=Tier.MUTATE,
)
async def window_focus(window_id: int) -> dict:
    """Bring a window to the foreground and give it input focus."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("window.focus", {"window_id": window_id})


@Tool(
    description="Close a window by its ID",
    tier=Tier.DESTRUCTIVE,
)
async def window_close(window_id: int) -> dict:
    """Close a window."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("window.close", {"window_id": window_id})


@Tool(
    description="Move/resize a window (compositor only)",
    tier=Tier.MUTATE,
)
async def window_move(window_id: int, x: int, y: int, w: int, h: int) -> dict:
    """Move and resize a window. Automatically switches to floating mode."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("window.move", {
        "window_id": window_id, "x": x, "y": y, "w": w, "h": h,
    })


@Tool(
    description="Type text into the focused window (compositor only)",
    tier=Tier.MUTATE,
)
async def input_type(text: str) -> dict:
    """Type text into the currently focused window via virtual keyboard."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("input.type", {"text": text})


@Tool(
    description="Send a keyboard shortcut (compositor only)",
    tier=Tier.MUTATE,
)
async def input_key(combo: str) -> dict:
    """Send a keyboard shortcut like 'ctrl+c', 'alt+f4', 'super+1'."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("input.key", {"combo": combo})


@Tool(
    description="Move/click the mouse (compositor only)",
    tier=Tier.MUTATE,
)
async def input_mouse(
    x: float, y: float,
    button: int = None, action: str = "click",
) -> dict:
    """Move the pointer to (x, y) and optionally click."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    params = {"x": x, "y": y}
    if button is not None:
        params["button"] = button
        params["action"] = action
    return _send("input.mouse", params)


@Tool(
    description="Take a screenshot of the entire screen (compositor only)",
    tier=Tier.OBSERVE,
)
async def screen_capture() -> dict:
    """Capture the screen as a base64-encoded PNG."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("screen.capture")


@Tool(
    description="Take a screenshot of a specific window (compositor only)",
    tier=Tier.OBSERVE,
)
async def window_screenshot(window_id: int) -> dict:
    """Capture a specific window as a base64-encoded PNG."""
    if not _is_available():
        return {"error": "Semantic daemon not running"}
    return _send("window.screenshot", {"window_id": window_id})
