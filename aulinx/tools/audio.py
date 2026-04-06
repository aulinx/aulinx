"""Audio tools — volume control via wpctl (PipeWire) or pactl (PulseAudio)."""

import subprocess
from aulinx.tools.registry import Tool, Tier


def _run(cmd: list[str], timeout: int = 5) -> dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"stdout": result.stdout.strip(), "returncode": result.returncode, "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"error": f"{cmd[0]} not found"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out"}


async def audio_get_volume() -> dict:
    """Get current audio volume and mute status."""
    # Try wpctl (PipeWire/WirePlumber) first
    r = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if "error" not in r and r["returncode"] == 0:
        # Output: "Volume: 0.75" or "Volume: 0.75 [MUTED]"
        line = r["stdout"]
        muted = "[MUTED]" in line
        try:
            vol = float(line.split(":")[1].strip().split()[0])
            return {"volume_percent": round(vol * 100), "muted": muted, "backend": "pipewire"}
        except (IndexError, ValueError):
            pass

    # Fallback: pactl (PulseAudio)
    r = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    if "error" not in r and r["returncode"] == 0:
        # Parse "Volume: front-left: 65536 / 100% / ..."
        for part in r["stdout"].split("/"):
            part = part.strip()
            if part.endswith("%"):
                try:
                    vol = int(part[:-1])
                    # Check mute
                    mute_r = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
                    muted = "yes" in mute_r.get("stdout", "").lower()
                    return {"volume_percent": vol, "muted": muted, "backend": "pulseaudio"}
                except ValueError:
                    pass

    return {"error": "No audio backend found (install wpctl or pactl)"}


async def audio_set_volume(volume: int) -> dict:
    """Set audio volume (0-100)."""
    vol = max(0, min(150, volume))  # allow up to 150% like PulseAudio

    # Try wpctl first
    r = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol / 100:.2f}"])
    if "error" not in r and r["returncode"] == 0:
        return {"volume_percent": vol, "backend": "pipewire"}

    # Fallback: pactl
    r = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"])
    if "error" not in r and r["returncode"] == 0:
        return {"volume_percent": vol, "backend": "pulseaudio"}

    return {"error": "Failed to set volume"}


async def audio_mute(mute: bool = True) -> dict:
    """Mute or unmute audio."""
    state = "1" if mute else "0"

    r = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", state])
    if "error" not in r and r["returncode"] == 0:
        return {"muted": mute, "backend": "pipewire"}

    pa_state = "1" if mute else "0"
    r = _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", pa_state])
    if "error" not in r and r["returncode"] == 0:
        return {"muted": mute, "backend": "pulseaudio"}

    return {"error": "Failed to set mute"}


TOOLS = [
    Tool(
        name="audio_get_volume",
        description="Get current audio volume (0-100%) and mute status",
        fn=audio_get_volume,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="audio_set_volume",
        description="Set audio volume (0-150%)",
        fn=audio_set_volume,
        parameters={"volume": "int (0-150)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="audio_mute",
        description="Mute or unmute audio output",
        fn=audio_mute,
        parameters={"mute": "bool (true=mute, false=unmute)"},
        tier=Tier.LOW_RISK,
    ),
]
