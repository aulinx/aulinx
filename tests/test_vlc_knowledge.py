"""Tests for VLC media player knowledge base and recipe matching."""

from benchmark.vlc_knowledge import (
    build_vlc_recipe_prompt,
    find_vlc_recipe,
)


class TestFindVlcRecipe:
    def test_play_pause(self):
        r = find_vlc_recipe("Play or pause the video in VLC")
        assert r is not None
        assert any("space" in cmd for cmd in r["commands"])

    def test_stop(self):
        r = find_vlc_recipe("Stop playback in VLC")
        assert r is not None

    def test_next_track(self):
        r = find_vlc_recipe("Skip to the next track in VLC")
        assert r is not None
        assert any("n" in cmd for cmd in r["commands"])

    def test_previous_track(self):
        r = find_vlc_recipe("Go back to the previous track")
        assert r is not None
        assert any("p" in cmd for cmd in r["commands"])

    def test_volume_up(self):
        r = find_vlc_recipe("Increase the volume in VLC")
        assert r is not None
        assert any("ctrl" in cmd and "up" in cmd for cmd in r["commands"])

    def test_volume_down(self):
        r = find_vlc_recipe("Decrease volume in VLC")
        assert r is not None
        assert any("ctrl" in cmd and "down" in cmd for cmd in r["commands"])

    def test_mute(self):
        r = find_vlc_recipe("Mute the audio")
        assert r is not None
        assert any("m" in cmd for cmd in r["commands"])

    def test_fullscreen(self):
        r = find_vlc_recipe("Enter fullscreen mode in VLC")
        assert r is not None
        assert any("f" in cmd for cmd in r["commands"])

    def test_open_file(self):
        r = find_vlc_recipe("Open a file in VLC")
        assert r is not None
        assert any("ctrl" in cmd and "o" in cmd for cmd in r["commands"])

    def test_open_url(self):
        r = find_vlc_recipe("Open a network stream URL in VLC")
        assert r is not None
        assert any("ctrl" in cmd and "n" in cmd for cmd in r["commands"])

    def test_cycle_subtitles(self):
        r = find_vlc_recipe("Cycle through subtitle tracks in VLC")
        assert r is not None

    def test_add_subtitle(self):
        r = find_vlc_recipe("Add a subtitle file to VLC")
        assert r is not None

    def test_speed_up(self):
        r = find_vlc_recipe("Speed up playback in VLC")
        assert r is not None

    def test_speed_down(self):
        r = find_vlc_recipe("Slow down playback speed")
        assert r is not None

    def test_playlist(self):
        r = find_vlc_recipe("Show the VLC playlist")
        assert r is not None
        assert any("ctrl" in cmd and "l" in cmd for cmd in r["commands"])

    def test_loop(self):
        r = find_vlc_recipe("Toggle loop mode in VLC")
        assert r is not None

    def test_audio_track(self):
        r = find_vlc_recipe("Switch audio track in VLC")
        assert r is not None
        assert any("b" in cmd for cmd in r["commands"])

    def test_preferences(self):
        r = find_vlc_recipe("Open VLC preferences")
        assert r is not None
        assert any("ctrl" in cmd and "p" in cmd for cmd in r["commands"])

    def test_screenshot(self):
        r = find_vlc_recipe("Take a screenshot of the video frame")
        assert r is not None
        assert any("shift" in cmd and "s" in cmd for cmd in r["commands"])

    def test_aspect_ratio(self):
        r = find_vlc_recipe("Change the aspect ratio in VLC")
        assert r is not None

    def test_cli_fullscreen(self):
        r = find_vlc_recipe("Play a file in fullscreen from the terminal using cvlc")
        assert r is not None

    def test_no_match(self):
        assert find_vlc_recipe("What time is it?") is None

    def test_no_match_unrelated(self):
        assert find_vlc_recipe("Open Chrome browser") is None


class TestBuildVlcRecipePrompt:
    def test_returns_commands(self):
        prompt = build_vlc_recipe_prompt("Play or pause the video in VLC")
        assert "space" in prompt.lower()
        assert "VLC" in prompt

    def test_returns_verify(self):
        prompt = build_vlc_recipe_prompt("Mute the audio in VLC")
        assert "Verification" in prompt or "verify" in prompt.lower()

    def test_empty_for_unknown(self):
        assert build_vlc_recipe_prompt("random unrelated task") == ""

    def test_fullscreen_prompt(self):
        prompt = build_vlc_recipe_prompt("Enter fullscreen in VLC")
        assert len(prompt) > 0
        assert "VLC" in prompt

    def test_volume_prompt(self):
        prompt = build_vlc_recipe_prompt("Increase VLC volume")
        assert "ctrl" in prompt.lower()
