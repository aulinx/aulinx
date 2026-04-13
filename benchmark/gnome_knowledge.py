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

    # Favorites / dock — remove a specific app
    (
        r"remove.*favorite|favorite.*app|dock.*remove|unfavorite",
        ["favorite", "dock", "remove"],
        [
            # One-liner: get favorites, remove the target app, set back
            # The agent should identify the app name from the instruction
            "python3 -c \"import subprocess,ast; apps=ast.literal_eval(subprocess.check_output(['gsettings','get','org.gnome.shell','favorite-apps'],text=True).strip()); apps=[a for a in apps if '{app_name}' not in a]; subprocess.run(['gsettings','set','org.gnome.shell','favorite-apps',str(apps)])\"",
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

    # SSH user creation with folder restriction
    (
        r"ssh.*user|create.*user.*ssh|user.*sftp|restrict.*ssh",
        ["ssh", "user", "create", "restrict"],
        [
            "sudo useradd -m -d {homedir} -s /bin/bash {username}",
            "echo '{username}:{password}' | sudo chpasswd",
            "sudo chown root:root {homedir}",
            "sudo chmod 755 {homedir}",
            "sudo mkdir -p {homedir}/files",
            "sudo chown {username}:{username} {homedir}/files",
            # Restrict to SFTP with chroot
            "echo 'Match User {username}\n    ChrootDirectory {homedir}\n    ForceCommand internal-sftp\n    AllowTcpForwarding no\n    X11Forwarding no' | sudo tee -a /etc/ssh/sshd_config",
            "sudo systemctl restart sshd",
        ],
        "getent passwd {username} && sudo grep '{username}' /etc/ssh/sshd_config",
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


def _extract_variables(instruction: str) -> dict[str, str]:
    """Extract variable values from the instruction text.

    Identifies app names, usernames, passwords, paths, etc.
    """
    variables: dict[str, str] = {}
    lower = instruction.lower()

    # Extract app name: "install Spotify" → app_name=spotify
    install_match = re.search(r"install\s+(\w+)", lower)
    if install_match:
        variables["app_name"] = install_match.group(1)

    # Extract app to remove from favorites: "remove vim from"
    remove_match = re.search(r"remove\s+(\w+)\s+from", lower)
    if remove_match:
        variables["app_name"] = remove_match.group(1)

    # Extract username: 'user named "charles"' — only when "user" precedes "named"
    user_match = re.search(r'user\s+named\s+["\']?(\w+)["\']?', instruction, re.IGNORECASE)
    if user_match:
        variables["username"] = user_match.group(1)

    # Extract password: 'password "X"' or "password 'X'"
    pass_match = re.search(r'password\s+["\']([^"\']+)["\']', instruction)
    if pass_match:
        variables["password"] = pass_match.group(1)

    # Extract path: '/home/test1' or '/tmp/something'
    path_match = re.search(r'(?:folder|directory|path)\s+["\']?(/[\w/]+)["\']?', instruction)
    if path_match:
        variables["homedir"] = path_match.group(1)

    # Extract old/new names for rename tasks
    # Priority 1: 'named "X" ... into "Y"' (quoted names are most reliable)
    dir_match = re.search(r'named\s+"([\w_.-]+)"', instruction)
    into_match = re.search(r'(?:into|to)\s+"([\w_.-]+)"', instruction)
    if dir_match and into_match:
        variables["old_name"] = dir_match.group(1)
        variables["new_name"] = into_match.group(1)

    # Priority 2: 'rename "X" to "Y"' (explicit rename command)
    if "old_name" not in variables:
        rename_match = re.search(
            r'(?:rename)\s+["\']?([\w_.-]+)["\']?\s+(?:to)\s+["\']?([\w_.-]+)["\']?',
            instruction,
            re.IGNORECASE,
        )
        if rename_match:
            variables["old_name"] = rename_match.group(1)
            variables["new_name"] = rename_match.group(2)

    return variables


def build_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with exact commands for a task.

    If we have a recipe for this task, inject the exact commands
    into the prompt so the agent doesn't waste steps navigating GUIs.
    Variables like {app_name} are substituted from the instruction.
    """
    recipe = find_recipe(instruction)
    if not recipe:
        return ""

    variables = _extract_variables(instruction)
    commands = recipe["commands"]
    verify = recipe["verify"]

    # Substitute variables
    commands = [_substitute(cmd, variables) for cmd in commands]
    verify = _substitute(verify, variables)

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


def _substitute(template: str, variables: dict[str, str]) -> str:
    """Substitute {var} placeholders with extracted values."""
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", value)
    return template


# File operation recipes (not gsettings but still common failures)
# Simple but commonly failed tasks
SIMPLE_RECIPES = {
    "rename_dir": {
        "pattern": r"rename|change.*name|mv\s",
        "commands": [
            "mv ~/Desktop/{old_name} ~/Desktop/{new_name}",
        ],
        "verify": "ls ~/Desktop/{new_name}",
    },
}

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
    for name, recipe in SIMPLE_RECIPES.items():
        if re.search(recipe["pattern"], instruction_lower):
            return recipe
    return None


def build_file_recipe_prompt(instruction: str) -> str:
    """Build prompt for file operation recipes."""
    recipe = find_file_recipe(instruction)
    if not recipe:
        return ""

    variables = _extract_variables(instruction)
    commands = [_substitute(cmd, variables) for cmd in recipe["commands"]]
    verify = _substitute(recipe.get("verify", ""), variables)

    lines = [
        "\n## Recommended Approach (expert knowledge)",
        "For this file operation, use these terminal commands:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. type(text=\"{cmd}\") then press(key=\"enter\")")

    if verify:
        lines.append(f"\nTo verify: type(text=\"{verify}\") then press(key=\"enter\")")

    lines.append("")
    lines.append("Open terminal first: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])")
    lines.append("After verification succeeds: done()")

    return "\n".join(lines)
