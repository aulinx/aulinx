"""File operation tools."""

import os
from pathlib import Path
from aulinx.tools.registry import Tool, Tier


async def file_read(path: str, limit: int = 100) -> str:
    """Read a file's content."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        if not p.is_file():
            return f"Not a file: {path}"
        text = p.read_text(errors="replace")
        lines = text.splitlines()
        if len(lines) > limit:
            return "\n".join(lines[:limit]) + f"\n... ({len(lines) - limit} more lines)"
        return text
    except Exception as e:
        return f"Error reading {path}: {e}"


async def file_list(path: str = ".", include_hidden: bool = False) -> list[dict]:
    """List directory contents."""
    try:
        p = Path(path).expanduser()
        if not p.is_dir():
            return [{"error": f"Not a directory: {path}"}]

        entries = []
        for item in sorted(p.iterdir()):
            if not include_hidden and item.name.startswith("."):
                continue
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size,
            })
        return entries[:100]
    except Exception as e:
        return [{"error": str(e)}]


async def file_search(query: str, path: str = "~", max_results: int = 20) -> list[str]:
    """Search for files by name."""
    try:
        p = Path(path).expanduser()
        results = []
        for item in p.rglob(f"*{query}*"):
            results.append(str(item))
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        return [f"Error: {e}"]


TOOLS = [
    Tool(
        name="file_read",
        description="Read a file's content",
        fn=file_read,
        parameters={"path": "string", "limit": "int (max lines, default 100)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="file_list",
        description="List directory contents",
        fn=file_list,
        parameters={"path": "string (default: current dir)", "include_hidden": "bool"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="file_search",
        description="Search for files by name pattern",
        fn=file_search,
        parameters={"query": "string", "path": "string (default: home)", "max_results": "int"},
        tier=Tier.OBSERVE,
    ),
]
