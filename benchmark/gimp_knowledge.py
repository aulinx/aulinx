"""GIMP image editor knowledge base — keyboard shortcuts and CLI recipes.

Maps GIMP task patterns to precise keyboard shortcuts, menu paths, and
Script-Fu / CLI commands. Used by the prompt builder to inject domain-specific
guidance so the agent uses direct shortcuts instead of hunting through menus.

GIMP supports batch operations via Script-Fu console (Filters > Script-Fu >
Console) and headless CLI mode: gimp -i -b '(script-fu-cmd)' -b '(gimp-quit 0)'.
"""

from __future__ import annotations

import re

# pattern_regex -> (keywords, commands list, verify hint)
GIMP_RECIPES: dict[str, tuple[list[str], list[str], str]] = {
    # --- File operations ---
    r"gimp.*open|open.*gimp|open.*image.*gimp|gimp.*load": (
        ["gimp", "open", "file", "image"],
        [
            "hotkey(keys=[\"ctrl\",\"o\"])",
            "wait()",
        ],
        "Open dialog should appear for file selection",
    ),
    r"gimp.*save|save.*gimp|overwrite.*image": (
        ["gimp", "save", "overwrite"],
        [
            "hotkey(keys=[\"ctrl\",\"s\"])",
            "wait()",
        ],
        "Image should be saved (overwrite current file)",
    ),
    r"gimp.*export|export.*as|export.*image|save.*as.*png|save.*as.*jpg": (
        ["gimp", "export", "save as", "png", "jpg"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"e\"])",
            "wait()",
        ],
        "Export As dialog should appear for choosing format and path",
    ),

    # --- Crop ---
    r"autocrop|auto.*crop|crop.*automatic": (
        ["gimp", "autocrop", "trim"],
        [
            "hotkey(keys=[\"shift\",\"ctrl\",\"x\"])",
        ],
        "Image should be autocropped to remove empty borders",
    ),
    r"crop.*selection|crop.*to.*select": (
        ["gimp", "crop", "selection"],
        [
            # Image > Crop to Selection
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
            # Navigate menu: Image > Crop to Selection
        ],
        "Image should be cropped to the current selection bounds",
    ),

    # --- Resize / Scale ---
    r"scale.*image|resize.*image|image.*size|change.*dimension|change.*resolution": (
        ["gimp", "scale", "resize", "dimensions"],
        [
            # Image > Scale Image
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
            # Then navigate to Scale Image in the menu
        ],
        "Scale Image dialog should appear with width/height fields",
    ),
    r"canvas.*size|change.*canvas|resize.*canvas": (
        ["gimp", "canvas", "resize"],
        [
            # Image > Canvas Size
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "Canvas Size dialog should appear",
    ),

    # --- Rotate ---
    r"rotate.*90.*c|rotate.*clock|rotate.*cw|rotate.*right": (
        ["gimp", "rotate", "90", "clockwise"],
        [
            # Image > Transform > Rotate 90 CW
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
            # Navigate: Image > Transform > Rotate 90° clockwise
        ],
        "Image should be rotated 90 degrees clockwise",
    ),
    r"rotate.*90.*cc|rotate.*counter|rotate.*ccw|rotate.*left": (
        ["gimp", "rotate", "90", "counterclockwise"],
        [
            # Image > Transform > Rotate 90 CCW
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "Image should be rotated 90 degrees counterclockwise",
    ),
    r"rotate.*180|flip.*upside|turn.*upside": (
        ["gimp", "rotate", "180"],
        [
            # Image > Transform > Rotate 180°
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "Image should be rotated 180 degrees",
    ),

    # --- Flip ---
    r"flip.*horiz|mirror.*horiz|horizontal.*flip": (
        ["gimp", "flip", "horizontal", "mirror"],
        [
            # Image > Transform > Flip Horizontally
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "Image should be flipped horizontally",
    ),
    r"flip.*vert|mirror.*vert|vertical.*flip": (
        ["gimp", "flip", "vertical", "mirror"],
        [
            # Image > Transform > Flip Vertically
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "Image should be flipped vertically",
    ),

    # --- Filters ---
    r"gaussian.*blur|blur.*image|apply.*blur": (
        ["gimp", "blur", "gaussian", "filter"],
        [
            # Filters > Blur > Gaussian Blur
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
            # Navigate: Filters > Blur > Gaussian Blur
        ],
        "Gaussian Blur dialog should appear with radius controls",
    ),
    r"sharpen.*image|apply.*sharpen|unsharp.*mask": (
        ["gimp", "sharpen", "enhance", "filter"],
        [
            # Filters > Enhance > Sharpen (Unsharp Mask)
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
        ],
        "Sharpen / Unsharp Mask dialog should appear",
    ),

    # --- Layers ---
    r"new.*layer|add.*layer|create.*layer": (
        ["gimp", "layer", "new", "create"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"n\"])",
            "wait()",
        ],
        "New Layer dialog should appear",
    ),
    r"duplicate.*layer|copy.*layer": (
        ["gimp", "layer", "duplicate", "copy"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"d\"])",
        ],
        "Current layer should be duplicated",
    ),
    r"merge.*down|merge.*layer.*down": (
        ["gimp", "layer", "merge", "down"],
        [
            # Layer > Merge Down
            "hotkey(keys=[\"alt\",\"y\"])",
            "wait()",
        ],
        "Current layer should merge with the layer below",
    ),
    r"flatten.*image|merge.*all.*layer|flatten.*layer": (
        ["gimp", "flatten", "merge all", "layers"],
        [
            # Image > Flatten Image
            "hotkey(keys=[\"alt\",\"i\"])",
            "wait()",
        ],
        "All layers should be merged into one",
    ),

    # --- Color adjustments ---
    r"brightness.*contrast|adjust.*brightness|adjust.*contrast": (
        ["gimp", "brightness", "contrast", "color"],
        [
            # Colors > Brightness-Contrast
            "hotkey(keys=[\"alt\",\"c\"])",
            "wait()",
        ],
        "Brightness-Contrast dialog should appear",
    ),
    r"hue.*saturation|adjust.*hue|adjust.*saturation|change.*color.*tone": (
        ["gimp", "hue", "saturation", "color"],
        [
            # Colors > Hue-Saturation
            "hotkey(keys=[\"alt\",\"c\"])",
            "wait()",
        ],
        "Hue-Saturation dialog should appear",
    ),
    r"desaturate|convert.*grayscale|make.*grayscale|black.*and.*white|greyscale": (
        ["gimp", "desaturate", "grayscale", "black and white"],
        [
            # Colors > Desaturate
            "hotkey(keys=[\"alt\",\"c\"])",
            "wait()",
        ],
        "Desaturate dialog should appear or image should turn grayscale",
    ),

    # --- Selection ---
    r"select.*all.*gimp|gimp.*select.*all": (
        ["gimp", "select", "all"],
        [
            "hotkey(keys=[\"ctrl\",\"a\"])",
        ],
        "Entire image should be selected (marching ants around canvas)",
    ),
    r"select.*none|deselect|remove.*selection|clear.*selection": (
        ["gimp", "select", "none", "deselect"],
        [
            "hotkey(keys=[\"ctrl\",\"shift\",\"a\"])",
        ],
        "Selection should be removed",
    ),

    # --- Script-Fu / CLI batch ---
    r"script.*fu|batch.*gimp|gimp.*script|gimp.*console": (
        ["gimp", "script-fu", "batch", "console"],
        [
            # Filters > Script-Fu > Console
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
            # Navigate: Filters > Script-Fu > Console
        ],
        "Script-Fu console should open for entering commands",
    ),
    r"python.*fu|gimp.*python|python.*console.*gimp": (
        ["gimp", "python-fu", "console", "scripting"],
        [
            # Filters > Python-Fu > Console
            "hotkey(keys=[\"alt\",\"t\"])",
            "wait()",
        ],
        "Python-Fu console should open for entering Python commands",
    ),
    r"gimp.*cli|gimp.*command.*line|gimp.*headless|gimp.*batch": (
        ["gimp", "cli", "headless", "batch", "command line"],
        [
            "hotkey(keys=[\"ctrl\",\"alt\",\"t\"])",
            "wait()",
            # Use: gimp -i -b '(script-fu-command)' -b '(gimp-quit 0)'
        ],
        "Terminal should open for GIMP CLI batch commands",
    ),

    # --- Undo / Redo ---
    r"undo.*gimp|gimp.*undo": (
        ["gimp", "undo"],
        [
            "hotkey(keys=[\"ctrl\",\"z\"])",
        ],
        "Last action should be undone",
    ),
    r"redo.*gimp|gimp.*redo": (
        ["gimp", "redo"],
        [
            "hotkey(keys=[\"ctrl\",\"y\"])",
        ],
        "Last undone action should be redone",
    ),
}


def find_gimp_recipe(instruction: str) -> dict | None:
    """Find a matching GIMP recipe for a task instruction.

    Returns a dict with:
    - commands: list of action strings to execute
    - verify: verification hint
    - keywords: list of keywords for the match
    - pattern: the regex pattern that matched
    """
    instruction_lower = instruction.lower()

    for pattern, (keywords, commands, verify) in GIMP_RECIPES.items():
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_gimp_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with GIMP shortcuts for a task.

    If we have a recipe for this GIMP task, inject the exact actions
    into the prompt so the agent uses keyboard shortcuts and menu
    navigation instead of hunting through menus.
    """
    recipe = find_gimp_recipe(instruction)
    if not recipe:
        return ""

    commands = recipe["commands"]
    verify = recipe["verify"]

    lines = [
        "\n## Recommended Approach (GIMP expert knowledge)",
        "For this GIMP task, use these keyboard shortcuts / menu navigation:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        lines.append(f"{i}. {cmd}")

    if verify:
        lines.append(f"\nVerification: {verify}")

    lines.append("")
    lines.append("GIMP shortcuts: Ctrl+Shift+E (Export As), Ctrl+S (overwrite), "
                  "Ctrl+Shift+N (new layer), Ctrl+Shift+D (duplicate layer).")
    lines.append("For batch operations: use Script-Fu console "
                  "(Filters > Script-Fu > Console) or CLI: "
                  "gimp -i -b '(script-fu-cmd)' -b '(gimp-quit 0)'.")

    return "\n".join(lines)
