"""Tests for the ReAct-style planner module."""

from aulinx.planner import (
    ExecutionPlan,
    PlanStep,
    build_planning_prompt,
    inject_plan_into_system,
    parse_plan,
)


class TestParsePlan:
    def test_basic_plan(self):
        text = """1. [window_list] — check what windows are open
2. [app_launch] — launch the file manager
3. [file_write] — create the new file"""
        steps = parse_plan(text)
        assert len(steps) == 3
        assert steps[0].tool == "window_list"
        assert steps[1].tool == "app_launch"
        assert steps[2].tool == "file_write"

    def test_plan_with_dashes(self):
        text = """1. window_list - check windows
2. app_launch - launch app"""
        steps = parse_plan(text)
        assert len(steps) == 2
        assert steps[0].tool == "window_list"

    def test_plan_with_brackets(self):
        text = """1. [atspi_get_tree] — read UI tree
2. [atspi_do_action] — click button"""
        steps = parse_plan(text)
        assert len(steps) == 2

    def test_empty_text(self):
        assert parse_plan("") == []

    def test_non_plan_text(self):
        assert parse_plan("This is not a plan at all.") == []

    def test_plan_with_extra_text(self):
        text = """Here's my plan:
1. [file_read] — read the config
2. [file_write] — update the config
That should do it."""
        steps = parse_plan(text)
        assert len(steps) == 2


class TestExecutionPlan:
    def _make_plan(self):
        return ExecutionPlan(
            goal="test task",
            steps=[
                PlanStep(1, "window_list", "check windows"),
                PlanStep(2, "app_launch", "launch app"),
                PlanStep(3, "file_write", "write file"),
            ],
        )

    def test_initial_state(self):
        plan = self._make_plan()
        assert plan.current_step == 0
        assert not plan.is_complete
        assert plan.next_step.tool == "window_list"

    def test_advance(self):
        plan = self._make_plan()
        plan.advance("found 3 windows")
        assert plan.current_step == 1
        assert plan.next_step.tool == "app_launch"
        assert plan.steps[0].status == "done"
        assert plan.steps[0].result_summary == "found 3 windows"

    def test_complete(self):
        plan = self._make_plan()
        plan.advance()
        plan.advance()
        plan.advance()
        assert plan.is_complete
        assert plan.next_step is None

    def test_fail_current(self):
        plan = self._make_plan()
        plan.fail_current("connection error")
        assert plan.steps[0].status == "failed"
        assert plan.steps[0].result_summary == "connection error"

    def test_format_plan(self):
        plan = self._make_plan()
        plan.advance("ok")
        text = plan.format_plan()
        assert "[x]" in text  # completed
        assert "[ ]" in text  # pending

    def test_format_completed(self):
        plan = self._make_plan()
        assert plan.format_completed() == "(none)"
        plan.advance("ok")
        text = plan.format_completed()
        assert "OK" in text
        assert "window_list" in text


class TestBuildPlanningPrompt:
    def test_includes_goal(self):
        prompt = build_planning_prompt("open firefox", ["app_launch", "window_list"], "desktop context")
        assert "open firefox" in prompt

    def test_includes_tools(self):
        prompt = build_planning_prompt("test", ["app_launch", "window_list"], "ctx")
        assert "app_launch" in prompt
        assert "window_list" in prompt

    def test_includes_context(self):
        prompt = build_planning_prompt("test", ["tool1"], "my desktop state")
        assert "my desktop state" in prompt


class TestInjectPlanIntoSystem:
    def test_injects_plan(self):
        plan = ExecutionPlan(
            goal="test",
            steps=[PlanStep(1, "window_list", "check windows")],
        )
        result = inject_plan_into_system("base prompt", plan)
        assert "EXECUTION PLAN" in result
        assert "window_list" in result
        assert "base prompt" in result

    def test_no_inject_when_complete(self):
        plan = ExecutionPlan(goal="test", steps=[PlanStep(1, "tool", "desc")])
        plan.advance()
        result = inject_plan_into_system("base prompt", plan)
        assert result == "base prompt"
