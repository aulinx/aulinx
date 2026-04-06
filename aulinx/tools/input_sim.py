"""Input simulation tools — keyboard shortcuts and virtual typing."""

import shutil
import subprocess

from aulinx.tools.base import Tier, Tool


def _find_input_tool() -> str | None:
    """Find an available input simulation tool."""
    for tool in ["wtype", "xdotool", "ydotool"]:
        if shutil.which(tool):
            return tool
    return None


async def input_key_combo(keys: str) -> dict:
    """Send a keyboard shortcut (e.g. 'ctrl+s', 'alt+F4', 'super+l', 'ctrl+shift+t').

    Format: modifier+modifier+key, where modifiers are ctrl, alt, shift, super.
    """
    tool = _find_input_tool()
    if not tool:
        return {"error": "No input tool found. Install wtype (Wayland), xdotool (X11), or ydotool."}

    try:
        if tool == "xdotool":
            # xdotool format: "ctrl+shift+t" → "xdotool key ctrl+shift+t"
            xdo_keys = keys.replace("super", "super").replace("ctrl", "ctrl").replace("alt", "alt")
            result = subprocess.run(
                ["xdotool", "key", xdo_keys],
                capture_output=True, text=True, timeout=5,
            )
        elif tool == "wtype":
            # wtype format: -M ctrl -M shift -P t -p t -m shift -m ctrl
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
        elif tool == "ydotool":
            # ydotool uses key codes, more complex — use xdotool-style for simplicity
            result = subprocess.run(
                ["ydotool", "key", keys],
                capture_output=True, text=True, timeout=5,
            )
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
    """Type text as if from a keyboard. Use for apps where AT-SPI set_text doesn't work."""
    tool = _find_input_tool()
    if not tool:
        return {"error": "No input tool found. Install wtype (Wayland), xdotool (X11), or ydotool."}

    try:
        if tool == "xdotool":
            cmd = ["xdotool", "type"]
            if delay_ms > 0:
                cmd.extend(["--delay", str(delay_ms)])
            cmd.append(text)
        elif tool == "wtype":
            cmd = ["wtype"]
            if delay_ms > 0:
                cmd.extend(["-d", str(delay_ms)])
            cmd.append(text)
        elif tool == "ydotool":
            cmd = ["ydotool", "type", text]
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
        description="Send a keyboard shortcut (e.g. 'ctrl+s', 'alt+F4', 'super+l', 'ctrl+shift+t')",
        fn=input_key_combo,
        parameters={"keys": "string (e.g. ctrl+s, alt+tab, super+l)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="input_type_text",
        description="Type text via virtual keyboard. Fallback when AT-SPI set_text doesn't work.",
        fn=input_type_text,
        parameters={"text": "string", "delay_ms": "int (inter-key delay, default 0)"},
        tier=Tier.MUTATE,
    ),
]
