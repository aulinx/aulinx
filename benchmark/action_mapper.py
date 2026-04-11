"""Map LLM responses to OSWorld computer_13 action format.

Parses the LLM's structured output (action: type(params)) into
the dictionary format that OSWorld's DesktopEnv.step() expects.
"""

from __future__ import annotations

import ast
import re


def parse_response(response: str) -> tuple[str, dict | str]:
    """Parse an LLM response into (thought, action).

    Expected format:
        thought: some reasoning
        action: click(x=100, y=200)

    Returns (thought_text, action_dict_or_string).
    """
    thought = ""
    action_str = ""

    for line in response.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("thought:"):
            thought = line[len("thought:"):].strip()
        elif line.lower().startswith("action:"):
            action_str = line[len("action:"):].strip()

    if not action_str:
        # Try to find action anywhere in the response
        match = re.search(r"(click|double_click|right_click|type|press|hotkey|scroll|drag|wait|done|fail)\s*\(", response)
        if match:
            # Extract from the match to the closing paren
            start = match.start()
            depth = 0
            end = start
            for i in range(start, len(response)):
                if response[i] == "(":
                    depth += 1
                elif response[i] == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            action_str = response[start:end]

    if not action_str:
        return thought, "WAIT"

    return thought, _parse_action(action_str)


def _parse_action(action_str: str) -> dict | str:
    """Parse an action string like 'click(x=100, y=200)' into a computer_13 dict."""
    action_str = action_str.strip().rstrip(".")

    # Terminal actions
    lower = action_str.lower().strip("()")
    if lower in ("wait", "wait()"):
        return "WAIT"
    if lower in ("done", "done()"):
        return "DONE"
    if lower in ("fail", "fail()"):
        return "FAIL"

    # Parse function call
    match = re.match(r"(\w+)\s*\((.*)\)$", action_str, re.DOTALL)
    if not match:
        return "WAIT"

    func_name = match.group(1).lower()
    params_str = match.group(2).strip()
    params = _parse_params(params_str)

    return _map_to_computer13(func_name, params)


def _parse_params(params_str: str) -> dict:
    """Parse keyword arguments from a function call string."""
    if not params_str:
        return {}

    params = {}

    # Try to parse as Python kwargs using ast
    try:
        # Wrap in a function call for ast parsing
        tree = ast.parse(f"f({params_str})", mode="eval")
        call = tree.body
        for kw in call.keywords:
            if kw.arg:
                params[kw.arg] = ast.literal_eval(kw.value)
        return params
    except (SyntaxError, ValueError):
        pass

    # Fallback: regex-based parsing
    for match in re.finditer(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\[[^\]]*\]|-?\d+)', params_str):
        key = match.group(1)
        val = match.group(2)
        try:
            params[key] = ast.literal_eval(val)
        except (SyntaxError, ValueError):
            params[key] = val.strip("\"'")

    return params


def _map_to_computer13(func_name: str, params: dict) -> dict | str:
    """Map a parsed action to OSWorld's computer_13 format."""
    if func_name == "click":
        return {
            "action_type": "CLICK",
            "coordinate": [params.get("x", 0), params.get("y", 0)],
            "direction": "down_then_up",
            "button": params.get("button", "left"),
            "num_clicks": params.get("num_clicks", 1),
        }

    if func_name == "double_click":
        return {
            "action_type": "DOUBLE_CLICK",
            "coordinate": [params.get("x", 0), params.get("y", 0)],
        }

    if func_name == "right_click":
        return {
            "action_type": "RIGHT_CLICK",
            "coordinate": [params.get("x", 0), params.get("y", 0)],
        }

    if func_name == "type":
        return {
            "action_type": "TYPING",
            "text": params.get("text", ""),
        }

    if func_name == "press":
        return {
            "action_type": "PRESS",
            "key": params.get("key", ""),
        }

    if func_name == "hotkey":
        keys = params.get("keys", [])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]
        return {
            "action_type": "HOTKEY",
            "key": keys,
        }

    if func_name == "scroll":
        direction = params.get("direction", "down")
        amount = params.get("amount", 3)
        dx, dy = 0, 0
        if direction == "up":
            dy = amount
        elif direction == "down":
            dy = -amount
        elif direction == "left":
            dx = -amount
        elif direction == "right":
            dx = amount
        return {
            "action_type": "SCROLL",
            "coordinate": [params.get("x", 0), params.get("y", 0)],
            "direction": direction,
            "dx": dx,
            "dy": dy,
        }

    if func_name == "drag":
        return {
            "action_type": "DRAG_TO",
            "startCoordinate": [params.get("start_x", 0), params.get("start_y", 0)],
            "endCoordinate": [params.get("end_x", 0), params.get("end_y", 0)],
        }

    if func_name in ("wait", ""):
        return "WAIT"
    if func_name == "done":
        return "DONE"
    if func_name == "fail":
        return "FAIL"

    # Unknown action — wait
    return "WAIT"
