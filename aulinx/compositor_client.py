"""Re-export the Aulinx compositor client for convenience.

Usage:
    from aulinx.compositor_client import connect, AulinxCompositor

    with connect() as c:
        print(c.describe())
        c.type_text("hello")
"""

import sys
import os

# Add compositor dir to path if the client library isn't importable
_compositor_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "compositor")
if os.path.exists(os.path.join(_compositor_dir, "aulinx_compositor.py")):
    sys.path.insert(0, _compositor_dir)

try:
    from aulinx_compositor import AulinxCompositor, connect  # noqa: F401
except ImportError:
    # Inline minimal client if the compositor package isn't available
    import json
    import socket
    from typing import Any, Optional

    class AulinxCompositor:
        """Minimal compositor client (full version in compositor/aulinx_compositor.py)."""

        def __init__(self, socket_path: Optional[str] = None):
            self._path = socket_path or self._default_path()
            self._sock = None
            self._id = 0

        @staticmethod
        def _default_path():
            if "AULINX_SOCKET" in os.environ:
                return os.environ["AULINX_SOCKET"]
            xdg = os.environ.get("XDG_RUNTIME_DIR", "")
            return os.path.join(xdg, "aulinx", "semantic.sock") if xdg else "/tmp/aulinx-semantic.sock"

        def connect(self):
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(5)
            self._sock.connect(self._path)
            return self

        def close(self):
            if self._sock:
                self._sock.close()
                self._sock = None

        def __enter__(self): return self.connect()
        def __exit__(self, *a): self.close()

        def _rpc(self, method: str, params: dict = None) -> Any:
            self._id += 1
            req = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
            self._sock.sendall((req + "\n").encode())
            data = b""
            while b"\n" not in data:
                chunk = self._sock.recv(1048576)
                if not chunk: break
                data += chunk
            resp = json.loads(data.decode().strip())
            if "error" in resp:
                raise RuntimeError(resp["error"].get("message", str(resp["error"])))
            return resp.get("result")

        def describe(self) -> str: return self._rpc("scene.describe").get("description", "")
        def windows(self) -> list: return self._rpc("scene.windows")
        def status(self) -> dict: return self._rpc("scene.status")
        def screenshot(self, path=None):
            import base64
            r = self._rpc("scene.screenshot")
            png = base64.b64decode(r["data"])
            if path:
                with open(path, "wb") as f: f.write(png)
            return png
        def type_text(self, text): self._rpc("input.type", {"text": text})
        def key(self, combo): self._rpc("input.key", {"combo": combo})
        def click(self, x, y, button=1): self._rpc("input.click", {"x": x, "y": y, "button": button})
        def spawn(self, cmd): return self._rpc("window.spawn", {"command": cmd, "args": []}).get("pid", 0)

    def connect(socket_path=None):
        return AulinxCompositor(socket_path).connect()
