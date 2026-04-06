"""XDG tools — open files/URLs, manage default applications."""

import subprocess
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def xdg_open(target: str) -> dict:
    """Open a file, URL, or directory with the default application.

    Examples: xdg_open("https://github.com"), xdg_open("~/Documents/report.pdf"),
    xdg_open("/home/user/Pictures")
    """
    # Expand ~ and resolve
    if not target.startswith(("http://", "https://", "ftp://")):
        target = str(Path(target).expanduser().resolve())

    try:
        result = subprocess.run(
            ["xdg-open", target],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"opened": True, "target": target}
        return {"error": result.stderr.strip() or "xdg-open failed"}
    except FileNotFoundError:
        return {"error": "xdg-open not found (install xdg-utils)"}
    except subprocess.TimeoutExpired:
        # xdg-open may not exit immediately for some apps — that's OK
        return {"opened": True, "target": target, "note": "app may still be launching"}


async def default_app_get(mime_type: str) -> dict:
    """Get the default application for a MIME type.

    Examples: "text/html", "application/pdf", "image/png", "x-scheme-handler/http"
    """
    try:
        result = subprocess.run(
            ["xdg-mime", "query", "default", mime_type],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"mime_type": mime_type, "default_app": result.stdout.strip()}
        return {"mime_type": mime_type, "default_app": None}
    except FileNotFoundError:
        return {"error": "xdg-mime not found"}


async def default_app_set(mime_type: str, desktop_file: str) -> dict:
    """Set the default application for a MIME type.

    desktop_file should be a .desktop file name, e.g. "firefox.desktop", "org.gnome.Nautilus.desktop"
    """
    try:
        result = subprocess.run(
            ["xdg-mime", "default", desktop_file, mime_type],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"set": True, "mime_type": mime_type, "app": desktop_file}
        return {"error": result.stderr.strip() or "Failed to set default"}
    except FileNotFoundError:
        return {"error": "xdg-mime not found"}


async def mime_type_of(path: str) -> dict:
    """Detect the MIME type of a file."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"File not found: {path}"}

    try:
        result = subprocess.run(
            ["xdg-mime", "query", "filetype", str(p)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"path": str(p), "mime_type": result.stdout.strip()}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        # Fallback to file command
        try:
            result = subprocess.run(
                ["file", "--mime-type", "-b", str(p)],
                capture_output=True, text=True, timeout=5,
            )
            return {"path": str(p), "mime_type": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "Neither xdg-mime nor file command found"}


TOOLS = [
    Tool(
        name="xdg_open",
        description="Open a file, URL, or directory with the default application",
        fn=xdg_open,
        parameters={"target": "string (file path, URL, or directory)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="default_app_get",
        description="Get the default app for a MIME type (e.g. text/html, application/pdf)",
        fn=default_app_get,
        parameters={"mime_type": "string"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="default_app_set",
        description="Set the default app for a MIME type",
        fn=default_app_set,
        parameters={"mime_type": "string", "desktop_file": "string (e.g. firefox.desktop)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="mime_type_of",
        description="Detect the MIME type of a file",
        fn=mime_type_of,
        parameters={"path": "string"},
        tier=Tier.OBSERVE,
    ),
]
