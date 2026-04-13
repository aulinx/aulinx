"""Tests for Chrome browser knowledge base and recipe matching."""

from benchmark.chrome_knowledge import (
    build_chrome_recipe_prompt,
    find_chrome_recipe,
)


class TestFindChromeRecipe:
    def test_do_not_track(self):
        r = find_chrome_recipe("Enable Do Not Track in Chrome")
        assert r is not None
        assert any("privacy" in cmd for cmd in r["commands"])

    def test_passwords(self):
        r = find_chrome_recipe("Show saved passwords in Chrome")
        assert r is not None
        assert any("passwords" in cmd for cmd in r["commands"])

    def test_downloads_settings(self):
        r = find_chrome_recipe("Change Chrome download folder location")
        assert r is not None
        assert any("downloads" in cmd for cmd in r["commands"])

    def test_extensions(self):
        r = find_chrome_recipe("Manage Chrome extensions")
        assert r is not None
        assert any("extensions" in cmd for cmd in r["commands"])

    def test_reopen_tab(self):
        r = find_chrome_recipe("Reopen the last closed tab")
        assert r is not None
        assert any("shift" in cmd and "t" in cmd for cmd in r["commands"])

    def test_new_tab(self):
        r = find_chrome_recipe("Open a new tab in Chrome")
        assert r is not None
        assert any("ctrl" in cmd and "t" in cmd for cmd in r["commands"])

    def test_close_tab(self):
        r = find_chrome_recipe("Close the current tab")
        assert r is not None
        assert any("ctrl" in cmd and "w" in cmd for cmd in r["commands"])

    def test_add_bookmark(self):
        r = find_chrome_recipe("Bookmark this page")
        assert r is not None
        assert any("ctrl" in cmd and "d" in cmd for cmd in r["commands"])

    def test_bookmark_manager(self):
        r = find_chrome_recipe("Open bookmark manager")
        assert r is not None
        assert any("shift" in cmd and "o" in cmd for cmd in r["commands"])

    def test_bookmark_folder(self):
        r = find_chrome_recipe("Create a new folder in bookmarks")
        assert r is not None

    def test_address_bar(self):
        r = find_chrome_recipe("Focus the URL address bar")
        assert r is not None
        assert any("ctrl" in cmd and "l" in cmd for cmd in r["commands"])

    def test_go_back(self):
        r = find_chrome_recipe("Go back to the previous page")
        assert r is not None
        assert any("alt" in cmd and "left" in cmd for cmd in r["commands"])

    def test_go_forward(self):
        r = find_chrome_recipe("Navigate forward in browser")
        assert r is not None
        assert any("alt" in cmd and "right" in cmd for cmd in r["commands"])

    def test_clear_browsing_data(self):
        r = find_chrome_recipe("Clear browsing data and cache")
        assert r is not None
        assert any("delete" in cmd for cmd in r["commands"])

    def test_view_downloads(self):
        r = find_chrome_recipe("View my downloads list")
        assert r is not None

    def test_view_history(self):
        r = find_chrome_recipe("Open browsing history")
        assert r is not None

    def test_find_in_page(self):
        r = find_chrome_recipe("Find text in this page")
        assert r is not None

    def test_zoom_in(self):
        r = find_chrome_recipe("Zoom in on this page")
        assert r is not None

    def test_zoom_out(self):
        r = find_chrome_recipe("Zoom out to make smaller")
        assert r is not None

    def test_fullscreen(self):
        r = find_chrome_recipe("Enter full screen mode")
        assert r is not None

    def test_homepage(self):
        r = find_chrome_recipe("Set Chrome homepage")
        assert r is not None
        assert any("onStartup" in cmd for cmd in r["commands"])

    def test_search_engine(self):
        r = find_chrome_recipe("Change the default search engine in Chrome")
        assert r is not None
        assert any("search" in cmd for cmd in r["commands"])

    def test_no_match(self):
        assert find_chrome_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_chrome_recipe("Set the volume to max") is None


class TestBuildChromeRecipePrompt:
    def test_returns_commands(self):
        prompt = build_chrome_recipe_prompt("Enable Do Not Track in Chrome")
        assert "privacy" in prompt
        assert "Chrome" in prompt

    def test_returns_verify(self):
        prompt = build_chrome_recipe_prompt("Show saved passwords in Chrome")
        assert "Verification" in prompt or "verify" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_chrome_recipe_prompt("random task") == ""

    def test_bookmark_prompt(self):
        prompt = build_chrome_recipe_prompt("Bookmark this page in Chrome")
        assert "ctrl" in prompt.lower()
        assert "chrome://" in prompt.lower() or "address bar" in prompt.lower()

    def test_tab_management_prompt(self):
        prompt = build_chrome_recipe_prompt("Reopen the last closed tab")
        assert "shift" in prompt.lower()
        assert len(prompt) > 0
