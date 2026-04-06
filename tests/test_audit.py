"""Tests for audit log."""

from unittest.mock import patch

import pytest

from aulinx.audit import AuditLog, _redact_secrets


@pytest.fixture(autouse=True)
def temp_audit(tmp_path):
    """Redirect audit storage to temp directory."""
    audit_file = tmp_path / "audit.jsonl"
    with patch("aulinx.audit.AUDIT_DIR", tmp_path), \
         patch("aulinx.audit.AUDIT_FILE", audit_file):
        yield audit_file


class TestAuditLog:
    def test_log_and_read(self):
        log = AuditLog()
        log.log("window_list", {}, '{"windows": []}', 42)
        entries = log.recent()
        assert len(entries) == 1
        assert entries[0]["tool"] == "window_list"
        assert entries[0]["duration_ms"] == 42

    def test_multiple_entries(self):
        log = AuditLog()
        log.log("tool_a", {}, "result_a", 10)
        log.log("tool_b", {"x": 1}, "result_b", 20)
        log.log("tool_c", {}, "result_c", 30)
        entries = log.recent(2)
        assert len(entries) == 2
        assert entries[0]["tool"] == "tool_b"
        assert entries[1]["tool"] == "tool_c"

    def test_clear(self):
        log = AuditLog()
        log.log("test", {}, "result", 0)
        log.clear()
        assert log.recent() == []

    def test_empty_log(self):
        log = AuditLog()
        assert log.recent() == []


class TestRedaction:
    def test_redacts_password(self):
        result = _redact_secrets({"ssid": "MyWifi", "password": "hunter2"})
        assert result["ssid"] == "MyWifi"
        assert result["password"] == "***REDACTED***"

    def test_redacts_token(self):
        result = _redact_secrets({"api_token": "sk-abc123"})
        assert result["api_token"] == "***REDACTED***"

    def test_redacts_api_key(self):
        result = _redact_secrets({"api_key": "key123", "name": "safe"})
        assert result["api_key"] == "***REDACTED***"
        assert result["name"] == "safe"

    def test_no_secrets(self):
        result = _redact_secrets({"path": "/home", "limit": 50})
        assert result == {"path": "/home", "limit": 50}
