"""ReAct-style structured planner for multi-step task execution.

Before blindly calling tools, the agent first generates a plan (3-8 steps),
then executes step-by-step with re-planning after each observation.
This prevents thrashing and improves task completion rates.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

PLANNING_PROMPT = """\
You are a planning module. Given the user's goal and current desktop state, \
output a numbered plan of 3-8 concrete steps to accomplish the goal.

Rules:
- Each step must be a single tool call or observation
- Be specific: name the exact tool and key arguments
- If you're unsure about the current state, make step 1 an observation (e.g., atspi_get_tree, window_list)
- Keep the plan SHORT — only steps that are actually needed
- Output ONLY the numbered plan, no other text

Format:
1. [tool_name] — description of what to do and why
2. [tool_name] — description
...

User's goal: {goal}

Available tools: {tools}

Current state:
{context}
"""

REPLAN_PROMPT = """\
You are re-evaluating your plan after step {step_num} completed.

Original goal: {goal}

Original plan:
{plan}

Steps completed so far:
{completed_steps}

Last step result:
{last_result}

Should you continue with the next planned step, or does the plan need adjustment?
If the goal is already achieved, say "DONE".
If the plan needs adjustment, output a revised remaining plan (numbered from {next_step}).
If the next step is still correct, say "CONTINUE".

Reply with exactly one of: DONE, CONTINUE, or a revised plan.
"""


class VerifyType(Enum):
    """Types of verification conditions for plan steps."""
    NONE = "none"              # no verification needed
    ELEMENT_VISIBLE = "element_visible"  # check if a UI element is visible
    FILE_EXISTS = "file_exists"          # check if a file exists
    OUTPUT_CONTAINS = "output_contains"  # check if output contains a string
    WINDOW_OPEN = "window_open"          # check if a window is open
    APP_RUNNING = "app_running"          # check if an app is running


@dataclass
class VerifyCondition:
    """A condition that must be true for a step to be considered successful."""
    type: VerifyType
    target: str  # what to check (element name, file path, output string, etc.)
    description: str = ""  # human-readable description


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    number: int
    tool: str
    description: str
    status: str = "pending"  # pending, running, done, failed, skipped
    result_summary: str = ""
    verify: VerifyCondition | None = None  # optional verification condition


@dataclass
class ExecutionPlan:
    """A structured plan for accomplishing a goal."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0

    @property
    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps)

    @property
    def next_step(self) -> PlanStep | None:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self, result_summary: str = ""):
        """Mark current step as done and advance."""
        if self.current_step < len(self.steps):
            step = self.steps[self.current_step]
            step.status = "done"
            step.result_summary = result_summary
            self.current_step += 1

    def fail_current(self, error: str = ""):
        """Mark current step as failed."""
        if self.current_step < len(self.steps):
            self.steps[self.current_step].status = "failed"
            self.steps[self.current_step].result_summary = error

    def format_completed(self) -> str:
        """Format completed steps for re-planning prompt."""
        lines = []
        for step in self.steps[:self.current_step]:
            status = "OK" if step.status == "done" else "FAILED"
            lines.append(f"{step.number}. [{status}] {step.tool} — {step.description}")
            if step.result_summary:
                lines.append(f"   Result: {step.result_summary[:200]}")
        return "\n".join(lines) or "(none)"

    def format_plan(self) -> str:
        """Format the full plan for display."""
        lines = []
        for step in self.steps:
            marker = {"pending": " ", "running": ">", "done": "x", "failed": "!", "skipped": "-"}
            lines.append(f"[{marker.get(step.status, ' ')}] {step.number}. [{step.tool}] {step.description}")
        return "\n".join(lines)


def parse_plan(text: str) -> list[PlanStep]:
    """Parse a numbered plan from LLM output into PlanStep objects."""
    steps = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match patterns like "1. [tool_name] — description" or "1. tool_name - description"
        match = re.match(r"(\d+)\.\s*\[?(\w+)\]?\s*[—\-–:]\s*(.*)", line)
        if match:
            num = int(match.group(1))
            tool = match.group(2)
            desc = match.group(3).strip()
            steps.append(PlanStep(number=num, tool=tool, description=desc))
    return steps


def build_planning_prompt(goal: str, tool_names: list[str], context: str) -> str:
    """Build the planning prompt for the LLM."""
    # Limit tool list to avoid blowing up the prompt
    tools_str = ", ".join(tool_names[:60])
    return PLANNING_PROMPT.format(
        goal=goal,
        tools=tools_str,
        context=context[:2000],
    )


def build_replan_prompt(
    plan: ExecutionPlan,
    last_result: str,
) -> str:
    """Build a re-planning prompt after a step completes."""
    return REPLAN_PROMPT.format(
        step_num=plan.current_step,
        goal=plan.goal,
        plan=plan.format_plan(),
        completed_steps=plan.format_completed(),
        last_result=last_result[:1000],
        next_step=plan.current_step + 1,
    )


def inject_plan_into_system(system_prompt: str, plan: ExecutionPlan) -> str:
    """Inject the current plan context into the system prompt.

    This guides the LLM to execute the next step rather than freestyle.
    """
    if plan.is_complete:
        return system_prompt

    step = plan.next_step
    plan_context = (
        f"\n\n--- EXECUTION PLAN ---\n"
        f"Goal: {plan.goal}\n"
        f"Current plan:\n{plan.format_plan()}\n\n"
        f"YOU ARE NOW ON STEP {step.number}: [{step.tool}] {step.description}\n"
        f"Execute this step by calling the appropriate tool. "
        f"Focus on THIS step only — do not skip ahead.\n"
        f"--- END PLAN ---"
    )
    return system_prompt + plan_context


# --- Task decomposition with verification ---

DECOMPOSITION_PROMPT = """\
You are a task decomposition module. Break down this complex goal into \
independent subtasks that can be verified separately.

For each subtask, specify:
- The tool to use
- What to do
- How to VERIFY success (one of: element_visible, file_exists, output_contains, window_open, app_running)
- What to check (the target for verification)

Format:
1. [tool_name] — description | verify: <type>(<target>)
2. [tool_name] — description | verify: <type>(<target>)

Example:
1. [app_launch] — open the file manager | verify: window_open(nautilus)
2. [file_write] — create test.txt | verify: file_exists(/home/user/test.txt)
3. [atspi_find_elements] — confirm file appears in list | verify: element_visible(test.txt)

Goal: {goal}

Available tools: {tools}

Current state:
{context}
"""


def parse_plan_with_verification(text: str) -> list[PlanStep]:
    """Parse a plan that includes verification conditions.

    Format: 1. [tool] — description | verify: type(target)
    """
    steps = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Split on verification marker
        verify = None
        main_part = line
        verify_match = re.search(r"\|\s*verify:\s*(\w+)\(([^)]*)\)", line)
        if verify_match:
            verify_type_str = verify_match.group(1)
            verify_target = verify_match.group(2).strip()
            main_part = line[:verify_match.start()].strip()
            try:
                verify_type = VerifyType(verify_type_str)
                verify = VerifyCondition(type=verify_type, target=verify_target)
            except ValueError:
                pass

        # Parse the main step
        match = re.match(r"(\d+)\.\s*\[?(\w+)\]?\s*[—\-–:]\s*(.*)", main_part)
        if match:
            num = int(match.group(1))
            tool = match.group(2)
            desc = match.group(3).strip()
            steps.append(PlanStep(number=num, tool=tool, description=desc, verify=verify))

    return steps


def build_decomposition_prompt(goal: str, tool_names: list[str], context: str) -> str:
    """Build a decomposition prompt that requests verification conditions."""
    tools_str = ", ".join(tool_names[:60])
    return DECOMPOSITION_PROMPT.format(
        goal=goal,
        tools=tools_str,
        context=context[:2000],
    )


def check_verification(verify: VerifyCondition, tool_result: dict | str) -> bool:
    """Check if a verification condition is met based on a tool result.

    This is a heuristic check — for more reliable verification,
    the agent should call a dedicated observation tool.
    """
    if verify.type == VerifyType.NONE:
        return True

    result_str = str(tool_result).lower() if tool_result else ""
    target_lower = verify.target.lower()

    if verify.type == VerifyType.OUTPUT_CONTAINS:
        return target_lower in result_str

    if verify.type == VerifyType.FILE_EXISTS:
        # Check if the result doesn't contain an error about the file
        return "error" not in result_str and "not found" not in result_str

    if verify.type in (VerifyType.ELEMENT_VISIBLE, VerifyType.WINDOW_OPEN, VerifyType.APP_RUNNING):
        # These need a follow-up observation — return True optimistically
        # The agent should call the appropriate tool to verify
        return target_lower in result_str or "error" not in result_str

    return True
