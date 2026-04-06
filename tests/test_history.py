"""Tests for conversation history persistence."""

from unittest.mock import patch

import pytest

from aulinx.history import HistoryManager


@pytest.fixture(autouse=True)
def temp_history(tmp_path):
    """Redirect history storage to temp directory."""
    with patch("aulinx.history.HISTORY_DIR", tmp_path):
        yield tmp_path


class TestHistoryManager:
    def test_save_and_load(self):
        mgr = HistoryManager()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        mgr.save(messages)
        loaded = mgr.load_latest()
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["content"] == "hello"

    def test_list_sessions(self):
        mgr = HistoryManager()
        mgr.save([{"role": "user", "content": "first session"}])

        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["messages"] == 1
        assert "first session" in sessions[0]["preview"]

    def test_load_specific_session(self):
        mgr = HistoryManager()
        mgr.save([{"role": "user", "content": "test"}])

        sessions = mgr.list_sessions()
        sid = sessions[0]["session_id"]
        loaded = mgr.load_session(sid)
        assert loaded is not None
        assert loaded[0]["content"] == "test"

    def test_load_nonexistent_session(self):
        mgr = HistoryManager()
        assert mgr.load_session("fake-session-id") is None

    def test_empty_history(self):
        mgr = HistoryManager()
        assert mgr.load_latest() is None
        assert mgr.list_sessions() == []
