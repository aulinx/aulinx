"""Tests for the learning-from-outcomes module."""

import tempfile
from pathlib import Path

from aulinx.outcomes import (
    OutcomeStore,
    TaskOutcome,
    _extract_keywords,
    _keyword_overlap,
)


class TestExtractKeywords:
    def test_basic(self):
        keywords = _extract_keywords("open the file manager")
        assert "open" in keywords
        assert "file" in keywords
        assert "manager" in keywords
        assert "the" not in keywords  # stop word

    def test_empty(self):
        assert _extract_keywords("") == set()

    def test_strips_punctuation(self):
        keywords = _extract_keywords("hello, world!")
        assert "hello" in keywords
        assert "world" in keywords


class TestKeywordOverlap:
    def test_full_overlap(self):
        assert _keyword_overlap({"a", "b"}, {"a", "b"}) == 1.0

    def test_partial_overlap(self):
        score = _keyword_overlap({"a", "b", "c"}, {"a", "b"})
        assert 0.5 <= score <= 0.8

    def test_no_overlap(self):
        assert _keyword_overlap({"a"}, {"b"}) == 0.0

    def test_empty(self):
        assert _keyword_overlap(set(), {"a"}) == 0.0


class TestOutcomeStore:
    def _make_store(self, tmp_path):
        return OutcomeStore(store_dir=tmp_path)

    def test_record_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            outcome = TaskOutcome(
                goal="open the file manager",
                actions_taken=["app_launch(name=nautilus)"],
                success=True,
                model="test",
            )
            store.record(outcome)

            results = store.retrieve_relevant("open file manager")
            assert len(results) == 1
            assert results[0].success is True

    def test_retrieve_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            assert store.retrieve_relevant("anything") == []

    def test_relevance_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))

            # Record two different outcomes
            store.record(TaskOutcome(goal="open the file manager", success=True))
            store.record(TaskOutcome(goal="check disk usage", success=False))

            # Query about files should match the file manager task
            results = store.retrieve_relevant("open file browser")
            assert len(results) >= 1
            assert "file" in results[0].goal.lower()

    def test_build_experience_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            store.record(TaskOutcome(
                goal="install python packages",
                actions_taken=["shell_exec(cmd=pip install)"],
                success=True,
            ))

            ctx = store.build_experience_context("install python dependencies")
            assert "Past Experience" in ctx
            assert "SUCCEEDED" in ctx

    def test_build_experience_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            assert store.build_experience_context("anything") == ""

    def test_get_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            store.record(TaskOutcome(goal="task1", success=True))
            store.record(TaskOutcome(goal="task2", success=False))

            stats = store.get_stats()
            assert stats["total"] == 2
            assert stats["successes"] == 1
            assert stats["failures"] == 1
            assert stats["success_rate"] == 50.0

    def test_failed_outcome_includes_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(Path(tmp))
            store.record(TaskOutcome(
                goal="delete system files",
                success=False,
                failure_reason="permission denied",
            ))

            ctx = store.build_experience_context("delete files")
            assert "FAILED" in ctx
            assert "permission denied" in ctx
