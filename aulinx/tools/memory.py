"""Workflow memory — persistent key-value store across sessions."""

import json
import time
from pathlib import Path
from aulinx.tools.registry import Tool, Tier

MEMORY_DIR = Path.home() / ".local/share/aulinx"
MEMORY_FILE = MEMORY_DIR / "memory.json"


def _load_memory() -> dict:
    """Load memory from disk."""
    if not MEMORY_FILE.exists():
        return {}
    try:
        data = json.loads(MEMORY_FILE.read_text())
        # Prune expired entries
        now = time.time()
        pruned = {}
        for ns, entries in data.items():
            pruned[ns] = {}
            for key, entry in entries.items():
                expires = entry.get("expires_at")
                if expires and expires < now:
                    continue
                pruned[ns][key] = entry
            if not pruned[ns]:
                del pruned[ns]
        return pruned
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_memory(data: dict):
    """Save memory to disk."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


async def memory_store(namespace: str, key: str, value: str, ttl_hours: float = 0) -> dict:
    """Store a value in persistent memory. Use namespaces to organize (e.g., 'project/aulinx', 'preferences')."""
    data = _load_memory()

    if namespace not in data:
        data[namespace] = {}

    previous = data[namespace].get(key, {}).get("value")

    entry = {
        "value": value,
        "stored_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if ttl_hours > 0:
        entry["expires_at"] = time.time() + (ttl_hours * 3600)

    data[namespace][key] = entry
    _save_memory(data)

    result = {"stored": True, "namespace": namespace, "key": key}
    if previous is not None:
        result["previous_value"] = previous
    return result


async def memory_get(namespace: str = "", key: str = "", search: str = "") -> list[dict]:
    """Retrieve from persistent memory. Filter by namespace, key, or search across all values."""
    data = _load_memory()
    results = []

    for ns, entries in data.items():
        if namespace and namespace.lower() not in ns.lower():
            continue
        for k, entry in entries.items():
            if key and key.lower() not in k.lower():
                continue
            if search and search.lower() not in f"{k} {entry.get('value', '')}".lower():
                continue
            results.append({
                "namespace": ns,
                "key": k,
                "value": entry.get("value"),
                "stored_at": entry.get("stored_at"),
                "expires_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(entry["expires_at"])
                ) if "expires_at" in entry else None,
            })

    return results[:50]


async def memory_delete(namespace: str, key: str) -> dict:
    """Delete a specific memory entry."""
    data = _load_memory()

    if namespace not in data or key not in data[namespace]:
        return {"error": f"Not found: {namespace}/{key}"}

    deleted_value = data[namespace][key].get("value")
    del data[namespace][key]
    if not data[namespace]:
        del data[namespace]

    _save_memory(data)
    return {"deleted": True, "namespace": namespace, "key": key, "value": deleted_value}


async def memory_list_namespaces() -> list[dict]:
    """List all memory namespaces and their entry counts."""
    data = _load_memory()
    return [
        {"namespace": ns, "entries": len(entries)}
        for ns, entries in sorted(data.items())
    ]


TOOLS = [
    Tool(
        name="memory_store",
        description="Store a value in persistent memory (survives across sessions). Use namespaces like 'preferences', 'project/name', 'workflows'.",
        fn=memory_store,
        parameters={"namespace": "string", "key": "string", "value": "string", "ttl_hours": "float (0=permanent)"},
        tier=Tier.LOW_RISK,
    ),
    Tool(
        name="memory_get",
        description="Retrieve from persistent memory. Filter by namespace, key, or search all values.",
        fn=memory_get,
        parameters={"namespace": "string (optional)", "key": "string (optional)", "search": "string (optional)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="memory_delete",
        description="Delete a specific memory entry",
        fn=memory_delete,
        parameters={"namespace": "string", "key": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="memory_list_namespaces",
        description="List all memory namespaces and their entry counts",
        fn=memory_list_namespaces,
        tier=Tier.OBSERVE,
    ),
]
