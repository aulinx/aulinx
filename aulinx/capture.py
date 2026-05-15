"""Screen capture — portal-first on Wayland, with native-tool fallback.

Backend priority:
  Wayland: portal (GNOME/KDE/wlroots) -> grim (wlroots only) -> gnome-screenshot (GNOME only)
  X11:     scrot -> ImageMagick import

The xdg-desktop-portal Screenshot backend is the only capture method that
works on KDE Plasma Wayland, so it is preferred on every Wayland session.
See docs/superpowers/plans/2026-05-15-portal-screen-capture.md.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path


def _session_type(env: dict[str, str] | None = None) -> str:
    """Classify the display session as 'wayland', 'x11', or 'headless'."""
    env = os.environ if env is None else env
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "headless"


def _backend_order(env: dict[str, str] | None = None) -> list[str]:
    """Return capture backend names in priority order for this session."""
    stype = _session_type(env)
    if stype == "wayland":
        return ["portal", "grim", "gnome-screenshot"]
    if stype == "x11":
        return ["scrot", "import"]
    return []


async def _run_capture_cmd(cmd: list[str], dest: Path, timeout: float = 10.0) -> bool:
    """Run a screenshot subprocess; return True if it produced a non-empty file."""
    try:
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0


async def _capture_grim(dest: Path) -> bool:
    return await _run_capture_cmd(["grim", str(dest)], dest)


async def _capture_gnome_screenshot(dest: Path) -> bool:
    return await _run_capture_cmd(["gnome-screenshot", "-f", str(dest)], dest)


async def _capture_scrot(dest: Path) -> bool:
    return await _run_capture_cmd(["scrot", str(dest)], dest)


async def _capture_import(dest: Path) -> bool:
    return await _run_capture_cmd(["import", "-window", "root", str(dest)], dest)


async def _capture_portal(dest: Path) -> bool:
    """Placeholder — real implementation added in Task 6."""
    return False


_BACKENDS = {
    "portal": _capture_portal,
    "grim": _capture_grim,
    "gnome-screenshot": _capture_gnome_screenshot,
    "scrot": _capture_scrot,
    "import": _capture_import,
}


async def capture_screen(prefer: str | None = None) -> dict:
    """Capture the full screen to a temp PNG.

    Tries backends in session-appropriate priority order. `prefer` moves a
    named backend to the front. Returns {"path", "size_bytes", "method"} on
    success or {"error": ...} if every backend fails.
    """
    dest = Path(tempfile.gettempdir()) / f"aulinx-screenshot-{int(time.time() * 1000)}.png"
    order = _backend_order()
    if prefer and prefer in _BACKENDS:
        order = [prefer] + [b for b in order if b != prefer]

    tried: list[str] = []
    for name in order:
        backend = _BACKENDS.get(name)
        if backend is None:
            continue
        tried.append(name)
        try:
            if await backend(dest):
                return {
                    "path": str(dest),
                    "size_bytes": dest.stat().st_size,
                    "method": name,
                }
        except Exception:
            continue

    detail = ", ".join(tried) if tried else "none — headless session"
    return {"error": f"No screen capture backend succeeded (tried: {detail})"}
