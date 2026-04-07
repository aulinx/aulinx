"""Workflow automation tools — create, list, run, delete workflows."""

from aulinx.tools.base import Tier, Tool
from aulinx.workflows import (
    workflow_create,
    workflow_delete,
    workflow_list,
    workflow_run,
    workflow_toggle,
)

TOOLS = [
    Tool(
        name="workflow_create",
        description="Create an automated workflow. Trigger: 'manual', 'app:firefox', 'time:09:00'",
        fn=workflow_create,
        parameters={
            "name": "string (e.g. 'Morning Setup')",
            "description": "string (what the workflow does)",
            "trigger": "string ('manual', 'app:appname', 'time:HH:MM')",
            "steps": "list of {tool: string, args: dict} (e.g. [{tool: 'app_launch', args: {app: 'firefox'}}])",
        },
        tier=Tier.MUTATE,
    ),
    Tool(
        name="workflow_list",
        description="List all saved workflows with their triggers and run counts",
        fn=workflow_list,
        tier=Tier.OBSERVE,
    ),
    Tool(
        name="workflow_run",
        description="Run a workflow by its ID",
        fn=workflow_run,
        parameters={"workflow_id": "string (e.g. 'wf-1712345678')"},
        tier=Tier.MUTATE,
    ),
    Tool(
        name="workflow_delete",
        description="Delete a workflow by ID",
        fn=workflow_delete,
        parameters={"workflow_id": "string"},
        tier=Tier.DESTRUCTIVE,
    ),
    Tool(
        name="workflow_toggle",
        description="Enable or disable a workflow",
        fn=workflow_toggle,
        parameters={"workflow_id": "string"},
        tier=Tier.MUTATE,
    ),
]
