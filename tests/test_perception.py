"""Tests for the hybrid perception module."""

from aulinx.perception import (
    ObservationMode,
    build_hybrid_prompt_section,
    count_interactive_elements,
    decide_observation_mode,
)


class TestDecideObservationMode:
    def test_empty_tree_returns_screenshot(self):
        assert decide_observation_mode("", "", 0) == ObservationMode.SCREENSHOT

    def test_no_elements_message_returns_screenshot(self):
        assert decide_observation_mode(
            "[No accessibility tree available]", "", 0
        ) == ObservationMode.SCREENSHOT

    def test_rich_tree_returns_semantic(self):
        assert decide_observation_mode(
            '[0] button "Save"\n[1] textbox "Name"\n[2] button "Cancel"',
            "gedit",
            3,
        ) == ObservationMode.SEMANTIC

    def test_opaque_app_sparse_tree_returns_hybrid(self):
        assert decide_observation_mode(
            '[0] button "Back"',
            "Firefox",
            1,
        ) == ObservationMode.HYBRID

    def test_opaque_app_rich_tree_returns_hybrid(self):
        # Even with rich tree, opaque apps get hybrid
        assert decide_observation_mode(
            '[0] button "a"\n[1] button "b"\n[2] button "c"',
            "Firefox",
            3,
        ) == ObservationMode.HYBRID

    def test_sparse_tree_non_opaque_returns_hybrid(self):
        assert decide_observation_mode(
            '[0] button "OK"',
            "gedit",
            1,
        ) == ObservationMode.HYBRID

    def test_force_mode(self):
        assert decide_observation_mode(
            "anything", "anything", 0,
            force_mode=ObservationMode.SEMANTIC,
        ) == ObservationMode.SEMANTIC


class TestCountInteractiveElements:
    def test_empty(self):
        assert count_interactive_elements("") == 0

    def test_no_elements_message(self):
        assert count_interactive_elements("[No interactive elements found]") == 0

    def test_counts_buttons_and_text(self):
        tree = '[0] button "Save" at (100,200) size (80,30)\n[1] textbox "Name" at (200,100) size (300,30)'
        assert count_interactive_elements(tree) == 2

    def test_counts_numbered_elements(self):
        tree = '[0] frame "Main"\n[1] panel "Side"\n[2] label "Title"'
        assert count_interactive_elements(tree) == 3


class TestBuildHybridPromptSection:
    def test_semantic_only(self):
        result = build_hybrid_prompt_section('[0] button "Save"')
        assert "UI Elements" in result
        assert "Save" in result

    def test_with_screenshot(self):
        result = build_hybrid_prompt_section(
            '[0] button "Save"',
            "A dialog with a save button",
        )
        assert "UI Elements" in result
        assert "Visual Context" in result

    def test_empty_returns_no_observation(self):
        result = build_hybrid_prompt_section("", "")
        assert "No observation available" in result

    def test_no_elements_message_skipped(self):
        result = build_hybrid_prompt_section(
            "[No interactive elements found]",
            "A screenshot description",
        )
        assert "Visual Context" in result
