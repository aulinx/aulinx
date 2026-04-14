"""VLC media player knowledge base — keyboard shortcuts and CLI recipes.

Maps VLC task patterns to precise keyboard shortcuts and command-line
options. Used by the prompt builder to inject domain-specific guidance
so the agent uses direct shortcuts instead of hunting through menus.

VLC keyboard shortcuts work when the player window is focused.
For headless/CLI usage, ``cvlc`` runs without a GUI.
"""

from __future__ import annotations

import re

# pattern_regex → (keywords, commands list, verify hint)
VLC_RECIPES: dict[str, tuple[list[str], list[str], str]] = {
    # --- Playback controls ---
    r"play.*pause|pause.*play|toggle.*play|resume.*play": (
        ["vlc", "play", "pause", "toggle"],
        [
            "press(key=\"space\")",
        ],
        "Playback should toggle between play and pause",
    ),
    r"stop.*play|stop.*video|stop.*media": (
        ["vlc", "stop", "playback"],
        [
            "press(key=\"s\")",
        ],
        "Playback should stop",
    ),
    r"next.*track|skip.*track|next.*song|next.*video": (
        ["vlc", "next", "track", "skip"],
        [
            "press(key=\"n\")",
        ],
        "Next track in playlist should start playing",
    ),
    r"previous.*track|prev.*track|previous.*song|back.*track": (
        ["vlc", "previous", "track", "back"],
        [
            "press(key=\"p\")",
        ],
        "Previous track in playlist should start playing",
    ),

    # --- Volume ---
    r"volume.*up|increase.*volume|louder|raise.*volume": (
        ["vlc", "volume", "up", "increase"],
        [
            "hotkey(keys=[\"ctrl\",\"up\"])",
        ],
        "Volume should increase",
    ),
    r"volume.*down|decrease.*volume|quieter|lower.*volume": (
        ["vlc", "volume", "down", "decrease"],
        [
            "hotkey(keys=[\"ctrl\",\"down\"])",
        ],
        "Volume should decrease",
    ),
    r"mute|unmute|toggle.*mute|silence.*audio": (
        ["vlc", "mute", "unmute", "toggle"],
        [
            "press(key=\"m\")",
        ],
        "Audio should toggle between muted and unmuted",
    ),

    # --- Display ---
    r"full.*screen|enter.*fullscreen|toggle.*fullscreen|exit.*fullscreen": (
        ["vlc", "fullscreen", "toggle"],
        [
            "press(key=\"f\")",
        ],
        "VLC should toggle fullscreen mode",
    ),
    r"screenshot|capture.*frame|snap.*screen|save.*frame": (
        ["vlc", "screenshot", "capture", "frame"],
        [
            "hotkey(keys=[\"shift\",\"s\"])",
        ],
        "A screenshot of the current video frame should be saved",
    ),
    r"crop|aspect.*ratio|change.*ratio|video.*ratio": (
        ["vlc", "crop", "aspect ratio"],
        [
            "press(key=\"c\")",
        ],
        "Aspect ratio / crop mode should cycle",
    ),

    # --- File opening ---
    r"open.*file|load.*file|play.*file|open.*media": (
        ["vlc", "open", "file", "media"],
        [
            "hotkey(keys=[\"ctrl\",\"o\"])",
            "wait()",
        ],
        "Open file dialog should appear",
    ),
    r"open.*url|open.*stream|play.*url|network.*stream|open.*network": (
        ["vlc", "open", "url", "stream", "network"],
        [
            "hotkey(keys=[\"ctrl\",\"n\"])",
            "wait()",
        ],
        "Open network stream dialog should appear",
    ),

    # --- Subtitles ---
    r"cycle.*subtitle|next.*subtitle|switch.*subtitle|change.*subtitle": (
        ["vlc", "subtitle", "cycle", "switch"],
        [
            "press(key=\"v\")",
        ],
        "Subtitle track should cycle to the next available track",
    ),
    r"add.*subtitle|load.*subtitle|import.*subtitle": (
        ["vlc", "subtitle", "add", "load"],
        [
            # Menu: Subtitle → Add Subtitle File
            "hotkey(keys=[\"ctrl\",\"o\"])",
            "wait()",
        ],
        "Use Subtitle menu → Add Subtitle File to load an external subtitle file",
    ),

    # --- Playback speed ---
    r"speed.*up|faster.*play|increase.*speed|playback.*faster": (
        ["vlc", "speed", "faster", "increase"],
        [
            "press(key=\"]\")",
        ],
        "Playback speed should increase",
    ),
    r"speed.*down|slow.*down|slower.*play|decrease.*speed|playback.*slower": (
        ["vlc", "speed", "slower", "decrease"],
        [
            "press(key=\"[\")",
        ],
        "Playback speed should decrease",
    ),

    # --- Playlist and loop ---
    r"show.*playlist|open.*playlist|view.*playlist|toggle.*playlist": (
        ["vlc", "playlist", "show", "toggle"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "wait()",
        ],
        "Playlist panel should toggle visibility",
    ),
    r"loop|repeat|toggle.*loop|toggle.*repeat": (
        ["vlc", "loop", "repeat", "toggle"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
        ],
        "Loop / repeat mode should toggle",
    ),

    # --- Audio track ---
    r"audio.*track|switch.*audio|change.*audio|next.*audio": (
        ["vlc", "audio", "track", "switch"],
        [
            "press(key=\"b\")",
        ],
        "Audio track should cycle to the next available track",
    ),

    # --- Preferences ---
    r"vlc.*preference|vlc.*setting|open.*preference|vlc.*config": (
        ["vlc", "preferences", "settings", "config"],
        [
            "hotkey(keys=[\"ctrl\",\"p\"])",
            "wait()",
        ],
        "VLC preferences dialog should open",
    ),

    # --- CLI usage ---
    r"vlc.*fullscreen.*cli|play.*fullscreen.*terminal|cvlc|headless.*vlc": (
        ["vlc", "cli", "fullscreen", "cvlc", "headless"],
        [
            "type(text=\"vlc --fullscreen /path/to/file\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "VLC should open the file in fullscreen; use cvlc for headless playback",
    ),
}


def find_vlc_recipe(instruction: str) -> dict | None:
    """Find a matching VLC recipe for a task instruction.

    Returns a dict with:
    - commands: list of action strings to execute
    - verify: verification hint
    - keywords: list of keywords for the match
    - pattern: the regex pattern that matched
    """
    instruction_lower = instruction.lower()

    for pattern, (keywords, commands, verify) in VLC_RECIPES.items():
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_vlc_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with VLC shortcuts for a task.

    If we have a recipe for this VLC task, inject the exact actions
    into the prompt so the agent uses keyboard shortcuts instead of
    hunting through menus.
    """
    recipe = find_vlc_recipe(instruction)
    if not recipe:
        return ""

    commands = recipe["commands"]
    verify = recipe["verify"]

    lines = [
        "\n## Recommended Approach (VLC expert knowledge)",
        "For this VLC task, use these keyboard shortcuts / commands:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. {cmd}")

    if verify:
        lines.append(f"\nVerification: {verify}")

    lines.append("")
    lines.append("VLC keyboard shortcuts work when the player window is focused. "
                  "Use cvlc for headless/CLI playback without a GUI.")
    lines.append("After opening dialogs: wait() for the dialog to appear before interacting.")

    return "\n".join(lines)
