"""Integration tests — run each tool and verify it returns valid output.

These tests work on any Linux system (WSL included). AT-SPI and desktop
tools are skipped if unavailable. Run with: pytest tests/test_tools_integration.py -v
"""

import os
import platform

import pytest

# Skip entire file on non-Linux
pytestmark = pytest.mark.skipif(
    platform.system() != "Linux",
    reason="Integration tests require Linux",
)


# --- Files ---

class TestFileTools:
    @pytest.mark.asyncio
    async def test_file_list_home(self):
        from aulinx.tools.files import file_list
        result = await file_list(os.path.expanduser("~"))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "name" in result[0]

    @pytest.mark.asyncio
    async def test_file_read_etc_hostname(self):
        from aulinx.tools.files import file_read
        result = await file_read("/etc/hostname")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_file_write_and_read(self, tmp_path):
        from aulinx.tools.files import file_write, file_read
        path = str(tmp_path / "test.txt")
        w = await file_write(path, "hello aulinx")
        assert w["written"] is True
        r = await file_read(path)
        assert "hello aulinx" in r

    @pytest.mark.asyncio
    async def test_file_edit(self, tmp_path):
        from aulinx.tools.files import file_write, file_edit, file_read
        path = str(tmp_path / "edit.txt")
        await file_write(path, "old text here")
        result = await file_edit(path, "old text", "new text")
        assert result["edited"] is True
        content = await file_read(path)
        assert "new text" in content

    @pytest.mark.asyncio
    async def test_file_search(self, tmp_path):
        from aulinx.tools.files import file_write, file_search
        await file_write(str(tmp_path / "findme.txt"), "data")
        result = await file_search("findme", str(tmp_path))
        assert any("findme" in r for r in result)

    @pytest.mark.asyncio
    async def test_file_trash(self, tmp_path):
        from aulinx.tools.files import file_write, file_trash
        path = str(tmp_path / "trashme.txt")
        await file_write(path, "goodbye")
        result = await file_trash(path)
        assert result.get("trashed") is True or "error" in result


# --- Text ---

class TestTextTools:
    @pytest.mark.asyncio
    async def test_text_count(self):
        from aulinx.tools.text import text_count
        result = await text_count(text="hello world\nline two")
        assert result["words"] == 4
        assert result["lines"] == 2

    @pytest.mark.asyncio
    async def test_text_grep(self, tmp_path):
        from aulinx.tools.files import file_write
        from aulinx.tools.text import text_grep
        await file_write(str(tmp_path / "code.py"), "async def hello():\n    pass\n")
        result = await text_grep("async def", str(tmp_path))
        assert len(result) > 0
        assert "hello" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_text_head_tail(self, tmp_path):
        from aulinx.tools.files import file_write
        from aulinx.tools.text import text_head, text_tail
        content = "\n".join(["line %d" % i for i in range(100)])
        path = str(tmp_path / "long.txt")
        await file_write(path, content)
        head = await text_head(path, lines=5)
        assert "line 0" in head
        assert "line 99" not in head
        tail = await text_tail(path, lines=5)
        assert "line 99" in tail
        assert "line 0" not in tail


# --- Git ---

class TestGitTools:
    @pytest.mark.asyncio
    async def test_git_status(self):
        from aulinx.tools.git import git_status
        result = await git_status("/mnt/e/Github/aulinx")
        assert "branch" in result or "error" in result

    @pytest.mark.asyncio
    async def test_git_log(self):
        from aulinx.tools.git import git_log
        result = await git_log("/mnt/e/Github/aulinx", limit=3)
        assert isinstance(result, list)
        if result and "error" not in result[0]:
            assert "message" in result[0]

    @pytest.mark.asyncio
    async def test_git_diff(self):
        from aulinx.tools.git import git_diff
        result = await git_diff("/mnt/e/Github/aulinx")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_git_branch(self):
        from aulinx.tools.git import git_branch
        result = await git_branch("/mnt/e/Github/aulinx")
        assert "branches" in result or "error" in result


# --- Process ---

class TestProcessTools:
    @pytest.mark.asyncio
    async def test_process_list(self):
        from aulinx.tools.process import process_list
        result = await process_list(limit=5)
        assert isinstance(result, list)
        if result and "error" not in result[0]:
            assert "pid" in result[0]
            assert "name" in result[0]

    @pytest.mark.asyncio
    async def test_process_list_by_memory(self):
        from aulinx.tools.process import process_list
        result = await process_list(sort_by="memory", limit=3)
        assert isinstance(result, list)


# --- Session ---

class TestSessionTools:
    @pytest.mark.asyncio
    async def test_who_am_i(self):
        from aulinx.tools.session import who_am_i
        result = await who_am_i()
        assert "user" in result
        assert "home" in result
        assert len(result["user"]) > 0

    @pytest.mark.asyncio
    async def test_uptime(self):
        from aulinx.tools.session import uptime
        result = await uptime()
        assert "uptime" in result or "uptime_seconds" in result

    @pytest.mark.asyncio
    async def test_disk_usage(self):
        from aulinx.tools.session import disk_usage
        result = await disk_usage()
        assert isinstance(result, list)
        if result and "error" not in result[0]:
            assert "mount" in result[0]

    @pytest.mark.asyncio
    async def test_env_get_path(self):
        from aulinx.tools.session import env_get
        result = await env_get("PATH")
        assert "value" in result
        assert len(result["value"]) > 0

    @pytest.mark.asyncio
    async def test_env_get_all(self):
        from aulinx.tools.session import env_get
        result = await env_get()
        assert "PATH" in result


# --- System ---

class TestSystemTools:
    @pytest.mark.asyncio
    async def test_system_info(self):
        from aulinx.tools.system import system_info
        result = await system_info()
        assert isinstance(result, dict)
        # At least one of these should be present on Linux
        assert "os" in result or "kernel" in result or "MemTotal" in result

    @pytest.mark.asyncio
    async def test_shell_exec_echo(self):
        from aulinx.tools.system import shell_exec
        result = await shell_exec("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_shell_exec_timeout(self):
        from aulinx.tools.system import shell_exec
        result = await shell_exec("sleep 60")
        assert "error" in result or result["exit_code"] != 0


# --- DateTime ---

class TestDateTimeTools:
    @pytest.mark.asyncio
    async def test_date_now(self):
        from aulinx.tools.datetime_tools import date_now
        result = await date_now()
        assert "local" in result
        assert "unix" in result
        assert result["unix"] > 1700000000

    @pytest.mark.asyncio
    async def test_date_convert_unix(self):
        from aulinx.tools.datetime_tools import date_convert
        result = await date_convert("1712419200", from_format="unix")
        assert "iso" in result
        assert "2024" in result["iso"]

    @pytest.mark.asyncio
    async def test_calendar_show(self):
        from aulinx.tools.datetime_tools import calendar_show
        result = await calendar_show(month=4, year=2026)
        assert "April" in result
        assert "2026" in result


# --- Memory ---

class TestMemoryToolsIntegration:
    @pytest.mark.asyncio
    async def test_full_memory_cycle(self, tmp_path):
        from unittest.mock import patch
        from aulinx.tools import memory as mem
        mem_file = tmp_path / "memory.json"
        with patch.object(mem, "MEMORY_DIR", tmp_path), \
             patch.object(mem, "MEMORY_FILE", mem_file):
            await mem.memory_store("test", "key1", "value1")
            result = await mem.memory_get(namespace="test")
            assert len(result) == 1
            assert result[0]["value"] == "value1"
            ns = await mem.memory_list_namespaces()
            assert any(n["namespace"] == "test" for n in ns)
            await mem.memory_delete("test", "key1")
            result = await mem.memory_get(namespace="test")
            assert len(result) == 0


# --- Packages ---

class TestPackageTools:
    @pytest.mark.asyncio
    async def test_package_list_installed(self):
        from aulinx.tools.packages import package_list_installed
        result = await package_list_installed("python3")
        assert isinstance(result, list)
        # On any Linux system, python3 should be installed
        assert len(result) > 0 or result == ["No supported package manager found"]


# --- Services ---

class TestServiceTools:
    @pytest.mark.asyncio
    async def test_service_list(self):
        from aulinx.tools.services import service_list
        result = await service_list()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_service_status(self):
        from aulinx.tools.services import service_status
        result = await service_status("ssh")
        assert isinstance(result, dict)
        # ssh may or may not be running, but shouldn't crash


# --- Timer ---

class TestTimerTools:
    @pytest.mark.asyncio
    async def test_set_and_list_timer(self):
        from aulinx.tools.timer import set_timer, list_timers, cancel_timer
        result = await set_timer(seconds=300, message="test timer")
        assert "timer_id" in result
        tid = result["timer_id"]

        timers = await list_timers()
        assert any(t["timer_id"] == tid for t in timers)

        cancel = await cancel_timer(tid)
        assert cancel["cancelled"] is True


# --- XDG ---

class TestXDGTools:
    @pytest.mark.asyncio
    async def test_mime_type_of(self):
        from aulinx.tools.xdg import mime_type_of
        result = await mime_type_of("/etc/hostname")
        assert "mime_type" in result or "error" in result


# --- Clipboard (may fail without display) ---

class TestClipboardTools:
    @pytest.mark.asyncio
    async def test_clipboard_get(self):
        from aulinx.tools.clipboard import clipboard_get
        result = await clipboard_get()
        # May return error without clipboard tool, but shouldn't crash
        assert isinstance(result, dict)


# --- Workflow ---

class TestWorkflowTools:
    @pytest.mark.asyncio
    async def test_context_get(self):
        from aulinx.tools.workflow import context_get
        result = await context_get()
        assert isinstance(result, dict)
        assert "time" in result

    @pytest.mark.asyncio
    async def test_wait(self):
        import time
        from aulinx.tools.workflow import wait
        t0 = time.monotonic()
        result = await wait(seconds=0.5, reason="test")
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.4
        assert result["waited"] == 0.5
