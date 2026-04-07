"""Long-term memory tools — remember and recall across sessions."""

from aulinx.long_memory import LongMemory
from aulinx.tools.base import Tier, Tool

_memory = LongMemory()


async def remember(content: str, category: str = "general") -> dict:
    """Store something in long-term memory. Survives across sessions."""
    _memory.remember(content, category)
    return {"remembered": True, "category": category, "total_memories": _memory.count()}


async def recall(query: str, limit: int = 5) -> list[dict]:
    """Search long-term memory by keywords."""
    return _memory.recall(query, limit)


async def recall_recent(limit: int = 10) -> list[dict]:
    """Get the most recent memories."""
    return _memory.recall_recent(limit)


async def forget(keyword: str) -> dict:
    """Remove memories containing a keyword."""
    count = _memory.forget(keyword)
    return {"removed": count, "keyword": keyword}


async def memory_count() -> dict:
    """Count total long-term memory entries."""
    return {"count": _memory.count()}


TOOLS = [
    Tool(
        name="remember",
        description="Store a fact, preference, or pattern in long-term memory. Survives across sessions.",
        fn=remember,
        parameters={
            "content": "string (what to remember, e.g. 'User prefers dark mode')",
            "category": "string (optional: 'preference', 'fact', 'workflow', 'general')",
        },
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="recall",
        description="Search long-term memory by keywords. Use to retrieve past knowledge.",
        fn=recall,
        parameters={
            "query": "string (search terms)",
            "limit": "int (default 5)",
        },
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="recall_recent",
        description="Get the most recent long-term memories",
        fn=recall_recent,
        parameters={"limit": "int (default 10)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="forget",
        description="Remove memories containing a keyword",
        fn=forget,
        parameters={"keyword": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="memory_count",
        description="Count total entries in long-term memory",
        fn=memory_count,
        tier=Tier.OBSERVE,
    ),
]
