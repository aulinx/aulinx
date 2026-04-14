"""Tests for Thunderbird email client knowledge base and recipe matching."""

from benchmark.thunderbird_knowledge import (
    build_thunderbird_recipe_prompt,
    find_thunderbird_recipe,
)


class TestFindThunderbirdRecipe:
    def test_compose_new(self):
        r = find_thunderbird_recipe("Compose a new email in Thunderbird")
        assert r is not None
        assert any("ctrl" in cmd and "n" in cmd for cmd in r["commands"])

    def test_reply(self):
        r = find_thunderbird_recipe("Reply to this message")
        assert r is not None
        assert any("ctrl" in cmd and "r" in cmd for cmd in r["commands"])

    def test_reply_all(self):
        r = find_thunderbird_recipe("Reply all to the email")
        assert r is not None
        assert any("shift" in cmd and "r" in cmd for cmd in r["commands"])

    def test_forward(self):
        r = find_thunderbird_recipe("Forward this email to someone")
        assert r is not None
        assert any("ctrl" in cmd and "l" in cmd for cmd in r["commands"])

    def test_send(self):
        r = find_thunderbird_recipe("Send the email message")
        assert r is not None
        assert any("ctrl" in cmd and "enter" in cmd for cmd in r["commands"])

    def test_address_book(self):
        r = find_thunderbird_recipe("Open the address book")
        assert r is not None
        assert any("shift" in cmd and "b" in cmd for cmd in r["commands"])

    def test_quick_filter(self):
        r = find_thunderbird_recipe("Search for a message in mail")
        assert r is not None
        assert any("ctrl" in cmd and "k" in cmd for cmd in r["commands"])

    def test_advanced_search(self):
        r = find_thunderbird_recipe("Advanced search across all folders")
        assert r is not None
        assert any("shift" in cmd and "f" in cmd for cmd in r["commands"])

    def test_new_folder(self):
        r = find_thunderbird_recipe("Create a new folder in Thunderbird")
        assert r is not None

    def test_move_message(self):
        r = find_thunderbird_recipe("Move message to another folder")
        assert r is not None
        assert any("shift" in cmd and "m" in cmd for cmd in r["commands"])

    def test_delete_message(self):
        r = find_thunderbird_recipe("Delete this email message")
        assert r is not None
        assert any("delete" in cmd for cmd in r["commands"])

    def test_mark_junk(self):
        r = find_thunderbird_recipe("Mark this message as junk")
        assert r is not None

    def test_mark_read_unread(self):
        r = find_thunderbird_recipe("Mark message as read")
        assert r is not None

    def test_tag_message(self):
        r = find_thunderbird_recipe("Tag this message with a label")
        assert r is not None

    def test_toggle_message_pane(self):
        r = find_thunderbird_recipe("Toggle the message preview pane")
        assert r is not None

    def test_attach_file(self):
        r = find_thunderbird_recipe("Attach a file to the email")
        assert r is not None
        assert any("shift" in cmd and "a" in cmd for cmd in r["commands"])

    def test_account_settings(self):
        r = find_thunderbird_recipe("Open account settings in Thunderbird")
        assert r is not None

    def test_signature(self):
        r = find_thunderbird_recipe("Set up an email signature")
        assert r is not None

    def test_preferences(self):
        r = find_thunderbird_recipe("Open Thunderbird preferences")
        assert r is not None

    def test_message_filters(self):
        r = find_thunderbird_recipe("Create a message filter")
        assert r is not None

    def test_print(self):
        r = find_thunderbird_recipe("Print this email message")
        assert r is not None
        assert any("ctrl" in cmd and "p" in cmd for cmd in r["commands"])

    def test_check_mail(self):
        r = find_thunderbird_recipe("Check for new mail")
        assert r is not None
        assert any("f5" in cmd for cmd in r["commands"])

    def test_no_match(self):
        assert find_thunderbird_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_thunderbird_recipe("Open a new tab in Chrome") is None


class TestBuildThunderbirdRecipePrompt:
    def test_returns_commands(self):
        prompt = build_thunderbird_recipe_prompt("Compose a new email")
        assert "ctrl" in prompt.lower()
        assert "Thunderbird" in prompt

    def test_returns_verify(self):
        prompt = build_thunderbird_recipe_prompt("Reply to this message")
        assert "Verification" in prompt or "verify" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_thunderbird_recipe_prompt("random unrelated task") == ""

    def test_attachment_prompt(self):
        prompt = build_thunderbird_recipe_prompt("Attach a file to the email")
        assert "shift" in prompt.lower()
        assert "keyboard shortcuts" in prompt.lower()

    def test_check_mail_prompt(self):
        prompt = build_thunderbird_recipe_prompt("Check for new mail")
        assert "f5" in prompt.lower()
        assert len(prompt) > 0
