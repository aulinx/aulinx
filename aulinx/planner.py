"""ReAct-style structured planner for multi-step task execution.

Before blindly calling tools, the agent first generates a plan (3-8 steps),
then executes step-by-step with re-planning after each observation.
This prevents thrashing and improves task completion rates.
"""

from dataclasses import dataclass, field

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


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    number: int
    tool: str
    description: str
    status: str = "pending"  # pending, running, done, failed, skipped
    result_summary: str = ""


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
        import re
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
