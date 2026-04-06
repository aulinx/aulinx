"""Conversation history — save/load sessions for continuity."""

import json
import time
from pathlib import Path

HISTORY_DIR = Path.home() / ".local/share/aulinx/history"


class HistoryManager:
    """Manages conversation history persistence."""

    def __init__(self):
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self._session_file = HISTORY_DIR / f"{self.session_id}.json"

    def save(self, messages: list[dict]):
        """Save current conversation to disk."""
        try:
            data = {
                "session_id": self.session_id,
                "started_at": self.session_id,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "message_count": len(messages),
                "messages": messages,
            }
            self._session_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except OSError:
            pass

    def load_latest(self) -> list[dict] | None:
        """Load the most recent conversation session."""
        sessions = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
        if not sessions:
            return None

        try:
            data = json.loads(sessions[0].read_text())
            return data.get("messages", [])
        except (json.JSONDecodeError, OSError):
            return None

    def list_sessions(self, limit: int = 10) -> list[dict]:
        """List recent conversation sessions."""
        sessions = sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:limit]
        result = []
        for path in sessions:
            try:
                data = json.loads(path.read_text())
                # Get first user message as preview
                preview = ""
                for msg in data.get("messages", []):
                    if msg.get("role") == "user" and msg.get("content"):
                        preview = msg["content"][:80]
                        break
                result.append({
                    "session_id": data.get("session_id", path.stem),
                    "messages": data.get("message_count", 0),
                    "updated_at": data.get("updated_at", ""),
                    "preview": preview,
                })
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def load_session(self, session_id: str) -> list[dict] | None:
        """Load a specific session by ID."""
        path = HISTORY_DIR / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return data.get("messages", [])
        except (json.JSONDecodeError, OSError):
            return None
