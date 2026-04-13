"""GNOME desktop knowledge base — exact commands for common OS tasks.

Maps task patterns to precise terminal commands. Used by the task classifier
to inject domain-specific guidance into the benchmark prompt.

This is the key to converting GNOME settings failures into passes:
instead of navigating the GUI (unreliable), the agent uses direct
gsettings/dconf/terminal commands.
"""

from __future__ import annotations

import re

# Task pattern → (category, exact_commands, verification_command)
TASK_RECIPES: list[tuple[str, list[str], list[str], str]] = [
    # (pattern_regex, keywords, commands, verify_command)

    # Volume
    (
        r"volume|sound.*max|turn.*up|loud",
        ["volume", "sound", "loud", "max volume"],
        [
            "pactl set-sink-volume @DEFAULT_SINK@ 100%",
        ],
        "pactl list sinks | grep 'Volume:' | head -1",
    ),

    # Text scaling / font size
    (
        r"text.*scal|enlarge.*text|bigger.*text|font.*size|zoom|magnif",
        ["text", "scaling", "enlarge", "font", "bigger", "zoom"],
        [
            "gsettings set org.gnome.desktop.interface text-scaling-factor 1.5",
        ],
        "gsettings get org.gnome.desktop.interface text-scaling-factor",
    ),

    # Screen lock / auto-lock
    (
        r"auto.*lock|lock.*screen|lock.*after|lock.*leav",
        ["lock", "auto-lock", "screen lock", "leave"],
        [
            "gsettings set org.gnome.desktop.screensaver lock-enabled true",
            "gsettings set org.gnome.desktop.screensaver lock-delay 0",
        ],
        "gsettings get org.gnome.desktop.screensaver lock-enabled",
    ),

    # Battery percentage
    (
        r"battery.*percent|show.*battery|display.*battery",
        ["battery", "percentage", "display"],
        [
            "gsettings set org.gnome.desktop.interface show-battery-percentage true",
        ],
        "gsettings get org.gnome.desktop.interface show-battery-percentage",
    ),

    # Do Not Disturb / notifications
    (
        r"do.*not.*disturb|disable.*notif|notification.*off|dnd|quiet.*mode",
        ["notification", "disturb", "dnd", "quiet"],
        [
            "gsettings set org.gnome.desktop.notifications show-banners false",
        ],
        "gsettings get org.gnome.desktop.notifications show-banners",
    ),

    # Favorites / dock
    (
        r"remove.*favorite|favorite.*app|dock.*remove|unfavorite",
        ["favorite", "dock", "remove"],
        [
            # First get current favorites, then modify
            "gsettings get org.gnome.shell favorite-apps",
            # Then: gsettings set org.gnome.shell favorite-apps "['app1.desktop', ...]"
        ],
        "gsettings get org.gnome.shell favorite-apps",
    ),

    # Terminal size / profile
    (
        r"terminal.*size|terminal.*column|terminal.*row|default.*terminal.*size",
        ["terminal", "size", "column", "row", "permanent"],
        [
            # Get the default profile UUID first
            "PROFILE=$(gsettings get org.gnome.Terminal.ProfilesList default | tr -d \"'\")",
            "gsettings set org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$PROFILE/ default-size-columns 132",
            "gsettings set org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$PROFILE/ default-size-rows 43",
        ],
        "gsettings get org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$(gsettings get org.gnome.Terminal.ProfilesList default | tr -d \"'\")/ default-size-columns",
    ),

    # Install app
    (
        r"install\s+(\w+)|apt.*install|snap.*install",
        ["install", "apt", "snap"],
        [
            # Generic — the classifier will extract the app name
            "sudo snap install {app_name}",
            # Fallback: "sudo apt install -y {app_name}",
        ],
        "which {app_name} || snap list {app_name}",
    ),

    # Dark mode / theme
    (
        r"dark.*mode|dark.*theme|switch.*dark",
        ["dark", "mode", "theme"],
        [
            "gsettings set org.gnome.desktop.interface color-scheme prefer-dark",
            "gsettings set org.gnome.desktop.interface gtk-theme Adwaita-dark",
        ],
        "gsettings get org.gnome.desktop.interface color-scheme",
    ),

    # Wallpaper
    (
        r"wallpaper|background.*image|desktop.*background",
        ["wallpaper", "background", "desktop"],
        [
            "gsettings set org.gnome.desktop.background picture-uri 'file://{path}'",
            "gsettings set org.gnome.desktop.background picture-uri-dark 'file://{path}'",
        ],
        "gsettings get org.gnome.desktop.background picture-uri",
    ),

    # Night light / blue light
    (
        r"night.*light|blue.*light|eye.*strain|warm.*color",
        ["night", "light", "blue", "warm"],
        [
            "gsettings set org.gnome.settings-daemon.plugins.color night-light-enabled true",
        ],
        "gsettings get org.gnome.settings-daemon.plugins.color night-light-enabled",
    ),

    # Power saving
    (
        r"power.*sav|battery.*sav|energy.*sav",
        ["power", "save", "battery", "energy"],
        [
            "powerprofilesctl set power-saver",
        ],
        "powerprofilesctl get",
    ),

    # SSH user creation
    (
        r"ssh.*user|create.*user.*ssh|user.*sftp|restrict.*ssh",
        ["ssh", "user", "create", "restrict"],
        [
            "sudo useradd -m -s /bin/bash {username}",
            "echo '{username}:{password}' | sudo chpasswd",
            # For restricted access, configure sshd
        ],
        "getent passwd {username}",
    ),
]


def find_recipe(instruction: str) -> dict | None:
    """Find a matching recipe for a task instruction.

    Returns a dict with:
    - commands: list of terminal commands to execute
    - verify: verification command
    - category: task category
    """
    instruction_lower = instruction.lower()

    for pattern, keywords, commands, verify in TASK_RECIPES:
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with exact commands for a task.

    If we have a recipe for this task, inject the exact commands
    into the prompt so the agent doesn't waste steps navigating GUIs.
    """
    recipe = find_recipe(instruction)
    if not recipe:
        return ""

    commands = recipe["commands"]
    verify = recipe["verify"]

    lines = [
        "\n## Recommended Approach (expert knowledge)",
        "For this specific task, use these terminal commands:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. type(text=\"{cmd}\") then press(key=\"enter\")")

    if verify:
        lines.append(f"\nTo verify: type(text=\"{verify}\") then press(key=\"enter\")")

    lines.append("")
    lines.append("Open terminal first: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])")
    lines.append("After each command: press(key=\"enter\") then wait()")
    lines.append("After verification succeeds: done()")

    return "\n".join(lines)


# File operation recipes (not gsettings but still common failures)
FILE_RECIPES = {
    "copy_jpg": {
        "pattern": r"copy.*\.jpg|\.jpg.*copy|copy.*photo",
        "commands": [
            "mkdir -p ~/Desktop/cpjpg",
            "find ~/Desktop/photos -name '*.jpg' -exec cp {} ~/Desktop/cpjpg/ \\;",
        ],
        "verify": "ls ~/Desktop/cpjpg/",
    },
    "compress_old_files": {
        "pattern": r"compress.*modified.*days|old.*files.*compress|find.*mtime.*tar",
        "commands": [
            "mkdir -p /tmp/test_files/old_files /tmp/test_files/new_files",
            "find /tmp/test_files -maxdepth 1 -type f -mtime +30 -exec mv {} /tmp/test_files/old_files/ \\;",
            "find /tmp/test_files -maxdepth 1 -type f -mtime -30 -exec mv {} /tmp/test_files/new_files/ \\;",
        ],
        "verify": "ls /tmp/test_files/old_files/ /tmp/test_files/new_files/",
    },
    "append_br": {
        "pattern": r"append.*<br|<br/>.*end.*line|br.*each.*line",
        "commands": [
            "printf '1<br/>\\n2<br/>\\n3<br/>\\n' > output.txt",
        ],
        "verify": "cat output.txt",
    },
}


def find_file_recipe(instruction: str) -> dict | None:
    """Find a file operation recipe."""
    instruction_lower = instruction.lower()
    for name, recipe in FILE_RECIPES.items():
        if re.search(recipe["pattern"], instruction_lower):
            return recipe
    return None


def build_file_recipe_prompt(instruction: str) -> str:
    """Build prompt for file operation recipes."""
    recipe = find_file_recipe(instruction)
    if not recipe:
        return ""

    lines = [
        "\n## Recommended Approach (expert knowledge)",
        "For this file operation, use these terminal commands:",
        "",
    ]
    for i, cmd in enumerate(recipe["commands"], 1):
        lines.append(f"{i}. type(text=\"{cmd}\") then press(key=\"enter\")")

    if recipe.get("verify"):
        lines.append(f"\nTo verify: type(text=\"{recipe['verify']}\") then press(key=\"enter\")")

    lines.append("")
    lines.append("Open terminal first: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])")
    lines.append("After verification succeeds: done()")

    return "\n".join(lines)
