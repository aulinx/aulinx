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
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


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


def _portal_uri_to_path(uri: str) -> PurePosixPath:
    """Convert a portal 'file://' result URI to a local filesystem path.

    Returns a PurePosixPath so that str() always uses forward slashes on
    every platform (portal URIs are always POSIX paths from Linux).
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected a file:// URI from the portal, got: {uri!r}")
    return PurePosixPath(unquote(parsed.path))


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
        from dbus_next.introspection import Node
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

        # The org.freedesktop.portal.Request interface is fixed and tiny. Parsing
        # it from a static description (rather than an async bus.introspect call)
        # leaves zero await points between Screenshot() returning and the Response
        # listener being attached — closing the race where a fast portal emits
        # Response before we subscribe.
        request_intr = Node.parse(
            '<node><interface name="org.freedesktop.portal.Request">'
            '<method name="Close"/>'
            '<signal name="Response">'
            '<arg type="u" name="response"/>'
            '<arg type="a{sv}" name="results"/>'
            "</signal></interface></node>"
        )

        token = f"aulinx_{uuid.uuid4().hex}"
        # Screenshot() returns the object path of a Request; its Response signal
        # carries the result.
        request_path = await screenshot.call_screenshot(
            "",  # parent window — empty for an unparented agent request
            {
                "interactive": Variant("b", False),
                "handle_token": Variant("s", token),
            },
        )

        # No await between here and request.on_response() below — see comment above.
        req_obj = bus.get_proxy_object(
            "org.freedesktop.portal.Desktop", request_path, request_intr
        )
        request = req_obj.get_interface("org.freedesktop.portal.Request")

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[tuple[int, dict]] = loop.create_future()

        def _on_response(response: int, results: dict) -> None:
            if not result_future.done():
                result_future.set_result((response, results))

        request.on_response(_on_response)

        try:
            response, results = await asyncio.wait_for(result_future, timeout=30.0)
        except asyncio.TimeoutError:
            logger.debug("portal Screenshot timed out after 30s")
            return False

        # response: 0 = success, 1 = user cancelled, 2 = ended some other way
        if response != 0:
            return False

        uri_variant = results.get("uri")
        if uri_variant is None:
            return False
        uri = uri_variant.value if isinstance(uri_variant, Variant) else uri_variant

        # _portal_uri_to_path returns a PurePosixPath (portal paths are always
        # Linux POSIX); Path() makes it concrete for filesystem access on the host.
        src = Path(_portal_uri_to_path(uri))
        if not src.exists():
            return False
        await asyncio.to_thread(shutil.copyfile, src, dest)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        logger.debug("portal Screenshot capture failed: %s", e)
        return False
    finally:
        if bus is not None:
            bus.disconnect()


_BACKENDS = {
    "portal": _capture_portal,
    "grim": _capture_grim,
    "gnome-screenshot": _capture_gnome_screenshot,
    "scrot": _capture_scrot,
    "import": _capture_import,
}


async def capture_screen(prefer: str | None = None) -> dict:
    """Capture the full screen to a temp PNG.

    Tries backends in session-appropriate priority order. `prefer` puts a
    named backend first — including one not in this session's default order
    (e.g. forcing the portal on an X11 session). Returns {"path",
    "size_bytes", "method"} on success or {"error": ...} if every backend fails.
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
