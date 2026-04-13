"""Tests for GNOME knowledge base and recipe matching."""

from benchmark.gnome_knowledge import (
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


class TestBuildFileRecipePrompt:
    def test_returns_commands(self):
        prompt = build_file_recipe_prompt("Copy .jpg files")
        assert "find" in prompt
        assert "terminal" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_file_recipe_prompt("random task") == ""
