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
You are Aulinx, an AI agent controlling a Linux desktop. You receive a structured \
accessibility tree describing visible UI elements with their coordinates. You must \
complete the user's task by outputting ONE action per step.

## Action format

Respond with exactly one action in this format:

action: ACTION_TYPE(param1=value1, param2=value2)
thought: brief reasoning for this action

## Available actions

- click(x=<int>, y=<int>) — left click at screen coordinates
- double_click(x=<int>, y=<int>) — double click
- right_click(x=<int>, y=<int>) — right click
- type(text="<string>") — type text into focused element
- press(key="<key>") — press a key (enter, tab, escape, backspace, delete, space, up, down, left, right, home, end, pageup, pagedown, f1-f12)
- hotkey(keys=["<key1>", "<key2>"]) — press key combination (e.g. ["ctrl", "s"], ["alt", "f4"])
- scroll(x=<int>, y=<int>, direction="<up|down|left|right>", amount=<int>) — scroll at position
- drag(start_x=<int>, start_y=<int>, end_x=<int>, end_y=<int>) — drag from start to end
- wait() — wait for the screen to update
- done() — task is complete
- fail() — task cannot be completed

## Rules

1. Output EXACTLY ONE action per response
2. Use the a11y tree to find element coordinates — click the CENTER of the element
3. To calculate center: x = screencoord_x + size_w/2, y = screencoord_y + size_h/2
4. For text input: first click the text field, then type
5. When the task is complete, output done()
6. If stuck after multiple attempts, output fail()
7. Be precise with coordinates — use the values from the a11y tree
"""


def parse_a11y_tree(xml_str: str, max_elements: int = 80) -> str:
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
        if elem.get("coord"):
            parts.append(f"at ({elem['coord'][0]},{elem['coord'][1]}) size ({elem['size'][0]},{elem['size'][1]})")
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
                 history: list[dict] | None = None) -> list[dict]:
    """Build the full message list for the LLM.

    Returns a list of message dicts suitable for chat completion APIs.
    """
    parsed_tree = parse_a11y_tree(a11y_tree)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add history (previous steps in this task)
    if history:
        for entry in history[-10:]:  # Keep last 10 steps to fit context
            messages.append({"role": "user", "content": entry["observation"]})
            messages.append({"role": "assistant", "content": entry["response"]})

    # Current observation
    obs_parts = [f"## Task\n{instruction}\n"]
    obs_parts.append(f"## Current Screen (Accessibility Tree)\n{parsed_tree}")
    if screenshot_desc:
        obs_parts.append(f"\n## Screenshot Description\n{screenshot_desc}")

    messages.append({"role": "user", "content": "\n".join(obs_parts)})

    return messages
