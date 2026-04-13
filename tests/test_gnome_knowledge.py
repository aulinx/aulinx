"""Tests for GNOME knowledge base and recipe matching."""

from benchmark.gnome_knowledge import (
    _extract_variables,
    build_file_recipe_prompt,
    build_recipe_prompt,
    find_file_recipe,
    find_recipe,
)


class TestFindRecipe:
    def test_volume(self):
        r = find_recipe("Turn up the volume to max")
        assert r is not None
        assert "pactl" in r["commands"][0]

    def test_text_scaling(self):
        r = find_recipe("Enlarge the text on my screen")
        assert r is not None
        assert "text-scaling-factor" in r["commands"][0]

    def test_auto_lock(self):
        r = find_recipe("Auto-lock my screen when I leave")
        assert r is not None
        assert "lock-enabled" in r["commands"][0]

    def test_battery(self):
        r = find_recipe("Show battery percentage on screen")
        assert r is not None
        assert "show-battery-percentage" in r["commands"][0]

    def test_notifications(self):
        r = find_recipe("Switch to do not disturb mode")
        assert r is not None
        assert "show-banners" in r["commands"][0]

    def test_favorites(self):
        r = find_recipe("Remove vim from favorite apps")
        assert r is not None
        assert "favorite-apps" in r["commands"][0]

    def test_terminal_size(self):
        r = find_recipe("Set terminal size permanently to 132x43")
        assert r is not None
        assert "columns" in r["commands"][1] or "PROFILE" in r["commands"][0]

    def test_install_app(self):
        r = find_recipe("Install Spotify on my system")
        assert r is not None
        assert "snap" in r["commands"][0] or "install" in r["commands"][0]

    def test_no_match(self):
        assert find_recipe("What time is it?") is None


class TestFindFileRecipe:
    def test_copy_jpg(self):
        r = find_file_recipe("Copy .jpg files from photos directory")
        assert r is not None
        assert "find" in r["commands"][1]

    def test_append_br(self):
        r = find_file_recipe("Append <br/> to end of each line")
        assert r is not None
        assert "output.txt" in r["commands"][0]

    def test_compress_old(self):
        r = find_file_recipe("Compress files modified 30 days ago")
        assert r is not None

    def test_no_match(self):
        assert find_file_recipe("Read the README file") is None


class TestBuildRecipePrompt:
    def test_returns_commands(self):
        prompt = build_recipe_prompt("Turn up volume to max")
        assert "pactl" in prompt
        assert "terminal" in prompt.lower()

    def test_returns_verify(self):
        prompt = build_recipe_prompt("Enable auto-lock")
        assert "verify" in prompt.lower() or "Verify" in prompt

    def test_empty_for_unknown(self):
        assert build_recipe_prompt("random task") == ""


class TestExtractVariables:
    def test_install_app(self):
        v = _extract_variables("Install Spotify on my system")
        assert v["app_name"] == "spotify"

    def test_remove_favorite(self):
        v = _extract_variables("Remove vim from favorite apps")
        assert v["app_name"] == "vim"

    def test_ssh_user(self):
        v = _extract_variables('Create SSH user named "charles" with password "Ex@mpleP@55w0rd!" on Ubuntu who is only allowed to access the folder "/home/test1"')
        assert v["username"] == "charles"
        assert v["password"] == "Ex@mpleP@55w0rd!"
        assert v["homedir"] == "/home/test1"

    def test_empty(self):
        v = _extract_variables("What time is it?")
        assert v == {}


class TestBuildRecipePromptWithVariables:
    def test_install_substitutes_app(self):
        prompt = build_recipe_prompt("Install Spotify on my system")
        assert "spotify" in prompt

    def test_ssh_substitutes_user(self):
        prompt = build_recipe_prompt('Create SSH user named "charles" with password "test123" who is only allowed to access the folder "/home/test1"')
        assert "charles" in prompt
        assert "test123" in prompt

    def test_remove_favorite_substitutes_app(self):
        prompt = build_recipe_prompt("Remove vim from favorite apps")
        assert "vim" in prompt


class TestBuildFileRecipePrompt:
    def test_returns_commands(self):
        prompt = build_file_recipe_prompt("Copy .jpg files")
        assert "find" in prompt
        assert "terminal" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_file_recipe_prompt("random task") == ""
