"""Build LLM prompts from OSWorld observations.

Converts a11y tree XML + task instruction into a compact prompt
that guides the LLM to output structured actions.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# Namespace prefixes used by OSWorld's a11y tree
_NS_STATE = "https://accessibility.ubuntu.example.org/ns/state"
_NS_COMP = "https://accessibility.ubuntu.example.org/ns/component"
_NS_VALUE = "https://accessibility.ubuntu.example.org/ns/value"

# Roles we care about (interactive elements)
_INTERACTIVE_ROLES = {
    "button", "push button", "toggle button",
    "text", "textbox", "text field", "entry",
    "link",
    "menu", "menu item", "menu bar",
    "check box", "check-box", "radio button",
    "combo box", "combo-box", "list box",
    "tab", "tab item",
    "slider", "spin button",
    "tree item", "list item",
    "tool bar", "scroll bar",
}

SYSTEM_PROMPT = """\
You are Aulinx, an AI agent controlling an Ubuntu Linux desktop via GNOME. \
You receive a structured accessibility tree listing visible UI elements with \
their screen coordinates. Complete the user's task by outputting ONE action per step.

## Response format

You MUST respond with EXACTLY this format — thought first, then action:

thought: <your reasoning about what to do next and why>
action: <one action call>

Do NOT output multiple actions. Do NOT output anything else.

## Available actions

- click(x=<int>, y=<int>) — left click at coordinates
- double_click(x=<int>, y=<int>) — double click (use to open files/folders)
- right_click(x=<int>, y=<int>) — right click for context menu
- type(text="<string>") — type text into the currently focused text field
- press(key="<key>") — press a single key: enter, tab, escape, backspace, delete, space, up, down, left, right, home, end, pageup, pagedown, f1-f12
- hotkey(keys=["<key>", "<key>"]) — key combination, e.g. ["ctrl", "s"], ["alt", "f4"], ["ctrl", "shift", "t"]
- scroll(x=<int>, y=<int>, direction="<up|down>", amount=<int>) — scroll at position
- drag(start_x=<int>, start_y=<int>, end_x=<int>, end_y=<int>) — drag between positions
- wait() — wait for UI to update (use after launching apps or slow operations)
- done() — task is complete, stop
- fail() — task cannot be completed, stop

## Coordinate rules

- Elements show: role "name" at (x,y) size (w,h) center=(cx,cy)
- The center= value is PRE-COMPUTED for you — use it directly for clicks
- Example: button "Save" at (100,200) size (80,30) center=(140,215) → click(x=140, y=215)
- ALWAYS use the center= coordinates, do NOT compute coordinates yourself

## Strategy rules

1. ALWAYS compare the current screen state to your previous actions before acting
2. If the screen hasn't changed after your last action, try a DIFFERENT approach — do not repeat the same click
3. To open a folder: double_click it (single click only selects)
4. To type in a field: click the field first to focus it, then use type()
5. Use hotkey(keys=["ctrl","l"]) to focus the address bar in file managers and browsers
6. Use the application menu or keyboard shortcuts when clicking doesn't work
7. Output done() as soon as the task objective is visibly achieved
8. Output fail() if you've tried 5+ different approaches without progress — do NOT exhaust all steps

## Multi-app workflow strategy

When a task involves multiple applications:
1. Break it into sub-tasks mentally: "First do X in App1, then Y in App2"
2. Complete one app's work fully before switching to the next
3. Use Alt+Tab to switch between windows, or click the target window in the taskbar
4. Use the terminal for file operations between apps (copy, convert, move)
5. For file format conversions: use libreoffice --headless --convert-to pdf file.docx
6. To copy text between apps: Ctrl+C in source, Alt+Tab to target, Ctrl+V
7. To open a file in a specific app: use the terminal (e.g., libreoffice file.docx, gimp image.png)

## Self-correction rules

1. After EVERY action, compare the new screen state to the previous one
2. If the screen state is IDENTICAL after your action, your action had no effect — try something different
3. If a terminal command produced an error, read the error message and fix the command
4. If you've been clicking the same area 3+ times with no change, switch to keyboard shortcuts
5. For settings changes: ALWAYS prefer terminal commands (gsettings/dconf) over GUI navigation
6. After completing the task, call done() IMMEDIATELY — do not continue with unnecessary verification steps
7. If the task asks to change a setting, change it and call done(). You don't need to visually confirm.

## Terminal usage

When using the terminal:
1. Open terminal: hotkey(keys=["ctrl","alt","t"])
2. Type the command: type(text="your command here")
3. Execute it: press(key="enter")
4. Wait for output: wait()
5. Read the terminal output from the accessibility tree before continuing
- ALWAYS press Enter after typing a command — type() alone does NOT execute it
- After execution, the terminal output appears in the accessibility tree as text elements

## GNOME system settings (IMPORTANT)

Do NOT waste steps trying to navigate the GNOME Settings GUI by clicking. Instead, use terminal commands:
- **Volume:** type(text="pactl set-sink-volume @DEFAULT_SINK@ 100%") then press(key="enter")
- **Text/scaling:** type(text="gsettings set org.gnome.desktop.interface text-scaling-factor 1.5") then press(key="enter")
- **Auto-lock:** type(text="gsettings set org.gnome.desktop.screensaver lock-enabled true") then press(key="enter")
- **Battery %:** type(text="gsettings set org.gnome.desktop.interface show-battery-percentage true") then press(key="enter")
- **Do Not Disturb:** type(text="gsettings set org.gnome.desktop.notifications show-banners false") then press(key="enter")
- **Favorites:** type(text="gsettings get org.gnome.shell favorite-apps") to see current, then use gsettings set to modify
- **Any GNOME setting:** use gsettings or dconf in the terminal — it's faster and more reliable than GUI navigation
- **Install apps:** type(text="sudo apt install -y <package>") or type(text="sudo snap install <package>")
"""


def parse_a11y_tree(xml_str: str, max_elements: int = 50) -> str:
    """Parse OSWorld's a11y XML into a compact text representation.

    Returns a numbered list of interactive elements with their roles,
    names, coordinates, and states. Much more token-efficient than
    raw XML.
    """
    if not xml_str or not xml_str.strip():
        return "[No accessibility tree available]"

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        # Sometimes the tree is already a plain-text representation
        return xml_str[:4000]

    elements = []
    _walk(root, elements, max_elements)

    if not elements:
        return "[No interactive elements found in accessibility tree]"

    lines = []
    for i, elem in enumerate(elements):
        parts = [f"[{i}] {elem['role']}"]
        if elem.get("name"):
            parts.append(f'"{elem["name"]}"')
        if elem.get("value"):
            parts.append(f"value={elem['value']!r}")
        if elem.get("coord") and elem.get("size"):
            x, y = elem["coord"]
            w, h = elem["size"]
            cx, cy = x + w // 2, y + h // 2
            parts.append(f"at ({x},{y}) size ({w},{h}) center=({cx},{cy})")
        states = []
        if elem.get("focused"):
            states.append("focused")
        if elem.get("checked"):
            states.append("checked")
        if elem.get("selected"):
            states.append("selected")
        if elem.get("expanded"):
            states.append("expanded")
        if states:
            parts.append(f"[{','.join(states)}]")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def _walk(node: ET.Element, elements: list, max_elements: int):
    """Recursively walk the a11y tree, collecting interactive elements."""
    if len(elements) >= max_elements:
        return

    tag = node.tag.lower().replace("_", " ").replace("-", " ")
    name = node.get("name", "") or node.get("description", "") or ""
    showing = node.get(f"{{{_NS_STATE}}}showing", node.get("showing", ""))
    visible = node.get(f"{{{_NS_STATE}}}visible", node.get("visible", ""))

    # Parse coordinates
    coord_str = node.get(f"{{{_NS_COMP}}}screencoord", node.get("screencoord", ""))
    size_str = node.get(f"{{{_NS_COMP}}}size", node.get("size", ""))

    coord = _parse_tuple(coord_str)
    size = _parse_tuple(size_str)

    # Include if it's interactive, visible, and has coordinates
    is_interactive = any(r in tag for r in _INTERACTIVE_ROLES) or name.strip()
    is_visible = showing != "false" and visible != "false"

    if is_interactive and is_visible and coord and size and size[0] > 0 and size[1] > 0:
        elem = {
            "role": tag,
            "name": name.strip(),
            "coord": coord,
            "size": size,
        }

        # Value
        value = node.get(f"{{{_NS_VALUE}}}value", node.get("value", ""))
        if value:
            elem["value"] = value[:100]

        # States
        for state_name in ("focused", "checked", "selected", "expanded"):
            val = node.get(f"{{{_NS_STATE}}}{state_name}", node.get(state_name, ""))
            if val == "true":
                elem[state_name] = True

        elements.append(elem)

    # Recurse into children
    for child in node:
        _walk(child, elements, max_elements)


def _parse_tuple(s: str) -> tuple[int, int] | None:
    """Parse a coordinate/size string like '(123, 456)' into (123, 456)."""
    if not s:
        return None
    match = re.match(r"\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?", s)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return None


def build_prompt(instruction: str, a11y_tree: str, screenshot_desc: str | None = None,
                 history: list[dict] | None = None, max_steps: int = 30) -> list[dict]:
    """Build the full message list for the LLM.

    Returns a list of message dicts suitable for chat completion APIs.
    """
    parsed_tree = parse_a11y_tree(a11y_tree)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add history as a compact summary in the user message
    history_block = ""
    if history:
        recent = history[-6:]  # Last 6 steps
        # Older steps get compressed, recent steps kept verbose
        history_lines = []
        for i, entry in enumerate(recent):
            obs = entry.get("observation", "")
            resp = entry.get("response", "")
            if i < len(recent) - 3:
                # Older: just the action taken
                history_lines.append(f"  {resp}")
            else:
                # Recent: action + key observation
                obs_first = obs.split("\n")[0] if obs else ""
                history_lines.append(f"  {resp}  ({obs_first})")
        history_block = "\n## Previous Actions (oldest→newest)\n" + "\n".join(history_lines)
        history_block += "\n\nDo NOT repeat the same action. Try a DIFFERENT approach if the screen hasn't changed."
        history_block += "\nUse the center= coordinates shown above for clicks — they are pre-computed for you."

    # Inject domain-specific recipes if we have expert knowledge for this task
    recipe_block = ""
    if not history:  # Only on first step — don't repeat every step
        from .chrome_knowledge import build_chrome_recipe_prompt
        from .gimp_knowledge import build_gimp_recipe_prompt
        from .gnome_knowledge import build_file_recipe_prompt, build_recipe_prompt
        from .libreoffice_knowledge import build_libreoffice_recipe_prompt
        from .thunderbird_knowledge import build_thunderbird_recipe_prompt
        from .vlc_knowledge import build_vlc_recipe_prompt
        from .vscode_knowledge import build_vscode_recipe_prompt
        recipe_block = (
            build_recipe_prompt(instruction)
            or build_chrome_recipe_prompt(instruction)
            or build_vscode_recipe_prompt(instruction)
            or build_libreoffice_recipe_prompt(instruction)
            or build_gimp_recipe_prompt(instruction)
            or build_thunderbird_recipe_prompt(instruction)
            or build_vlc_recipe_prompt(instruction)
            or build_file_recipe_prompt(instruction)
        )

    # Step counter — helps the LLM manage its budget
    step_num = len(history) + 1 if history else 1
    steps_remaining = max_steps - step_num + 1

    # Current observation
    step_info = f"[Step {step_num}/{max_steps} — {steps_remaining} remaining]"
    if steps_remaining <= 5:
        step_info += " ⚠ Running low on steps! Finish the task or call done()/fail() soon."
    obs_parts = [f"## Task\n{instruction}\n{step_info}\n"]
    if recipe_block:
        obs_parts.append(recipe_block)
    obs_parts.append(f"## Current Screen (Accessibility Tree)\n{parsed_tree}")
    if history_block:
        obs_parts.append(history_block)
    if screenshot_desc:
        obs_parts.append(f"\n## Screenshot Description\n{screenshot_desc}")

    messages.append({"role": "user", "content": "\n".join(obs_parts)})

    return messages
