"""Tests for the screen capture module."""

from aulinx.capture import _session_type, _backend_order


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
