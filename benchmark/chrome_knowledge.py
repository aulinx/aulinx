"""Chrome browser knowledge base — keyboard shortcuts and URL recipes.

Maps Chrome task patterns to precise keyboard shortcuts and chrome://
URL navigation. Used by the prompt builder to inject domain-specific
guidance so the agent uses direct navigation instead of hunting through
menus.

Chrome settings are web pages at chrome://settings/* so the fastest
approach is always: focus address bar (Ctrl+L), type the URL, press
Enter.
"""

from __future__ import annotations

import re

# pattern_regex → (keywords, commands list, verify hint)
CHROME_RECIPES: dict[str, tuple[list[str], list[str], str]] = {
    # --- Settings navigation ---
    r"do.*not.*track|dnt|tracking.*protect": (
        ["chrome", "do not track", "privacy", "tracking"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/privacy\")",
            "press(key=\"enter\")",
            "wait()",
            # Then find and enable "Send a Do Not Track request"
        ],
        "Look for 'Do Not Track' toggle on the privacy settings page",
    ),
    r"chrome.*password|saved.*password|manage.*password": (
        ["chrome", "passwords", "saved"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/passwords\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "Password manager page should be visible",
    ),
    r"chrome.*download|download.*setting|download.*folder|download.*location": (
        ["chrome", "downloads", "settings"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/downloads\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "Downloads settings page should be visible",
    ),
    r"chrome.*extension|manage.*extension|install.*extension": (
        ["chrome", "extensions", "manage"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://extensions\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "Extensions page should be visible",
    ),
    r"chrome.*homepage|set.*homepage|startup.*page": (
        ["chrome", "homepage", "startup"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/onStartup\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "On Startup settings page should be visible",
    ),
    r"chrome.*search.*engine|default.*search|change.*search": (
        ["chrome", "search engine", "default"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/search\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "Search engine settings page should be visible",
    ),
    r"chrome.*appearance|chrome.*theme|chrome.*font": (
        ["chrome", "appearance", "theme", "font"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
            "type(text=\"chrome://settings/appearance\")",
            "press(key=\"enter\")",
            "wait()",
        ],
        "Appearance settings page should be visible",
    ),
    r"clear.*brows|clear.*cache|clear.*history|delete.*cookies": (
        ["chrome", "clear", "browsing data", "cache", "cookies"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"delete\"])",
            "wait()",
        ],
        "Clear browsing data dialog should be visible",
    ),

    # --- Tab management ---
    r"reopen.*tab|restore.*tab|closed.*tab.*back": (
        ["chrome", "reopen", "tab", "restore"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"t\"])",
        ],
        "Previously closed tab should reappear",
    ),
    r"new.*tab": (
        ["chrome", "new", "tab"],
        [
            "hotkey(keys=[\"ctrl\",\"t\"])",
        ],
        "New tab should open",
    ),
    r"close.*tab": (
        ["chrome", "close", "tab"],
        [
            "hotkey(keys=[\"ctrl\",\"w\"])",
        ],
        "Current tab should close",
    ),
    r"next.*tab|switch.*tab|tab.*right": (
        ["chrome", "next", "tab", "switch"],
        [
            "hotkey(keys=[\"ctrl\",\"tab\"])",
        ],
        "Focus should move to the next tab",
    ),
    r"previous.*tab|tab.*left": (
        ["chrome", "previous", "tab"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"tab\"])",
        ],
        "Focus should move to the previous tab",
    ),

    # --- Bookmarks ---
    r"add.*bookmark|bookmark.*page|bookmark.*this|save.*bookmark": (
        ["chrome", "bookmark", "add", "save"],
        [
            "hotkey(keys=[\"ctrl\",\"d\"])",
            "wait()",
        ],
        "Bookmark dialog should appear",
    ),
    r"bookmark.*manager|manage.*bookmark|organize.*bookmark|edit.*bookmark": (
        ["chrome", "bookmark", "manager", "organize"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"o\"])",
            "wait()",
        ],
        "Bookmark manager tab should open",
    ),
    r"bookmark.*folder|create.*folder.*bookmark|new.*folder.*bookmark": (
        ["chrome", "bookmark", "folder", "create"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"o\"])",
            "wait()",
            # Then right-click in the bookmark manager to create a folder
        ],
        "Bookmark manager should open; right-click to add folder",
    ),
    r"show.*bookmark.*bar|bookmark.*bar.*visible|toggle.*bookmark.*bar": (
        ["chrome", "bookmark bar", "show", "toggle"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"b\"])",
        ],
        "Bookmark bar visibility should toggle",
    ),

    # --- Navigation ---
    r"address.*bar|url.*bar|focus.*bar|location.*bar": (
        ["chrome", "address bar", "url", "focus"],
        [
            "hotkey(keys=[\"ctrl\",\"l\"])",
        ],
        "Address bar should be focused",
    ),
    r"go.*back|navigate.*back|previous.*page": (
        ["chrome", "back", "navigate"],
        [
            "hotkey(keys=[\"alt\",\"left\"])",
        ],
        "Browser should navigate back",
    ),
    r"go.*forward|navigate.*forward": (
        ["chrome", "forward", "navigate"],
        [
            "hotkey(keys=[\"alt\",\"right\"])",
        ],
        "Browser should navigate forward",
    ),
    r"reload|refresh.*page": (
        ["chrome", "reload", "refresh"],
        [
            "hotkey(keys=[\"ctrl\",\"r\"])",
        ],
        "Page should reload",
    ),
    r"open.*dev.*tool|inspect.*element|developer.*tool": (
        ["chrome", "developer tools", "inspect"],
        [
            "press(key=\"f12\")",
            "wait()",
        ],
        "Developer tools panel should open",
    ),
    r"view.*download|open.*download|download.*list|show.*download": (
        ["chrome", "downloads", "list", "view"],
        [
            "hotkey(keys=[\"ctrl\",\"j\"])",
            "wait()",
        ],
        "Downloads page should open",
    ),
    r"open.*history|view.*history|browsing.*history": (
        ["chrome", "history", "view"],
        [
            "hotkey(keys=[\"ctrl\",\"h\"])",
            "wait()",
        ],
        "History page should open",
    ),
    r"find.*in.*page|search.*page|find.*text": (
        ["chrome", "find", "search", "page"],
        [
            "hotkey(keys=[\"ctrl\",\"f\"])",
            "wait()",
        ],
        "Find bar should appear",
    ),
    r"zoom.*in|increase.*zoom|make.*bigger": (
        ["chrome", "zoom", "in", "bigger"],
        [
            "hotkey(keys=[\"ctrl\",\"equal\"])",
        ],
        "Page zoom should increase",
    ),
    r"zoom.*out|decrease.*zoom|make.*smaller": (
        ["chrome", "zoom", "out", "smaller"],
        [
            "hotkey(keys=[\"ctrl\",\"minus\"])",
        ],
        "Page zoom should decrease",
    ),
    r"reset.*zoom|zoom.*100|default.*zoom": (
        ["chrome", "zoom", "reset", "default"],
        [
            "hotkey(keys=[\"ctrl\",\"0\"])",
        ],
        "Page zoom should reset to 100%",
    ),
    r"full.*screen|enter.*fullscreen": (
        ["chrome", "fullscreen"],
        [
            "press(key=\"f11\")",
        ],
        "Browser should enter fullscreen mode",
    ),
}


def find_chrome_recipe(instruction: str) -> dict | None:
    """Find a matching Chrome recipe for a task instruction.

    Returns a dict with:
    - commands: list of action strings to execute
    - verify: verification hint
    - keywords: list of keywords for the match
    - pattern: the regex pattern that matched
    """
    instruction_lower = instruction.lower()

    for pattern, (keywords, commands, verify) in CHROME_RECIPES.items():
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_chrome_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with Chrome shortcuts for a task.

    If we have a recipe for this Chrome task, inject the exact actions
    into the prompt so the agent uses keyboard shortcuts and chrome://
    URLs instead of hunting through menus.
    """
    recipe = find_chrome_recipe(instruction)
    if not recipe:
        return ""

    commands = recipe["commands"]
    verify = recipe["verify"]

    lines = [
        "\n## Recommended Approach (Chrome expert knowledge)",
        "For this Chrome task, use these keyboard shortcuts / URL navigation:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. {cmd}")

    if verify:
        lines.append(f"\nVerification: {verify}")

    lines.append("")
    lines.append("Chrome settings are web pages — navigate via address bar (Ctrl+L) "
                  "and chrome:// URLs instead of clicking through menus.")
    lines.append("After navigation: wait() for the page to load before interacting.")

    return "\n".join(lines)
