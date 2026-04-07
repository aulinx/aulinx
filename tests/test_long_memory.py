"""Tests for long-term memory system."""

from unittest.mock import patch

import pytest

from aulinx.long_memory import LongMemory, _extract_keywords


@pytest.fixture(autouse=True)
def temp_memory(tmp_path):
    import aulinx.long_memory as lm
    mem_file = tmp_path / "long_memory.jsonl"
    with patch.object(lm, "MEMORY_DIR", tmp_path), \
         patch.object(lm, "LONG_MEMORY_FILE", mem_file):
        yield mem_file


class TestLongMemory:
    def test_remember_and_recall(self):
        mem = LongMemory()
        mem.remember("User prefers dark mode", category="preference")

        results = mem.recall("dark mode")
        assert len(results) == 1
        assert "dark mode" in results[0]["content"]
        assert results[0]["category"] == "preference"

    def test_recall_empty(self):
        mem = LongMemory()
        results = mem.recall("anything")
        assert results == []

    def test_recall_recent(self):
        mem = LongMemory()
        mem.remember("fact one")
        mem.remember("fact two")
        mem.remember("fact three")

        recent = mem.recall_recent(2)
        assert len(recent) == 2
        assert recent[-1]["content"] == "fact three"

    def test_forget(self):
        mem = LongMemory()
        mem.remember("keep this")
        mem.remember("remove dark mode preference")

        removed = mem.forget("dark mode")
        assert removed == 1
        assert mem.count() == 1

    def test_count(self):
        mem = LongMemory()
        assert mem.count() == 0
        mem.remember("one")
        mem.remember("two")
        assert mem.count() == 2

    def test_summarize_for_context(self):
        mem = LongMemory()
        mem.remember("User prefers dark mode")
        mem.remember("User uses Firefox as browser")

        summary = mem.summarize_for_context("dark mode")
        assert "dark mode" in summary
        assert "Relevant memories" in summary

    def test_summarize_empty(self):
        mem = LongMemory()
        assert mem.summarize_for_context("anything") == ""

    def test_keyword_relevance(self):
        mem = LongMemory()
        mem.remember("Python is a programming language")
        mem.remember("The weather today is sunny")
        mem.remember("Python Flask web development")

        results = mem.recall("python programming")
        assert len(results) >= 1
        # Python-related entries should rank higher
        assert "python" in results[0]["content"].lower()


class TestKeywordExtraction:
    def test_basic(self):
        keywords = _extract_keywords("The quick brown fox jumps over the lazy dog")
        assert "quick" in keywords
        assert "brown" in keywords
        assert "the" not in keywords  # stop word

    def test_strips_punctuation(self):
        keywords = _extract_keywords("hello, world! test.")
        assert "hello" in keywords
        assert "world" in keywords

    def test_short_words_excluded(self):
        keywords = _extract_keywords("I am a go to it")
        assert len(keywords) == 0  # all short or stop words
