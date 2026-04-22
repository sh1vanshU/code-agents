"""Tests for the PR size optimizer."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.pr_split import PRSplitter, SplitGroup, format_split_report


class TestSplitGroup:
    """Test SplitGroup dataclass."""

    def test_defaults(self):
        g = SplitGroup(name="g1", files=["a.py"], description="test", risk="low")
        assert g.estimated_review_min == 0

    def test_fields(self):
        g = SplitGroup(name="api", files=["a.py", "b.py"], description="API changes", risk="high", estimated_review_min=15)
        assert g.name == "api"
        assert len(g.files) == 2
        assert g.risk == "high"
        assert g.estimated_review_min == 15


class TestPRSplitter:
    """Test PRSplitter methods."""

    def _make_splitter(self, tmp_path):
        return PRSplitter(cwd=str(tmp_path))

    def test_get_changed_files_empty(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            files = splitter._get_changed_files("main")
            assert files == []

    def test_get_changed_files(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="src/a.py\nsrc/b.py\ntests/test_a.py\n", stderr="")
            files = splitter._get_changed_files("main")
            assert len(files) == 3
            assert "src/a.py" in files

    def test_get_changed_files_git_failure(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fatal: bad rev")
            files = splitter._get_changed_files("main")
            assert files == []

    def test_group_by_directory(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        files = ["src/a.py", "src/b.py", "tests/test_a.py", "README.md"]
        groups = splitter._group_by_directory(files)
        assert len(groups) == 3  # src, tests, (root)
        names = {g.name for g in groups}
        assert "src/" in names
        assert "tests/" in names

    def test_group_by_directory_single_dir(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        files = ["src/a.py", "src/b.py", "src/c.py"]
        groups = splitter._group_by_directory(files)
        assert len(groups) == 1
        assert groups[0].name == "src/"

    def test_group_by_independence_no_cross_refs(self, tmp_path):
        # Create files that don't reference each other
        src = tmp_path / "a.py"
        src.write_text("print('hello')")
        src2 = tmp_path / "b.py"
        src2.write_text("print('world')")

        splitter = self._make_splitter(tmp_path)
        groups = splitter._group_by_independence(["a.py", "b.py"])
        assert len(groups) == 2  # independent

    def test_group_by_independence_with_cross_refs(self, tmp_path):
        # Create files that reference each other
        (tmp_path / "a.py").write_text("import b\nprint(b)")
        (tmp_path / "b.py").write_text("x = 1")

        splitter = self._make_splitter(tmp_path)
        groups = splitter._group_by_independence(["a.py", "b.py"])
        assert len(groups) == 1  # connected

    def test_assess_risk_high(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._assess_risk(["deploy/config.yaml"]) == "high"
        assert splitter._assess_risk(["auth/handler.py"]) == "high"

    def test_assess_risk_medium(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._assess_risk(["tests/test_foo.py"]) == "medium"

    def test_assess_risk_low(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._assess_risk(["src/utils.py"]) == "low"

    def test_analyze_no_changes(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch.object(splitter, "_get_changed_files", return_value=[]):
            groups = splitter.analyze(base="main")
            assert groups == []

    def test_analyze_full(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        splitter = self._make_splitter(tmp_path)
        with patch.object(splitter, "_get_changed_files", return_value=["a.py", "b.py"]):
            with patch.object(splitter, "_get_diff_stat", return_value=80):
                groups = splitter.analyze(base="main")
                assert len(groups) >= 1
                assert all(g.estimated_review_min >= 1 for g in groups)

    def test_estimate_review_time(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch.object(splitter, "_get_diff_stat", return_value=200):
            mins = splitter._estimate_review_time(["a.py", "b.py"])
            assert mins >= 1


class TestFormatSplitReport:
    """Test formatting."""

    def test_empty(self):
        report = format_split_report([])
        assert "nothing to split" in report.lower() or "No changes" in report

    def test_with_groups(self):
        groups = [
            SplitGroup(name="src/", files=["src/a.py"], description="Source changes", risk="low", estimated_review_min=5),
            SplitGroup(name="tests/", files=["tests/test_a.py"], description="Test changes", risk="medium", estimated_review_min=3),
        ]
        report = format_split_report(groups)
        assert "PR 1" in report
        assert "PR 2" in report
        assert "src/" in report
        assert "tests/" in report
        assert "Total" in report
