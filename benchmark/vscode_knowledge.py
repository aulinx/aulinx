"""VS Code knowledge base — exact commands for common VS Code tasks.

Maps task patterns to precise terminal/keyboard commands. Used by the
prompt builder to inject domain-specific guidance into the benchmark prompt.

Key insight: Many VS Code tasks can be done via the ``code`` CLI command
in terminal, which is more reliable than GUI navigation.
"""

from __future__ import annotations

import re

# pattern_regex → (keywords, commands, verify_command)
VSCODE_RECIPES: list[tuple[str, list[str], list[str], str]] = [
    # --- Command palette (must come before open-file to avoid false matches) ---
    (
        r"command\s+palette|(?:vs\s*code|code).*palette",
        ["command", "palette", "vscode"],
        [
            "# Press Ctrl+Shift+P to open the command palette",
        ],
        "",
    ),

    # --- File operations ---

    # Open a specific file
    (
        r"open.*file.*(?:in|with|using)\s+(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*open.*file|"
        r"open\s+/[\w/.-]+\s+(?:in|with|using)\s+(?:vs\s*code|code)",
        ["open", "file", "vscode", "code"],
        [
            "code {file_path}",
        ],
        "code --status",
    ),

    # Open a folder / project
    (
        r"open.*folder.*(?:in|with|using)\s+(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*open.*folder|"
        r"open\s+[\w/\\. -]+\s+(?:folder|directory|project)\s+in\s+(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*open.*(?:directory|project)",
        ["open", "folder", "directory", "project", "vscode"],
        [
            "code {folder_path}",
        ],
        "code --status",
    ),

    # New file
    (
        r"(?:create|new)\s+(?:a\s+)?(?:new\s+)?(?:untitled\s+)?file\s+(?:in|with|using)\s+(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*new\s+file",
        ["new", "file", "vscode", "create"],
        [
            # Open VS Code then use Ctrl+N for new untitled file
            "code --new-window",
            "# Then press Ctrl+N for a new file",
        ],
        "",
    ),

    # Save file
    (
        r"save.*(?:file|document).*(?:in|with|using)\s+(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*save\s+(?:as|file)",
        ["save", "file", "vscode"],
        [
            "# Press Ctrl+S to save, or Ctrl+Shift+S for Save As",
        ],
        "",
    ),

    # --- Extensions ---

    # Install extension from VSIX file
    (
        r"install.*(?:extension|vsix).*\.vsix|\.vsix.*install",
        ["install", "extension", "vsix"],
        [
            "code --install-extension {vsix_path}",
        ],
        "code --list-extensions",
    ),

    # Install extension from marketplace
    (
        r"install.*extension.*(?:vs\s*code|code)|"
        r"(?:vs\s*code|code).*install.*extension|"
        r"install.*(?:vs\s*code|code)\s+extension",
        ["install", "extension", "marketplace", "vscode"],
        [
            "code --install-extension {extension_id}",
        ],
        "code --list-extensions",
    ),

    # --- Settings ---

    # Open settings JSON
    (
        r"(?:open|edit).*settings?\s*(?:\.json|json)|"
        r"(?:vs\s*code|code).*(?:user\s+)?settings?\s*json",
        ["settings", "json", "vscode", "open"],
        [
            "# Press Ctrl+Shift+P, then type 'Preferences: Open User Settings (JSON)' and press Enter",
            "# Or edit directly: ~/.config/Code/User/settings.json",
        ],
        "cat ~/.config/Code/User/settings.json",
    ),

    # Word wrap column
    (
        r"word\s*wrap.*column|wrap.*column|(?:vs\s*code|code).*word\s*wrap|"
        r"editor\.wordWrapColumn",
        ["word", "wrap", "column", "vscode", "settings"],
        [
            'python3 -c "\nimport json, os\npath = os.path.expanduser(\'~/.config/Code/User/settings.json\')\nos.makedirs(os.path.dirname(path), exist_ok=True)\ntry:\n    settings = json.load(open(path))\nexcept (FileNotFoundError, json.JSONDecodeError):\n    settings = {{}}\nsettings[\'editor.wordWrapColumn\'] = {wrap_column}\nsettings[\'editor.wordWrap\'] = \'wordWrapColumn\'\njson.dump(settings, open(path, \'w\'), indent=4)\n"',
        ],
        "cat ~/.config/Code/User/settings.json",
    ),

    # Rulers / line length
    (
        r"ruler|line\s*(?:length|limit)|editor\.rulers|"
        r"(?:vs\s*code|code).*ruler",
        ["ruler", "line", "length", "vscode", "settings"],
        [
            'python3 -c "\nimport json, os\npath = os.path.expanduser(\'~/.config/Code/User/settings.json\')\nos.makedirs(os.path.dirname(path), exist_ok=True)\ntry:\n    settings = json.load(open(path))\nexcept (FileNotFoundError, json.JSONDecodeError):\n    settings = {{}}\nsettings[\'editor.rulers\'] = [{ruler_value}]\njson.dump(settings, open(path, \'w\'), indent=4)\n"',
        ],
        "cat ~/.config/Code/User/settings.json",
    ),

    # Generic settings change
    (
        r"(?:change|set|modify|update|configure).*(?:vs\s*code|code)\s+setting|"
        r"(?:vs\s*code|code).*(?:change|set|modify|update|configure)\s+setting",
        ["change", "set", "setting", "vscode", "configure"],
        [
            "# Edit settings.json directly:",
            "# ~/.config/Code/User/settings.json",
            '# Use: python3 -c "import json; ... json.dump(...)"',
        ],
        "cat ~/.config/Code/User/settings.json",
    ),

    # --- Editing ---

    # Find and replace
    (
        r"find\s+and\s+replace|replace\s+(?:all|every|each)|"
        r"(?:vs\s*code|code).*(?:find|replace|substitut)",
        ["find", "replace", "vscode"],
        [
            "# Press Ctrl+H to open Find and Replace",
            "# Type the search text, press Tab, type the replacement",
            "# Click 'Replace All' button or press Ctrl+Alt+Enter",
        ],
        "",
    ),

    # --- Workspace ---

    # Save workspace
    (
        r"save.*workspace|workspace.*save",
        ["save", "workspace", "vscode"],
        [
            "# Press Ctrl+Shift+P → type 'Workspaces: Save Workspace As...' → Enter",
        ],
        "",
    ),

    # Add folder to workspace
    (
        r"add\s+folder.*workspace|workspace.*add\s+folder|add.*to.*workspace",
        ["add", "folder", "workspace", "vscode"],
        [
            "code --add {folder_path}",
        ],
        "",
    ),
]


def find_vscode_recipe(instruction: str) -> dict | None:
    """Find a matching VS Code recipe for a task instruction.

    Returns a dict with:
    - commands: list of terminal/keyboard commands to execute
    - verify: verification command
    - keywords: matching keywords
    - pattern: the regex that matched
    """
    instruction_lower = instruction.lower()

    for pattern, keywords, commands, verify in VSCODE_RECIPES:
        if re.search(pattern, instruction_lower):
            return {
                "pattern": pattern,
                "commands": commands,
                "verify": verify,
                "keywords": keywords,
            }

    return None


def _extract_vscode_variables(instruction: str) -> dict[str, str]:
    """Extract variable values from the instruction text.

    Identifies file paths, extension names, settings values, etc.
    """
    variables: dict[str, str] = {}

    # Extract file path: '/path/to/file' or "~/something"
    path_match = re.search(
        r'["\']?((?:/|~/?)[\w/._-]+)["\']?',
        instruction,
    )
    if path_match:
        path = path_match.group(1)
        variables["file_path"] = path
        variables["folder_path"] = path

    # Extract VSIX path: something.vsix
    vsix_match = re.search(
        r'["\']?([\w/._~-]+\.vsix)["\']?',
        instruction,
    )
    if vsix_match:
        variables["vsix_path"] = vsix_match.group(1)

    # Extract extension ID: publisher.extension-name
    ext_match = re.search(
        r'["\']?([\w-]+\.[\w-]+)["\']?',
        instruction,
    )
    if ext_match:
        candidate = ext_match.group(1)
        # Exclude things that look like filenames with common extensions
        if not re.search(r'\.(py|js|ts|json|txt|md|html|css|vsix|xml|yaml|yml|toml)$', candidate):
            variables["extension_id"] = candidate

    # Extract numeric values for settings (e.g., column width, ruler value)
    num_match = re.search(r'(?:to|=|:)\s*(\d+)', instruction)
    if num_match:
        val = num_match.group(1)
        variables["wrap_column"] = val
        variables["ruler_value"] = val

    # Extract setting value from quoted string
    setting_val_match = re.search(r'(?:to|=|:)\s*["\']([^"\']+)["\']', instruction)
    if setting_val_match:
        variables["setting_value"] = setting_val_match.group(1)

    return variables


def _substitute(template: str, variables: dict[str, str]) -> str:
    """Substitute {var} placeholders with extracted values."""
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", value)
    return template


def build_vscode_recipe_prompt(instruction: str) -> str:
    """Build a targeted prompt section with exact commands for a VS Code task.

    If we have a recipe for this task, inject the exact commands
    into the prompt so the agent doesn't waste steps navigating GUIs.
    Variables like {file_path} are substituted from the instruction.
    """
    recipe = find_vscode_recipe(instruction)
    if not recipe:
        return ""

    variables = _extract_vscode_variables(instruction)
    commands = recipe["commands"]
    verify = recipe["verify"]

    # Substitute variables
    commands = [_substitute(cmd, variables) for cmd in commands]
    verify = _substitute(verify, variables)

    lines = [
        "\n## Recommended Approach — VS Code (expert knowledge)",
        "For this VS Code task, prefer CLI commands over GUI navigation:",
        "",
    ]
    for i, cmd in enumerate(commands, 1):
        if cmd.startswith("#"):
            lines.append(f"{i}. {cmd.lstrip('# ')}")
        else:
            lines.append(f"{i}. type(text=\"{cmd}\") then press(key=\"enter\")")

    if verify:
        lines.append(f"\nTo verify: type(text=\"{verify}\") then press(key=\"enter\")")

    lines.append("")
    lines.append("Open terminal first: hotkey(keys=[\"ctrl\",\"alt\",\"t\"])")
    lines.append("Many VS Code tasks work best via the `code` CLI — it's faster and more reliable than GUI navigation.")
    lines.append("After verification succeeds: done()")

    return "\n".join(lines)
