"""Tests for the multi-agent task delegation framework."""

from aulinx.multi_agent import (
    DelegationPlan,
    Subtask,
    SubtaskStatus,
    build_coordination_summary,
    parse_delegation_plan,
)


class TestParseDelegationPlan:
    def test_basic_plan(self):
        text = """1. Install Python packages | tools: shell_exec, packages_install
2. Configure git settings | tools: git_status, shell_exec
3. Set up VS Code | tools: app_launch, shell_exec"""
        plan = parse_delegation_plan(text, "set up dev env")
        assert len(plan.subtasks) == 3
        assert plan.subtasks[0].description == "Install Python packages"
        assert "shell_exec" in plan.subtasks[0].tools_hint
        assert plan.goal == "set up dev env"

    def test_no_tools_hint(self):
        text = "1. Do something\n2. Do another thing"
        plan = parse_delegation_plan(text, "goal")
        assert len(plan.subtasks) == 2
        assert plan.subtasks[0].tools_hint == []

    def test_single_subtask(self):
        text = "1. Just do it | tools: shell_exec"
        plan = parse_delegation_plan(text, "simple task")
        assert len(plan.subtasks) == 1

    def test_parse_failure_creates_single(self):
        text = "This is not a numbered plan at all."
        plan = parse_delegation_plan(text, "the goal")
        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].description == "the goal"

    def test_empty_text(self):
        plan = parse_delegation_plan("", "fallback goal")
        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].description == "fallback goal"


class TestDelegationPlan:
    def _make_plan(self):
        return DelegationPlan(
            goal="test",
            subtasks=[
                Subtask(id=1, description="task 1"),
                Subtask(id=2, description="task 2"),
            ],
        )

    def test_not_complete_initially(self):
        plan = self._make_plan()
        assert not plan.is_complete

    def test_complete_when_all_done(self):
        plan = self._make_plan()
        plan.subtasks[0].status = SubtaskStatus.COMPLETED
        plan.subtasks[1].status = SubtaskStatus.COMPLETED
        assert plan.is_complete
        assert plan.all_succeeded

    def test_complete_with_failures(self):
        plan = self._make_plan()
        plan.subtasks[0].status = SubtaskStatus.COMPLETED
        plan.subtasks[1].status = SubtaskStatus.FAILED
        assert plan.is_complete
        assert not plan.all_succeeded

    def test_summary(self):
        plan = self._make_plan()
        plan.subtasks[0].status = SubtaskStatus.COMPLETED
        plan.subtasks[0].duration_s = 2.5
        plan.subtasks[1].status = SubtaskStatus.FAILED
        plan.subtasks[1].error = "connection refused"
        summary = plan.summary()
        assert "COMPLETED" in summary
        assert "FAILED" in summary
        assert "2.5s" in summary
        assert "connection refused" in summary


class TestBuildCoordinationSummary:
    def test_all_succeeded(self):
        plan = DelegationPlan(
            goal="test goal",
            subtasks=[
                Subtask(id=1, description="task 1", status=SubtaskStatus.COMPLETED, result="done"),
                Subtask(id=2, description="task 2", status=SubtaskStatus.COMPLETED, result="done"),
            ],
        )
        summary = build_coordination_summary(plan)
        assert "All subtasks completed" in summary
        assert "test goal" in summary

    def test_with_failure(self):
        plan = DelegationPlan(
            goal="test",
            subtasks=[
                Subtask(id=1, description="ok task", status=SubtaskStatus.COMPLETED, result="ok"),
                Subtask(id=2, description="bad task", status=SubtaskStatus.FAILED, error="timeout"),
            ],
        )
        summary = build_coordination_summary(plan)
        assert "1 subtask(s) failed" in summary
        assert "timeout" in summary
