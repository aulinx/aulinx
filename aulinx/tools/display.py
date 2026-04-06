"""Display and brightness tools."""

import subprocess
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def display_list() -> list[dict]:
    """List connected displays with resolution and refresh rate."""
    # Try wlr-randr (Wayland/wlroots)
    displays = _try_wlr_randr()
    if displays:
        return displays

    # Try xrandr (X11)
    displays = _try_xrandr()
    if displays:
        return displays

    # Try gnome-randr or KDE equivalent
    displays = _try_gnome_display()
    if displays:
        return displays

    return [{"error": "No display tool found (install wlr-randr or xrandr)"}]


def _try_wlr_randr() -> list[dict] | None:
    try:
        result = subprocess.run(
            ["wlr-randr"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        displays = []
        current = None
        for line in result.stdout.splitlines():
            if not line.startswith(" ") and not line.startswith("\t"):
                if current:
                    displays.append(current)
                name = line.strip()
                current = {"name": name, "resolution": "", "refresh": "", "enabled": True}
            elif current and "current" in line.lower():
                # e.g. "  2560x1440 px, 59.951000 Hz (current)"
                parts = line.strip().split(",")
                if parts:
                    current["resolution"] = parts[0].strip().split()[0] if parts[0].strip() else ""
                if len(parts) > 1:
                    hz = parts[1].strip().split()[0]
                    current["refresh"] = f"{float(hz):.0f}Hz" if hz.replace(".", "").isdigit() else ""

        if current:
            displays.append(current)
        return displays if displays else None

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _try_xrandr() -> list[dict] | None:
    try:
        result = subprocess.run(
            ["xrandr", "--current"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        displays = []
        for line in result.stdout.splitlines():
            if " connected" in line:
                parts = line.split()
                name = parts[0]
                # Find resolution (e.g., "2560x1440+0+0")
                res = ""
                for p in parts:
                    if "x" in p and "+" in p:
                        res = p.split("+")[0]
                        break
                displays.append({
                    "name": name,
                    "resolution": res,
                    "primary": "primary" in line,
                    "enabled": res != "",
                })
        return displays if displays else None

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _try_gnome_display() -> list[dict] | None:
    try:
        result = subprocess.run(
            ["gnome-randr"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [{"raw": result.stdout[:500]}]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


async def display_brightness(level: int = -1) -> dict:
    """Get or set display brightness (0-100). Call with no level to get current."""
    # Find backlight sysfs path
    backlight_dirs = list(Path("/sys/class/backlight").iterdir()) if Path("/sys/class/backlight").exists() else []

    if not backlight_dirs:
        # Try brightnessctl as alternative
        return await _brightness_via_brightnessctl(level)

    bl = backlight_dirs[0]
    try:
        max_brightness = int((bl / "max_brightness").read_text().strip())
        current = int((bl / "actual_brightness").read_text().strip())
        current_pct = round(current / max_brightness * 100)

        if level < 0:
            return {"brightness": current_pct, "device": bl.name}

        # Set brightness
        target = max(0, min(100, level))
        target_raw = round(target / 100 * max_brightness)
        (bl / "brightness").write_text(str(target_raw))
        return {"brightness": target, "previous": current_pct, "device": bl.name}

    except PermissionError:
        # Need brightnessctl or pkexec
        return await _brightness_via_brightnessctl(level)
    except Exception as e:
        return {"error": str(e)}


async def _brightness_via_brightnessctl(level: int) -> dict:
    """Use brightnessctl as fallback."""
    try:
        if level < 0:
            result = subprocess.run(
                ["brightnessctl", "get"], capture_output=True, text=True, timeout=5,
            )
            max_r = subprocess.run(
                ["brightnessctl", "max"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and max_r.returncode == 0:
                current = int(result.stdout.strip())
                maximum = int(max_r.stdout.strip())
                return {"brightness": round(current / maximum * 100), "backend": "brightnessctl"}
        else:
            target = max(0, min(100, level))
            result = subprocess.run(
                ["brightnessctl", "set", f"{target}%"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return {"brightness": target, "backend": "brightnessctl"}

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"error": "Cannot access brightness (install brightnessctl or run as root)"}


TOOLS = [
    Tool(
        name="display_list",
        description="List connected displays with resolution and refresh rate",
        fn=display_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="display_brightness",
        description="Get or set display brightness (0-100). Call with no level arg to get current.",
        fn=display_brightness,
        parameters={"level": "int 0-100 (omit to get current)"},
        tier=Tier.LOW_RISK,
    ),
]
