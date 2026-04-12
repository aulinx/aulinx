"""Tests for history summarization module."""

from aulinx.summarizer import (
    should_summarize,
    summarize_history,
    _summarize_tool_result,
)


class TestShouldSummarize:
    def test_short_history(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert not should_summarize(messages)

    def test_long_history(self):
        messages = [{"role": "tool", "content": "{}"} for _ in range(7)]
        assert should_summarize(messages)


class TestSummarizeHistory:
    def test_short_passthrough(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert summarize_history(messages) == messages

    def test_compresses_old_messages(self):
        messages = [
            {"role": "user", "content": "task 1"},
            {"role": "assistant", "content": "doing task 1", "tool_calls": [{"function": {"name": "file_read"}}]},
            {"role": "tool", "content": '{"content": "file data"}'},
            {"role": "assistant", "content": "task 1 done"},
            {"role": "user", "content": "task 2"},
            {"role": "assistant", "content": "doing task 2", "tool_calls": [{"function": {"name": "file_write"}}]},
            {"role": "tool", "content": '{"success": true}'},
            {"role": "assistant", "content": "task 2 done"},
            {"role": "user", "content": "task 3"},
            {"role": "assistant", "content": "on it"},
        ]
        result = summarize_history(messages, max_recent=4)
        # Should have 1 summary + 4 recent
        assert len(result) == 5
        assert "summary" in result[0]["content"].lower()
        assert result[-1]["content"] == "on it"

    def test_preserves_recent(self):
        messages = [
            {"role": "user", "content": f"msg {i}"} for i in range(10)
        ]
        result = summarize_history(messages, max_recent=3)
        assert result[-1]["content"] == "msg 9"
        assert result[-2]["content"] == "msg 8"
        assert result[-3]["content"] == "msg 7"


class TestSummarizeToolResult:
    def test_json_success(self):
        result = _summarize_tool_result('{"files": ["a.txt", "b.txt"], "count": 2}')
        assert "OK" in result

    def test_json_error(self):
        result = _summarize_tool_result('{"error": "file not found"}')
        assert "ERROR" in result

    def test_json_list(self):
        result = _summarize_tool_result('[1, 2, 3]')
        assert "3 items" in result

    def test_plain_text(self):
        result = _summarize_tool_result("some plain text result")
        assert "some plain text" in result

    def test_empty(self):
        assert _summarize_tool_result("") == "(empty)"
