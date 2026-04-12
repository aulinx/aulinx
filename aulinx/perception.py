"""Hybrid perception — decides per-step whether semantic tree or screenshot is needed.

The key insight: AT-SPI/scene graph gives ground truth for interactive elements
(buttons, text fields, menus), but some content is opaque (canvas apps, PDF
viewers, image content). This module detects when the tree is insufficient
and triggers a screenshot + annotation fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ObservationMode(Enum):
    """How the agent perceives the desktop this step."""
    SEMANTIC = "semantic"       # a11y tree only (default, cheapest)
    SCREENSHOT = "screenshot"   # screenshot only (for canvas/opaque apps)
    HYBRID = "hybrid"           # both: tree for structure, screenshot for visual content


# Apps that typically have poor a11y tree coverage
_OPAQUE_APPS = {
    "firefox", "chromium", "chrome", "google-chrome",  # web content in canvas
    "gimp", "inkscape", "krita",                       # image editors
    "libreoffice", "soffice",                          # complex layouts
    "evince", "okular", "document viewer",             # PDF viewers
    "eog", "image viewer", "feh",                      # image viewers
    "vlc", "mpv", "totem",                             # media players
    "blender", "godot",                                # 3D/game editors
}

# Roles that indicate rich, interactive UI (tree is sufficient)
_INTERACTIVE_ROLES = {
    "button", "push button", "toggle button",
    "text", "textbox", "text field", "entry",
    "menu", "menu item", "menu bar",
    "check box", "radio button",
    "combo box", "list box",
    "tab", "slider", "spin button",
    "tree item", "list item",
}

# Minimum number of interactive elements for the tree to be "sufficient"
_MIN_INTERACTIVE_ELEMENTS = 3


@dataclass
class Observation:
    """A single observation of the desktop state."""
    mode: ObservationMode
    semantic_tree: str = ""           # parsed a11y tree text
    screenshot_path: str = ""         # path to screenshot file
    annotated_screenshot: str = ""    # base64 annotated screenshot
    element_count: int = 0            # number of interactive elements found
    app_name: str = ""                # focused app name


def decide_observation_mode(
    a11y_tree: str,
    focused_app: str = "",
    element_count: int = 0,
    force_mode: ObservationMode | None = None,
) -> ObservationMode:
    """Decide which observation mode to use for this step.

    Args:
        a11y_tree: The current accessibility tree (parsed text)
        focused_app: Name of the currently focused application
        element_count: Number of interactive elements found in the tree
        force_mode: Override the decision (for testing or user preference)

    Returns:
        The observation mode to use
    """
    if force_mode is not None:
        return force_mode

    # Check if the focused app is known to be opaque
    app_lower = focused_app.lower()
    is_opaque_app = any(opaque in app_lower for opaque in _OPAQUE_APPS)

    # Check if the tree has enough interactive elements
    tree_is_sparse = element_count < _MIN_INTERACTIVE_ELEMENTS

    # Check if the tree is empty or minimal
    tree_is_empty = not a11y_tree or a11y_tree.strip() in (
        "[No accessibility tree available]",
        "[No interactive elements found in accessibility tree]",
    )

    if tree_is_empty:
        return ObservationMode.SCREENSHOT

    if is_opaque_app and tree_is_sparse:
        return ObservationMode.HYBRID

    if is_opaque_app:
        # Even opaque apps sometimes have good a11y (e.g., Firefox menus)
        return ObservationMode.HYBRID

    if tree_is_sparse:
        # Sparse tree on a non-opaque app — might be loading, try hybrid
        return ObservationMode.HYBRID

    return ObservationMode.SEMANTIC


def count_interactive_elements(parsed_tree: str) -> int:
    """Count interactive elements in a parsed a11y tree string.

    The parsed tree format from prompt_builder is:
    [0] button "Save" at (100,200) size (80,30)
    [1] textbox "Name" at (200,100) size (300,30) [focused]
    """
    if not parsed_tree:
        return 0

    count = 0
    for line in parsed_tree.split("\n"):
        line = line.strip()
        if not line or line.startswith("[No "):
            continue
        # Check if any interactive role appears in the line
        line_lower = line.lower()
        if any(role in line_lower for role in _INTERACTIVE_ROLES):
            count += 1
        elif line.startswith("["):
            # Any numbered element is likely interactive
            count += 1
    return count


def build_hybrid_prompt_section(
    semantic_tree: str,
    screenshot_desc: str = "",
) -> str:
    """Build the observation section for a hybrid prompt.

    Combines semantic tree (structure) with screenshot description (visual).
    """
    parts = []

    if semantic_tree and not semantic_tree.startswith("[No "):
        parts.append(f"## UI Elements (from accessibility tree)\n{semantic_tree}")

    if screenshot_desc:
        parts.append(f"## Visual Context (from screenshot)\n{screenshot_desc}")

    if not parts:
        return "## Current Screen\n[No observation available — try wait() then retry]"

    return "\n\n".join(parts)
