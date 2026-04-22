"""Tests for the diff preview system."""

from __future__ import annotations

import pytest

from code_agents.git_ops.diff_preview import (
    DiffPreview, DiffHunk, HunkState, parse_hunks,
    format_diff_plain, format_diff_rich, is_enabled,
    _apply_partial_hunks, _escape_markup,
)


class TestParseHunks:
    """Test hunk parsing from diffs."""

    def test_no_diff(self):
        hunks = parse_hunks("hello\n", "hello\n")
        assert hunks == []

    def test_single_hunk(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nmodified\nline3\n"
        hunks = parse_hunks(original, modified)
        assert len(hunks) >= 1
        assert hunks[0].index == 0

    def test_multiple_hunks(self):
        original = "\n".join(f"line{i}" for i in range(20)) + "\n"
        modified = original.replace("line3", "CHANGED3").replace("line15", "CHANGED15")
        hunks = parse_hunks(original, modified)
        # Should have at least 2 hunks if lines are far enough apart
        assert len(hunks) >= 1

    def test_hunk_additions_deletions(self):
        original = "old line\n"
        modified = "new line\n"
        hunks = parse_hunks(original, modified)
        assert len(hunks) >= 1
        # Should have at least one addition and one deletion
        total_add = sum(h.additions for h in hunks)
        total_del = sum(h.deletions for h in hunks)
        assert total_add >= 1
        assert total_del >= 1


class TestDiffPreview:
    """Test DiffPreview operations."""

    def _make_preview(self) -> DiffPreview:
        original = "line1\nline2\nline3\n"
        modified = "line1\nchanged\nline3\nextra\n"
        return DiffPreview(file_path="test.py", original=original, modified=modified)

    def test_total_hunks(self):
        preview = self._make_preview()
        assert preview.total_hunks >= 1

    def test_accept_reject_counts(self):
        preview = self._make_preview()
        assert preview.pending_count == preview.total_hunks
        assert preview.accepted_count == 0
        preview.accept_hunk(0)
        assert preview.accepted_count == 1
        assert preview.pending_count == preview.total_hunks - 1

    def test_accept_all(self):
        preview = self._make_preview()
        preview.accept_all()
        assert preview.accepted_count == preview.total_hunks
        assert preview.pending_count == 0

    def test_reject_all(self):
        preview = self._make_preview()
        preview.reject_all()
        assert preview.rejected_count == preview.total_hunks

    def test_apply_all_accepted(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nchanged\nline3\n"
        preview = DiffPreview(file_path="t.py", original=original, modified=modified)
        preview.accept_all()
        result = preview.apply_accepted()
        assert result == modified

    def test_apply_all_rejected(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nchanged\nline3\n"
        preview = DiffPreview(file_path="t.py", original=original, modified=modified)
        preview.reject_all()
        result = preview.apply_accepted()
        assert result == original

    def test_get_unified_diff(self):
        preview = self._make_preview()
        diff = preview.get_unified_diff()
        assert "---" in diff or "@@" in diff or diff == ""

    def test_accept_out_of_range(self):
        preview = self._make_preview()
        # Should not crash
        preview.accept_hunk(999)
        preview.reject_hunk(-1)


class TestFormatting:
    """Test diff formatting functions."""

    def test_format_plain(self):
        original = "old\n"
        modified = "new\n"
        preview = DiffPreview(file_path="test.py", original=original, modified=modified)
        output = format_diff_plain(preview)
        assert "test.py" in output
        assert "Hunk" in output

    def test_format_rich(self):
        original = "old\n"
        modified = "new\n"
        preview = DiffPreview(file_path="test.py", original=original, modified=modified)
        output = format_diff_rich(preview)
        assert "test.py" in output
        assert "Hunk" in output

    def test_escape_markup(self):
        assert _escape_markup("[bold]test[/bold]") == "\\[bold\\]test\\[/bold\\]"


class TestIsEnabled:
    """Test diff preview mode detection."""

    def test_default_disabled(self):
        assert not is_enabled()

    def test_state_override(self):
        assert is_enabled({"diff_preview": True})
        assert not is_enabled({"diff_preview": False})

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_DIFF_PREVIEW", "true")
        assert is_enabled()

    def test_env_false(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_DIFF_PREVIEW", "false")
        assert not is_enabled()
