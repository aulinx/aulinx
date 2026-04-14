"""Thunderbird email client knowledge base — keyboard shortcuts and menu recipes.

Maps Thunderbird task patterns to precise keyboard shortcuts and menu
navigation. Used by the prompt builder to inject domain-specific
guidance so the agent uses direct shortcuts instead of hunting through
menus.

Thunderbird is a desktop mail client — most actions are reachable via
keyboard shortcuts. For settings that lack shortcuts, navigate via
Edit > Account Settings or Tools > Message Filters menus.
"""

from __future__ import annotations

import re

# pattern_regex → (keywords, commands list, verify hint)
THUNDERBIRD_RECIPES: dict[str, tuple[list[str], list[str], str]] = {
    # --- Compose / Reply / Forward ---
    r"compose.*new|new.*email|new.*message|write.*email|write.*message|create.*email": (
        ["thunderbird", "compose", "new", "email"],
        [
            "hotkey(keys=[\"ctrl\",\"n\"])",
            "wait()",
        ],
        "Compose window should open with empty To/Subject/Body fields",
    ),
    r"reply(?!.*all).*message|reply(?!.*all).*email|reply(?!.*all).*sender": (
        ["thunderbird", "reply", "email"],
        [
            "hotkey(keys=[\"ctrl\",\"r\"])",
            "wait()",
        ],
        "Reply compose window should open with original message quoted",
    ),
    r"reply.*all|reply.*everyone": (
        ["thunderbird", "reply all", "email"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"r\"])",
            "wait()",
        ],
        "Reply All compose window should open with all recipients",
    ),
    r"forward.*message|forward.*email|fwd": (
        ["thunderbird", "forward", "email"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "wait()",
        ],
        "Forward compose window should open with original message",
    ),
    r"send.*email|send.*message|send.*mail": (
        ["thunderbird", "send", "email"],
        [
            "hotkey(keys=[\"ctrl\",\"enter\"])",
        ],
        "Message should be sent and compose window should close",
    ),

    # --- Address Book ---
    r"address.*book|contact.*list|open.*contacts|manage.*contacts": (
        ["thunderbird", "address book", "contacts"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"b\"])",
            "wait()",
        ],
        "Address Book window should open",
    ),

    # --- Search ---
    r"quick.*filter|filter.*message|search.*message|search.*mail|find.*message|find.*mail": (
        ["thunderbird", "search", "filter", "message"],
        [
            "hotkey(keys=[\"ctrl\",\"k\"])",
            "wait()",
        ],
        "Quick filter bar or search box should be focused",
    ),
    r"advanced.*search|search.*all|global.*search": (
        ["thunderbird", "advanced search", "global"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"f\"])",
            "wait()",
        ],
        "Advanced search dialog should open",
    ),

    # --- Folder Management ---
    r"new.*folder|create.*folder|add.*folder": (
        ["thunderbird", "folder", "new", "create"],
        [
            # Right-click on the parent folder in the folder pane, then select New Folder
            "right_click(x=100, y=300)",
            "wait()",
        ],
        "Context menu should appear — select 'New Folder' to create a subfolder",
    ),
    r"move.*message|move.*mail|move.*to.*folder": (
        ["thunderbird", "move", "message", "folder"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"m\"])",
            "wait()",
        ],
        "Move to folder dialog should appear",
    ),

    # --- Delete / Junk ---
    r"delete.*message|delete.*email|remove.*message|remove.*email": (
        ["thunderbird", "delete", "message"],
        [
            "press(key=\"delete\")",
        ],
        "Selected message should be moved to Trash",
    ),
    r"mark.*junk|spam.*message|junk.*mail": (
        ["thunderbird", "junk", "spam"],
        [
            "press(key=\"j\")",
        ],
        "Message should be marked as junk",
    ),

    # --- Read / Unread ---
    r"mark.*read|mark.*unread|toggle.*read": (
        ["thunderbird", "mark", "read", "unread"],
        [
            "press(key=\"m\")",
        ],
        "Message read/unread status should toggle",
    ),

    # --- Tags ---
    r"tag.*message|label.*message|add.*tag|set.*tag": (
        ["thunderbird", "tag", "label"],
        [
            # Keys 1-9 set tags on selected messages
        ],
        "Use number keys 1-9 to set tags on the selected message",
    ),

    # --- Message Pane ---
    r"toggle.*message.*pane|show.*message.*pane|hide.*message.*pane|preview.*pane": (
        ["thunderbird", "message pane", "toggle", "preview"],
        [
            "press(key=\"f8\")",
        ],
        "Message pane visibility should toggle",
    ),

    # --- Attachment ---
    r"attach.*file|add.*attachment|insert.*attachment": (
        ["thunderbird", "attach", "file", "attachment"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"a\"])",
            "wait()",
        ],
        "File picker dialog should open for selecting attachment",
    ),

    # --- Settings / Preferences ---
    r"account.*setting|mail.*account|configure.*account|setup.*account": (
        ["thunderbird", "account settings", "configure"],
        [
            # Edit → Account Settings (or Tools → Account Settings)
            "hotkey(keys=[\"alt\",\"e\"])",
            "wait()",
            # Then click Account Settings in the menu
        ],
        "Account Settings dialog should open — navigate via Edit menu or Tools menu",
    ),
    r"signature|email.*signature|set.*signature|add.*signature": (
        ["thunderbird", "signature", "account"],
        [
            # Tools → Account Settings → signature section
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
            # Then click Account Settings
        ],
        "Open Account Settings, select the account, and edit the signature text area",
    ),
    r"preference|thunderbird.*setting|general.*setting|edit.*preference": (
        ["thunderbird", "preferences", "settings"],
        [
            # Edit → Preferences
            "hotkey(keys=[\"alt\",\"e\"])",
            "wait()",
            # Then click Preferences in the menu
        ],
        "Preferences tab should open in Thunderbird",
    ),

    # --- Filters ---
    r"message.*filter|mail.*filter|create.*filter|manage.*filter": (
        ["thunderbird", "filter", "message", "manage"],
        [
            # Tools → Message Filters
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
            # Then click Message Filters in the menu
        ],
        "Message Filters dialog should open",
    ),

    # --- Print ---
    r"print.*message|print.*email|print.*mail": (
        ["thunderbird", "print", "message"],
        [
            "hotkey(keys=[\"ctrl\",\"p\"])",
            "wait()",
        ],
        "Print dialog should appear",
    ),

    # --- Check Mail ---
    r"check.*mail|check.*email|get.*mail|get.*new.*mail|fetch.*mail|receive.*mail": (
        ["thunderbird", "check", "mail", "fetch"],
        [
            "press(key=\"f5\")",
            "wait()",
        ],
        "Thunderbird should check for new messages",
    ),
}


def find_thunderbird_recipe(instruction: str) -> dict | None:
    """Find a matching Thunderbird recipe for a task instruction.

    Returns a dict with:
    - commands: list of action strings to execute
    - verify: verification hint
    - keywords: list of keywords for the match
    - pattern: the regex pattern that matched
    """
    instruction_lower = instruction.lower()

    for pattern, (keywords, commands, verify) in THUNDERBIRD_RECIPES.items():
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_thunderbird_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with Thunderbird shortcuts for a task.

    If we have a recipe for this Thunderbird task, inject the exact actions
    into the prompt so the agent uses keyboard shortcuts instead of hunting
    through menus.
    """
    recipe = find_thunderbird_recipe(instruction)
    if not recipe:
        return ""

    commands = recipe["commands"]
    verify = recipe["verify"]

    lines = [
        "\n## Recommended Approach (Thunderbird expert knowledge)",
        "For this Thunderbird task, use these keyboard shortcuts / menu navigation:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. {cmd}")

    if verify:
        lines.append(f"\nVerification: {verify}")

    lines.append("")
    lines.append("Thunderbird is a desktop email client — use keyboard shortcuts "
                  "for speed. For settings without shortcuts, use the menu bar "
                  "(Edit/Tools menus).")
    lines.append("After actions: wait() for dialogs/windows to appear before interacting.")

    return "\n".join(lines)
