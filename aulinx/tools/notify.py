"""Notification tools — send desktop notifications via D-Bus."""

import subprocess
from aulinx.tools.registry import Tool, Tier


async def notification_send(
    title: str, body: str = "", urgency: str = "normal", icon: str = ""
) -> dict:
    """Send a desktop notification."""
    cmd = ["notify-send"]

    if urgency in ("low", "normal", "critical"):
        cmd.extend(["--urgency", urgency])

    if icon:
        cmd.extend(["--icon", icon])

    cmd.append(title)
    if body:
        cmd.append(body)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return {"sent": True, "title": title}
        return {"error": result.stderr.strip() or "notify-send failed"}
    except FileNotFoundError:
        return {"error": "notify-send not found (install libnotify)"}
    except subprocess.TimeoutExpired:
        return {"error": "notify-send timed out"}


TOOLS = [
    Tool(
        name="notification_send",
        description="Send a desktop notification",
        fn=notification_send,
        parameters={
            "title": "string",
            "body": "string (optional)",
            "urgency": "low|normal|critical (default: normal)",
            "icon": "string (icon name, optional)",
        },
        tier=Tier.LOW_RISK,
    ),
]
