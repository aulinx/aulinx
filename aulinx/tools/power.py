"""Power management tools — battery, power profiles, suspend/shutdown."""

import subprocess
from pathlib import Path
from aulinx.tools.registry import Tool, Tier


async def power_status() -> dict:
    """Get battery status, power profile, and AC adapter state."""
    info = {}

    # Battery via /sys
    bat_path = Path("/sys/class/power_supply/BAT0")
    if not bat_path.exists():
        bat_path = Path("/sys/class/power_supply/BAT1")

    if bat_path.exists():
        try:
            info["battery"] = {
                "present": True,
                "percent": int((bat_path / "capacity").read_text().strip()),
                "status": (bat_path / "status").read_text().strip(),  # Charging, Discharging, Full, Not charging
            }
            # Time to empty/full if available
            try:
                energy_now = int((bat_path / "energy_now").read_text().strip())
                power_now = int((bat_path / "power_now").read_text().strip())
                if power_now > 0:
                    hours = energy_now / power_now
                    info["battery"]["hours_remaining"] = round(hours, 1)
            except (FileNotFoundError, ValueError, ZeroDivisionError):
                pass
        except (FileNotFoundError, ValueError):
            info["battery"] = {"present": False}
    else:
        info["battery"] = {"present": False}

    # AC adapter
    ac_path = Path("/sys/class/power_supply/AC")
    if not ac_path.exists():
        ac_path = Path("/sys/class/power_supply/ACAD")
    if ac_path.exists():
        try:
            info["ac_connected"] = (ac_path / "online").read_text().strip() == "1"
        except FileNotFoundError:
            pass

    # Power profile via power-profiles-daemon
    try:
        result = subprocess.run(
            ["powerprofilesctl", "get"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["power_profile"] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return info


async def power_profile(profile: str) -> dict:
    """Set power profile: performance, balanced, or power-saver."""
    if profile not in ("performance", "balanced", "power-saver"):
        return {"error": "Profile must be: performance, balanced, or power-saver"}

    try:
        result = subprocess.run(
            ["powerprofilesctl", "set", profile],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"profile": profile, "set": True}
        return {"error": result.stderr.strip() or "Failed to set profile"}
    except FileNotFoundError:
        return {"error": "powerprofilesctl not found (install power-profiles-daemon)"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


async def power_suspend() -> dict:
    """Suspend the system (sleep)."""
    try:
        result = subprocess.run(
            ["systemctl", "suspend"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {"suspended": True}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "systemctl not found"}


async def power_shutdown(action: str = "poweroff", delay: int = 0) -> dict:
    """Shutdown or reboot the system."""
    if action not in ("poweroff", "reboot"):
        return {"error": "Action must be: poweroff or reboot"}

    cmd = ["systemctl", action]
    if delay > 0:
        # Use shutdown command for delayed shutdown
        flag = "-h" if action == "poweroff" else "-r"
        cmd = ["shutdown", flag, f"+{delay // 60 or 1}"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return {"action": action, "initiated": True, "delay_seconds": delay}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "systemctl/shutdown not found"}


TOOLS = [
    Tool(
        name="power_status",
        description="Get battery level, charging status, AC adapter, and power profile",
        fn=power_status,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="power_profile",
        description="Set power profile: performance, balanced, or power-saver",
        fn=power_profile,
        parameters={"profile": "performance|balanced|power-saver"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="power_suspend",
        description="Suspend/sleep the system",
        fn=power_suspend,
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="power_shutdown",
        description="Shutdown or reboot the system",
        fn=power_shutdown,
        parameters={"action": "poweroff|reboot", "delay": "int seconds (default 0)"},
        tier=Tier.IRREVERSIBLE,
    ),
]
