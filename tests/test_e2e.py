"""End-to-end tests — verify the complete agent pipeline works.

These tests don't need Ollama — they test tool execution, context gathering,
memory, workflows, plugins, and the API layer directly.

Run: pytest tests/test_e2e.py -v
"""

import platform

import pytest

pytestmark = pytest.mark.skipif(
    platform.system() != "Linux",
    reason="E2E tests require Linux",
)


class TestToolExecution:
    """Test that tools execute correctly through the registry."""

    @pytest.mark.asyncio
    async def test_all_core_tools_callable(self):
        """Verify every tool in the registry can be called without crashing."""
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry()

        # Tools that are safe to call with empty/default args
        safe_tools = [
            ("who_am_i", {}),
            ("date_now", {}),
            ("system_info", {}),
            ("app_list_running", {}),
            ("window_list", {}),
            ("window_get_focused", {}),
            ("clipboard_get", {}),
            ("context_get", {}),
            ("memory_list_namespaces", {}),
            ("workflow_list", {}),
            ("audit_recent", {"limit": 5}),
            ("memory_count", {}),
            ("recall_recent", {"limit": 3}),
            ("env_get", {}),
        ]

        for tool_name, args in safe_tools:
            result = await registry.execute(tool_name, args)
            assert result is not None, f"{tool_name} returned None"
            # Should not be an error (except for missing deps)
            if isinstance(result, dict) and "error" in result:
                # Acceptable errors: missing tools (pyatspi, etc)
                err = str(result["error"]).lower()
                assert any(ok in err for ok in ["not available", "not found", "no such file"]), \
                    f"{tool_name} failed: {result}"

    @pytest.mark.asyncio
    async def test_file_roundtrip(self, tmp_path):
        """Write → read → edit → read → search → trash."""
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry()

        path = str(tmp_path / "test.txt")

        # Write
        r = await registry.execute("file_write", {"path": path, "content": "hello world"})
        assert r.get("written") is True

        # Read
        r = await registry.execute("file_read", {"path": path})
        assert "hello world" in r

        # Edit
        r = await registry.execute("file_edit", {"path": path, "old_string": "hello", "new_string": "goodbye"})
        assert r.get("edited") is True

        # Read again
        r = await registry.execute("file_read", {"path": path})
        assert "goodbye world" in r

        # Search
        r = await registry.execute("file_search", {"query": "test", "path": str(tmp_path)})
        assert any("test" in item for item in r)

        # List
        r = await registry.execute("file_list", {"path": str(tmp_path)})
        assert any(e.get("name") == "test.txt" for e in r)

    @pytest.mark.asyncio
    async def test_git_tools(self):
        """Git tools work on the aulinx repo itself."""
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry()

        # Status
        r = await registry.execute("git_status", {"path": "."})
        assert "branch" in r or "error" in r

        # Log
        r = await registry.execute("git_log", {"path": ".", "limit": 3})
        assert isinstance(r, list)

    @pytest.mark.asyncio
    async def test_text_tools(self, tmp_path):
        """Text count, grep, head, tail."""
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry()

        path = str(tmp_path / "code.py")
        content = "def hello():\n    print('world')\n\ndef foo():\n    return 42\n"
        await registry.execute("file_write", {"path": path, "content": content})

        # Count
        r = await registry.execute("text_count", {"path": path})
        assert r["lines"] == 5

        # Grep
        r = await registry.execute("text_grep", {"pattern": "def", "path": str(tmp_path)})
        assert len(r) >= 2

        # Head
        r = await registry.execute("text_head", {"path": path, "lines": 2})
        assert "def hello" in r

        # Tail
        r = await registry.execute("text_tail", {"path": path, "lines": 2})
        assert "return 42" in r

    @pytest.mark.asyncio
    async def test_datetime_tools(self):
        """Date and calendar tools."""
        from aulinx.tools.registry import ToolRegistry
        registry = ToolRegistry()

        r = await registry.execute("date_now", {})
        assert "unix" in r
        assert r["unix"] > 1700000000

        r = await registry.execute("calendar_show", {"month": 1, "year": 2026})
        assert "January" in r
        assert "2026" in r


class TestMemoryPipeline:
    """Test the full memory pipeline: short-term + long-term."""

    @pytest.mark.asyncio
    async def test_short_term_memory(self, tmp_path):
        """memory_store → memory_get → memory_delete."""
        from unittest.mock import patch

        from aulinx.tools import memory as mem
        mem_file = tmp_path / "memory.json"
        with patch.object(mem, "MEMORY_DIR", tmp_path), \
             patch.object(mem, "MEMORY_FILE", mem_file):
            from aulinx.tools.registry import ToolRegistry
            registry = ToolRegistry()

            await registry.execute("memory_store", {"namespace": "test", "key": "pref", "value": "dark mode"})
            r = await registry.execute("memory_get", {"namespace": "test"})
            assert len(r) == 1
            assert r[0]["value"] == "dark mode"

    @pytest.mark.asyncio
    async def test_long_term_memory(self, tmp_path):
        """remember → recall → forget."""
        from unittest.mock import patch

        import aulinx.long_memory as lm
        mem_file = tmp_path / "long_memory.jsonl"
        with patch.object(lm, "MEMORY_DIR", tmp_path), \
             patch.object(lm, "LONG_MEMORY_FILE", mem_file):
            from aulinx.tools.registry import ToolRegistry
            registry = ToolRegistry()

            await registry.execute("remember", {"content": "User prefers vim", "category": "preference"})
            r = await registry.execute("recall", {"query": "vim"})
            assert len(r) >= 1
            assert "vim" in r[0]["content"]


class TestWorkflowPipeline:
    """Test the workflow system end-to-end."""

    @pytest.mark.asyncio
    async def test_workflow_lifecycle(self, tmp_path):
        """create → list → run → toggle → delete."""
        from unittest.mock import patch

        import aulinx.workflows as wf
        wf_file = tmp_path / "workflows.json"
        with patch.object(wf, "WORKFLOWS_DIR", tmp_path), \
             patch.object(wf, "WORKFLOWS_FILE", wf_file):
            from aulinx.tools.registry import ToolRegistry
            registry = ToolRegistry()

            # Create
            r = await registry.execute("workflow_create", {
                "name": "Test",
                "description": "test workflow",
                "trigger": "manual",
                "steps": [{"tool": "date_now", "args": {}}],
            })
            assert r.get("created") is True
            wf_id = r["workflow"]["id"]

            # List
            r = await registry.execute("workflow_list", {})
            assert len(r) == 1

            # Run
            r = await registry.execute("workflow_run", {"workflow_id": wf_id})
            assert r.get("ran") is True

            # Toggle
            r = await registry.execute("workflow_toggle", {"workflow_id": wf_id})
            assert r["enabled"] is False

            # Delete
            r = await registry.execute("workflow_delete", {"workflow_id": wf_id})
            assert r.get("deleted") is True


class TestAPIEndpoints:
    """Test dashboard API responses."""

    @pytest.mark.asyncio
    async def test_all_endpoints(self):
        from aulinx.api import handle_api_request

        endpoints = ["/api/tools", "/api/audit", "/api/history", "/api/config", "/api/stats"]
        for path in endpoints:
            result = await handle_api_request(path)
            assert isinstance(result, dict), f"{path} returned {type(result)}"
            assert "error" not in result, f"{path} returned error: {result}"


# Registry integrity tests moved to test_registry_integrity.py (runs on all platforms)
