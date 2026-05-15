"""Tests for the screen capture module."""

import os
import platform
from pathlib import Path

import pytest

from aulinx import capture as cap
from aulinx.capture import _backend_order, _session_type


def test_session_type_wayland():
    assert _session_type({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"


def test_session_type_x11():
    assert _session_type({"DISPLAY": ":0"}) == "x11"


def test_session_type_wayland_wins_when_both_set():
    # A Wayland session often also sets DISPLAY for XWayland — Wayland wins.
    assert _session_type({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}) == "wayland"


def test_session_type_headless():
    assert _session_type({}) == "headless"


def test_backend_order_wayland_prefers_portal():
    order = _backend_order({"WAYLAND_DISPLAY": "wayland-0"})
    assert order[0] == "portal"
    assert order == ["portal", "grim", "gnome-screenshot"]


def test_backend_order_x11_has_no_portal():
    order = _backend_order({"DISPLAY": ":0"})
    assert "portal" not in order
    assert order == ["scrot", "import"]


def test_backend_order_headless_is_empty():
    assert _backend_order({}) == []


async def test_capture_screen_returns_first_successful_backend(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def fake_grim(dest):
        Path(dest).write_bytes(b"PNGDATA")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", fake_grim)
    result = await cap.capture_screen()
    assert result["method"] == "grim"
    assert result["size_bytes"] == 7
    assert Path(result["path"]).exists()


async def test_capture_screen_falls_through_to_next_backend(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def fail(dest):
        return False

    async def ok(dest):
        Path(dest).write_bytes(b"OK")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", fail)
    monkeypatch.setitem(cap._BACKENDS, "gnome-screenshot", ok)
    result = await cap.capture_screen()
    assert result["method"] == "gnome-screenshot"


async def test_capture_screen_backend_exception_is_not_fatal(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def boom(dest):
        raise RuntimeError("backend crashed")

    async def ok(dest):
        Path(dest).write_bytes(b"OK")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", boom)
    monkeypatch.setitem(cap._BACKENDS, "gnome-screenshot", ok)
    result = await cap.capture_screen()
    assert result["method"] == "gnome-screenshot"


async def test_capture_screen_prefer_moves_backend_to_front(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["portal", "grim"])
    calls = []

    async def portal_backend(dest):
        calls.append("portal")
        return False

    async def grim_backend(dest):
        calls.append("grim")
        return False

    monkeypatch.setitem(cap._BACKENDS, "portal", portal_backend)
    monkeypatch.setitem(cap._BACKENDS, "grim", grim_backend)
    await cap.capture_screen(prefer="grim")
    assert calls[0] == "grim"


async def test_capture_screen_all_fail_returns_error(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim"])

    async def fail(dest):
        return False

    monkeypatch.setitem(cap._BACKENDS, "grim", fail)
    result = await cap.capture_screen()
    assert "error" in result
    assert "grim" in result["error"]


async def test_capture_screen_headless_returns_error(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: [])
    result = await cap.capture_screen()
    assert "error" in result


async def test_window_screenshot_delegates_to_capture(monkeypatch):
    from aulinx.tools import atspi_tools

    async def fake_capture(prefer=None):
        return {"path": "/tmp/x.png", "size_bytes": 123, "method": prefer or "portal"}

    monkeypatch.setattr(atspi_tools, "capture_screen", fake_capture)
    result = await atspi_tools.window_screenshot(method="grim")
    assert result["method"] == "grim"
    assert result["size_bytes"] == 123


async def test_screen_screenshot_window_fallback_uses_capture(monkeypatch):
    from aulinx.tools import screen

    async def fake_capture(prefer=None):
        return {"path": "/tmp/full.png", "size_bytes": 999, "method": "portal"}

    monkeypatch.setattr(screen, "capture_screen", fake_capture)
    # No app_name -> full-screen path -> must delegate to capture.
    result = await screen.screenshot_window()
    assert result["path"] == "/tmp/full.png"
    assert result["method"] == "portal"


def test_portal_uri_to_path_decodes_file_uri():
    from aulinx.capture import _portal_uri_to_path

    p = _portal_uri_to_path("file:///tmp/Screenshot%20From%202026.png")
    assert str(p) == "/tmp/Screenshot From 2026.png"


def test_portal_uri_to_path_rejects_non_file_uri():
    from aulinx.capture import _portal_uri_to_path

    with pytest.raises(ValueError):
        _portal_uri_to_path("https://example.com/x.png")


@pytest.mark.skipif(
    platform.system() != "Linux" or not os.environ.get("WAYLAND_DISPLAY"),
    reason="portal capture requires a Linux Wayland session with xdg-desktop-portal",
)
async def test_capture_portal_integration():
    """Real end-to-end portal capture. May show a permission prompt on first run."""
    import tempfile

    from aulinx.capture import _capture_portal

    dest = Path(tempfile.gettempdir()) / "aulinx-portal-itest.png"
    dest.unlink(missing_ok=True)
    try:
        ok = await _capture_portal(dest)
        assert ok is True, "portal capture failed — check xdg-desktop-portal is running"
        assert dest.stat().st_size > 0
    finally:
        dest.unlink(missing_ok=True)


async def test_capture_portal_returns_false_without_dbus_next(monkeypatch):
    """If dbus-next is not installed, the portal backend degrades to False."""
    import sys

    from aulinx.capture import _capture_portal

    # Setting the module to None makes `import dbus_next` raise ImportError.
    monkeypatch.setitem(sys.modules, "dbus_next", None)
    result = await _capture_portal(Path("/nonexistent/aulinx-x.png"))
    assert result is False
