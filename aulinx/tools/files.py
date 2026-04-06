"""File operation tools — read, write, edit, search, trash."""

import shutil
import time
from pathlib import Path

from aulinx.tools.base import Tier, Tool

# XDG trash directories
_TRASH_FILES = Path.home() / ".local/share/Trash/files"
_TRASH_INFO = Path.home() / ".local/share/Trash/info"


async def file_read(path: str, limit: int = 100) -> str:
    """Read a file's content."""
    try:
        p = Path(path).expanduser().resolve()
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


async def file_write(path: str, content: str, append: bool = False) -> dict:
    """Write content to a file. Creates parent directories if needed."""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode) as f:
            f.write(content)
        return {"written": True, "path": str(p), "bytes": len(content.encode()), "append": append}
    except Exception as e:
        return {"error": f"Failed to write {path}: {e}"}


async def file_edit(path: str, old_string: str, new_string: str) -> dict:
    """Replace a specific string in a file. The old_string must be unique in the file."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            return {"error": f"Not a file: {path}"}

        text = p.read_text(errors="replace")
        count = text.count(old_string)

        if count == 0:
            return {"error": "old_string not found in file"}
        if count > 1:
            return {"error": f"old_string found {count} times — must be unique. Provide more context."}

        new_text = text.replace(old_string, new_string, 1)
        p.write_text(new_text)
        return {"edited": True, "path": str(p), "replacements": 1}
    except Exception as e:
        return {"error": f"Failed to edit {path}: {e}"}


async def file_move(source: str, destination: str) -> dict:
    """Move or rename a file or directory."""
    try:
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        if not src.exists():
            return {"error": f"Source not found: {source}"}
        if dst.exists():
            return {"error": f"Destination already exists: {destination}"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"moved": True, "from": str(src), "to": str(dst)}
    except Exception as e:
        return {"error": f"Failed to move: {e}"}


async def file_trash(path: str) -> dict:
    """Move a file to the XDG trash (recoverable delete)."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"error": f"Not found: {path}"}

        _TRASH_FILES.mkdir(parents=True, exist_ok=True)
        _TRASH_INFO.mkdir(parents=True, exist_ok=True)

        # Generate unique trash name
        trash_name = p.name
        dest = _TRASH_FILES / trash_name
        counter = 1
        while dest.exists():
            trash_name = f"{p.stem}.{counter}{p.suffix}"
            dest = _TRASH_FILES / trash_name
            counter += 1

        # Write .trashinfo
        info_path = _TRASH_INFO / f"{trash_name}.trashinfo"
        info_path.write_text(
            f"[Trash Info]\nPath={p}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        )

        shutil.move(str(p), str(dest))
        return {"trashed": True, "original": str(p), "restore_from": str(dest)}

    except Exception as e:
        return {"error": f"Failed to trash: {e}"}


async def file_list(path: str = ".", include_hidden: bool = False) -> list[dict]:
    """List directory contents."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            return [{"error": f"Not a directory: {path}"}]

        entries = []
        for item in sorted(p.iterdir()):
            if not include_hidden and item.name.startswith("."):
                continue
            try:
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": stat.st_size,
                })
            except PermissionError:
                entries.append({"name": item.name, "type": "?", "size": 0})
        return entries[:100]
    except Exception as e:
        return [{"error": str(e)}]


async def file_search(query: str, path: str = "~", max_results: int = 20) -> list[str]:
    """Search for files by name."""
    try:
        p = Path(path).expanduser().resolve()
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
        name="file_write",
        description="Write content to a file (creates parent dirs). Use append=true to append.",
        fn=file_write,
        parameters={"path": "string", "content": "string", "append": "bool (default false)"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="file_edit",
        description="Replace a unique string in a file (like find-and-replace). old_string must appear exactly once.",
        fn=file_edit,
        parameters={"path": "string", "old_string": "string", "new_string": "string"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="file_move",
        description="Move or rename a file/directory",
        fn=file_move,
        parameters={"source": "string", "destination": "string"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="file_trash",
        description="Move a file to trash (recoverable via XDG trash spec)",
        fn=file_trash,
        parameters={"path": "string"},
        tier=Tier.DESTRUCTIVE,
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
