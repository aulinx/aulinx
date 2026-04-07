"""Tests for LLM client utilities."""

from aulinx.llm import extract_tool_call, strip_json_blocks


class TestExtractToolCall:
    def test_json_code_block(self):
        text = '```json\n{"tool": "date_now", "args": {}}\n```'
        result = extract_tool_call(text)
        assert result is not None
        assert result[0] == "date_now"

    def test_inline_json(self):
        text = 'Let me check: {"tool": "window_list", "args": {}}'
        result = extract_tool_call(text)
        assert result is not None
        assert result[0] == "window_list"

    def test_no_tool(self):
        assert extract_tool_call("just plain text") is None

    def test_empty(self):
        assert extract_tool_call("") is None


class TestStripJsonBlocks:
    def test_strips_code_block(self):
        text = 'Hello ```json\n{"tool":"x"}\n``` world'
        result = strip_json_blocks(text)
        assert "Hello" in result
        assert "world" in result
        assert "tool" not in result

    def test_strips_inline_json(self):
        text = 'Before {"tool": "test", "args": {}} after'
        result = strip_json_blocks(text)
        assert "Before" in result

    def test_no_json(self):
        text = "Normal text without JSON"
        assert strip_json_blocks(text) == text
