"""Tests for the commit splitter."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.commit_splitter import (
    CommitSplitter, FileInfo, SplitSuggestion, SplitAnalysis,
)


class TestFileInfo:
    """Test FileInfo dataclass."""

    def test_defaults(self):
        f = FileInfo(path="src/main.py")
        assert f.additions == 0
        assert f.category == "source"
        assert f.change_type == "modified"


class TestSplitAnalysis:
    """Test SplitAnalysis."""

    def test_summary_no_split(self):
        a = SplitAnalysis(total_files=2, should_split=False)
        assert "already focused" in a.summary

    def test_summary_split(self):
        a = SplitAnalysis(
            total_files=10, total_additions=100, total_deletions=50,
            should_split=True,
            suggestions=[MagicMock(), MagicMock(), MagicMock()],
        )
        assert "3 commits" in a.summary


class TestCommitSplitter:
    """Test CommitSplitter."""

    def _make_splitter(self, tmp_path):
        return CommitSplitter(cwd=str(tmp_path))

    def test_categorize_test_file(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._categorize_file("tests/test_auth.py") == "test"
        assert splitter._categorize_file("src/auth_test.go") == "test"

    def test_categorize_config(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._categorize_file("config.yaml") == "config"
        assert splitter._categorize_file("Dockerfile") == "config"

    def test_categorize_docs(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._categorize_file("README.md") == "docs"
        assert splitter._categorize_file("docs/setup.rst") == "docs"

    def test_categorize_ci(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._categorize_file(".github/workflows/ci.yml") == "ci"

    def test_categorize_source(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        assert splitter._categorize_file("src/main.py") == "source"

    def test_analyze_small_commit(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        with patch.object(splitter, "_get_commit_message", return_value="fix: small change"):
            with patch.object(splitter, "_get_commit_files", return_value=[
                FileInfo(path="src/main.py", additions=5),
            ]):
                analysis = splitter.analyze("HEAD")
        assert analysis.should_split is False

    def test_analyze_mixed_commit(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        files = [
            FileInfo(path="src/auth.py", additions=50),
            FileInfo(path="src/api.py", additions=30),
            FileInfo(path="tests/test_auth.py", additions=40),
            FileInfo(path="tests/test_api.py", additions=20),
            FileInfo(path="README.md", additions=10),
            FileInfo(path=".github/workflows/ci.yml", additions=5),
        ]
        with patch.object(splitter, "_get_commit_message", return_value="feat: big change"):
            with patch.object(splitter, "_get_commit_files", return_value=files):
                analysis = splitter.analyze("HEAD")
        assert analysis.should_split is True
        assert len(analysis.suggestions) >= 3
        categories = {s.category for s in analysis.suggestions}
        assert "test" in categories
        assert "docs" in categories

    def test_generate_script(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        analysis = SplitAnalysis(
            original_message="feat: big change",
            total_files=5,
            should_split=True,
            suggestions=[
                SplitSuggestion(order=1, message="feat(src): big change",
                                files=["src/main.py"], category="source"),
                SplitSuggestion(order=2, message="test(tests): big change",
                                files=["tests/test_main.py"], category="test"),
            ],
        )
        script = splitter.generate_script(analysis, commit="abc123")
        assert "#!/bin/bash" in script
        assert "git add src/main.py" in script
        assert 'git commit -m "feat(src): big change"' in script

    def test_generate_script_no_split(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        analysis = SplitAnalysis(should_split=False)
        script = splitter.generate_script(analysis)
        assert "No split needed" in script

    def test_group_by_category(self, tmp_path):
        splitter = self._make_splitter(tmp_path)
        files = [
            FileInfo(path="src/a.py", category="source"),
            FileInfo(path="src/b.py", category="source"),
            FileInfo(path="tests/t.py", category="test"),
        ]
        groups = splitter._group_by_category(files)
        assert "source" in groups
        assert "test" in groups
        assert len(groups["source"]) == 2
