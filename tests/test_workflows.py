"""Tests for workflow automation."""

from unittest.mock import patch

import pytest

from aulinx.workflows import (
    workflow_create,
    workflow_delete,
    workflow_list,
    workflow_run,
    workflow_toggle,
)


@pytest.fixture(autouse=True)
def temp_workflows(tmp_path):
    import aulinx.workflows as wf
    wf_file = tmp_path / "workflows.json"
    with patch.object(wf, "WORKFLOWS_DIR", tmp_path), \
         patch.object(wf, "WORKFLOWS_FILE", wf_file):
        yield wf_file


class TestWorkflowCRUD:
    @pytest.mark.asyncio
    async def test_create_and_list(self):
        result = await workflow_create(
            name="Test Flow",
            description="A test workflow",
            trigger="manual",
            steps=[{"tool": "date_now", "args": {}}],
        )
        assert result["created"] is True
        assert "id" in result["workflow"]

        workflows = await workflow_list()
        assert len(workflows) == 1
        assert workflows[0]["name"] == "Test Flow"
        assert workflows[0]["steps"] == 1

    @pytest.mark.asyncio
    async def test_delete(self):
        result = await workflow_create(
            name="To Delete", description="", trigger="manual", steps=[],
        )
        wf_id = result["workflow"]["id"]

        delete_result = await workflow_delete(wf_id)
        assert delete_result["deleted"] is True

        workflows = await workflow_list()
        assert len(workflows) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        result = await workflow_delete("fake-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_toggle(self):
        result = await workflow_create(
            name="Toggleable", description="", trigger="manual", steps=[],
        )
        wf_id = result["workflow"]["id"]

        toggle = await workflow_toggle(wf_id)
        assert toggle["enabled"] is False

        toggle2 = await workflow_toggle(wf_id)
        assert toggle2["enabled"] is True

    @pytest.mark.asyncio
    async def test_run_without_executor(self):
        result = await workflow_create(
            name="Runnable", description="", trigger="manual",
            steps=[{"tool": "date_now", "args": {}}],
        )
        wf_id = result["workflow"]["id"]

        run_result = await workflow_run(wf_id)
        assert run_result["ran"] is True
        assert len(run_result["results"]) == 1

    @pytest.mark.asyncio
    async def test_run_nonexistent(self):
        result = await workflow_run("fake-id")
        assert "error" in result
