"""Desktop context — gathers current state of the user's desktop via AT-SPI and system APIs."""

import json
import subprocess
import os
from datetime import datetime


class DesktopContext:
    """Collects desktop state for LLM context."""

    def __init__(self):
        self._atspi_available = False

    async def initialize(self):
        """Check what context sources are available."""
        # Check AT-SPI availability
        try:
            import pyatspi  # noqa: F401
            self._atspi_available = True
        except ImportError:
            self._atspi_available = False

    def status(self) -> str:
        parts = []
        parts.append(f"AT-SPI={'yes' if self._atspi_available else 'no (install pyatspi)'}")
        parts.append(f"platform={_get_platform()}")
        return ", ".join(parts)

    async def snapshot(self) -> str:
        """Return a structured context string for the LLM system prompt."""
        ctx = {}
        ctx["time"] = datetime.now().isoformat(timespec="seconds")
        ctx["user"] = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
        ctx["platform"] = _get_platform()

        # Focused window (AT-SPI)
        if self._atspi_available:
            ctx["focused_window"] = _get_focused_window_atspi()
            ctx["running_apps"] = _get_running_apps_atspi()

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
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None
