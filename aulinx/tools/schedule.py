"""Scheduled tasks — manage cron jobs for recurring automation."""

import subprocess

from aulinx.tools.base import Tier, Tool


async def cron_list() -> list[str]:
    """List current user's cron jobs."""
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [line for line in result.stdout.strip().splitlines() if line and not line.startswith("#")]
        return []
    except FileNotFoundError:
        return ["crontab not found"]


async def cron_add(schedule: str, command: str) -> dict:
    """Add a cron job. Schedule format: 'minute hour day month weekday' (e.g. '0 9 * * *' for 9am daily)."""
    try:
        # Get existing crontab
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        existing = result.stdout if result.returncode == 0 else ""

        # Add new job
        new_crontab = existing.rstrip() + f"\n{schedule} {command}\n"

        # Write back
        proc = subprocess.run(
            ["crontab", "-"], input=new_crontab, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return {"added": True, "schedule": schedule, "command": command}
        return {"error": proc.stderr.strip()}
    except FileNotFoundError:
        return {"error": "crontab not found"}


async def cron_remove(pattern: str) -> dict:
    """Remove cron jobs matching a pattern."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return {"error": "No crontab"}

        lines = result.stdout.splitlines()
        kept = [line for line in lines if pattern.lower() not in line.lower()]
        removed = len(lines) - len(kept)

        if removed == 0:
            return {"error": f"No jobs matching '{pattern}'"}

        proc = subprocess.run(
            ["crontab", "-"], input="\n".join(kept) + "\n", capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return {"removed": removed, "pattern": pattern}
        return {"error": proc.stderr.strip()}
    except FileNotFoundError:
        return {"error": "crontab not found"}


TOOLS = [
    Tool(
        name="cron_list",
        description="List current user's scheduled cron jobs",
        fn=cron_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="cron_add",
        description="Add a recurring scheduled task via cron. Schedule: 'min hour day month weekday'",
        fn=cron_add,
        parameters={
            "schedule": "string (cron format, e.g. '0 9 * * *' for daily at 9am, '*/5 * * * *' for every 5 min)",
            "command": "string (shell command to run)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="cron_remove",
        description="Remove cron jobs matching a text pattern",
        fn=cron_remove,
        parameters={"pattern": "string (text to match in cron entries)"},
        tier=Tier.DESTRUCTIVE,
    ),
]
