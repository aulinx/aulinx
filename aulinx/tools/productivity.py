"""Productivity tools — quick notes, to-do list, text snippets."""

import json
import time
from pathlib import Path

from aulinx.tools.base import Tier, Tool

_DATA_DIR = Path.home() / ".local/share/aulinx"
_NOTES_FILE = _DATA_DIR / "notes.json"
_TODOS_FILE = _DATA_DIR / "todos.json"
_SNIPPETS_FILE = _DATA_DIR / "snippets.json"


def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_json(path: Path, data: list):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# --- Notes ---

async def note_add(content: str, tag: str = "") -> dict:
    """Add a quick note."""
    notes = _load_json(_NOTES_FILE)
    note = {
        "id": len(notes) + 1,
        "content": content,
        "tag": tag,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    notes.append(note)
    _save_json(_NOTES_FILE, notes)
    return {"added": True, "id": note["id"]}


async def note_list(tag: str = "") -> list[dict]:
    """List all notes, optionally filtered by tag."""
    notes = _load_json(_NOTES_FILE)
    if tag:
        notes = [n for n in notes if n.get("tag", "").lower() == tag.lower()]
    return notes


async def note_delete(note_id: int) -> dict:
    """Delete a note by ID."""
    notes = _load_json(_NOTES_FILE)
    before = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    if len(notes) == before:
        return {"error": f"Note {note_id} not found"}
    _save_json(_NOTES_FILE, notes)
    return {"deleted": True, "id": note_id}


# --- To-Do ---

async def todo_add(task: str, priority: str = "normal") -> dict:
    """Add a to-do item."""
    todos = _load_json(_TODOS_FILE)
    todo = {
        "id": len(todos) + 1,
        "task": task,
        "priority": priority,
        "done": False,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    todos.append(todo)
    _save_json(_TODOS_FILE, todos)
    return {"added": True, "id": todo["id"]}


async def todo_list(show_done: bool = False) -> list[dict]:
    """List to-do items. By default hides completed items."""
    todos = _load_json(_TODOS_FILE)
    if not show_done:
        todos = [t for t in todos if not t.get("done")]
    return todos


async def todo_done(todo_id: int) -> dict:
    """Mark a to-do as done."""
    todos = _load_json(_TODOS_FILE)
    for t in todos:
        if t.get("id") == todo_id:
            t["done"] = True
            t["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save_json(_TODOS_FILE, todos)
            return {"done": True, "id": todo_id, "task": t["task"]}
    return {"error": f"Todo {todo_id} not found"}


# --- Snippets ---

async def snippet_save(name: str, content: str) -> dict:
    """Save a reusable text snippet."""
    snippets = _load_json(_SNIPPETS_FILE)
    # Update if exists
    for s in snippets:
        if s["name"] == name:
            s["content"] = content
            s["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save_json(_SNIPPETS_FILE, snippets)
            return {"saved": True, "name": name, "updated": True}

    snippets.append({
        "name": name,
        "content": content,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save_json(_SNIPPETS_FILE, snippets)
    return {"saved": True, "name": name}


async def snippet_get(name: str) -> dict:
    """Get a saved text snippet by name."""
    snippets = _load_json(_SNIPPETS_FILE)
    for s in snippets:
        if s["name"].lower() == name.lower():
            return s
    return {"error": f"Snippet '{name}' not found"}


async def snippet_list() -> list[dict]:
    """List all saved snippets."""
    snippets = _load_json(_SNIPPETS_FILE)
    return [{"name": s["name"], "preview": s["content"][:60]} for s in snippets]


TOOLS = [
    Tool(name="note_add", description="Add a quick note (with optional tag)", fn=note_add,
         parameters={"content": "string", "tag": "string (optional)"}, tier=Tier.LOW_RISK),
    Tool(name="note_list", description="List all notes, optionally filtered by tag", fn=note_list,
         parameters={"tag": "string (optional)"}, tier=Tier.OBSERVE),
    Tool(name="note_delete", description="Delete a note by ID", fn=note_delete,
         parameters={"note_id": "int"}, tier=Tier.DESTRUCTIVE),
    Tool(name="todo_add", description="Add a to-do item with priority (low/normal/high)", fn=todo_add,
         parameters={"task": "string", "priority": "low|normal|high (default: normal)"}, tier=Tier.LOW_RISK),
    Tool(name="todo_list", description="List to-do items (hides done by default)", fn=todo_list,
         parameters={"show_done": "bool (default false)"}, tier=Tier.OBSERVE),
    Tool(name="todo_done", description="Mark a to-do as completed", fn=todo_done,
         parameters={"todo_id": "int"}, tier=Tier.LOW_RISK),
    Tool(name="snippet_save", description="Save a reusable text snippet by name", fn=snippet_save,
         parameters={"name": "string", "content": "string"}, tier=Tier.LOW_RISK),
    Tool(name="snippet_get", description="Get a saved snippet by name", fn=snippet_get,
         parameters={"name": "string"}, tier=Tier.OBSERVE),
    Tool(name="snippet_list", description="List all saved text snippets", fn=snippet_list, tier=Tier.OBSERVE),
]
