"""Multi-agent task delegation — decompose and parallelize complex tasks.

For complex goals, this module:
1. Analyzes the goal to identify independent subtasks
2. Spawns worker agents (separate LLM sessions) for each subtask
3. Coordinates execution and merges results

Example: "Set up a Python dev environment" decomposes into:
  - Worker 1: Install packages (python3, pip, venv)
  - Worker 2: Configure git (user, email, aliases)
  - Worker 3: Set up editor (install extensions, config)

Workers share the same tool registry but have independent conversation
histories and can run concurrently.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from aulinx.llm import LLMClient


class SubtaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Subtask:
    """A single subtask for a worker agent."""
    id: int
    description: str
    tools_hint: list[str] = field(default_factory=list)  # suggested tools
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: str = ""
    error: str = ""
    duration_s: float = 0.0


@dataclass
class DelegationPlan:
    """A plan for delegating work to multiple agents."""
    goal: str
    subtasks: list[Subtask] = field(default_factory=list)
    parallel: bool = True  # whether subtasks can run in parallel

    @property
    def is_complete(self) -> bool:
        return all(s.status in (SubtaskStatus.COMPLETED, SubtaskStatus.FAILED) for s in self.subtasks)

    @property
    def all_succeeded(self) -> bool:
        return all(s.status == SubtaskStatus.COMPLETED for s in self.subtasks)

    def summary(self) -> str:
        lines = [f"Goal: {self.goal}", f"Subtasks: {len(self.subtasks)}", ""]
        for st in self.subtasks:
            status = st.status.value.upper()
            line = f"  [{status}] {st.id}. {st.description}"
            if st.duration_s > 0:
                line += f" ({st.duration_s:.1f}s)"
            if st.error:
                line += f" — ERROR: {st.error[:100]}"
            lines.append(line)
        return "\n".join(lines)


DECOMPOSE_PROMPT = """\
You are a task coordinator. Break down this goal into 2-5 INDEPENDENT subtasks \
that can be worked on separately. Each subtask should be self-contained.

Rules:
- Only create subtasks that are truly independent (no dependencies between them)
- Each subtask should be completable with a few tool calls
- If the task is simple (1-2 steps), output just 1 subtask
- Include suggested tools for each subtask

Format (output ONLY this, no other text):
1. Description of subtask | tools: tool1, tool2
2. Description of subtask | tools: tool3, tool4

Goal: {goal}

Available tools: {tools}
"""


def parse_delegation_plan(text: str, goal: str) -> DelegationPlan:
    """Parse LLM output into a DelegationPlan."""
    import re

    subtasks = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Parse: "1. Description | tools: tool1, tool2"
        match = re.match(r"(\d+)\.\s*(.*?)(?:\|\s*tools?:\s*(.*))?$", line)
        if match:
            num = int(match.group(1))
            desc = match.group(2).strip().rstrip("|").strip()
            tools_str = match.group(3) or ""
            tools = [t.strip() for t in tools_str.split(",") if t.strip()]
            subtasks.append(Subtask(id=num, description=desc, tools_hint=tools))

    # If parsing failed, create a single subtask with the full goal
    if not subtasks:
        subtasks = [Subtask(id=1, description=goal)]

    return DelegationPlan(goal=goal, subtasks=subtasks)


async def decompose_task(
    goal: str,
    llm: LLMClient,
    tool_names: list[str],
) -> DelegationPlan:
    """Use the LLM to decompose a complex task into subtasks."""
    tools_str = ", ".join(tool_names[:60])
    prompt = DECOMPOSE_PROMPT.format(goal=goal, tools=tools_str)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": goal},
    ]

    response_text = ""
    async for event in llm.chat_with_tools(messages, []):
        if event.type == "token":
            response_text += event.data.get("content", "")
        elif event.type == "done":
            response_text = event.data.get("content", response_text)

    return parse_delegation_plan(response_text, goal)


async def execute_subtask(
    subtask: Subtask,
    llm: LLMClient,
    tools_registry,
    system_prompt: str = "",
) -> Subtask:
    """Execute a single subtask using a worker agent.

    Creates an independent LLM session for the subtask.
    """
    subtask.status = SubtaskStatus.RUNNING
    t0 = time.monotonic()

    worker_prompt = (
        f"{system_prompt}\n\n"
        f"You are a worker agent assigned to ONE specific subtask. "
        f"Complete this subtask and report the result:\n\n"
        f"Subtask: {subtask.description}\n"
    )
    if subtask.tools_hint:
        worker_prompt += f"Suggested tools: {', '.join(subtask.tools_hint)}\n"

    messages = [
        {"role": "system", "content": worker_prompt},
        {"role": "user", "content": subtask.description},
    ]

    tools = tools_registry.to_ollama_tools()

    try:
        full_content = ""
        tool_calls = None

        async for event in llm.chat_with_tools(messages, tools):
            if event.type == "done":
                full_content = event.data.get("content", "")
                tool_calls = event.data.get("tool_calls")

        if tool_calls:
            # Execute the tool calls
            results = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if name and name in tools_registry:
                    result = await tools_registry.execute(name, args)
                    results.append(f"{name}: {str(result)[:200]}")

            subtask.result = "; ".join(results) if results else full_content
        else:
            subtask.result = full_content

        subtask.status = SubtaskStatus.COMPLETED

    except Exception as e:
        subtask.status = SubtaskStatus.FAILED
        subtask.error = str(e)

    subtask.duration_s = round(time.monotonic() - t0, 1)
    return subtask


async def execute_delegation_plan(
    plan: DelegationPlan,
    llm: LLMClient,
    tools_registry,
    system_prompt: str = "",
) -> DelegationPlan:
    """Execute all subtasks in a delegation plan.

    If plan.parallel is True, runs subtasks concurrently.
    Otherwise, runs sequentially.
    """
    if plan.parallel and len(plan.subtasks) > 1:
        # Run all subtasks concurrently
        tasks = [
            execute_subtask(st, llm, tools_registry, system_prompt)
            for st in plan.subtasks
        ]
        await asyncio.gather(*tasks)
    else:
        # Run sequentially
        for st in plan.subtasks:
            await execute_subtask(st, llm, tools_registry, system_prompt)

    return plan


def build_coordination_summary(plan: DelegationPlan) -> str:
    """Build a summary of the delegation results for the coordinator.

    This summary is injected into the main agent's context so it can
    report the combined results to the user.
    """
    parts = [f"## Multi-agent results for: {plan.goal}\n"]

    for st in plan.subtasks:
        status_emoji = "OK" if st.status == SubtaskStatus.COMPLETED else "FAILED"
        parts.append(f"### Subtask {st.id} [{status_emoji}]: {st.description}")
        if st.result:
            parts.append(f"Result: {st.result[:300]}")
        if st.error:
            parts.append(f"Error: {st.error[:200]}")
        parts.append("")

    if plan.all_succeeded:
        parts.append("All subtasks completed successfully.")
    else:
        failed = [st for st in plan.subtasks if st.status == SubtaskStatus.FAILED]
        parts.append(f"{len(failed)} subtask(s) failed. Review errors above.")

    return "\n".join(parts)
