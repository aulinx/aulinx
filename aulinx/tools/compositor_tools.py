"""Compositor tools — interact with the Aulinx compositor via IPC.

These tools are available when the agent runs inside the Aulinx compositor
(or connects to it via the semantic IPC socket). They provide direct
compositor-level control: window management, input injection, screenshots,
and real-time event subscriptions.

Falls back gracefully if the compositor is not running.
"""

import base64
import json
import os
import socket
from typing import Optional

from aulinx.tools.base import Tier, Tool


def _get_socket_path() -> str:
    """Get the compositor IPC socket path."""
    if "AULINX_SOCKET" in os.environ:
        return os.environ["AULINX_SOCKET"]
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg:
        return os.path.join(xdg, "aulinx", "semantic.sock")
    return "/tmp/aulinx-semantic.sock"


def _rpc(method: str, params: Optional[dict] = None) -> dict:
    """Send a JSON-RPC request to the compositor."""
    path = _get_socket_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(path)
    except (FileNotFoundError, ConnectionRefusedError):
        raise RuntimeError(
            f"Compositor not running (socket {path} not found). "
            "Start with: aulinx-compositor"
        )

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    s.sendall((json.dumps(request) + "\n").encode())

    data = b""
    while b"\n" not in data:
        chunk = s.recv(1048576)
        if not chunk:
            break
        data += chunk
    s.close()

    response = json.loads(data.decode().strip())
    if "error" in response:
        raise RuntimeError(response["error"].get("message", str(response["error"])))
    return response.get("result")


# ---- Tool implementations ----


async def compositor_status() -> dict:
    """Get compositor status: version, uptime, window count, backend, and config."""
    return _rpc("scene.status")


async def compositor_ping() -> str:
    """Quick health check — verify the compositor is responsive."""
    try:
        result = _rpc("ping")
        if result.get("pong"):
            return f"Compositor alive (v{result.get('version', '?')})"
        return "Compositor not responding"
    except Exception as e:
        return f"Compositor unreachable: {e}"


async def compositor_config() -> dict:
    """Get the current compositor configuration (layout, appearance, terminal)."""
    return _rpc("scene.config")


async def compositor_suggest() -> list[dict]:
    """Get suggested next actions from the compositor based on current desktop state.

    Returns a list of suggestions with action, params, and reason.
    Use this when you're unsure what to do next.
    """
    return _rpc("scene.suggest").get("suggestions", [])


async def compositor_summary() -> str:
    """Get a complete desktop summary in one call — description, layout, suggestions, status.

    This is the best tool to call first when starting a new task.
    Returns text + ASCII map + suggestions, all in one response.
    """
    result = _rpc("scene.summary")
    parts = []
    parts.append(result.get("description", ""))
    parts.append("")
    parts.append(result.get("ascii", ""))
    suggestions = result.get("suggestions", [])
    if suggestions:
        parts.append("\nSuggested actions:")
        for s in suggestions:
            parts.append(f"  -> {s.get('action')}: {s.get('reason')}")
    st = result.get("status", {})
    parts.append(f"\n({st.get('window_count', 0)} windows, {st.get('uptime_seconds', 0)}s uptime, {st.get('backend', '?')} backend)")
    return "\n".join(parts)


async def compositor_ascii() -> str:
    """Get an ASCII art map of the desktop layout.

    Text-only agents can 'see' the desktop without images. Shows window positions and IDs.
    """
    return _rpc("scene.ascii").get("ascii", "empty")


async def compositor_describe() -> str:
    """Get a natural language description of the desktop.

    Returns text like: '2 in master+stack layout. Window 1 [master]: "foot" — 761x792'
    Use this to understand what's on screen before taking action.
    """
    return _rpc("scene.describe").get("description", "empty")


async def compositor_windows() -> list[dict]:
    """List all windows in the Aulinx compositor with metadata and geometry."""
    return _rpc("scene.windows")


async def compositor_focused() -> dict:
    """Get the currently focused window in the compositor."""
    return _rpc("scene.focused")


async def compositor_find_window(title: str = "", app_id: str = "") -> list[dict]:
    """Find windows matching a title or app_id (case-insensitive substring match)."""
    params = {}
    if title:
        params["title"] = title
    if app_id:
        params["app_id"] = app_id
    return _rpc("scene.find_window", params)


async def compositor_element_at(x: float, y: float) -> dict:
    """Query what window is at the given screen coordinates."""
    return _rpc("scene.element_at", {"x": x, "y": y})


async def compositor_screenshot(save_path: str = "/tmp/aulinx_screenshot.png") -> str:
    """Take a screenshot of the compositor and save as PNG.

    Returns the file path where the screenshot was saved.
    """
    result = _rpc("scene.screenshot")
    png_data = base64.b64decode(result["data"])
    with open(save_path, "wb") as f:
        f.write(png_data)
    return f"Screenshot saved to {save_path} ({len(png_data)} bytes)"


async def compositor_annotated_screenshot(save_path: str = "/tmp/aulinx_annotated.png") -> str:
    """Take an annotated screenshot — window boundaries and IDs overlaid on the image.

    AI agents with vision can see both content and semantic structure in one image.
    Like Agent S3's Set-of-Marks but from compositor ground truth.
    """
    result = _rpc("scene.annotated_screenshot")
    import base64
    png_data = base64.b64decode(result["data"])
    with open(save_path, "wb") as f:
        f.write(png_data)
    return f"Annotated screenshot saved to {save_path} ({len(png_data)} bytes)"


async def compositor_type_text(text: str) -> str:
    """Type text into the focused window in the compositor.

    Handles uppercase letters automatically via shift key injection.
    """
    _rpc("input.type", {"text": text})
    return f"Typed {len(text)} characters"


async def compositor_key(combo: str) -> str:
    """Send a key combination to the focused window.

    Examples: 'ctrl+s', 'ctrl+shift+z', 'super+return', 'escape', 'F1'
    """
    _rpc("input.key", {"combo": combo})
    return f"Sent key combo: {combo}"


async def compositor_click(x: float, y: float, button: int = 1) -> str:
    """Click at screen coordinates in the compositor.

    button: 1=left (default), 2=middle, 3=right
    """
    _rpc("input.click", {"x": x, "y": y, "button": button})
    return f"Clicked at ({x}, {y}) button={button}"


async def compositor_scroll(x: float, y: float, dy: float = -3.0) -> str:
    """Scroll at screen coordinates. Negative dy = scroll up, positive = down."""
    _rpc("input.scroll", {"x": x, "y": y, "dy": dy})
    return f"Scrolled at ({x}, {y}) dy={dy}"


async def compositor_drag(x1: float, y1: float, x2: float, y2: float) -> str:
    """Drag from (x1,y1) to (x2,y2) in the compositor."""
    _rpc("input.drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return f"Dragged ({x1},{y1}) -> ({x2},{y2})"


async def compositor_focus_window(window_id: int) -> str:
    """Focus a window by its compositor ID."""
    _rpc("window.focus", {"window_id": window_id})
    return f"Focused window {window_id}"


async def compositor_minimize(window_id: int) -> str:
    """Minimize a window — removes it from the tiling layout."""
    _rpc("window.minimize", {"window_id": window_id})
    return f"Minimized window {window_id}"


async def compositor_close_window(window_id: int) -> str:
    """Close a window by its compositor ID."""
    _rpc("window.close", {"window_id": window_id})
    return f"Closed window {window_id}"


async def compositor_spawn(command: str) -> str:
    """Launch an application inside the Aulinx compositor.

    The app will appear as a new tiled window.
    """
    result = _rpc("window.spawn", {"command": command, "args": []})
    pid = result.get("pid", "?")
    return f"Spawned '{command}' (pid={pid})"


async def compositor_swap_master(window_id: int) -> str:
    """Swap a window to the master (largest) position in the tiling layout."""
    _rpc("window.swap_master", {"window_id": window_id})
    return f"Swapped window {window_id} to master"


async def compositor_batch(actions: str) -> dict:
    """Execute multiple input actions atomically in one IPC call.

    Actions is a JSON array string, e.g.:
    [{"method":"input.type","params":{"text":"hello"}},{"method":"input.key","params":{"combo":"return"}}]

    Supported methods: input.type, input.key, input.click, input.move, sleep.
    """
    import json as _json
    parsed = _json.loads(actions)
    return _rpc("input.batch", {"actions": parsed})


async def compositor_set_ratio(ratio: float = 0.6) -> str:
    """Set the master window width ratio (0.2-0.8). Default is 0.6."""
    result = _rpc("layout.set_ratio", {"ratio": ratio})
    return f"Master ratio set to {result.get('ratio', ratio)}"


async def compositor_set_gap(gap: int = 4) -> str:
    """Set the gap between tiled windows in pixels (0-32)."""
    result = _rpc("layout.set_gap", {"gap": gap})
    return f"Gap set to {result.get('gap', gap)}px"


async def compositor_diff() -> list[dict]:
    """Get scene changes since the last query. Returns list of events (window_opened, window_closed, etc)."""
    return _rpc("scene.diff").get("events", [])


async def compositor_wait_for(title: str = "", app_id: str = "", count: int = 0, timeout: float = 10.0) -> str:
    """Wait until a window condition is met.

    Args:
        title: Window title substring to match.
        app_id: App ID substring to match.
        count: Minimum number of windows required.
        timeout: Maximum seconds to wait.
    """
    import time
    params = {}
    if title:
        params["title"] = title
    if app_id:
        params["app_id"] = app_id
    if count:
        params["count"] = count

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _rpc("scene.wait_for", params)
        if result.get("matched"):
            return "Condition met"
        time.sleep(0.3)
    return "Timed out waiting for condition"


async def compositor_run_and_type(command: str, text: str, wait_seconds: float = 3.0) -> str:
    """Spawn an app, wait for it to appear, then type text into it.

    This is the most common AI agent pattern: launch → wait → interact.
    """
    import time

    # Spawn
    result = _rpc("window.spawn", {"command": command, "args": []})
    pid = result.get("pid", "?")

    # Wait for the window to appear
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        r = _rpc("scene.wait_for", {"count": 1})
        if r.get("matched"):
            break
        time.sleep(0.3)

    time.sleep(0.5)  # Brief settle time

    # Type text
    _rpc("input.type", {"text": text})
    return f"Spawned '{command}' (pid={pid}) and typed {len(text)} chars"


async def compositor_window_count() -> int:
    """Get the number of open windows in the compositor."""
    result = _rpc("scene.window_count")
    return result["count"]


# ---- Tool registration ----


def _is_compositor_available() -> bool:
    """Check if the compositor IPC socket exists."""
    path = _get_socket_path()
    return os.path.exists(path)


TOOLS = [
    Tool("compositor_ping", "Health check — verify compositor is responsive",
         compositor_ping, tier=Tier.OBSERVE),
    Tool("compositor_config", "Get compositor configuration (gaps, ratio, colors, terminal)",
         compositor_config, tier=Tier.OBSERVE),
    Tool("compositor_suggest", "Get suggested next actions based on desktop state",
         compositor_suggest, tier=Tier.OBSERVE),
    Tool("compositor_summary", "Complete desktop context in one call (description + ASCII + suggestions)",
         compositor_summary, tier=Tier.OBSERVE),
    Tool("compositor_ascii", "ASCII art map of desktop layout",
         compositor_ascii, tier=Tier.OBSERVE),
    Tool("compositor_describe", "Describe the desktop in natural language",
         compositor_describe, tier=Tier.OBSERVE),
    Tool("compositor_status", "Get compositor status (version, uptime, windows, config)",
         compositor_status, tier=Tier.OBSERVE),
    Tool("compositor_windows", "List all windows in the Aulinx compositor",
         compositor_windows, tier=Tier.OBSERVE),
    Tool("compositor_focused", "Get the focused window in the compositor",
         compositor_focused, tier=Tier.OBSERVE),
    Tool("compositor_find_window", "Find windows by title or app_id",
         compositor_find_window,
         parameters={"title": "string — title substring", "app_id": "string — app ID substring"},
         tier=Tier.OBSERVE),
    Tool("compositor_element_at", "Query what's at screen coordinates",
         compositor_element_at,
         parameters={"x": "float — X coordinate", "y": "float — Y coordinate"},
         tier=Tier.OBSERVE),
    Tool("compositor_annotated_screenshot", "Screenshot with window boundaries + labels overlaid",
         compositor_annotated_screenshot,
         parameters={"save_path": "string — Path to save PNG"},
         tier=Tier.OBSERVE),
    Tool("compositor_screenshot", "Take a compositor screenshot",
         compositor_screenshot,
         parameters={"save_path": "string — Path to save PNG (default: /tmp/aulinx_screenshot.png)"},
         tier=Tier.OBSERVE),
    Tool("compositor_window_count", "Count open compositor windows",
         compositor_window_count, tier=Tier.OBSERVE),
    Tool("compositor_type", "Type text into focused compositor window",
         compositor_type_text,
         parameters={"text": "string — Text to type"},
         tier=Tier.LOW_RISK),
    Tool("compositor_key", "Send key combo to focused window (e.g. ctrl+s)",
         compositor_key,
         parameters={"combo": "string — Key combination"},
         tier=Tier.LOW_RISK),
    Tool("compositor_click", "Click at coordinates in compositor",
         compositor_click,
         parameters={"x": "float — X", "y": "float — Y", "button": "int — 1=left 2=mid 3=right"},
         tier=Tier.LOW_RISK),
    Tool("compositor_scroll", "Scroll at coordinates",
         compositor_scroll,
         parameters={"x": "float — X", "y": "float — Y", "dy": "float — scroll amount"},
         tier=Tier.LOW_RISK),
    Tool("compositor_drag", "Drag from one point to another",
         compositor_drag,
         parameters={"x1": "float", "y1": "float", "x2": "float", "y2": "float"},
         tier=Tier.LOW_RISK),
    Tool("compositor_focus", "Focus a compositor window by ID",
         compositor_focus_window,
         parameters={"window_id": "int — Window ID"},
         tier=Tier.LOW_RISK),
    Tool("compositor_minimize", "Minimize window (remove from tiling layout)",
         compositor_minimize,
         parameters={"window_id": "int — Window ID"},
         tier=Tier.MUTATE),
    Tool("compositor_close", "Close a compositor window by ID",
         compositor_close_window,
         parameters={"window_id": "int — Window ID"},
         tier=Tier.MUTATE),
    Tool("compositor_spawn", "Launch an app in the compositor",
         compositor_spawn,
         parameters={"command": "string — Command to run (e.g. 'firefox')"},
         tier=Tier.MUTATE),
    Tool("compositor_swap_master", "Swap window to master position",
         compositor_swap_master,
         parameters={"window_id": "int — Window ID"},
         tier=Tier.LOW_RISK),
    Tool("compositor_batch", "Execute multiple input actions atomically",
         compositor_batch,
         parameters={"actions": "string — JSON array of actions [{method, params}, ...]"},
         tier=Tier.LOW_RISK),
    Tool("compositor_set_ratio", "Set master window width ratio (0.2-0.8)",
         compositor_set_ratio,
         parameters={"ratio": "float — master width ratio (default 0.6)"},
         tier=Tier.LOW_RISK),
    Tool("compositor_set_gap", "Set gap between tiled windows in pixels",
         compositor_set_gap,
         parameters={"gap": "int — gap in pixels (0-32)"},
         tier=Tier.LOW_RISK),
    Tool("compositor_run_and_type", "Spawn app, wait for it, then type text",
         compositor_run_and_type,
         parameters={"command": "string — app to launch", "text": "string — text to type", "wait_seconds": "float — max wait (default 3)"},
         tier=Tier.MUTATE),
    Tool("compositor_diff", "Get recent scene changes (window open/close/focus events)",
         compositor_diff, tier=Tier.OBSERVE),
    Tool("compositor_wait_for", "Wait for a window condition (title/app_id/count)",
         compositor_wait_for,
         parameters={"title": "string — title substring", "app_id": "string — app ID", "count": "int — min windows", "timeout": "float — seconds"},
         tier=Tier.OBSERVE),
]
