# Portal-First Screen Capture (Tier 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `xdg-desktop-portal` screen-capture backend so Aulinx's Tier 2 agent can take screenshots on **KDE Plasma Wayland** (currently impossible) and on any portal-supporting Wayland compositor, while consolidating three duplicated screenshot implementations into one module.

**Architecture:** A new `aulinx/capture.py` module owns all screen capture. It exposes one async entry point, `capture_screen()`, which selects a backend by session type (`WAYLAND_DISPLAY` / `DISPLAY`) and tries them in priority order with graceful fallback. On Wayland the preferred backend is the `org.freedesktop.portal.Screenshot` D-Bus interface (works on GNOME, KDE Plasma, and wlroots); `grim` and `gnome-screenshot` remain as fallbacks. The three existing call sites (`atspi_tools.window_screenshot`, `screen.screenshot_window`, `ocr.py`) become thin delegates.

**Tech Stack:** Python 3.10+, async/await, `dbus-next` (new optional dependency — pure-Python async D-Bus client), `pytest`, `pytest-asyncio`.

**Scope boundary:** This plan covers **screen capture only**. Portal-based **input injection** (the `org.freedesktop.portal.RemoteDesktop` interface, replacing the `ydotool` root-daemon path) is a separate, harder subsystem — write it as a follow-up plan (`2026-05-15-portal-input-injection.md`) after this lands.

**Risk note:** Task 6 (the portal D-Bus backend) is the only part that cannot be verified on a non-Linux dev machine. Its integration test (`test_capture_portal_integration`) is the gate — it must be run on a real Wayland desktop with `xdg-desktop-portal` running before this plan is considered complete. All other tasks are fully unit-testable anywhere.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `aulinx/capture.py` (new) | Session detection, backend priority order, subprocess + portal backends, `capture_screen()` orchestrator |
| `tests/test_capture.py` (new) | Unit tests for selection/fallback (pure, all platforms); portal integration test (Linux + Wayland only) |
| `aulinx/tools/atspi_tools.py` (modify) | `window_screenshot` delegates to `capture.capture_screen()` |
| `aulinx/tools/screen.py` (modify) | `screenshot_window` full-screen fallback delegates to `capture.capture_screen()` |
| `aulinx/tools/ocr.py` (modify) | OCR screenshot step delegates to `capture.capture_screen()` |
| `aulinx/doctor.py` (modify) | Add `xdg-desktop-portal` availability check |
| `pyproject.toml` (modify) | Add `dbus-next` to the `desktop` optional-dependency extra |
| `CLAUDE.md` (modify) | Document `capture.py` in the architecture map |

---

## Task 1: Session detection + backend priority order

**Files:**
- Create: `aulinx/capture.py`
- Test: `tests/test_capture.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_capture.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aulinx.capture'`

- [ ] **Step 3: Write minimal implementation**

```python
# aulinx/capture.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capture.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add aulinx/capture.py tests/test_capture.py
git commit -m "Add screen-capture session detection and backend ordering"
```

---

## Task 2: Subprocess capture backends + `capture_screen()` orchestrator

**Files:**
- Modify: `aulinx/capture.py`
- Test: `tests/test_capture.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_capture.py`:

```python
import asyncio
from pathlib import Path

import pytest

from aulinx import capture as cap


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_capture_screen_returns_first_successful_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def fake_grim(dest):
        Path(dest).write_bytes(b"PNGDATA")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", fake_grim)
    result = _run(cap.capture_screen())
    assert result["method"] == "grim"
    assert result["size_bytes"] == 7
    assert Path(result["path"]).exists()


def test_capture_screen_falls_through_to_next_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def fail(dest):
        return False

    async def ok(dest):
        Path(dest).write_bytes(b"OK")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", fail)
    monkeypatch.setitem(cap._BACKENDS, "gnome-screenshot", ok)
    result = _run(cap.capture_screen())
    assert result["method"] == "gnome-screenshot"


def test_capture_screen_backend_exception_is_not_fatal(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim", "gnome-screenshot"])

    async def boom(dest):
        raise RuntimeError("backend crashed")

    async def ok(dest):
        Path(dest).write_bytes(b"OK")
        return True

    monkeypatch.setitem(cap._BACKENDS, "grim", boom)
    monkeypatch.setitem(cap._BACKENDS, "gnome-screenshot", ok)
    result = _run(cap.capture_screen())
    assert result["method"] == "gnome-screenshot"


def test_capture_screen_prefer_moves_backend_to_front(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["portal", "grim"])
    calls = []

    async def track(name):
        async def backend(dest):
            calls.append(name)
            return False
        return backend

    monkeypatch.setitem(cap._BACKENDS, "portal", _run(track("portal")))
    monkeypatch.setitem(cap._BACKENDS, "grim", _run(track("grim")))
    _run(cap.capture_screen(prefer="grim"))
    assert calls[0] == "grim"


def test_capture_screen_all_fail_returns_error(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: ["grim"])

    async def fail(dest):
        return False

    monkeypatch.setitem(cap._BACKENDS, "grim", fail)
    result = _run(cap.capture_screen())
    assert "error" in result
    assert "grim" in result["error"]


def test_capture_screen_headless_returns_error(monkeypatch):
    monkeypatch.setattr(cap, "_backend_order", lambda env=None: [])
    result = _run(cap.capture_screen())
    assert "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py -v`
Expected: FAIL — `AttributeError: module 'aulinx.capture' has no attribute '_BACKENDS'`

- [ ] **Step 3: Write minimal implementation**

Append to `aulinx/capture.py` (add the new imports to the existing import block at the top):

```python
import asyncio
import subprocess
import tempfile
import time
from pathlib import Path


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capture.py -v`
Expected: PASS — 13 passed

- [ ] **Step 5: Commit**

```bash
git add aulinx/capture.py tests/test_capture.py
git commit -m "Add subprocess capture backends and capture_screen orchestrator"
```

---

## Task 3: Delegate `atspi_tools.window_screenshot` to the capture module

**Files:**
- Modify: `aulinx/tools/atspi_tools.py:381-417` (the `window_screenshot` function)
- Test: `tests/test_capture.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_capture.py`:

```python
async def test_window_screenshot_delegates_to_capture(monkeypatch):
    from aulinx.tools import atspi_tools

    async def fake_capture(prefer=None):
        return {"path": "/tmp/x.png", "size_bytes": 123, "method": prefer or "portal"}

    monkeypatch.setattr(atspi_tools, "capture_screen", fake_capture)
    result = await atspi_tools.window_screenshot(method="grim")
    assert result["method"] == "grim"
    assert result["size_bytes"] == 123
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py::test_window_screenshot_delegates_to_capture -v`
Expected: FAIL — `AttributeError: module 'aulinx.tools.atspi_tools' has no attribute 'capture_screen'`

- [ ] **Step 3: Write minimal implementation**

In `aulinx/tools/atspi_tools.py`, add to the top-level import block:

```python
from aulinx.capture import capture_screen
```

Replace the entire `window_screenshot` function body (currently `aulinx/tools/atspi_tools.py:381-417`) with:

```python
async def window_screenshot(method: str = "portal") -> dict:
    """Take a full-screen screenshot. Returns the file path.

    `method` names a preferred backend (portal, grim, gnome-screenshot,
    scrot, import); capture falls back through the others if it fails.
    """
    return await capture_screen(prefer=method)
```

Then update the tool's `parameters` entry (around `aulinx/tools/atspi_tools.py:489`) from:

```python
        parameters={"method": "grim|gnome-screenshot|scrot (default: grim)"},
```

to:

```python
        parameters={"method": "portal|grim|gnome-screenshot|scrot|import (default: portal)"},
```

- [ ] **Step 4: Run the focused test, then the full suite**

Run: `python -m pytest tests/test_capture.py::test_window_screenshot_delegates_to_capture -v`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS — 568 passed, 44 skipped (one more than the prior 567; no regressions). If any pre-existing test asserted on `window_screenshot`'s old internal `commands` dict, update it to assert on the delegated `{"path"/"method"/"error"}` shape instead.

- [ ] **Step 5: Commit**

```bash
git add aulinx/tools/atspi_tools.py tests/test_capture.py
git commit -m "Route window_screenshot through the capture module"
```

---

## Task 4: Delegate `screen.screenshot_window` and `ocr.py` to the capture module

**Files:**
- Modify: `aulinx/tools/screen.py:11-48` (the `screenshot_window` function)
- Modify: `aulinx/tools/ocr.py:15-35` (the screenshot step)
- Test: `tests/test_capture.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_capture.py`:

```python
async def test_screen_screenshot_window_fallback_uses_capture(monkeypatch):
    from aulinx.tools import screen

    async def fake_capture(prefer=None):
        return {"path": "/tmp/full.png", "size_bytes": 999, "method": "portal"}

    monkeypatch.setattr(screen, "capture_screen", fake_capture)
    # No app_name -> full-screen path -> must delegate to capture.
    result = await screen.screenshot_window()
    assert result["path"] == "/tmp/full.png"
    assert result["method"] == "portal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py::test_screen_screenshot_window_fallback_uses_capture -v`
Expected: FAIL — `AttributeError: module 'aulinx.tools.screen' has no attribute 'capture_screen'`

- [ ] **Step 3: Write minimal implementation**

In `aulinx/tools/screen.py`, add to the top-level import block:

```python
from aulinx.capture import capture_screen
```

In `screenshot_window`, replace the fallback block (currently `aulinx/tools/screen.py:35-48`, the `# Fallback: full screen screenshot` loop through `return {"error": ...}`) with:

```python
    # Fallback: full-screen capture via the shared capture module.
    return await capture_screen()
```

The per-window `xdotool` + `import` branch (`aulinx/tools/screen.py:15-33`) stays as-is — it is X11-window-specific and the portal `Screenshot` interface captures the full screen only.

In `aulinx/tools/ocr.py`, add to the top-level import block:

```python
from aulinx.capture import capture_screen
```

Replace the screenshot-acquisition block (currently `aulinx/tools/ocr.py:15-35`, the list of `["grim", ...]` commands loop including its `return {"error": ...}`) with:

```python
    shot = await capture_screen()
    if "error" in shot:
        return shot
    screenshot_path = Path(shot["path"])
```

Verify `from pathlib import Path` is already imported in `ocr.py`; if not, add it to the import block.

- [ ] **Step 4: Run the focused test, then the full suite**

Run: `python -m pytest tests/test_capture.py::test_screen_screenshot_window_fallback_uses_capture -v`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS — 569 passed, 44 skipped. No regressions.

- [ ] **Step 5: Commit**

```bash
git add aulinx/tools/screen.py aulinx/tools/ocr.py tests/test_capture.py
git commit -m "Route screen_window fallback and OCR capture through the capture module"
```

---

## Task 5: Add `dbus-next` optional dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Locate the `desktop` extra**

Run: `python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['optional-dependencies'].keys())"`
Expected: a list of extras including `desktop` (and `dev`). Note the exact key name; if the extra is named differently (e.g. `gui`), use that name in Step 2.

- [ ] **Step 2: Add the dependency**

In `pyproject.toml`, under `[project.optional-dependencies]`, add `"dbus-next>=0.2.3"` to the `desktop` extra's list. Example — if the extra currently reads:

```toml
desktop = ["pyatspi", "Pillow"]
```

change it to:

```toml
desktop = ["pyatspi", "Pillow", "dbus-next>=0.2.3"]
```

(Match the existing formatting — if entries are one-per-line, add it on its own line.)

- [ ] **Step 3: Verify the file still parses**

Run: `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject.toml OK')"`
Expected: `pyproject.toml OK`

- [ ] **Step 4: Install the new dependency**

Run: `pip install dbus-next>=0.2.3`
Expected: `Successfully installed dbus-next-...`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "Add dbus-next optional dependency for the portal capture backend"
```

---

## Task 6: Implement the `xdg-desktop-portal` Screenshot backend

**Files:**
- Modify: `aulinx/capture.py` (replace the `_capture_portal` placeholder)
- Test: `tests/test_capture.py`

**Risk note:** This is the one task that cannot be verified on a non-Linux machine. The unit test below covers the URI→path conversion (pure, runs anywhere). The *integration* test (`test_capture_portal_integration`) is the real gate and MUST be run on a Linux Wayland desktop with `xdg-desktop-portal` running. Known portal gotcha: the `Request.Response` signal can theoretically arrive before the listener is attached; the implementation below attaches the listener to the portal-returned `handle` object before awaiting, which is reliable for interactive screenshots — if the integration test flakes, switch to the predictable-request-path pattern (construct the path from `bus.unique_name` + `handle_token` and add a raw match rule before calling `Screenshot`).

- [ ] **Step 1: Write the failing unit test**

Add `import pytest` to the import block at the top of `tests/test_capture.py` if it is not already present (Task 2 removed it as unused). Then append these tests:

```python
def test_portal_uri_to_path_decodes_file_uri():
    from aulinx.capture import _portal_uri_to_path

    p = _portal_uri_to_path("file:///tmp/Screenshot%20From%202026.png")
    assert str(p) == "/tmp/Screenshot From 2026.png"


def test_portal_uri_to_path_rejects_non_file_uri():
    from aulinx.capture import _portal_uri_to_path

    with pytest.raises(ValueError):
        _portal_uri_to_path("https://example.com/x.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture.py::test_portal_uri_to_path_decodes_file_uri -v`
Expected: FAIL — `ImportError: cannot import name '_portal_uri_to_path'`

- [ ] **Step 3: Implement the URI helper and the portal backend**

In `aulinx/capture.py`, add to the import block:

```python
import uuid
from urllib.parse import unquote, urlparse
```

Add the URI helper:

```python
def _portal_uri_to_path(uri: str) -> Path:
    """Convert a portal 'file://' result URI to a local filesystem path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected a file:// URI from the portal, got: {uri!r}")
    return Path(unquote(parsed.path))
```

Replace the `_capture_portal` placeholder with the real implementation:

```python
async def _capture_portal(dest: Path) -> bool:
    """Capture the screen via the org.freedesktop.portal.Screenshot interface.

    Works on GNOME, KDE Plasma, and wlroots Wayland sessions. The first call
    in a session may show a permission prompt; `interactive=false` skips the
    portal's own editing UI. Returns True only if a PNG was written to `dest`.
    """
    try:
        from dbus_next import Variant
        from dbus_next.aio import MessageBus
        from dbus_next.constants import BusType
    except ImportError:
        return False  # dbus-next not installed — orchestrator falls back

    bus = None
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()

        intro = await bus.introspect(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )
        portal_obj = bus.get_proxy_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            intro,
        )
        screenshot = portal_obj.get_interface("org.freedesktop.portal.Screenshot")

        token = f"aulinx_{uuid.uuid4().hex}"
        # Screenshot() returns the object path of a Request; we listen to its
        # Response signal for the result.
        request_path = await screenshot.call_screenshot(
            "",  # parent window — empty for an unparented agent request
            {
                "interactive": Variant("b", False),
                "handle_token": Variant("s", token),
            },
        )

        req_intro = await bus.introspect(
            "org.freedesktop.portal.Desktop", request_path
        )
        req_obj = bus.get_proxy_object(
            "org.freedesktop.portal.Desktop", request_path, req_intro
        )
        request = req_obj.get_interface("org.freedesktop.portal.Request")

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future = loop.create_future()

        def _on_response(response: int, results: dict) -> None:
            if not result_future.done():
                result_future.set_result((response, results))

        request.on_response(_on_response)

        try:
            response, results = await asyncio.wait_for(result_future, timeout=30.0)
        except asyncio.TimeoutError:
            return False

        # response: 0 = success, 1 = user cancelled, 2 = ended some other way
        if response != 0:
            return False

        uri_variant = results.get("uri")
        if uri_variant is None:
            return False
        uri = uri_variant.value if isinstance(uri_variant, Variant) else uri_variant

        src = _portal_uri_to_path(uri)
        if not src.exists():
            return False
        await asyncio.to_thread(shutil.copyfile, src, dest)
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False
    finally:
        if bus is not None:
            bus.disconnect()
```

Add `import shutil` to the import block if it is not already present.

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python -m pytest tests/test_capture.py -v`
Expected: PASS — all unit tests pass (the 2 new URI tests included). The portal backend's own subprocess path is not exercised here.

- [ ] **Step 5: Write the integration test**

Append to `tests/test_capture.py`:

Add `import os` and `import platform` to the import block at the top of `tests/test_capture.py` if not already present, then append:

```python
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
    ok = await _capture_portal(dest)
    assert ok is True, "portal capture failed — check xdg-desktop-portal is running"
    assert dest.stat().st_size > 0
    dest.unlink(missing_ok=True)
```

- [ ] **Step 6: Run the integration test ON A LINUX WAYLAND DESKTOP**

Run (on a real GNOME/KDE/Sway Wayland session): `python -m pytest tests/test_capture.py::test_capture_portal_integration -v`
Expected: PASS (approve the permission prompt if one appears). On a non-Linux or non-Wayland machine the test reports SKIPPED — that is acceptable for the commit but the plan is **not complete** until it has passed on a real Wayland desktop. Verify KDE Plasma Wayland specifically, since that is the session this plan exists to fix.

- [ ] **Step 7: Commit**

```bash
git add aulinx/capture.py tests/test_capture.py
git commit -m "Implement xdg-desktop-portal Screenshot capture backend"
```

---

## Task 7: Add a portal availability check to `doctor.py`

**Files:**
- Modify: `aulinx/doctor.py:54-55` (near the existing `grim`/`scrot` checks)

- [ ] **Step 1: Inspect the existing check helpers**

Run: `grep -n "_check_binary\|def _check\|grim\|scrot" aulinx/doctor.py`
Expected: shows `_check_binary(...)` calls for `grim` and `scrot` around lines 54-55, and the `_check_binary` definition. Note its exact signature before Step 2.

- [ ] **Step 2: Add the portal check**

In `aulinx/doctor.py`, immediately after the existing `scrot` check line (`aulinx/doctor.py:55`), add:

```python
    _check_binary(table, "xdg-desktop-portal", "Screen capture portal (Wayland — GNOME/KDE)", "apt install xdg-desktop-portal")
```

If `_check_binary`'s signature differs from `(table, binary, description, install_hint)`, adapt the call to match the other calls in that function exactly.

- [ ] **Step 3: Verify doctor runs**

Run: `python -m aulinx.doctor` (or `aulinx --doctor` if the entry point is installed)
Expected: the diagnostics table now includes a row for `xdg-desktop-portal`. The command exits without error.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — 571 passed (plus 1 skipped portal integration test off-Linux), no regressions.

- [ ] **Step 5: Commit**

```bash
git add aulinx/doctor.py
git commit -m "Check for xdg-desktop-portal in doctor diagnostics"
```

---

## Task 8: Document the capture module

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `capture.py` to the architecture map**

In `CLAUDE.md`, in the `aulinx/` file-tree block, add this line in alphabetical position (between `audit.py` and `cli.py`, matching the surrounding `│` / `├──` formatting):

```
├── capture.py          — Screen capture: portal-first (GNOME/KDE/wlroots), grim/scrot fallback
```

- [ ] **Step 2: Add a Key Patterns bullet**

In `CLAUDE.md`, in the `## Key Patterns` section, add:

```
- **Portal-first capture**: `capture.py` prefers the `xdg-desktop-portal` Screenshot interface on Wayland (the only method that works on KDE Plasma Wayland), falling back to `grim`/`gnome-screenshot`/`scrot`. All screenshot tools delegate here.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the portal-first capture module in CLAUDE.md"
```

---

## Self-Review

**Spec coverage** — checked against the XDG Portal Audit findings:
- "Zero use of xdg-desktop-portal" → Task 6 adds the portal backend.
- "KDE Plasma Wayland has no working screenshot path" → Task 6 + integration test in Task 6 Step 6 explicitly verify KDE.
- "3 separate screenshot implementations" (`atspi_tools.py`, `ocr.py`, `screen.py`) → Tasks 3 & 4 consolidate all three onto `capture_screen()`.
- "doctor.py doesn't check for xdg-desktop-portal" → Task 7.
- Input injection (RemoteDesktop portal) → explicitly out of scope; called out as a follow-up plan in the header.

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". The Task 2 `_capture_portal` placeholder is intentional and is replaced with the full implementation in Task 6 — the plan states this in both places.

**Type consistency:** `capture_screen()` returns `{"path", "size_bytes", "method"}` or `{"error"}` consistently across Tasks 2, 3, 4. `_capture_*` backends all have signature `async (dest: Path) -> bool`. `_backend_order(env=None)` and `_session_type(env=None)` signatures match between definition (Task 1) and the `monkeypatch` calls (Task 2). `_portal_uri_to_path(uri: str) -> Path` defined and used in Task 6.

**Open assumption to verify during execution:** Task 5 assumes a `desktop` optional-dependencies extra exists — Step 1 verifies the real name first and Step 2 says to adapt. Task 7 assumes `_check_binary(table, binary, description, install_hint)` — Step 1 verifies the real signature first.
