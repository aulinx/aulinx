"""Tests for the dynamic tool selection module."""

from aulinx.tool_selector import classify_intent, select_tools


class TestClassifyIntent:
    def test_file_intent(self):
        intents = classify_intent("read the config file")
        assert "files" in intents

    def test_git_intent(self):
        intents = classify_intent("show me the git diff")
        assert "git" in intents

    def test_gui_intent(self):
        intents = classify_intent("click the save button")
        assert "gui_interaction" in intents

    def test_web_intent(self):
        intents = classify_intent("open firefox and search for python docs")
        assert "web_browser" in intents

    def test_system_intent(self):
        intents = classify_intent("check running docker containers")
        assert "system_admin" in intents

    def test_audio_intent(self):
        intents = classify_intent("set the volume to 50%")
        assert "media_audio" in intents

    def test_ambiguous_returns_multiple(self):
        intents = classify_intent("open the file manager and browse files")
        assert len(intents) >= 1

    def test_empty_query(self):
        intents = classify_intent("")
        assert intents == []


class TestSelectTools:
    def test_file_query_includes_file_tools(self):
        tools = select_tools("read the config file")
        assert "file_read" in tools
        assert "file_list" in tools

    def test_git_query_includes_git_tools(self):
        tools = select_tools("show git status")
        assert "git_status" in tools

    def test_always_includes_universal(self):
        tools = select_tools("anything")
        assert "shell_exec" in tools
        assert "system_info" in tools

    def test_compositor_mode_adds_compositor_tools(self):
        tools = select_tools("what's on screen", mode="compositor")
        assert "compositor_summary" in tools

    def test_respects_max_tools(self):
        tools = select_tools("manage files and browse web and check system", max_tools=20)
        assert len(tools) <= 20

    def test_filters_available_tools(self):
        available = {"file_read", "file_write", "shell_exec", "system_info", "who_am_i", "context_get", "clipboard_get", "clipboard_set"}
        tools = select_tools("read a file", available_tools=available)
        assert tools <= available

    def test_fallback_for_unknown_intent(self):
        tools = select_tools("xyzzy foobar nonsense")
        # Should still return a reasonable set
        assert len(tools) > 5
