"""Desktop context — gathers current state of the user's desktop via AT-SPI and system APIs."""

import json
import os
import subprocess
from datetime import datetime


class DesktopContext:
    """Collects desktop state for LLM context.

    Prefers the semantic daemon/compositor when available (structured,
    real-time, cheap). Falls back to AT-SPI for legacy support.
    """

    def __init__(self):
        self._atspi_available = False
        self._semantic_available = False

    async def initialize(self):
        """Check what context sources are available."""
        # Check semantic daemon/compositor
        self._semantic_available = _semantic_is_available()

        # Check AT-SPI availability
        try:
            import pyatspi  # noqa: F401
            self._atspi_available = True
        except ImportError:
            self._atspi_available = False

    def status(self) -> str:
        parts = []
        parts.append(f"semantic={'yes' if self._semantic_available else 'no'}")
        parts.append(f"AT-SPI={'yes' if self._atspi_available else 'no'}")
        parts.append(f"platform={_get_platform()}")
        return ", ".join(parts)

    async def snapshot(self) -> str:
        """Return a structured context string for the LLM system prompt."""
        ctx = {}
        ctx["time"] = datetime.now().isoformat(timespec="seconds")
        ctx["user"] = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
        ctx["platform"] = _get_platform()

        # Prefer semantic daemon for desktop state (100x cheaper than AT-SPI polling)
        if self._semantic_available:
            semantic_ctx = _get_semantic_context()
            if semantic_ctx:
                ctx["desktop"] = semantic_ctx
                ctx["context_source"] = "semantic"
        elif self._atspi_available:
            ctx["focused_window"] = _get_focused_window_atspi()
            ctx["running_apps"] = _get_running_apps_atspi()
            ctx["context_source"] = "atspi"

        # System info
        ctx["system"] = _get_system_info()

        # Clipboard
        ctx["clipboard_preview"] = _get_clipboard()

        return json.dumps(ctx, indent=2, ensure_ascii=False)


def _get_platform() -> str:
    """Detect desktop environment."""
    de = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    return f"{de} ({session})"


def _get_focused_window_atspi() -> dict | None:
    """Get the currently focused window via AT-SPI."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            try:
                for window in app:
                    state = window.getState()
                    if state.contains(pyatspi.STATE_ACTIVE):
                        return {
                            "app": app.name,
                            "title": window.name,
                            "role": window.getRoleName(),
                        }
            except Exception:
                continue
        return None
    except Exception:
        return None


def _get_running_apps_atspi() -> list[str]:
    """List running GUI applications via AT-SPI."""
    try:
        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        apps = []
        for app in desktop:
            try:
                if app.name:
                    apps.append(app.name)
            except Exception:
                continue
        return apps
    except Exception:
        return []


def _get_system_info() -> dict:
    """Basic system info from /proc and commands."""
    info = {}
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            info["load_avg"] = parts[0]
    except (FileNotFoundError, PermissionError):
        pass

    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            for line in lines[:3]:
                key, val = line.split(":")
                info[key.strip()] = val.strip()
    except (FileNotFoundError, PermissionError):
        pass

    return info


def _get_clipboard() -> str | None:
    """Try to read clipboard text."""
    for cmd in [
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout:
                return result.stdout[:200]
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
            continue
    return None


# ---- Semantic daemon integration ----


def _semantic_socket_path() -> str:
    """Get the semantic IPC socket path."""
    if "AULINX_SOCKET" in os.environ:
        return os.environ["AULINX_SOCKET"]
    xdg = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg:
        return os.path.join(xdg, "aulinx", "semantic.sock")
    return "/tmp/aulinx-semantic.sock"


def _semantic_is_available() -> bool:
    """Check if the semantic daemon or compositor is running."""
    return os.path.exists(_semantic_socket_path())


def _semantic_query(method: str, params: dict = None) -> dict | None:
    """Send a query to the semantic daemon."""
    import socket as sock_mod
    path = _semantic_socket_path()
    try:
        s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(path)
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }) + "\n"
        s.sendall(request.encode())
        data = b""
        while b"\n" not in data:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
        s.close()
        response = json.loads(data.decode().strip())
        return response.get("result")
    except Exception:
        return None


def _get_semantic_context() -> dict | None:
    """Get desktop context from the semantic daemon or compositor."""
    try:
        # Try scene.summary first (compositor-only, richest data — one call)
        summary = _semantic_query("scene.summary")
        if summary and "description" in summary:
            return {
                "description": summary.get("description"),
                "ascii_layout": summary.get("ascii"),
                "suggestions": summary.get("suggestions"),
                "compositor": summary.get("status"),
                "source": "compositor_summary",
            }

        # Fall back to individual queries
        status = _semantic_query("scene.status")

        # Get focused window + all windows
        focused = _semantic_query("scene.focused")
        windows = _semantic_query("scene.windows")

        if windows is None:
            return None

        ctx = {
            "focused": focused,
            "windows": [],
        }

        if status:
            ctx["compositor"] = {
                "version": status.get("version"),
                "uptime": status.get("uptime_seconds"),
                "backend": status.get("backend"),
                "window_count": status.get("window_count"),
            }

        for w in (windows if isinstance(windows, list) else []):
            entry = {
                "id": w.get("id"),
                "app_id": w.get("app_id"),
                "title": w.get("title"),
                "focused": w.get("focused", False),
            }
            # Include geometry if available (compositor mode)
            geo = w.get("geometry")
            if geo and geo.get("width"):
                entry["geometry"] = f"{geo['width']}x{geo['height']} at ({geo['x']},{geo['y']})"
            ctx["windows"].append(entry)

        return ctx
    except Exception:
        return None
