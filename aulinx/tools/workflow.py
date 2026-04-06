"""Workflow tools — batch execution, wait/delay, and context summary."""

import asyncio
import json
import time
from aulinx.tools.registry import Tool, Tier


async def context_get() -> dict:
    """Get a rich summary of the current desktop context — use this at the start of complex tasks."""
    from aulinx.context.desktop import DesktopContext
    ctx = DesktopContext()
    await ctx.initialize()
    snapshot = await ctx.snapshot()
    return json.loads(snapshot)


async def wait(seconds: float = 1.0, reason: str = "") -> dict:
    """Wait for a specified duration. Useful between actions that need time to take effect."""
    seconds = max(0.1, min(30, seconds))
    await asyncio.sleep(seconds)
    return {"waited": seconds, "reason": reason}


async def audit_recent(limit: int = 10) -> list[dict]:
    """Get recent tool call history — useful for understanding what actions were already taken."""
    from aulinx.audit import AuditLog
    log = AuditLog()
    return log.recent(limit)


TOOLS = [
    Tool(
        name="context_get",
        description="Get a rich snapshot of the current desktop state (focused window, running apps, clipboard, system info). Call this at the start of complex tasks.",
        fn=context_get,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="wait",
        description="Wait for a specified number of seconds (0.1-30). Use between actions that need time to take effect (e.g., after launching an app).",
        fn=wait,
        parameters={"seconds": "float (default 1.0)", "reason": "string (optional, why waiting)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="audit_recent",
        description="Get recent tool call history — see what actions were already performed in this session",
        fn=audit_recent,
        parameters={"limit": "int (default 10)"},
        tier=Tier.OBSERVE,
    ),
]
