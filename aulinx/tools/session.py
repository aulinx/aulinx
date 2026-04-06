"""Session and system info tools — user, uptime, disk, environment."""

import os
import subprocess

from aulinx.tools.base import Tier, Tool


async def who_am_i() -> dict:
    """Get current user, hostname, home directory, and shell."""
    return {
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
        "home": str(os.path.expanduser("~")),
        "hostname": _cmd_output(["hostname"]),
        "shell": os.environ.get("SHELL", "unknown"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "display": os.environ.get("WAYLAND_DISPLAY", os.environ.get("DISPLAY", "none")),
    }


async def uptime() -> dict:
    """Get system uptime, load averages, and logged-in users."""
    info = {}
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
            hours = int(secs // 3600)
            mins = int((secs % 3600) // 60)
            info["uptime"] = f"{hours}h {mins}m"
            info["uptime_seconds"] = int(secs)
    except FileNotFoundError:
        info["uptime"] = _cmd_output(["uptime", "-p"])

    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            info["load_avg"] = {"1m": parts[0], "5m": parts[1], "15m": parts[2]}
            info["running_tasks"] = parts[3]
    except FileNotFoundError:
        pass

    users = _cmd_output(["who"])
    if users:
        info["logged_in_users"] = len(users.strip().splitlines())

    return info


async def disk_usage(path: str = "/") -> list[dict]:
    """Get disk usage for all mounted filesystems or a specific path."""
    try:
        result = subprocess.run(
            ["df", "-h", "--output=source,fstype,size,used,avail,pcent,target", path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return [{"error": result.stderr.strip()}]

        disks = []
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split(None, 6)
            if len(parts) >= 7 and not parts[0].startswith("tmpfs"):
                disks.append({
                    "device": parts[0],
                    "type": parts[1],
                    "size": parts[2],
                    "used": parts[3],
                    "available": parts[4],
                    "use_percent": parts[5],
                    "mount": parts[6],
                })
        return disks
    except FileNotFoundError:
        return [{"error": "df not found"}]
    except subprocess.TimeoutExpired:
        return [{"error": "df timed out"}]


async def env_get(name: str = "") -> dict:
    """Get environment variable(s). If name is empty, returns common ones."""
    if name:
        val = os.environ.get(name)
        if val is None:
            return {"error": f"Environment variable '{name}' not set"}
        return {"name": name, "value": val}

    # Return common environment variables
    common = [
        "USER", "HOME", "SHELL", "PATH", "LANG",
        "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY",
        "EDITOR", "TERM", "XDG_RUNTIME_DIR",
    ]
    result = {}
    for key in common:
        val = os.environ.get(key)
        if val:
            result[key] = val
    return result


def _cmd_output(cmd: list[str]) -> str:
    """Run a command and return stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


TOOLS = [
    Tool(
        name="who_am_i",
        description="Get current user, hostname, shell, desktop environment, and display server",
        fn=who_am_i,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="uptime",
        description="Get system uptime, load averages, and number of logged-in users",
        fn=uptime,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="disk_usage",
        description="Get disk usage for all mounted filesystems",
        fn=disk_usage,
        parameters={"path": "string (default: /)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="env_get",
        description="Get environment variable(s). Empty name returns common vars (USER, PATH, DISPLAY, etc.)",
        fn=env_get,
        parameters={"name": "string (optional — specific variable name)"},
        tier=Tier.OBSERVE,
    ),
]
