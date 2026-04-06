"""Date and time tools."""

import subprocess
from datetime import datetime, timezone

from aulinx.tools.base import Tier, Tool


async def date_now(timezone_name: str = "") -> dict:
    """Get current date, time, and timezone."""
    now = datetime.now()
    utc = datetime.now(timezone.utc)

    info = {
        "local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc.strftime("%Y-%m-%d %H:%M:%S"),
        "unix": int(now.timestamp()),
        "day_of_week": now.strftime("%A"),
        "iso": now.isoformat(),
    }

    # Get timezone name
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["timezone"] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        import time as _time
        info["timezone"] = _time.tzname[0]

    return info


async def date_convert(value: str, from_format: str = "", to_format: str = "") -> dict:
    """Convert between date formats or parse a date string.

    Examples:
    - date_convert("2026-04-06") — parse ISO date
    - date_convert("1712419200", from_format="unix") — convert unix timestamp
    - date_convert("April 6, 2026", to_format="%Y-%m-%d") — reformat
    """
    try:
        # Try unix timestamp
        if from_format == "unix" or (value.isdigit() and len(value) >= 10):
            ts = int(value)
            if ts > 1e12:
                ts = ts // 1000  # milliseconds
            dt = datetime.fromtimestamp(ts)
        else:
            # Try common formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%B %d, %Y",
                "%b %d, %Y",
                "%d/%m/%Y",
                "%m/%d/%Y",
                from_format,
            ]:
                if not fmt:
                    continue
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return {"error": f"Cannot parse date: {value}"}

        result = {
            "iso": dt.isoformat(),
            "human": dt.strftime("%A, %B %d, %Y at %H:%M"),
            "unix": int(dt.timestamp()),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "day_of_week": dt.strftime("%A"),
        }
        if to_format:
            result["formatted"] = dt.strftime(to_format)
        return result

    except (ValueError, OverflowError, OSError) as e:
        return {"error": f"Date conversion failed: {e}"}


async def calendar_show(month: int = 0, year: int = 0) -> str:
    """Show a calendar for the current or specified month."""
    import calendar

    now = datetime.now()
    m = month or now.month
    y = year or now.year

    try:
        return calendar.month(y, m)
    except (ValueError, OverflowError) as e:
        return f"Error: {e}"


TOOLS = [
    Tool(
        name="date_now",
        description="Get current date, time, timezone, day of week, and unix timestamp",
        fn=date_now,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="date_convert",
        description="Parse or convert between date formats (ISO, unix timestamp, human-readable, custom strftime)",
        fn=date_convert,
        parameters={
            "value": "string (date to parse)",
            "from_format": "string (optional: 'unix' or strftime format)",
            "to_format": "string (optional: strftime output format)",
        },
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="calendar_show",
        description="Show a text calendar for the current or specified month/year",
        fn=calendar_show,
        parameters={"month": "int (1-12, default: current)", "year": "int (default: current)"},
        tier=Tier.OBSERVE,
    ),
]
