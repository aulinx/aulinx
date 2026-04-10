"""Aulinx Compositor Python Client Library.

Provides a clean Python API for all compositor IPC commands.

Usage:
    from aulinx_compositor import AulinxCompositor

    with AulinxCompositor() as compositor:
        # Query
        windows = compositor.windows()
        focused = compositor.focused()
        screenshot = compositor.screenshot()  # returns PNG bytes

        # Input
        compositor.type_text("hello world")
        compositor.key("ctrl+s")
        compositor.click(640, 400)
        compositor.scroll(640, 400, dy=-3)
        compositor.drag(100, 100, 500, 400)

        # Windows
        compositor.focus(window_id=1)
        compositor.close(window_id=1)
        compositor.swap_master(window_id=2)
        compositor.spawn("firefox")

        # Events
        for event in compositor.subscribe():
            print(event)
"""

import base64
import json
import os
import socket
from typing import Any, Iterator, Optional


class AulinxCompositor:
    """Client for the Aulinx compositor IPC protocol."""

    def __init__(self, socket_path: Optional[str] = None):
        self._socket_path = socket_path or self._default_socket_path()
        self._sock: Optional[socket.socket] = None
        self._next_id = 1

    @staticmethod
    def _default_socket_path() -> str:
        if "AULINX_SOCKET" in os.environ:
            return os.environ["AULINX_SOCKET"]
        xdg = os.environ.get("XDG_RUNTIME_DIR", "")
        if xdg:
            return os.path.join(xdg, "aulinx", "semantic.sock")
        return "/tmp/aulinx-semantic.sock"

    def connect(self) -> "AulinxCompositor":
        """Connect to the compositor IPC socket."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self._socket_path)
        self._sock.settimeout(5.0)
        return self

    def close(self) -> None:
        """Close the connection."""
        if self._sock:
            self._sock.close()
            self._sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.close()

    def _rpc(self, method: str, params: Optional[dict] = None) -> Any:
        """Send a JSON-RPC request and return the result."""
        if not self._sock:
            raise RuntimeError("Not connected. Call connect() first.")

        req_id = self._next_id
        self._next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        self._sock.sendall((json.dumps(request) + "\n").encode())

        data = b""
        while b"\n" not in data:
            chunk = self._sock.recv(1048576)
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk

        response = json.loads(data.decode().strip())
        if "error" in response:
            raise RuntimeError(f"IPC error: {response['error'].get('message', response['error'])}")
        return response.get("result")

    # ---- Scene Queries ----

    def windows(self) -> list[dict]:
        """List all windows with metadata and geometry."""
        return self._rpc("scene.windows")

    def focused(self) -> dict:
        """Get the currently focused window."""
        return self._rpc("scene.focused")

    def find(self, query: str) -> list[dict]:
        """Search for UI elements by query string."""
        return self._rpc("scene.find", {"query": query})

    def graph(self) -> dict:
        """Get the full scene graph tree."""
        return self._rpc("scene.graph")

    def element_at(self, x: float, y: float) -> Optional[dict]:
        """Query what window is at the given coordinates."""
        return self._rpc("scene.element_at", {"x": x, "y": y})

    def window_count(self) -> int:
        """Get the number of open windows."""
        return self._rpc("scene.window_count")["count"]

    def screenshot(self, save_path: Optional[str] = None) -> bytes:
        """Capture the compositor screen as PNG bytes.

        Args:
            save_path: If provided, save the PNG to this file path.

        Returns:
            Raw PNG bytes.
        """
        result = self._rpc("scene.screenshot")
        png_data = base64.b64decode(result["data"])
        if save_path:
            with open(save_path, "wb") as f:
                f.write(png_data)
        return png_data

    def ascii(self) -> str:
        """Get an ASCII art map of the desktop layout.

        Text-only AI agents can 'see' the desktop without screenshots.
        """
        return self._rpc("scene.ascii").get("ascii", "")

    def describe(self) -> str:
        """Get a natural language description of the desktop state.

        Returns something like:
        "2 in master+stack layout. Window 1 [master]: foot — 761x792 (focused)"
        """
        return self._rpc("scene.describe").get("description", "")

    def ping(self) -> bool:
        """Health check — returns True if compositor is responsive."""
        return self._rpc("scene.ping").get("pong", False)

    def status(self) -> dict:
        """Get full compositor status (version, uptime, window count, config)."""
        return self._rpc("scene.status")

    def annotated_screenshot(self, save_path: Optional[str] = None) -> bytes:
        """Capture screenshot with window boundaries and labels overlaid.

        The "Set of Marks" approach — AI agents see both content and structure
        in a single image.
        """
        result = self._rpc("scene.annotated_screenshot")
        png_data = base64.b64decode(result["data"])
        if save_path:
            with open(save_path, "wb") as f:
                f.write(png_data)
        return png_data

    def help(self) -> dict:
        """List all available IPC commands with descriptions."""
        return self._rpc("scene.list_commands")

    # ---- Input Injection ----

    def type_text(self, text: str) -> None:
        """Type text into the focused window."""
        self._rpc("input.type", {"text": text})

    def key(self, combo: str) -> None:
        """Inject a key combination (e.g. 'ctrl+s', 'super+return')."""
        self._rpc("input.key", {"combo": combo})

    def click(self, x: float, y: float, button: int = 1) -> None:
        """Click at screen coordinates. button: 1=left, 2=middle, 3=right."""
        self._rpc("input.click", {"x": x, "y": y, "button": button})

    def scroll(self, x: float, y: float, dx: float = 0, dy: float = 0) -> None:
        """Scroll at screen coordinates. Negative dy = scroll up."""
        self._rpc("input.scroll", {"x": x, "y": y, "dx": dx, "dy": dy})

    def move(self, x: float, y: float) -> None:
        """Move the pointer to screen coordinates."""
        self._rpc("input.move", {"x": x, "y": y})

    def drag(self, x1: float, y1: float, x2: float, y2: float, button: int = 1) -> None:
        """Drag from (x1,y1) to (x2,y2)."""
        self._rpc("input.drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "button": button})

    # ---- Window Management ----

    def focus_window(self, window_id: int) -> None:
        """Focus a window by its semantic ID."""
        self._rpc("window.focus", {"window_id": window_id})

    def close_window(self, window_id: Optional[int] = None) -> None:
        """Close a window. If window_id is None, closes the focused window."""
        params = {"window_id": window_id} if window_id is not None else {}
        self._rpc("window.close", params)

    def swap_master(self, window_id: int) -> None:
        """Swap a window to the master position in the layout."""
        self._rpc("window.swap_master", {"window_id": window_id})

    def spawn(self, command: str, args: Optional[list[str]] = None) -> int:
        """Launch an application inside the compositor. Returns PID."""
        result = self._rpc("window.spawn", {"command": command, "args": args or []})
        return result.get("pid", 0)

    def batch(self, actions: list[dict]) -> dict:
        """Execute multiple input actions atomically in one IPC call.

        Each action is {"method": "input.type", "params": {"text": "hello"}}.
        Supports: input.type, input.key, input.click, input.move, sleep.

        Example:
            compositor.batch([
                {"method": "input.type", "params": {"text": "ls -la"}},
                {"method": "input.key", "params": {"combo": "return"}},
                {"method": "sleep", "params": {"ms": 500}},
            ])
        """
        return self._rpc("input.batch", {"actions": actions})

    # ---- Scene Monitoring ----

    def diff(self) -> list[dict]:
        """Get scene changes since the last call. Returns list of events."""
        result = self._rpc("scene.diff")
        return result.get("events", [])

    def wait_for(self, title: Optional[str] = None, app_id: Optional[str] = None,
                 count: Optional[int] = None, timeout: float = 10.0, poll: float = 0.3) -> bool:
        """Wait until a condition is met (window with title/app_id exists, or window count reached).

        Args:
            title: Window title substring to match.
            app_id: App ID substring to match.
            count: Minimum number of windows.
            timeout: Maximum seconds to wait.
            poll: Seconds between checks.

        Returns:
            True if condition met, False if timed out.
        """
        import time
        deadline = time.monotonic() + timeout
        params = {}
        if title:
            params["title"] = title
        if app_id:
            params["app_id"] = app_id
        if count is not None:
            params["count"] = count

        while time.monotonic() < deadline:
            result = self._rpc("scene.wait_for", params)
            if result.get("matched"):
                return True
            time.sleep(poll)
        return False

    # ---- Event Subscriptions ----

    def subscribe(self, filter: str = "*") -> Iterator[dict]:
        """Subscribe to compositor events. Yields event dicts.

        Example:
            for event in compositor.subscribe():
                if event["event"] == "window_opened":
                    print(f"New window: {event['app_id']}")
        """
        self._rpc("scene.subscribe", {"filter": filter})
        self._sock.settimeout(None)  # Block indefinitely
        buffer = b""
        while True:
            try:
                chunk = self._sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    msg = json.loads(line.decode())
                    if msg.get("method") == "scene.event":
                        yield msg.get("params", {})
            except (ConnectionError, OSError):
                break


# Convenience function
def connect(socket_path: Optional[str] = None) -> AulinxCompositor:
    """Connect to the Aulinx compositor and return a client."""
    return AulinxCompositor(socket_path).connect()
