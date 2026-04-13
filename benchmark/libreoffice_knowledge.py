"""LibreOffice knowledge base — keyboard shortcuts and macro strategies.

Maps LibreOffice Calc/Writer/Impress task patterns to keyboard-driven
strategies and macro injection approaches. Used by the prompt builder
to inject domain-specific guidance into the benchmark prompt.

Key insight: LibreOffice tasks are the hardest because they require
precise cell-level interaction. The best strategy is:
1. Keyboard shortcuts (Ctrl+Home, Name Box for cell nav, Ctrl+D to fill)
2. For complex operations, inject a LibreOffice Basic macro via Alt+F11
3. CLI approach: libreoffice --headless for batch operations
"""

from __future__ import annotations

import re

# (pattern_regex, keywords, strategy_lines, verify_hint)
LIBREOFFICE_RECIPES: list[tuple[str, list[str], list[str], str]] = [

    # --- Calc: cell navigation and editing ---
    (
        r"(?:go\s+to|navigate\s+to|select)\s+cell|name\s*box|cell\s+[A-Z]+\d+",
        ["cell", "navigate", "name box", "select"],
        [
            "Click the Name Box (left of the formula bar) to focus it",
            "type(text=\"A1\") — replace A1 with the target cell reference",
            "press(key=\"enter\") — jumps to that cell",
        ],
        "Check that the Name Box shows the target cell reference",
    ),

    # --- Calc: enter / edit formula ---
    (
        r"formula|=SUM|=AVERAGE|=COUNT|=IF|=VLOOKUP|calculate|computation",
        ["formula", "sum", "average", "calculate", "function"],
        [
            "Navigate to the target cell via Name Box: click Name Box, type cell ref, press Enter",
            "type(text=\"=SUM(A1:A10)\") — replace with the actual formula",
            "press(key=\"enter\") to confirm the formula",
            "For filling down: select the range, then hotkey(keys=[\"ctrl\",\"d\"])",
        ],
        "Click the cell and check the formula bar shows the expected formula",
    ),

    # --- Calc: fill down / fill series ---
    (
        r"fill\s+down|fill\s+series|auto\s*fill|drag.*fill|copy.*formula.*down",
        ["fill", "autofill", "series", "drag"],
        [
            "Enter the formula or value in the first cell",
            "Select the range to fill: click first cell, then Shift+click last cell",
            "Or: click Name Box, type range like A1:A20, press Enter to select",
            "hotkey(keys=[\"ctrl\",\"d\"]) to fill down",
        ],
        "Check that all cells in the range contain the expected values",
    ),

    # --- Calc: sort data ---
    (
        r"sort.*(?:data|column|row|ascending|descending)|ascending|descending",
        ["sort", "ascending", "descending", "data", "column"],
        [
            "Select the data range: click Name Box, type the range (e.g. A1:D100), press Enter",
            "Open sort dialog: hotkey(keys=[\"alt\",\"d\"]) then press(key=\"s\") — or Data menu → Sort",
            "In the dialog, choose the sort column and order",
            "press(key=\"enter\") to apply",
            "Alternative: for simple sort, select the column header and use Data → Sort Ascending/Descending",
        ],
        "Verify the data is sorted by checking the first and last values",
    ),

    # --- Calc: insert/delete rows or columns ---
    (
        r"insert.*(?:row|column)|delete.*(?:row|column)|add.*(?:row|column)",
        ["insert", "delete", "row", "column"],
        [
            "Select the row/column: click the row number or column letter header",
            "Right-click for context menu",
            "Choose 'Insert Rows Above/Below' or 'Insert Columns Before/After'",
            "Or: hotkey(keys=[\"ctrl\",\"plus\"]) to insert, hotkey(keys=[\"ctrl\",\"minus\"]) to delete",
        ],
        "Verify the row/column count changed",
    ),

    # --- Calc: create chart ---
    (
        r"(?:create|insert|make|add).*chart|chart.*(?:from|using|of)",
        ["chart", "create", "insert", "graph"],
        [
            "Select the data range: click Name Box, type range (e.g. A1:B10), press Enter",
            "Insert chart: hotkey(keys=[\"alt\",\"i\"]) then click 'Chart' — or Insert menu → Chart",
            "In the chart wizard, select chart type and configure",
            "press(key=\"enter\") or click Finish to insert the chart",
        ],
        "Verify a chart object appears in the spreadsheet",
    ),

    # --- Calc: rename sheet tab ---
    (
        r"rename.*sheet|sheet.*rename|tab.*rename|rename.*tab",
        ["rename", "sheet", "tab"],
        [
            "Right-click the sheet tab at the bottom of the screen",
            "Click 'Rename Sheet' in the context menu",
            "type(text=\"NewSheetName\") — replace with the desired name",
            "press(key=\"enter\") to confirm",
            "Alternative: double-click the sheet tab to enter rename mode",
        ],
        "Check that the sheet tab shows the new name",
    ),

    # --- Calc: copy/move sheet ---
    (
        r"copy.*sheet|move.*sheet|duplicate.*sheet",
        ["copy", "move", "sheet", "duplicate"],
        [
            "Right-click the sheet tab at the bottom",
            "Click 'Move or Copy Sheet...'",
            "In the dialog, check 'Copy' if duplicating",
            "Select the target position",
            "press(key=\"enter\") to confirm",
        ],
        "Verify the new sheet tab appears",
    ),

    # --- Calc: macro for complex operations ---
    (
        r"macro|basic.*macro|run.*macro|automate|script.*calc|programmat",
        ["macro", "basic", "automate", "script"],
        [
            "Open macro editor: hotkey(keys=[\"alt\",\"f11\"]) — opens the Basic IDE",
            "Navigate to the module or create a new one",
            "Type the macro code in the editor",
            "Run macro: hotkey(keys=[\"alt\",\"f8\"]) — opens macro runner",
            "Or press F5 in the Basic IDE to run directly",
            "Close the IDE: hotkey(keys=[\"alt\",\"f4\"])",
        ],
        "Verify the macro's effect on the spreadsheet",
    ),

    # --- Calc: complex cell manipulation (use macro strategy) ---
    (
        r"(?:set|change|update|modify).*(?:cell|value|data).*(?:all|every|each|range|multiple)"
        r"|batch.*(?:edit|update|change)"
        r"|(?:across|through).*(?:cell|row|column)",
        ["batch", "cells", "update", "range", "multiple"],
        [
            "For complex multi-cell operations, use a LibreOffice Basic macro:",
            "Open macro editor: hotkey(keys=[\"alt\",\"f11\"])",
            "Write a Sub that uses ThisComponent.Sheets to manipulate cells:",
            "  Sub Main",
            "    Dim oSheet As Object",
            "    oSheet = ThisComponent.Sheets.getByIndex(0)",
            "    Dim oCell As Object",
            "    oCell = oSheet.getCellByPosition(0, 0)  ' Column A, Row 1",
            "    oCell.setString(\"Hello\")",
            "  End Sub",
            "Run with F5 or hotkey(keys=[\"alt\",\"f8\"])",
        ],
        "Check the affected cells for expected values",
    ),

    # --- Calc: conditional formatting ---
    (
        r"conditional.*format|highlight.*cell|color.*cell.*(?:if|when|based)",
        ["conditional", "formatting", "highlight", "color"],
        [
            "Select the target range via Name Box",
            "Open: Format menu → Conditional → Condition",
            "Or: hotkey(keys=[\"alt\",\"o\"]) → navigate to Conditional",
            "Set the condition and formatting style",
            "press(key=\"enter\") to apply",
        ],
        "Check that cells matching the condition show the expected formatting",
    ),

    # --- Calc: freeze rows/columns ---
    (
        r"freeze.*(?:row|column|pane)|(?:row|column).*freeze|split.*pane",
        ["freeze", "pane", "row", "column"],
        [
            "Click the cell below and right of where you want to freeze",
            "Example: to freeze row 1, click cell A2",
            "View menu → Freeze Rows and Columns",
            "Or: hotkey(keys=[\"alt\",\"v\"]) then navigate to Freeze",
        ],
        "Scroll down to verify the frozen rows stay visible",
    ),

    # --- Writer: text formatting ---
    (
        r"(?:bold|italic|underline|strikethrough).*(?:text|word|paragraph)"
        r"|format.*(?:text|font|paragraph)",
        ["bold", "italic", "underline", "format", "text", "font"],
        [
            "Select the text: click at start, then Shift+click at end",
            "Or: hotkey(keys=[\"ctrl\",\"a\"]) to select all",
            "Bold: hotkey(keys=[\"ctrl\",\"b\"])",
            "Italic: hotkey(keys=[\"ctrl\",\"i\"])",
            "Underline: hotkey(keys=[\"ctrl\",\"u\"])",
            "Font size: select text, then Format menu → Character",
        ],
        "Verify the text formatting by checking the toolbar state",
    ),

    # --- Writer: find and replace ---
    (
        r"find.*replace|search.*replace|replace.*(?:word|text|all)",
        ["find", "replace", "search"],
        [
            "Open Find & Replace: hotkey(keys=[\"ctrl\",\"h\"])",
            "type(text=\"search term\") in the Search For field",
            "press(key=\"tab\") to move to Replace With field",
            "type(text=\"replacement\") in the Replace With field",
            "Click 'Replace All' or press(key=\"alt+a\")",
            "press(key=\"escape\") to close the dialog",
        ],
        "Use Ctrl+F to search for the old text — it should not be found",
    ),

    # --- Writer: insert table ---
    (
        r"(?:insert|create|add).*table.*(?:writer|document|doc)"
        r"|table.*(?:in|into).*(?:writer|document|doc)",
        ["table", "insert", "writer", "document"],
        [
            "Position cursor where the table should go",
            "hotkey(keys=[\"ctrl\",\"f12\"]) — opens Insert Table dialog",
            "Set rows and columns count",
            "press(key=\"enter\") to insert",
            "Navigate cells with Tab key",
        ],
        "Verify the table appears in the document",
    ),

    # --- Writer: heading styles ---
    (
        r"heading|apply.*style|paragraph.*style|set.*heading",
        ["heading", "style", "paragraph"],
        [
            "Click on the target paragraph",
            "Click the Paragraph Style dropdown (top-left of toolbar, shows 'Default Paragraph Style')",
            "Or: hotkey(keys=[\"ctrl\",\"1\"]) for Heading 1, hotkey(keys=[\"ctrl\",\"2\"]) for Heading 2",
            "Alternative: Format menu → Paragraph Style",
        ],
        "Check that the paragraph style dropdown shows the expected style",
    ),

    # --- Writer: page setup ---
    (
        r"page.*(?:size|orient|margin|landscape|portrait)|landscape|portrait"
        r"|margin.*(?:set|change)",
        ["page", "size", "orientation", "margin", "landscape", "portrait"],
        [
            "Format menu → Page Style (or hotkey(keys=[\"alt\",\"o\"]) then P)",
            "In the Page tab: set paper size, orientation (Portrait/Landscape)",
            "In the Margins section: set left, right, top, bottom margins",
            "press(key=\"enter\") to apply",
        ],
        "Check Format → Page Style to verify the settings",
    ),

    # --- Impress: add slide ---
    (
        r"(?:add|insert|new).*slide|slide.*(?:add|insert|new)",
        ["slide", "add", "insert", "new"],
        [
            "hotkey(keys=[\"ctrl\",\"m\"]) — inserts a new slide after the current one",
            "Or: right-click in the slide panel (left side) → Insert New Slide",
            "To choose a layout: Slide menu → Slide Properties",
        ],
        "Verify the slide count increased in the slide panel",
    ),

    # --- Impress: slide transition ---
    (
        r"transition|slide.*effect|animation.*slide",
        ["transition", "effect", "slide"],
        [
            "Select the slide in the slide panel",
            "Slide menu → Slide Transition (or Slide → Slide Properties)",
            "Or: open the Slide Transition panel from the sidebar",
            "Choose a transition effect and speed",
            "Click 'Apply to All Slides' if needed",
        ],
        "Check the transition icon appears on the slide thumbnail",
    ),

    # --- Impress: add text/shape ---
    (
        r"(?:add|insert).*(?:text.*box|shape|rectangle|circle).*(?:slide|presentation)"
        r"|(?:text.*box|shape).*(?:impress|slide)",
        ["text", "shape", "insert", "slide", "presentation"],
        [
            "Insert menu → Text Box: then click and drag on the slide to create it",
            "Insert menu → Shape: choose the shape type",
            "Type text inside the shape or text box",
            "press(key=\"escape\") to deselect",
        ],
        "Verify the shape/text box appears on the slide",
    ),

    # --- General: save / save-as ---
    (
        r"save.*(?:file|document|spreadsheet|presentation)|export.*(?:pdf|csv)",
        ["save", "export", "pdf", "csv"],
        [
            "Save: hotkey(keys=[\"ctrl\",\"s\"])",
            "Save As: hotkey(keys=[\"ctrl\",\"shift\",\"s\"])",
            "Export as PDF: File menu → Export as PDF",
            "For format conversion, use Save As and choose the format from the dropdown",
        ],
        "Check the title bar for the saved filename",
    ),

    # --- General: open file via CLI ---
    (
        r"open.*(?:spreadsheet|document|presentation|\.xlsx|\.docx|\.pptx|\.ods|\.odt|\.odp)",
        ["open", "file", "spreadsheet", "document", "presentation"],
        [
            "Open terminal: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])",
            "type(text=\"libreoffice --calc /path/to/file.xlsx\") — adjust app and path",
            "For Writer: libreoffice --writer /path/to/file.docx",
            "For Impress: libreoffice --impress /path/to/file.pptx",
            "press(key=\"enter\")",
            "wait() — LibreOffice takes a few seconds to start",
        ],
        "Verify LibreOffice opens with the file loaded",
    ),

    # --- General: CLI headless operations ---
    (
        r"(?:convert|export|batch).*(?:headless|command.?line|cli)"
        r"|libreoffice.*--headless|--convert-to",
        ["convert", "headless", "cli", "batch", "command line"],
        [
            "Open terminal: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])",
            "type(text=\"libreoffice --headless --convert-to pdf /path/to/file.xlsx\")",
            "press(key=\"enter\")",
            "wait() — conversion may take a moment",
            "Other formats: csv, html, docx, png",
            "Batch: libreoffice --headless --convert-to pdf /path/to/dir/*.xlsx",
        ],
        "Check the output directory for the converted file",
    ),

    # --- Calc: filter / autofilter ---
    (
        r"filter|auto.*filter|show.*only|hide.*row",
        ["filter", "autofilter"],
        [
            "Click inside the data range",
            "Data menu → AutoFilter — adds dropdown arrows to column headers",
            "Or: hotkey(keys=[\"alt\",\"d\"]) then F for AutoFilter",
            "Click the dropdown arrow on the column to filter",
            "Select or deselect values to show/hide rows",
        ],
        "Verify only the matching rows are visible",
    ),

    # --- Calc: pivot table ---
    (
        r"pivot.*table|data.*pilot|summarize.*data|group.*by.*sum",
        ["pivot", "table", "summarize", "group"],
        [
            "Select the data range via Name Box",
            "Insert menu → Pivot Table (or Data → Pivot Table in older versions)",
            "Drag fields to Row, Column, and Data areas",
            "Configure the aggregation function (Sum, Count, Average)",
            "press(key=\"enter\") to create the pivot table",
        ],
        "Verify the pivot table sheet appears with summarized data",
    ),
]


def find_libreoffice_recipe(instruction: str) -> dict | None:
    """Find a matching LibreOffice recipe for a task instruction.

    Returns a dict with:
    - strategy: list of strategy/approach lines
    - verify: verification hint
    - keywords: matched keywords
    """
    instruction_lower = instruction.lower()

    for pattern, keywords, strategy, verify in LIBREOFFICE_RECIPES:
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "strategy": strategy,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def build_libreoffice_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with LibreOffice strategies.

    If we have a recipe for this task, inject keyboard-driven strategies
    so the agent uses efficient shortcuts instead of hunting through menus.
    """
    recipe = find_libreoffice_recipe(instruction)
    if not recipe:
        return ""

    lines = [
        "\n## LibreOffice Strategy (expert knowledge)",
        "For this task, follow this keyboard-driven approach:",
        "",
    ]
    for i, step in enumerate(recipe["strategy"], 1):
        lines.append(f"{i}. {step}")

    if recipe["verify"]:
        lines.append(f"\nVerification: {recipe['verify']}")

    lines.append("")
    lines.append("## LibreOffice Tips")
    lines.append("- Name Box (left of formula bar): click it, type a cell reference "
                 "(e.g. A1 or B5:D20), press Enter to jump/select")
    lines.append("- Ctrl+Home = go to cell A1; Ctrl+End = go to last used cell")
    lines.append("- For complex multi-cell operations, open the macro editor with Alt+F11 "
                 "and write a LibreOffice Basic macro")
    lines.append("- Alt+F8 = run a macro; F5 = run macro from within the Basic IDE")
    lines.append("- After any dialog: press Enter to confirm or Escape to cancel")

    return "\n".join(lines)
