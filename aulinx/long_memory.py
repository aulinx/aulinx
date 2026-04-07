"""Long-term conversation memory — remembers across sessions using simple text search.

Stores conversation summaries, user preferences, and learned patterns.
Uses keyword-based search (no external dependencies like vector DBs).
"""

import json
import time
from pathlib import Path

MEMORY_DIR = Path.home() / ".local/share/aulinx"
LONG_MEMORY_FILE = MEMORY_DIR / "long_memory.jsonl"


class LongMemory:
    """Persistent memory that survives across sessions.

    Stores facts, preferences, and conversation summaries as searchable entries.
    """

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def remember(self, content: str, category: str = "general", source: str = "agent"):
        """Store a memory entry."""
        entry = {
            "content": content,
            "category": category,
            "source": source,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "keywords": _extract_keywords(content),
        }
        with open(LONG_MEMORY_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Search memories by keyword relevance."""
        if not LONG_MEMORY_FILE.exists():
            return []

        query_keywords = _extract_keywords(query)
        if not query_keywords:
            return []

        scored = []
        for line in LONG_MEMORY_FILE.read_text().strip().splitlines():
            try:
                entry = json.loads(line)
                entry_keywords = set(entry.get("keywords", []))
                # Score by keyword overlap
                overlap = len(query_keywords & entry_keywords)
                if overlap > 0:
                    scored.append((overlap, entry))
            except json.JSONDecodeError:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def recall_recent(self, limit: int = 10) -> list[dict]:
        """Get the most recent memories."""
        if not LONG_MEMORY_FILE.exists():
            return []

        entries = []
        for line in LONG_MEMORY_FILE.read_text().strip().splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return entries[-limit:]

    def forget(self, keyword: str) -> int:
        """Remove memories containing a keyword. Returns count of removed entries."""
        if not LONG_MEMORY_FILE.exists():
            return 0

        lines = LONG_MEMORY_FILE.read_text().strip().splitlines()
        kept = []
        removed = 0
        for line in lines:
            try:
                entry = json.loads(line)
                if keyword.lower() in entry.get("content", "").lower():
                    removed += 1
                else:
                    kept.append(line)
            except json.JSONDecodeError:
                kept.append(line)

        LONG_MEMORY_FILE.write_text("\n".join(kept) + "\n" if kept else "")
        return removed

    def summarize_for_context(self, query: str = "", max_tokens: int = 500) -> str:
        """Get a brief context string of relevant memories for the LLM system prompt."""
        if query:
            memories = self.recall(query, limit=3)
        else:
            memories = self.recall_recent(limit=3)

        if not memories:
            return ""

        parts = ["Relevant memories:"]
        total_len = 0
        for m in memories:
            text = f"- [{m.get('category', 'general')}] {m['content']}"
            if total_len + len(text) > max_tokens * 4:  # rough char-to-token
                break
            parts.append(text)
            total_len += len(text)

        return "\n".join(parts)

    def count(self) -> int:
        """Count total memory entries."""
        if not LONG_MEMORY_FILE.exists():
            return 0
        return len(LONG_MEMORY_FILE.read_text().strip().splitlines())


def _extract_keywords(text: str) -> set[str]:
    """Extract searchable keywords from text."""
    # Simple: split into words, lowercase, remove short/common words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "must", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "and", "or", "but", "not", "no", "nor", "so", "yet", "both",
        "this", "that", "these", "those", "it", "its", "i", "my", "me",
        "you", "your", "he", "she", "we", "they", "them", "their",
        "what", "which", "who", "when", "where", "how", "why",
    }
    words = set()
    for word in text.lower().split():
        # Strip punctuation
        cleaned = word.strip(".,!?;:'\"()-/\\[]{}#@$%^&*+=<>~`")
        if len(cleaned) > 2 and cleaned not in stop_words:
            words.add(cleaned)
    return words
