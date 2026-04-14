"""Tests for GIMP image editor knowledge base and recipe matching."""

from benchmark.gimp_knowledge import (
    build_gimp_recipe_prompt,
    find_gimp_recipe,
)


class TestFindGimpRecipe:
    def test_open_file(self):
        r = find_gimp_recipe("Open an image in GIMP")
        assert r is not None
        assert any("ctrl" in cmd and "o" in cmd for cmd in r["commands"])

    def test_save(self):
        r = find_gimp_recipe("Save the image in GIMP")
        assert r is not None
        assert any("ctrl" in cmd and "s" in cmd for cmd in r["commands"])

    def test_export_as(self):
        r = find_gimp_recipe("Export image as PNG")
        assert r is not None
        assert any("shift" in cmd and "e" in cmd for cmd in r["commands"])

    def test_autocrop(self):
        r = find_gimp_recipe("Autocrop the image borders")
        assert r is not None
        assert any("shift" in cmd and "x" in cmd for cmd in r["commands"])

    def test_crop_to_selection(self):
        r = find_gimp_recipe("Crop image to selection")
        assert r is not None

    def test_scale_image(self):
        r = find_gimp_recipe("Resize image to 800x600")
        assert r is not None
        assert "scale" in r["keywords"] or "resize" in r["keywords"]

    def test_canvas_size(self):
        r = find_gimp_recipe("Change canvas size in GIMP")
        assert r is not None

    def test_rotate_90_cw(self):
        r = find_gimp_recipe("Rotate image 90 degrees clockwise")
        assert r is not None
        assert "rotate" in r["keywords"]

    def test_rotate_90_ccw(self):
        r = find_gimp_recipe("Rotate image 90 degrees counterclockwise")
        assert r is not None

    def test_rotate_180(self):
        r = find_gimp_recipe("Rotate image 180 degrees")
        assert r is not None

    def test_flip_horizontal(self):
        r = find_gimp_recipe("Flip the image horizontally")
        assert r is not None
        assert "horizontal" in r["keywords"]

    def test_flip_vertical(self):
        r = find_gimp_recipe("Flip the image vertically")
        assert r is not None
        assert "vertical" in r["keywords"]

    def test_gaussian_blur(self):
        r = find_gimp_recipe("Apply Gaussian blur to the image")
        assert r is not None
        assert "blur" in r["keywords"]

    def test_sharpen(self):
        r = find_gimp_recipe("Sharpen this image")
        assert r is not None
        assert "sharpen" in r["keywords"]

    def test_new_layer(self):
        r = find_gimp_recipe("Create a new layer")
        assert r is not None
        assert any("shift" in cmd and "n" in cmd for cmd in r["commands"])

    def test_duplicate_layer(self):
        r = find_gimp_recipe("Duplicate the current layer")
        assert r is not None
        assert any("shift" in cmd and "d" in cmd for cmd in r["commands"])

    def test_merge_down(self):
        r = find_gimp_recipe("Merge layer down")
        assert r is not None

    def test_flatten_image(self):
        r = find_gimp_recipe("Flatten image layers")
        assert r is not None

    def test_brightness_contrast(self):
        r = find_gimp_recipe("Adjust brightness and contrast")
        assert r is not None
        assert "brightness" in r["keywords"]

    def test_hue_saturation(self):
        r = find_gimp_recipe("Adjust hue and saturation")
        assert r is not None
        assert "hue" in r["keywords"]

    def test_desaturate(self):
        r = find_gimp_recipe("Desaturate the image to grayscale")
        assert r is not None
        assert "desaturate" in r["keywords"]

    def test_select_all(self):
        r = find_gimp_recipe("Select all in GIMP")
        assert r is not None
        assert any("ctrl" in cmd and "a" in cmd for cmd in r["commands"])

    def test_select_none(self):
        r = find_gimp_recipe("Deselect everything")
        assert r is not None
        assert any("shift" in cmd and "a" in cmd for cmd in r["commands"])

    def test_script_fu(self):
        r = find_gimp_recipe("Open Script-Fu console")
        assert r is not None

    def test_python_fu(self):
        r = find_gimp_recipe("Open Python-Fu console in GIMP")
        assert r is not None

    def test_cli_batch(self):
        r = find_gimp_recipe("Run GIMP in command line batch mode")
        assert r is not None

    def test_undo(self):
        r = find_gimp_recipe("Undo last action in GIMP")
        assert r is not None
        assert any("ctrl" in cmd and "z" in cmd for cmd in r["commands"])

    def test_redo(self):
        r = find_gimp_recipe("Redo in GIMP")
        assert r is not None
        assert any("ctrl" in cmd and "y" in cmd for cmd in r["commands"])

    def test_no_match(self):
        assert find_gimp_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_gimp_recipe("Set the volume to max") is None


class TestBuildGimpRecipePrompt:
    def test_returns_commands(self):
        prompt = build_gimp_recipe_prompt("Export image as PNG in GIMP")
        assert "GIMP" in prompt
        assert "ctrl" in prompt.lower()

    def test_returns_verify(self):
        prompt = build_gimp_recipe_prompt("Apply Gaussian blur to the image")
        assert "Verification" in prompt or "verify" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_gimp_recipe_prompt("random task") == ""

    def test_layer_prompt(self):
        prompt = build_gimp_recipe_prompt("Create a new layer in GIMP")
        assert "shift" in prompt.lower()
        assert len(prompt) > 0

    def test_includes_script_fu_hint(self):
        prompt = build_gimp_recipe_prompt("Save the image in GIMP")
        assert "Script-Fu" in prompt or "script-fu" in prompt.lower()
