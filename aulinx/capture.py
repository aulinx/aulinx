"""Screen capture — portal-first on Wayland, with native-tool fallback.

Backend priority:
  Wayland: portal (GNOME/KDE/wlroots) -> grim (wlroots only) -> gnome-screenshot (GNOME only)
  X11:     scrot -> ImageMagick import

The xdg-desktop-portal Screenshot backend is the only capture method that
works on KDE Plasma Wayland, so it is preferred on every Wayland session.
See docs/superpowers/plans/2026-05-15-portal-screen-capture.md.
"""

from __future__ import annotations

import os


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
