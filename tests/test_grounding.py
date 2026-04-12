"""Tests for the action grounding module."""

from aulinx.grounding import (
    GroundedElement,
    ground_action,
    ground_element_from_tree,
    _match_score,
    _parse_tree_line,
)

SAMPLE_TREE = """\
[0] button "Save" at (100,200) size (80,30)
[1] button "Cancel" at (200,200) size (80,30)
[2] textbox "Name" at (100,100) size (300,30) [focused]
[3] menu_item "File" at (10,10) size (40,20)
[4] button "OK" at (300,300) size (60,25)
"""


class TestGroundElementFromTree:
    def test_exact_match(self):
        elem = ground_element_from_tree("Save", SAMPLE_TREE)
        assert elem is not None
        assert elem.name == "Save"
        assert elem.center_x == 140  # 100 + 80/2
        assert elem.center_y == 215  # 200 + 30/2

    def test_case_insensitive(self):
        elem = ground_element_from_tree("save", SAMPLE_TREE)
        assert elem is not None
        assert elem.name == "Save"

    def test_role_filter(self):
        elem = ground_element_from_tree("Name", SAMPLE_TREE, role_filter="textbox")
        assert elem is not None
        assert elem.role == "textbox"

    def test_role_filter_excludes(self):
        # "Name" exists as textbox, not button
        elem = ground_element_from_tree("Name", SAMPLE_TREE, role_filter="button")
        assert elem is None

    def test_not_found(self):
        assert ground_element_from_tree("Delete", SAMPLE_TREE) is None

    def test_empty_tree(self):
        assert ground_element_from_tree("Save", "") is None

    def test_empty_query(self):
        assert ground_element_from_tree("", SAMPLE_TREE) is None


class TestGroundAction:
    def test_click_button(self):
        result = ground_action("click the Save button", SAMPLE_TREE)
        assert result is not None
        assert result["action"] == "click"
        assert result["x"] == 140
        assert result["y"] == 215

    def test_click_simple(self):
        result = ground_action("click OK", SAMPLE_TREE)
        assert result is not None
        assert result["action"] == "click"

    def test_type_in_field(self):
        result = ground_action('type "hello" in the Name field', SAMPLE_TREE)
        assert result is not None
        assert result["action"] == "type"
        assert result["text"] == "hello"

    def test_select_item(self):
        result = ground_action("select File", SAMPLE_TREE)
        assert result is not None
        assert result["action"] == "click"

    def test_ungrounded_action(self):
        result = ground_action("scroll down", SAMPLE_TREE)
        assert result is None


class TestParseTreeLine:
    def test_button(self):
        elem = _parse_tree_line('[0] button "Save" at (100,200) size (80,30)')
        assert elem is not None
        assert elem.name == "Save"
        assert elem.role == "button"
        assert elem.x == 100
        assert elem.y == 200
        assert elem.width == 80
        assert elem.height == 30

    def test_no_coords(self):
        elem = _parse_tree_line('[0] button "Save"')
        assert elem is None  # no coords, can't ground

    def test_with_state(self):
        elem = _parse_tree_line('[2] textbox "Name" at (100,100) size (300,30) [focused]')
        assert elem is not None
        assert elem.name == "Name"


class TestMatchScore:
    def test_exact_match(self):
        assert _match_score("save", "save", "button") == 1.0

    def test_contains(self):
        assert _match_score("save", "save as", "button") >= 0.7

    def test_no_match(self):
        assert _match_score("delete", "save", "button") < 0.3

    def test_role_in_query(self):
        score = _match_score("save button", "save", "button")
        assert score >= 0.6
