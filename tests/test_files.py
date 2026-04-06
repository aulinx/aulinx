"""Tests for file tools."""


import pytest

from aulinx.tools.files import file_edit, file_list, file_read, file_search, file_write


class TestFileRead:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\nline 2\n")
        result = await file_read(str(f))
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent(self):
        result = await file_read("/tmp/aulinx_nonexistent_xyz")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_with_limit(self, tmp_path):
        f = tmp_path / "long.txt"
        f.write_text("\n".join(f"line {i}" for i in range(200)))
        result = await file_read(str(f), limit=10)
        assert "more lines" in result


class TestFileWrite:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path):
        path = tmp_path / "new.txt"
        result = await file_write(str(path), "hello")
        assert result["written"] is True
        assert path.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_creates_parents(self, tmp_path):
        path = tmp_path / "a/b/c/deep.txt"
        result = await file_write(str(path), "deep")
        assert result["written"] is True
        assert path.read_text() == "deep"

    @pytest.mark.asyncio
    async def test_append(self, tmp_path):
        path = tmp_path / "append.txt"
        path.write_text("first\n")
        result = await file_write(str(path), "second\n", append=True)
        assert result["append"] is True
        assert path.read_text() == "first\nsecond\n"


class TestFileEdit:
    @pytest.mark.asyncio
    async def test_edit_unique_string(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world\nfoo bar\n")
        result = await file_edit(str(f), "foo bar", "baz qux")
        assert result["edited"] is True
        assert "baz qux" in f.read_text()

    @pytest.mark.asyncio
    async def test_edit_not_found(self, tmp_path):
        f = tmp_path / "edit2.txt"
        f.write_text("hello")
        result = await file_edit(str(f), "nonexistent", "replacement")
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_edit_not_unique(self, tmp_path):
        f = tmp_path / "edit3.txt"
        f.write_text("aaa\naaa\n")
        result = await file_edit(str(f), "aaa", "bbb")
        assert "2 times" in result["error"]


class TestFileList:
    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / ".hidden").write_text("h")
        result = await file_list(str(tmp_path))
        names = [e["name"] for e in result]
        assert "a.txt" in names
        assert "b.txt" in names
        assert ".hidden" not in names

    @pytest.mark.asyncio
    async def test_list_with_hidden(self, tmp_path):
        (tmp_path / ".hidden").write_text("h")
        result = await file_list(str(tmp_path), include_hidden=True)
        names = [e["name"] for e in result]
        assert ".hidden" in names


class TestFileSearch:
    @pytest.mark.asyncio
    async def test_search_by_name(self, tmp_path):
        (tmp_path / "report.pdf").write_text("pdf")
        (tmp_path / "notes.txt").write_text("txt")
        result = await file_search("report", str(tmp_path))
        assert any("report" in r for r in result)
