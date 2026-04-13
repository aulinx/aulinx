"""Tests for VS Code knowledge base and recipe matching."""

from benchmark.vscode_knowledge import (
    _extract_vscode_variables,
    build_vscode_recipe_prompt,
    find_vscode_recipe,
)


class TestFindVscodeRecipe:
    def test_open_file(self):
        r = find_vscode_recipe("Open /home/user/test.py in VS Code")
        assert r is not None
        assert any("code" in cmd for cmd in r["commands"])

    def test_open_folder(self):
        r = find_vscode_recipe("Open the folder /home/user/project in VS Code")
        assert r is not None
        assert any("code" in cmd for cmd in r["commands"])

    def test_install_vsix(self):
        r = find_vscode_recipe("Install the extension from /tmp/my-ext.vsix")
        assert r is not None
        assert any("--install-extension" in cmd for cmd in r["commands"])

    def test_install_marketplace_extension(self):
        r = find_vscode_recipe("Install the VS Code extension ms-python.python")
        assert r is not None
        assert any("--install-extension" in cmd for cmd in r["commands"])

    def test_command_palette(self):
        r = find_vscode_recipe("Open the command palette in VS Code")
        assert r is not None
        assert any("palette" in cmd.lower() or "ctrl" in cmd.lower() for cmd in r["commands"])

    def test_word_wrap_column(self):
        r = find_vscode_recipe("Set VS Code word wrap column to 80")
        assert r is not None
        assert any("wordWrapColumn" in cmd for cmd in r["commands"])

    def test_ruler(self):
        r = find_vscode_recipe("Add a ruler at line length 120 in VS Code")
        assert r is not None
        assert any("rulers" in cmd for cmd in r["commands"])

    def test_find_and_replace(self):
        r = find_vscode_recipe("Find and replace all occurrences in VS Code")
        assert r is not None
        assert any("Ctrl+H" in cmd for cmd in r["commands"])

    def test_save_workspace(self):
        r = find_vscode_recipe("Save the current workspace in VS Code")
        assert r is not None

    def test_add_folder_to_workspace(self):
        r = find_vscode_recipe("Add folder /home/user/lib to workspace")
        assert r is not None
        assert any("--add" in cmd for cmd in r["commands"])

    def test_settings_json(self):
        r = find_vscode_recipe("Open VS Code user settings JSON")
        assert r is not None
        assert any("settings.json" in cmd for cmd in r["commands"])

    def test_no_match(self):
        assert find_vscode_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_vscode_recipe("Set the system volume to max") is None


class TestExtractVscodeVariables:
    def test_file_path(self):
        v = _extract_vscode_variables("Open /home/user/test.py in VS Code")
        assert v["file_path"] == "/home/user/test.py"

    def test_vsix_path(self):
        v = _extract_vscode_variables("Install extension from /tmp/my-ext.vsix")
        assert v["vsix_path"] == "/tmp/my-ext.vsix"

    def test_extension_id(self):
        v = _extract_vscode_variables("Install ms-python.python extension")
        assert v["extension_id"] == "ms-python.python"

    def test_numeric_value(self):
        v = _extract_vscode_variables("Set word wrap column to 80")
        assert v["wrap_column"] == "80"
        assert v["ruler_value"] == "80"

    def test_empty(self):
        v = _extract_vscode_variables("What time is it?")
        assert v == {}

    def test_excludes_common_file_extensions(self):
        v = _extract_vscode_variables("Open file test.json")
        assert "extension_id" not in v


class TestBuildVscodeRecipePrompt:
    def test_returns_commands(self):
        prompt = build_vscode_recipe_prompt("Open /home/user/test.py in VS Code")
        assert "code" in prompt
        assert "VS Code" in prompt

    def test_substitutes_path(self):
        prompt = build_vscode_recipe_prompt("Open /home/user/test.py in VS Code")
        assert "/home/user/test.py" in prompt

    def test_substitutes_extension_id(self):
        prompt = build_vscode_recipe_prompt("Install VS Code extension ms-python.python")
        assert "ms-python.python" in prompt

    def test_substitutes_wrap_column(self):
        prompt = build_vscode_recipe_prompt("Set VS Code word wrap column to 80")
        assert "80" in prompt

    def test_empty_for_unknown(self):
        assert build_vscode_recipe_prompt("random task") == ""

    def test_includes_cli_advice(self):
        prompt = build_vscode_recipe_prompt("Install extension from /tmp/test.vsix")
        assert "CLI" in prompt or "cli" in prompt or "terminal" in prompt.lower()
