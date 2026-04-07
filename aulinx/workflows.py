"""Workflow automation — record, store, and replay multi-step tool sequences.

Workflows are triggered by context changes (app opened, wifi connected, time of day).
Stored in ~/.local/share/aulinx/workflows.json.
"""

import asyncio
import json
import time
from pathlib import Path

WORKFLOWS_DIR = Path.home() / ".local/share/aulinx"
WORKFLOWS_FILE = WORKFLOWS_DIR / "workflows.json"


def _load_workflows() -> list[dict]:
    if not WORKFLOWS_FILE.exists():
        return []
    try:
        return json.loads(WORKFLOWS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_workflows(workflows: list[dict]):
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOWS_FILE.write_text(json.dumps(workflows, indent=2, ensure_ascii=False))


async def workflow_create(
    name: str,
    description: str,
    trigger: str,
    steps: list[dict],
) -> dict:
    """Create a new workflow.

    trigger: "manual", "app:firefox" (when Firefox opens), "wifi:MyNetwork", "time:09:00"
    steps: list of {"tool": "tool_name", "args": {...}} dicts
    """
    workflows = _load_workflows()

    workflow = {
        "id": f"wf-{int(time.time())}",
        "name": name,
        "description": description,
        "trigger": trigger,
        "steps": steps,
        "enabled": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_run": None,
        "run_count": 0,
    }

    workflows.append(workflow)
    _save_workflows(workflows)

    return {"created": True, "workflow": workflow}


async def workflow_list() -> list[dict]:
    """List all workflows."""
    workflows = _load_workflows()
    return [
        {
            "id": w["id"],
            "name": w["name"],
            "trigger": w["trigger"],
            "steps": len(w["steps"]),
            "enabled": w["enabled"],
            "run_count": w.get("run_count", 0),
            "last_run": w.get("last_run"),
        }
        for w in workflows
    ]


async def workflow_run(workflow_id: str, tool_executor=None) -> dict:
    """Run a workflow by ID."""
    workflows = _load_workflows()

    target = None
    for w in workflows:
        if w["id"] == workflow_id:
            target = w
            break

    if not target:
        return {"error": f"Workflow '{workflow_id}' not found"}

    if not target.get("enabled"):
        return {"error": f"Workflow '{target['name']}' is disabled"}

    results = []
    for step in target["steps"]:
        tool_name = step.get("tool")
        args = step.get("args", {})

        if tool_executor:
            result = await tool_executor(tool_name, args)
            results.append({"tool": tool_name, "result": str(result)[:200]})
        else:
            results.append({"tool": tool_name, "args": args, "status": "skipped (no executor)"})

    # Update run stats
    target["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    target["run_count"] = target.get("run_count", 0) + 1
    _save_workflows(workflows)

    return {"ran": True, "workflow": target["name"], "results": results}


async def workflow_delete(workflow_id: str) -> dict:
    """Delete a workflow."""
    workflows = _load_workflows()
    before = len(workflows)
    workflows = [w for w in workflows if w["id"] != workflow_id]
    if len(workflows) == before:
        return {"error": f"Workflow '{workflow_id}' not found"}
    _save_workflows(workflows)
    return {"deleted": True}


async def workflow_toggle(workflow_id: str) -> dict:
    """Enable or disable a workflow."""
    workflows = _load_workflows()
    for w in workflows:
        if w["id"] == workflow_id:
            w["enabled"] = not w["enabled"]
            _save_workflows(workflows)
            return {"id": workflow_id, "enabled": w["enabled"]}
    return {"error": f"Workflow '{workflow_id}' not found"}


class WorkflowMonitor:
    """Monitors context and triggers workflows automatically."""

    def __init__(self, tool_executor=None):
        self.tool_executor = tool_executor
        self._running = False
        self._last_context: dict = {}

    async def start(self):
        """Start monitoring for workflow triggers."""
        self._running = True
        while self._running:
            try:
                await self._check_triggers()
            except Exception:
                pass
            await asyncio.sleep(10)

    async def stop(self):
        self._running = False

    async def _check_triggers(self):
        """Check if any workflow triggers match the current context."""
        from aulinx.context.desktop import DesktopContext

        ctx = DesktopContext()
        await ctx.initialize()
        snapshot_str = await ctx.snapshot()
        snapshot = json.loads(snapshot_str)

        workflows = _load_workflows()
        for wf in workflows:
            if not wf.get("enabled"):
                continue

            trigger = wf.get("trigger", "manual")
            if trigger == "manual":
                continue

            triggered = False

            if trigger.startswith("app:"):
                app_name = trigger[4:]
                running_apps = snapshot.get("running_apps", [])
                was_running = app_name in self._last_context.get("running_apps", [])
                is_running = app_name in running_apps
                if is_running and not was_running:
                    triggered = True

            elif trigger.startswith("time:"):
                target_time = trigger[5:]
                current_time = time.strftime("%H:%M")
                if current_time == target_time:
                    # Only trigger once per minute
                    last_run = wf.get("last_run", "")
                    if not last_run or last_run[:16] != time.strftime("%Y-%m-%dT%H:%M"):
                        triggered = True

            if triggered:
                await workflow_run(wf["id"], self.tool_executor)

        self._last_context = snapshot
