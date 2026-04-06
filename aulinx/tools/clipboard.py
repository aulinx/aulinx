"""Clipboard tools — read and write the system clipboard."""

import subprocess

from aulinx.tools.base import Tier, Tool


async def clipboard_get() -> dict:
    """Get current clipboard content."""
    for cmd in [
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return {"text": result.stdout[:2000], "length": len(result.stdout)}
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
            continue

    return {"error": "No clipboard tool available (install wl-paste, xclip, or xsel)"}


async def clipboard_set(text: str) -> dict:
    """Set clipboard content."""
    for cmd in [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]:
        try:
            result = subprocess.run(
                cmd, input=text, capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return {"success": True, "length": len(text)}
        except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
            continue

    return {"error": "No clipboard tool available (install wl-copy, xclip, or xsel)"}


TOOLS = [
    Tool(
        name="clipboard_get",
        description="Read current clipboard text content",
        fn=clipboard_get,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="clipboard_set",
        description="Set clipboard text content",
        fn=clipboard_set,
        parameters={"text": "string"},
        tier=Tier.LOW_RISK,
    ),
]
