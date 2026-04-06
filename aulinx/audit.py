"""Audit log — records every tool call for transparency and debugging."""

import json
import time
from pathlib import Path

AUDIT_DIR = Path.home() / ".local/share/aulinx"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"


class AuditLog:
    """Append-only JSONL audit log for tool calls."""

    def __init__(self):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self._file = None

    def log(self, tool: str, args: dict, result: str, duration_ms: int = 0):
        """Log a tool call."""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tool": tool,
            "args": _redact_secrets(args),
            "result_preview": result[:300] if result else "",
            "duration_ms": duration_ms,
        }
        try:
            with open(AUDIT_FILE, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def recent(self, limit: int = 20) -> list[dict]:
        """Read recent audit entries."""
        if not AUDIT_FILE.exists():
            return []
        try:
            lines = AUDIT_FILE.read_text().strip().splitlines()
            entries = []
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        except OSError:
            return []

    def clear(self):
        """Clear the audit log."""
        try:
            AUDIT_FILE.write_text("")
        except OSError:
            pass


def _redact_secrets(args: dict) -> dict:
    """Redact sensitive values from tool args before logging."""
    sensitive_keys = {"password", "token", "secret", "key", "api_key", "credential"}
    redacted = {}
    for k, v in args.items():
        if any(s in k.lower() for s in sensitive_keys):
            redacted[k] = "***REDACTED***"
        else:
            redacted[k] = v
    return redacted
