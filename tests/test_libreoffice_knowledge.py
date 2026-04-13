"""Tests for LibreOffice knowledge base and recipe matching."""

from benchmark.libreoffice_knowledge import (
    build_libreoffice_recipe_prompt,
    find_libreoffice_recipe,
)


class TestFindLibreOfficeRecipe:
    def test_cell_navigation(self):
        r = find_libreoffice_recipe("Navigate to cell B5 in the spreadsheet")
        assert r is not None
        assert "Name Box" in r["strategy"][0]

    def test_formula(self):
        r = find_libreoffice_recipe("Enter a SUM formula for column A")
        assert r is not None
        assert any("formula" in s.lower() for s in r["strategy"])

    def test_fill_down(self):
        r = find_libreoffice_recipe("Fill down the formula from A1 to A20")
        assert r is not None
        assert any("ctrl" in s.lower() for s in r["strategy"])

    def test_sort_data(self):
        r = find_libreoffice_recipe("Sort the data in ascending order by column B")
        assert r is not None
        assert any("sort" in s.lower() for s in r["strategy"])

    def test_insert_row(self):
        r = find_libreoffice_recipe("Insert a new row above row 5")
        assert r is not None

    def test_create_chart(self):
        r = find_libreoffice_recipe("Create a bar chart from the sales data")
        assert r is not None
        assert any("chart" in s.lower() for s in r["strategy"])

    def test_rename_sheet(self):
        r = find_libreoffice_recipe("Rename the sheet tab to 'Sales Q1'")
        assert r is not None
        assert any("tab" in s.lower() for s in r["strategy"])

    def test_macro(self):
        r = find_libreoffice_recipe("Run a macro to automate the calculations")
        assert r is not None
        assert any("alt" in s.lower() and "f11" in s.lower() for s in r["strategy"])

    def test_find_replace(self):
        r = find_libreoffice_recipe("Find and replace all occurrences of 'foo' with 'bar'")
        assert r is not None
        assert any("ctrl" in s.lower() and "h" in s.lower() for s in r["strategy"])

    def test_save(self):
        r = find_libreoffice_recipe("Save the document as PDF")
        assert r is not None
        assert any("save" in s.lower() or "pdf" in s.lower() for s in r["strategy"])

    def test_add_slide(self):
        r = find_libreoffice_recipe("Add a new slide to the presentation")
        assert r is not None

    def test_bold_text(self):
        r = find_libreoffice_recipe("Bold the paragraph text in the document")
        assert r is not None
        assert any("ctrl" in s.lower() and "b" in s.lower() for s in r["strategy"])

    def test_filter(self):
        r = find_libreoffice_recipe("Filter the data to show only sales > 100")
        assert r is not None

    def test_freeze_panes(self):
        r = find_libreoffice_recipe("Freeze the first row in the spreadsheet")
        assert r is not None

    def test_open_file(self):
        r = find_libreoffice_recipe("Open the spreadsheet file report.xlsx")
        assert r is not None
        assert any("libreoffice" in s.lower() for s in r["strategy"])

    def test_page_layout(self):
        r = find_libreoffice_recipe("Change page orientation to landscape")
        assert r is not None

    def test_pivot_table(self):
        r = find_libreoffice_recipe("Create a pivot table to summarize data by region")
        assert r is not None

    def test_no_match(self):
        assert find_libreoffice_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_libreoffice_recipe("Turn up the volume to max") is None


class TestBuildLibreOfficeRecipePrompt:
    def test_returns_strategy(self):
        prompt = build_libreoffice_recipe_prompt("Enter a SUM formula in cell A10")
        assert "LibreOffice Strategy" in prompt
        assert "formula" in prompt.lower()

    def test_returns_tips(self):
        prompt = build_libreoffice_recipe_prompt("Sort data ascending")
        assert "Name Box" in prompt
        assert "Ctrl+Home" in prompt

    def test_returns_verification(self):
        prompt = build_libreoffice_recipe_prompt("Create a chart from the data")
        assert "Verification" in prompt

    def test_empty_for_unknown(self):
        assert build_libreoffice_recipe_prompt("random task") == ""

    def test_empty_for_gnome_task(self):
        assert build_libreoffice_recipe_prompt("Set volume to max") == ""
