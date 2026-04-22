"""Tests for the merge conflict resolver."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.conflict_resolver import (
    ConflictResolver, ConflictHunk, Resolution, ConflictReport,
)


class TestConflictHunk:
    """Test ConflictHunk dataclass."""

    def test_fields(self):
        h = ConflictHunk(
            file_path="a.py", start_line=10, end_line=20,
            ours_label="HEAD", theirs_label="feature",
            ours_lines=["a = 1"], theirs_lines=["a = 2"],
        )
        assert h.start_line == 10
        assert h.ours_label == "HEAD"
        assert len(h.ours_lines) == 1


class TestResolution:
    """Test Resolution dataclass."""

    def test_fields(self):
        hunk = ConflictHunk(file_path="a.py", start_line=1, end_line=5,
                            ours_label="H", theirs_label="F")
        r = Resolution(hunk=hunk, strategy="ours", resolved_lines=["a = 1"],
                       explanation="chose ours", confidence=0.9)
        assert r.strategy == "ours"
        assert r.confidence == 0.9


class TestConflictReport:
    """Test ConflictReport."""

    def test_summary(self):
        r = ConflictReport(
            conflicts=[MagicMock(), MagicMock()],
            resolutions=[MagicMock()],
            files_affected=["a.py"],
        )
        assert "2 conflict(s)" in r.summary
        assert "1 file(s)" in r.summary


class TestConflictResolver:
    """Test ConflictResolver."""

    def _make_conflict_file(self, tmp_path, name="conflict.py"):
        content = """before line
<<<<<<< HEAD
a = 1
b = 2
=======
a = 10
b = 20
>>>>>>> feature
after line
"""
        f = tmp_path / name
        f.write_text(content)
        return str(f)

    def test_parse_conflicts_basic(self, tmp_path):
        path = self._make_conflict_file(tmp_path)
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunks = resolver.analyze_file(path)
        assert len(hunks) == 1
        assert hunks[0].ours_label == "HEAD"
        assert hunks[0].theirs_label == "feature"
        assert "a = 1" in hunks[0].ours_lines
        assert "a = 10" in hunks[0].theirs_lines

    def test_parse_multiple_conflicts(self, tmp_path):
        content = """<<<<<<< HEAD
x = 1
=======
x = 2
>>>>>>> branch
middle
<<<<<<< HEAD
y = 3
=======
y = 4
>>>>>>> branch
"""
        f = tmp_path / "multi.py"
        f.write_text(content)
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunks = resolver.analyze_file(str(f))
        assert len(hunks) == 2

    def test_resolve_identical(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunk = ConflictHunk(
            file_path="a.py", start_line=1, end_line=5,
            ours_label="HEAD", theirs_label="branch",
            ours_lines=["x = 1"], theirs_lines=["x = 1"],
        )
        res = resolver._resolve(hunk)
        assert res.strategy == "ours"
        assert res.confidence == 1.0

    def test_resolve_one_side_empty(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunk = ConflictHunk(
            file_path="a.py", start_line=1, end_line=5,
            ours_label="HEAD", theirs_label="branch",
            ours_lines=[], theirs_lines=["x = 1"],
        )
        res = resolver._resolve(hunk)
        assert res.strategy == "theirs"

    def test_resolve_superset_ours(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunk = ConflictHunk(
            file_path="a.py", start_line=1, end_line=5,
            ours_label="HEAD", theirs_label="branch",
            ours_lines=["x = 1", "y = 2", "z = 3"],
            theirs_lines=["x = 1", "y = 2"],
        )
        res = resolver._resolve(hunk)
        assert res.strategy == "ours"
        assert "superset" in res.explanation

    def test_resolve_manual_fallback(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunk = ConflictHunk(
            file_path="a.py", start_line=1, end_line=5,
            ours_label="HEAD", theirs_label="branch",
            ours_lines=["def process(x):", "    return x + 1"],
            theirs_lines=["def process(x):", "    return x * 2"],
        )
        res = resolver._resolve(hunk)
        assert res.strategy == "manual"
        assert res.confidence == 0.0

    def test_analyze_no_conflicts(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        with patch.object(resolver, "_get_conflicted_files", return_value=[]):
            report = resolver.analyze()
        assert len(report.conflicts) == 0
        assert len(report.files_affected) == 0

    def test_independent_additions(self, tmp_path):
        resolver = ConflictResolver(cwd=str(tmp_path))
        hunk = ConflictHunk(
            file_path="a.py", start_line=1, end_line=5,
            ours_label="HEAD", theirs_label="branch",
            ours_lines=["import os", "import sys"],
            theirs_lines=["import json", "import re"],
        )
        assert resolver._are_independent_additions(hunk) is True
