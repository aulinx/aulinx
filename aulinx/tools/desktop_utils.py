"""Desktop utility tools — color picker, screen recording, window snapping."""

import subprocess
import tempfile
import time
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def color_picker() -> dict:
    """Pick a color from the screen. Returns hex and RGB values."""
    # Try zenity color picker
    try:
        result = subprocess.run(
            ["zenity", "--color-selection"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            color = result.stdout.strip()
            return {"color": color}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try gpick
    try:
        result = subprocess.run(
            ["gpick", "-p"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return {"color": result.stdout.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"error": "No color picker available. Install: sudo apt install zenity"}


async def screen_record_start(output: str = "", duration: int = 0) -> dict:
    """Start screen recording. Returns the output file path."""
    if not output:
        output = str(Path(tempfile.gettempdir()) / f"aulinx-recording-{int(time.time())}.mp4")

    # Try wf-recorder (Wayland)
    try:
        cmd = ["wf-recorder", "-f", output]
        if duration > 0:
            cmd.extend(["-d", str(duration)])
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"recording": True, "path": output, "pid": proc.pid, "via": "wf-recorder"}
    except FileNotFoundError:
        pass

    # Try ffmpeg with screen capture
    try:
        cmd = ["ffmpeg", "-f", "x11grab", "-i", ":0", "-y", output]
        if duration > 0:
            cmd.extend(["-t", str(duration)])
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"recording": True, "path": output, "pid": proc.pid, "via": "ffmpeg"}
    except FileNotFoundError:
        pass

    return {"error": "No screen recorder. Install: wf-recorder (Wayland) or ffmpeg (X11)"}


async def screen_record_stop() -> dict:
    """Stop screen recording."""
    for proc_name in ["wf-recorder", "ffmpeg"]:
        try:
            result = subprocess.run(
                ["pkill", "-INT", proc_name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return {"stopped": True, "process": proc_name}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return {"error": "No active recording found"}


async def window_snap(title: str, position: str) -> dict:
    """Snap a window to a screen position.

    Positions: left, right, top-left, top-right, bottom-left, bottom-right, center, maximize
    """
    # Get screen resolution
    try:
        result = subprocess.run(
            ["xdpyinfo"], capture_output=True, text=True, timeout=5,
        )
        width, height = 1920, 1080  # defaults
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "dimensions:" in line:
                    dims = line.split()[1]
                    width, height = [int(x) for x in dims.split("x")]
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        width, height = 1920, 1080

    half_w, half_h = width // 2, height // 2
    positions = {
        "left": (0, 0, half_w, height),
        "right": (half_w, 0, half_w, height),
        "top-left": (0, 0, half_w, half_h),
        "top-right": (half_w, 0, half_w, half_h),
        "bottom-left": (0, half_h, half_w, half_h),
        "bottom-right": (half_w, half_h, half_w, half_h),
        "center": (width // 4, height // 4, half_w, half_h),
    }

    if position == "maximize":
        try:
            subprocess.run(
                ["wmctrl", "-r", title, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True, timeout=5,
            )
            return {"snapped": True, "title": title, "position": "maximize"}
        except FileNotFoundError:
            return {"error": "wmctrl not installed"}

    coords = positions.get(position)
    if not coords:
        return {"error": f"Unknown position: {position}. Use: left, right, top-left, top-right, bottom-left, bottom-right, center, maximize"}

    x, y, w, h = coords
    try:
        # Remove maximize first
        subprocess.run(
            ["wmctrl", "-r", title, "-b", "remove,maximized_vert,maximized_horz"],
            capture_output=True, timeout=5,
        )
        result = subprocess.run(
            ["wmctrl", "-r", title, "-e", f"0,{x},{y},{w},{h}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {"snapped": True, "title": title, "position": position, "geometry": f"{w}x{h}+{x}+{y}"}
        return {"error": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": "wmctrl not installed"}


TOOLS = [
    Tool(
        name="color_picker",
        description="Pick a color from the screen. Opens a color picker dialog.",
        fn=color_picker,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="screen_record_start",
        description="Start screen recording. Returns output file path and PID.",
        fn=screen_record_start,
        parameters={
            "output": "string (optional output path, auto-generated if empty)",
            "duration": "int (seconds, 0=unlimited, default 0)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="screen_record_stop",
        description="Stop the current screen recording",
        fn=screen_record_stop,
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="window_snap",
        description="Snap a window to a screen position (like Windows snap)",
        fn=window_snap,
        parameters={
            "title": "string (window title)",
            "position": "left|right|top-left|top-right|bottom-left|bottom-right|center|maximize",
        },
        tier=Tier.LOW_RISK,
    ),
]
