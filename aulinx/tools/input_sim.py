"""Input simulation tools — keyboard shortcuts and virtual typing.

Priority order: ydotool (works everywhere including GNOME Wayland) > wtype (wlroots Wayland) > xdotool (X11).
"""

import os
import shutil
import subprocess

from aulinx.tools.base import Tier, Tool


def _find_input_tool() -> str | None:
    """Find the best available input simulation tool.

    Priority: ydotool (kernel-level, works on GNOME Mutter) > wtype (Wayland/wlroots) > xdotool (X11).
    """
    # ydotool works on ALL compositors including GNOME Mutter (uses /dev/uinput)
    if shutil.which("ydotool"):
        # Ensure YDOTOOL_SOCKET is set (daemon may run as root with socket in /tmp)
        if "YDOTOOL_SOCKET" not in os.environ:
            for sock_path in ["/tmp/.ydotool_socket", f"/run/user/{os.getuid()}/.ydotool_socket"]:
                if os.path.exists(sock_path):
                    os.environ["YDOTOOL_SOCKET"] = sock_path
                    break

        # Check if ydotoold daemon is running
        try:
            result = subprocess.run(
                ["pgrep", "-x", "ydotoold"], capture_output=True, timeout=2
            )
            if result.returncode == 0:
                return "ydotool"
            # Try starting the daemon
            subprocess.Popen(
                ["ydotoold"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            import time
            time.sleep(0.5)
            return "ydotool"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # wtype works on wlroots-based compositors (Sway, Hyprland) but NOT GNOME Mutter
    if shutil.which("wtype"):
        session = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" not in session:  # skip wtype on GNOME — it will fail
            return "wtype"

    # xdotool works on X11 and XWayland apps
    if shutil.which("xdotool"):
        return "xdotool"

    return None


async def input_key_combo(keys: str) -> dict:
    """Send a keyboard shortcut (e.g. 'ctrl+s', 'alt+F4', 'super+l', 'ctrl+shift+t').

    Format: modifier+modifier+key, where modifiers are ctrl, alt, shift, super.
    """
    tool = _find_input_tool()
    if not tool:
        return {"error": "No input tool found. Install ydotool (recommended), wtype (Wayland), or xdotool (X11)."}

    try:
        if tool == "ydotool":
            # ydotool key combo: need to map to keycodes
            # For now, fall through to shell-based approach
            result = subprocess.run(
                ["ydotool", "key", keys],
                capture_output=True, text=True, timeout=5,
            )
        elif tool == "xdotool":
            result = subprocess.run(
                ["xdotool", "key", keys],
                capture_output=True, text=True, timeout=5,
            )
        elif tool == "wtype":
            parts = keys.lower().split("+")
            key = parts[-1]
            mods = parts[:-1]
            cmd = ["wtype"]
            mod_map = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "logo"}
            for m in mods:
                cmd.extend(["-M", mod_map.get(m, m)])
            cmd.extend(["-P", key, "-p", key])
            for m in reversed(mods):
                cmd.extend(["-m", mod_map.get(m, m)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        else:
            return {"error": f"Unsupported tool: {tool}"}

        if result.returncode == 0:
            return {"sent": True, "keys": keys, "via": tool}
        return {"error": result.stderr.strip() or "Key combo failed", "via": tool}

    except FileNotFoundError:
        return {"error": f"{tool} not found"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


async def input_type_text(text: str, delay_ms: int = 0) -> dict:
    """Type text into the currently focused window via virtual keyboard."""
    tool = _find_input_tool()
    if not tool:
        return {"error": "No input tool found. Install ydotool (recommended), wtype (Wayland), or xdotool (X11)."}

    try:
        if tool == "ydotool":
            cmd = ["ydotool", "type", "--"]
            if delay_ms > 0:
                cmd.extend(["--key-delay", str(delay_ms)])
            cmd.append(text)
        elif tool == "xdotool":
            cmd = ["xdotool", "type"]
            if delay_ms > 0:
                cmd.extend(["--delay", str(delay_ms)])
            cmd.append(text)
        elif tool == "wtype":
            cmd = ["wtype"]
            if delay_ms > 0:
                cmd.extend(["-d", str(delay_ms)])
            cmd.append(text)
        else:
            return {"error": f"Unsupported tool: {tool}"}

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"typed": True, "length": len(text), "via": tool}
        return {"error": result.stderr.strip() or "Typing failed", "via": tool}

    except FileNotFoundError:
        return {"error": f"{tool} not found"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


TOOLS = [
    Tool(
        name="input_key_combo",
        description="Send a keyboard shortcut to the focused window. Does NOT accept app names.",
        fn=input_key_combo,
        parameters={"keys": "string (e.g. 'ctrl+s', 'alt+F4', 'super+l', 'ctrl+shift+t')"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="input_type_text",
        description="Type text into the currently focused window via virtual keyboard. Only takes text and delay_ms — no app or window params.",
        fn=input_type_text,
        parameters={
            "text": "string (the text to type)",
            "delay_ms": "int (optional, inter-key delay in milliseconds, default 0)",
        },
        tier=Tier.MUTATE,
    ),
]
