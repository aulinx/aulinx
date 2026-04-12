"""Tests for benchmark adapter grounding and target extraction."""

from benchmark.osworld_adapter import _extract_click_target


class TestExtractClickTarget:
    def test_quoted_target(self):
        assert _extract_click_target("I need to click on 'New Folder'") == "New Folder"

    def test_double_quoted(self):
        assert _extract_click_target('click on "Save As"') == "Save As"

    def test_click_on_pattern(self):
        assert _extract_click_target("I need to click on Documents") == "Documents"

    def test_click_the_button(self):
        target = _extract_click_target("I'll click the Save button")
        assert target == "Save"

    def test_clicking_pattern(self):
        target = _extract_click_target("clicking on the OK button")
        assert target == "OK"

    def test_select_pattern(self):
        target = _extract_click_target("I need to select the Downloads option")
        assert target == "Downloads"

    def test_open_pattern(self):
        target = _extract_click_target("I'll open the Documents folder")
        assert target == "Documents"

    def test_empty(self):
        assert _extract_click_target("") == ""

    def test_no_click_target(self):
        assert _extract_click_target("I need to type something") == ""
