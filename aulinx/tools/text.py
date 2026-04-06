"""Text processing tools — count, search, transform."""

import re
from pathlib import Path

from aulinx.tools.base import Tier, Tool


async def text_count(text: str = "", path: str = "") -> dict:
    """Count words, lines, and characters in text or a file."""
    if path:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            return {"error": f"File not found: {path}"}
        text = p.read_text(errors="replace")

    if not text:
        return {"error": "Provide text or path"}

    lines = text.splitlines()
    words = text.split()
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
        "bytes": len(text.encode("utf-8")),
    }


async def text_grep(
    pattern: str, path: str, max_results: int = 30, ignore_case: bool = True
) -> list[dict]:
    """Search for a pattern in a file or directory (like grep)."""
    p = Path(path).expanduser().resolve()

    if not p.exists():
        return [{"error": f"Path not found: {path}"}]

    flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return [{"error": f"Invalid regex: {e}"}]

    results = []

    if p.is_file():
        _grep_file(p, compiled, results, max_results)
    elif p.is_dir():
        for fp in sorted(p.rglob("*")):
            if fp.is_file() and fp.stat().st_size < 1_000_000:  # skip files > 1MB
                _grep_file(fp, compiled, results, max_results)
                if len(results) >= max_results:
                    break

    return results


def _grep_file(path: Path, pattern: re.Pattern, results: list, max_results: int):
    """Search a single file for pattern matches."""
    try:
        text = path.read_text(errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                results.append({
                    "file": str(path),
                    "line": i,
                    "text": line.strip()[:200],
                })
                if len(results) >= max_results:
                    return
    except (PermissionError, OSError):
        pass


async def text_replace(
    path: str, pattern: str, replacement: str, regex: bool = False
) -> dict:
    """Find and replace text in a file. Supports plain text or regex."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}

    text = p.read_text(errors="replace")

    if regex:
        try:
            new_text, count = re.subn(pattern, replacement, text)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}
    else:
        count = text.count(pattern)
        new_text = text.replace(pattern, replacement)

    if count == 0:
        return {"error": "Pattern not found in file", "path": str(p)}

    p.write_text(new_text)
    return {"replaced": count, "path": str(p)}


async def text_head(path: str, lines: int = 20) -> str:
    """Read the first N lines of a file."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    result = "\n".join(text.splitlines()[:lines])
    return result


async def text_tail(path: str, lines: int = 20) -> str:
    """Read the last N lines of a file."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    result = "\n".join(text.splitlines()[-lines:])
    return result


TOOLS = [
    Tool(
        name="text_count",
        description="Count words, lines, characters in text or a file",
        fn=text_count,
        parameters={"text": "string (optional)", "path": "string (optional, file to count)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="text_grep",
        description="Search for a regex pattern in a file or directory (like grep -rn)",
        fn=text_grep,
        parameters={
            "pattern": "string (regex)",
            "path": "string (file or directory)",
            "max_results": "int (default 30)",
            "ignore_case": "bool (default true)",
        },
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="text_replace",
        description="Find and replace text in a file. Set regex=true for regex patterns.",
        fn=text_replace,
        parameters={
            "path": "string",
            "pattern": "string",
            "replacement": "string",
            "regex": "bool (default false)",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="text_head",
        description="Read the first N lines of a file",
        fn=text_head,
        parameters={"path": "string", "lines": "int (default 20)"},
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="text_tail",
        description="Read the last N lines of a file (like tail)",
        fn=text_tail,
        parameters={"path": "string", "lines": "int (default 20)"},
        tier=Tier.OBSERVE,
    ),
]
