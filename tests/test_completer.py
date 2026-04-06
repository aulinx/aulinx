"""Tests for tab completion."""

from prompt_toolkit.document import Document

from aulinx.completer import AulinxCompleter


class TestSlashCompletion:
    def test_completes_slash_commands(self):
        completer = AulinxCompleter(["window_list", "file_read"])
        doc = Document("/to")
        completions = list(completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "/tools" in names

    def test_completes_all_slashes_on_prefix(self):
        completer = AulinxCompleter([])
        doc = Document("/")
        completions = list(completer.get_completions(doc, None))
        assert len(completions) >= 6  # /tools, /context, /history, /audit, /doctor, /clear, /help

    def test_no_completions_for_plain_text(self):
        completer = AulinxCompleter(["window_list"])
        doc = Document("hello")
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 0


class TestToolCompletion:
    def test_completes_at_tool(self):
        completer = AulinxCompleter(["window_list", "window_get_focused", "file_read"])
        doc = Document("use @window")
        completions = list(completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "window_list" in names
        assert "window_get_focused" in names
        assert "file_read" not in names

    def test_at_with_empty_prefix(self):
        completer = AulinxCompleter(["a_tool", "b_tool"])
        doc = Document("@")
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 2
