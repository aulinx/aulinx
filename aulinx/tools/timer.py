"""Timer/reminder tools — set timers that send desktop notifications."""

import asyncio
import subprocess
import time

from aulinx.tools.base import Tier, Tool

# Active timers (for cancellation)
_active_timers: dict[str, asyncio.Task] = {}


async def set_timer(seconds: float, message: str = "Timer finished!") -> dict:
    """Set a timer that sends a desktop notification when it expires.

    Examples: set_timer(300, "Break time!"), set_timer(60, "Check the build")
    """
    seconds = max(1, min(86400, seconds))  # 1 second to 24 hours

    timer_id = f"timer-{int(time.time())}"

    async def _run_timer():
        await asyncio.sleep(seconds)
        # Send notification
        try:
            subprocess.run(
                ["notify-send", "--urgency=critical", "--icon=alarm",
                 "Aulinx Timer", message],
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        _active_timers.pop(timer_id, None)

    task = asyncio.create_task(_run_timer())
    _active_timers[timer_id] = task

    # Format duration for display
    if seconds >= 3600:
        display = f"{seconds / 3600:.1f} hours"
    elif seconds >= 60:
        display = f"{seconds / 60:.0f} minutes"
    else:
        display = f"{seconds:.0f} seconds"

    return {
        "timer_id": timer_id,
        "duration": display,
        "message": message,
        "fires_at": time.strftime(
            "%H:%M:%S", time.localtime(time.time() + seconds)
        ),
    }


async def cancel_timer(timer_id: str) -> dict:
    """Cancel an active timer."""
    task = _active_timers.pop(timer_id, None)
    if task:
        task.cancel()
        return {"cancelled": True, "timer_id": timer_id}
    return {"error": f"Timer '{timer_id}' not found or already expired"}


async def list_timers() -> list[dict]:
    """List all active timers."""
    timers = []
    for tid, task in _active_timers.items():
        timers.append({
            "timer_id": tid,
            "active": not task.done(),
        })
    return timers


TOOLS = [
    Tool(
        name="set_timer",
        description="Set a timer (1s-24h) that sends a desktop notification when done",
        fn=set_timer,
        parameters={"seconds": "float", "message": "string (notification text)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="cancel_timer",
        description="Cancel an active timer by ID",
        fn=cancel_timer,
        parameters={"timer_id": "string"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="list_timers",
        description="List all active timers",
        fn=list_timers,
        tier=Tier.OBSERVE,
    ),
]
