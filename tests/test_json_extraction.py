"""Tests for JSON tool call extraction from LLM responses."""

from aulinx.agent import _extract_tool_call


class TestExtractToolCall:
    def test_json_code_block(self):
        text = 'I\'ll list your windows.\n```json\n{"tool": "window_list", "args": {}}\n```'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "window_list"
        assert result[1] == {}

    def test_json_code_block_with_args(self):
        text = '```json\n{"tool": "file_read", "args": {"path": "/home/user/test.txt", "limit": 50}}\n```'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "file_read"
        assert result[1]["path"] == "/home/user/test.txt"
        assert result[1]["limit"] == 50

    def test_inline_json(self):
        text = 'Let me check: {"tool": "system_info", "args": {}}'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "system_info"

    def test_nested_braces(self):
        text = '{"tool": "dbus_call", "args": {"destination": "org.freedesktop.Notifications", "path": "/org/freedesktop/Notifications"}}'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "dbus_call"
        assert result[1]["destination"] == "org.freedesktop.Notifications"

    def test_no_tool_call(self):
        text = "I don't need to use any tools for this. The answer is 42."
        result = _extract_tool_call(text)
        assert result is None

    def test_empty_string(self):
        result = _extract_tool_call("")
        assert result is None

    def test_malformed_json(self):
        text = '{"tool": "broken", "args": {oops}}'
        result = _extract_tool_call(text)
        assert result is None

    def test_json_without_tool_key(self):
        text = '{"name": "not_a_tool", "value": 42}'
        result = _extract_tool_call(text)
        assert result is None

    def test_tool_with_no_args_key(self):
        text = '{"tool": "window_list"}'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "window_list"
        assert result[1] == {}

    def test_text_before_and_after_json(self):
        text = "Sure, I'll check your volume.\n```json\n{\"tool\": \"audio_get_volume\", \"args\": {}}\n```\nThis will show the current level."
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "audio_get_volume"

    def test_multiple_json_blocks_takes_first(self):
        text = '{"tool": "window_list", "args": {}}\nsome text\n{"tool": "file_read", "args": {"path": "/tmp"}}'
        result = _extract_tool_call(text)
        assert result is not None
        assert result[0] == "window_list"
