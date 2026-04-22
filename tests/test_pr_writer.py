"""Tests for the PR writer."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.pr_writer import PRWriter, PRDescription, FileChange


class TestFileChange:
    """Test FileChange dataclass."""

    def test_defaults(self):
        fc = FileChange(path="src/main.py")
        assert fc.additions == 0
        assert fc.deletions == 0
        assert fc.change_type == "modified"


class TestPRDescription:
    """Test PRDescription dataclass."""

    def test_to_markdown_basic(self):
        desc = PRDescription(
            title="Add feature",
            what="Added a new feature",
            why="User requested it",
            how="Modified core module",
            rollback_plan="Revert commit",
        )
        md = desc.to_markdown()
        assert "## What" in md
        assert "## Why" in md
        assert "## How" in md
        assert "## Rollback Plan" in md

    def test_to_markdown_with_breaking_changes(self):
        desc = PRDescription(
            title="t", what="w", why="y", how="h", rollback_plan="r",
            breaking_changes=["Removed old API"],
        )
        md = desc.to_markdown()
        assert "## Breaking Changes" in md
        assert "Removed old API" in md

    def test_to_markdown_with_reviewer_hints(self):
        desc = PRDescription(
            title="t", what="w", why="y", how="h", rollback_plan="r",
            reviewer_hints=["Start with models.py"],
        )
        md = desc.to_markdown()
        assert "## Reviewer Hints" in md

    def test_to_markdown_with_issues(self):
        desc = PRDescription(
            title="t", what="w", why="y", how="h", rollback_plan="r",
            related_issues=["PROJ-123", "#456"],
        )
        md = desc.to_markdown()
        assert "PROJ-123" in md


class TestPRWriter:
    """Test PRWriter generation."""

    def _mock_git(self, outputs: dict):
        """Create a mock _git that returns different outputs based on args."""
        def side_effect(*args):
            for key, val in outputs.items():
                if key in " ".join(args):
                    return val
            return ""
        return side_effect

    def test_generate_basic(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        with patch.object(writer, "_git") as mock:
            mock.side_effect = self._mock_git({
                "log": "feat: add user auth",
                "numstat": "10\t2\tsrc/auth.py\n5\t0\ttests/test_auth.py",
                "name-status": "M\tsrc/auth.py\nA\ttests/test_auth.py",
                "stat": "2 files changed",
            })
            desc = writer.generate("main", "HEAD")
        assert desc.title
        assert desc.what
        assert len(desc.files_changed) == 2

    def test_risk_high_for_migration(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        files = [FileChange(path="migrations/0001_add_user.py", additions=50)]
        risk = writer._assess_risk(files)
        assert risk == "high"

    def test_risk_medium_for_api(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        files = [FileChange(path="api/routes.py", additions=20)]
        risk = writer._assess_risk(files)
        assert risk == "medium"

    def test_risk_low_for_docs(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        files = [FileChange(path="README.md", additions=5)]
        risk = writer._assess_risk(files)
        assert risk == "low"

    def test_extract_issues(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        commits = ["fix: resolve PROJ-123 login bug", "test: add #456 coverage"]
        issues = writer._extract_issues(commits)
        assert "PROJ-123" in issues
        assert "#456" in issues

    def test_detect_breaking_changes(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        commits = ["BREAKING: remove old auth endpoint"]
        files = [FileChange(path="api/schema.py", change_type="deleted")]
        breaking = writer._detect_breaking_changes(commits, files)
        assert len(breaking) >= 1

    def test_rollback_with_migration(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        files = [FileChange(path="migrations/0001.py")]
        rollback = writer._generate_rollback(files, "high")
        assert "migration" in rollback.lower()

    def test_reviewer_hints_no_tests(self, tmp_path):
        writer = PRWriter(cwd=str(tmp_path))
        files = [FileChange(path="src/main.py", additions=100)]
        hints = writer._generate_reviewer_hints(files, "")
        assert any("test" in h.lower() for h in hints)
