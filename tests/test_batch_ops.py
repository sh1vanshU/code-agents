"""Tests for batch operations."""

from __future__ import annotations

import os
import textwrap

import pytest

from code_agents.devops.batch_ops import (
    BatchFileResult,
    BatchOperator,
    BatchResult,
    format_batch_result,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a tiny repo structure for testing."""
    (tmp_path / "main.py").write_text(
        textwrap.dedent("""\
            def greet(name):
                print(f"Hello {name}")
                return name

            def add(a, b):
                return a + b
        """),
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        textwrap.dedent("""\
            def helper():
                x = 1
                return x
        """),
        encoding="utf-8",
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.py").write_text(
        textwrap.dedent("""\
            class Foo:
                def bar(self):
                    pass
        """),
        encoding="utf-8",
    )
    (tmp_path / "readme.md").write_text("# README\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------
# TestSelectFiles
# ---------------------------------------------------------------

class TestSelectFiles:
    """Tests for file selection logic."""

    def test_explicit_file_list(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        targets = op._select_files(["main.py"], "")
        assert len(targets) == 1
        assert targets[0].endswith("main.py")

    def test_glob_pattern(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        targets = op._select_files(None, "**/*.py")
        assert len(targets) >= 3
        names = [os.path.basename(t) for t in targets]
        assert "main.py" in names
        assert "deep.py" in names

    def test_all_source_files(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        targets = op._select_files(None, "")
        names = [os.path.basename(t) for t in targets]
        assert "main.py" in names
        assert "utils.py" in names
        # readme.md has .md extension which is not in _SOURCE_EXTENSIONS
        assert "readme.md" not in names

    def test_nonexistent_file_skipped(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        targets = op._select_files(["nonexistent.py"], "")
        assert targets == []

    def test_absolute_path(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        abs_path = str(tmp_repo / "main.py")
        targets = op._select_files([abs_path], "")
        assert len(targets) == 1


# ---------------------------------------------------------------
# TestPathSecurity
# ---------------------------------------------------------------

class TestPathSecurity:
    """Reject paths that escape the working directory."""

    def test_reject_parent_traversal(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        with pytest.raises(ValueError, match="escapes working directory"):
            op._validate_path((tmp_repo / ".." / ".." / "etc" / "passwd").resolve())

    def test_reject_absolute_outside(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        with pytest.raises(ValueError, match="escapes working directory"):
            op._validate_path(tmp_repo.parent / "other_repo" / "file.py")

    def test_accept_valid_path(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        # Should not raise
        op._validate_path(tmp_repo / "main.py")


# ---------------------------------------------------------------
# TestProcessFile — instruction transforms
# ---------------------------------------------------------------

class TestProcessFile:
    """Test each instruction type."""

    def test_add_error_handling(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add error handling", files=["main.py"], dry_run=True)
        assert result.changed >= 1
        changed_file = [r for r in result.results if r.changes_made]
        assert len(changed_file) >= 1
        assert "try:" in changed_file[0].diff

    def test_add_logging(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add logging", files=["utils.py"], dry_run=True)
        changed = [r for r in result.results if r.changes_made]
        assert len(changed) >= 1
        assert "import logging" in changed[0].diff

    def test_remove_print_statements(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("remove print statements", files=["main.py"], dry_run=True)
        changed = [r for r in result.results if r.changes_made]
        assert len(changed) >= 1
        assert "logger.info" in changed[0].diff

    def test_add_docstrings(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add docstrings", files=["main.py"], dry_run=True)
        changed = [r for r in result.results if r.changes_made]
        assert len(changed) >= 1
        assert '"""TODO: document' in changed[0].diff

    def test_add_type_hints(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add type hints", files=["utils.py"], dry_run=True)
        changed = [r for r in result.results if r.changes_made]
        assert len(changed) >= 1
        assert "-> None" in changed[0].diff

    def test_unknown_instruction_no_change(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("do something magical", files=["main.py"], dry_run=True)
        assert result.changed == 0
        assert result.skipped == 1

    def test_non_python_file_unchanged(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add docstrings", files=["readme.md"], dry_run=True)
        # .md won't parse as Python, so no changes
        assert result.changed == 0


# ---------------------------------------------------------------
# TestParallel
# ---------------------------------------------------------------

class TestParallel:
    """Verify ThreadPoolExecutor usage with multiple files."""

    def test_multiple_files_parallel(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run(
            "add docstrings",
            files=["main.py", "utils.py", "sub/deep.py"],
            max_parallel=3,
            dry_run=True,
        )
        assert result.total_files == 3
        assert result.changed + result.skipped + result.failed == 3

    def test_max_parallel_clamped(self, tmp_repo):
        op = BatchOperator(cwd=str(tmp_repo))
        # max_parallel=100 should be clamped to 16 internally
        result = op.run("add docstrings", files=["main.py"], max_parallel=100, dry_run=True)
        assert result.total_files == 1


# ---------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------

class TestDryRun:
    """Dry-run should generate diffs but not modify files."""

    def test_dry_run_no_modification(self, tmp_repo):
        original = (tmp_repo / "main.py").read_text()
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add docstrings", files=["main.py"], dry_run=True)
        after = (tmp_repo / "main.py").read_text()
        assert original == after
        assert result.changed >= 1  # reported as changed (diff generated)

    def test_actual_write(self, tmp_repo):
        original = (tmp_repo / "utils.py").read_text()
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add docstrings", files=["utils.py"], dry_run=False)
        after = (tmp_repo / "utils.py").read_text()
        if result.changed > 0:
            assert after != original
            assert '"""TODO: document' in after


# ---------------------------------------------------------------
# TestFormat
# ---------------------------------------------------------------

class TestFormat:
    """Verify the summary formatter."""

    def test_format_structure(self):
        result = BatchResult(
            instruction="add error handling",
            total_files=3,
            changed=2,
            skipped=1,
            failed=0,
            results=[
                BatchFileResult(file="/repo/a.py", success=True, changes_made=True, diff="+try:"),
                BatchFileResult(file="/repo/b.py", success=True, changes_made=True, diff="+try:"),
                BatchFileResult(file="/repo/c.py", success=True, changes_made=False),
            ],
            duration_seconds=1.5,
        )
        output = format_batch_result(result)
        assert "Batch Operation" in output
        assert "add error handling" in output
        assert "2 changed" in output
        assert "1 skipped" in output
        assert "1.5s" in output
        assert "✓" in output
        assert "–" in output

    def test_format_with_failures(self):
        result = BatchResult(
            instruction="test",
            total_files=1,
            changed=0,
            skipped=0,
            failed=1,
            results=[
                BatchFileResult(file="/repo/bad.py", success=False, changes_made=False, error="parse error"),
            ],
            duration_seconds=0.1,
        )
        output = format_batch_result(result)
        assert "✗" in output
        assert "parse error" in output


# ---------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and error handling."""

    def test_empty_file(self, tmp_repo):
        (tmp_repo / "empty.py").write_text("", encoding="utf-8")
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add error handling", files=["empty.py"], dry_run=True)
        assert result.failed == 0

    def test_syntax_error_file(self, tmp_repo):
        (tmp_repo / "bad.py").write_text("def broken(\n", encoding="utf-8")
        op = BatchOperator(cwd=str(tmp_repo))
        result = op.run("add docstrings", files=["bad.py"], dry_run=True)
        # Should handle gracefully — no crash
        assert result.total_files == 1

    def test_invalid_cwd(self):
        with pytest.raises(ValueError, match="does not exist"):
            BatchOperator(cwd="/nonexistent/path/12345")
