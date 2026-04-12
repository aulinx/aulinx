"""Action grounding — resolve natural language element references to exact coordinates.

Instead of the LLM guessing coordinates from text descriptions, this module
queries the scene graph (AT-SPI or compositor) for exact element positions.

Flow: LLM says "click Save button" → grounding finds element → returns exact (x,y)

This eliminates coordinate hallucination, the most common failure mode in
screenshot-based agents. Aulinx has ground truth from AT-SPI/compositor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GroundedElement:
    """An element resolved to exact screen coordinates."""
    name: str
    role: str
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    confidence: float  # 0-1, how confident the match is
    source: str  # "atspi", "compositor", "parsed_tree"

    @property
    def center(self) -> tuple[int, int]:
        return (self.center_x, self.center_y)


def ground_element_from_tree(
    query: str,
    parsed_tree: str,
    role_filter: str = "",
) -> GroundedElement | None:
    """Find an element in the parsed a11y tree and return its coordinates.

    The parsed tree format (from prompt_builder.parse_a11y_tree):
    [0] button "Save" at (100,200) size (80,30)
    [1] textbox "Name" at (200,100) size (300,30) [focused]

    Args:
        query: Text to search for (e.g., "Save", "Name field")
        parsed_tree: The parsed accessibility tree string
        role_filter: Optional role filter (e.g., "button", "textbox")

    Returns:
        GroundedElement with exact coordinates, or None if not found
    """
    if not parsed_tree or not query:
        return None

    query_lower = query.lower()
    best_match: GroundedElement | None = None
    best_score = 0.0

    for line in parsed_tree.split("\n"):
        line = line.strip()
        if not line or line.startswith("[No "):
            continue

        element = _parse_tree_line(line)
        if element is None:
            continue

        # Apply role filter
        if role_filter and role_filter.lower() not in element.role.lower():
            continue

        # Score the match
        score = _match_score(query_lower, element.name.lower(), element.role.lower())
        if score > best_score:
            best_score = score
            best_match = element

    if best_match and best_score >= 0.3:
        best_match.confidence = best_score
        return best_match

    return None


def ground_action(
    action_text: str,
    parsed_tree: str,
) -> dict | None:
    """Parse a natural language action and ground it to coordinates.

    Handles patterns like:
    - "click the Save button" → find "Save" button → click(center_x, center_y)
    - "type in the Name field" → find "Name" textbox → click to focus → type
    - "click OK" → find "OK" → click

    Args:
        action_text: Natural language description of the action
        parsed_tree: The current accessibility tree

    Returns:
        A grounded action dict with coordinates, or None if grounding failed
    """
    action_lower = action_text.lower()

    # Pattern: "click [the] <name> [button/link/etc]"
    click_match = re.search(
        r"click\s+(?:the\s+|on\s+)?[\"']?(.+?)[\"']?\s*(?:button|link|tab|menu|item|checkbox|icon)?$",
        action_lower,
    )
    if click_match:
        target = click_match.group(1).strip()
        element = ground_element_from_tree(target, parsed_tree)
        if element:
            return {
                "action": "click",
                "x": element.center_x,
                "y": element.center_y,
                "grounded_from": element.name,
                "confidence": element.confidence,
            }

    # Pattern: "type <text> in [the] <field>"
    type_match = re.search(
        r"type\s+[\"']?(.+?)[\"']?\s+in(?:to)?\s+(?:the\s+)?(.+)",
        action_lower,
    )
    if type_match:
        text = type_match.group(1).strip()
        field = type_match.group(2).strip()
        element = ground_element_from_tree(field, parsed_tree, role_filter="text")
        if element:
            return {
                "action": "type",
                "text": text,
                "focus_x": element.center_x,
                "focus_y": element.center_y,
                "grounded_from": element.name,
                "confidence": element.confidence,
            }

    # Pattern: "select <item>"
    select_match = re.search(r"select\s+(?:the\s+)?[\"']?(.+?)[\"']?$", action_lower)
    if select_match:
        target = select_match.group(1).strip()
        element = ground_element_from_tree(target, parsed_tree)
        if element:
            return {
                "action": "click",
                "x": element.center_x,
                "y": element.center_y,
                "grounded_from": element.name,
                "confidence": element.confidence,
            }

    return None


def _parse_tree_line(line: str) -> GroundedElement | None:
    """Parse a single line from the parsed a11y tree.

    Format: [0] button "Save" at (100,200) size (80,30) [focused]
    """
    # Match: [index] role "name" at (x,y) size (w,h)
    match = re.match(
        r"\[(\d+)\]\s+(\S+)\s+"           # [index] role
        r'(?:"([^"]*)")?\s*'               # "name" (optional)
        r"(?:.*?at\s+\((\d+),(\d+)\))?\s*"  # at (x,y) (optional)
        r"(?:size\s+\((\d+),(\d+)\))?",     # size (w,h) (optional)
        line,
    )
    if not match:
        return None

    role = match.group(2) or ""
    name = match.group(3) or ""
    x = int(match.group(4)) if match.group(4) else 0
    y = int(match.group(5)) if match.group(5) else 0
    w = int(match.group(6)) if match.group(6) else 0
    h = int(match.group(7)) if match.group(7) else 0

    if not (x or y):
        return None

    return GroundedElement(
        name=name,
        role=role,
        x=x,
        y=y,
        width=w,
        height=h,
        center_x=x + w // 2,
        center_y=y + h // 2,
        confidence=0.0,
        source="parsed_tree",
    )


def _match_score(query: str, name: str, role: str) -> float:
    """Score how well a query matches an element's name and role.

    Returns 0.0-1.0 where 1.0 is an exact match.
    """
    if not query:
        return 0.0

    # Exact name match
    if query == name:
        return 1.0

    # Name contains query
    if query in name:
        return 0.8

    # Query contains name (e.g., query="save button", name="save")
    if name and name in query:
        return 0.7

    # Role match in query (e.g., query="save button", role="button")
    if role in query:
        # Check if the non-role part matches the name
        query_without_role = query.replace(role, "").strip()
        if query_without_role and query_without_role in name:
            return 0.75
        if query_without_role and name in query_without_role:
            return 0.65

    # Fuzzy: any word overlap
    query_words = set(query.split())
    name_words = set(name.split()) if name else set()
    if query_words & name_words:
        overlap = len(query_words & name_words) / max(len(query_words), 1)
        return 0.3 + overlap * 0.3

    return 0.0
