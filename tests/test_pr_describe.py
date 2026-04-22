"""Tests for PR Description Generator."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.git_ops.pr_describe import (
    PRDescription,
    PRDescriptionGenerator,
    RiskArea,
    SuggestedReviewer,
    format_pr_description,
)


class TestPRDescriptionGenerator:
    """Tests for PRDescriptionGenerator."""

    def test_init_defaults(self):
        gen = PRDescriptionGenerator()
        assert gen.base == "main"
        assert gen.include_reviewers is True
        assert gen.include_risk is True

    def test_init_custom(self):
        gen = PRDescriptionGenerator(cwd="/tmp", base="develop", include_reviewers=False)
        assert gen.cwd == "/tmp"
        assert gen.base == "develop"
        assert gen.include_reviewers is False

    @patch.object(PRDescriptionGenerator, "_run_git")
    def test_get_commits(self, mock_git):
        mock_git.return_value = "abc12345|Alice|alice@test.com|feat: add login|body text"
        gen = PRDescriptionGenerator()
        commits = gen._get_commits()
        assert len(commits) == 1
        assert commits[0]["hash"] == "abc12345"[:8]
        assert commits[0]["author"] == "Alice"
        assert commits[0]["subject"] == "feat: add login"

    @patch.object(PRDescriptionGenerator, "_run_git")
    def test_get_commits_empty(self, mock_git):
        mock_git.return_value = ""
        gen = PRDescriptionGenerator()
        assert gen._get_commits() == []

    @patch.object(PRDescriptionGenerator, "_run_git")
    def test_get_changed_files(self, mock_git):
        mock_git.return_value = "src/auth.py\nsrc/login.py"
        gen = PRDescriptionGenerator()
        files = gen._get_changed_files()
        assert files == ["src/auth.py", "src/login.py"]

    @patch.object(PRDescriptionGenerator, "_run_git")
    def test_get_diff_stats(self, mock_git):
        mock_git.return_value = " 3 files changed, 100 insertions(+), 20 deletions(-)"
        gen = PRDescriptionGenerator()
        stats = gen._get_diff_stats()
        assert stats["files"] == 3
        assert stats["insertions"] == 100
        assert stats["deletions"] == 20

    @patch.object(PRDescriptionGenerator, "_run_git")
    def test_get_diff_stats_empty(self, mock_git):
        mock_git.return_value = ""
        gen = PRDescriptionGenerator()
        stats = gen._get_diff_stats()
        assert stats["files"] == 0

    def test_generate_title_single_commit(self):
        gen = PRDescriptionGenerator()
        commits = [{"subject": "feat: add user auth", "hash": "abc", "author": "A", "email": "a@b.com"}]
        assert gen._generate_title(commits) == "feat: add user auth"

    def test_generate_title_no_commits(self):
        gen = PRDescriptionGenerator()
        assert gen._generate_title([]) == "Update"

    def test_extract_changes(self):
        gen = PRDescriptionGenerator()
        commits = [
            {"subject": "feat: add login", "body": "- add form\n- add validation"},
            {"subject": "fix: typo", "body": ""},
        ]
        changes = gen._extract_changes(commits)
        assert len(changes) == 4  # 2 subjects + 2 body items

    def test_assess_risk_security_file(self):
        gen = PRDescriptionGenerator()
        risks = gen._assess_risk(["config/credentials.py"])
        assert any(r.severity == "high" for r in risks)

    def test_check_test_coverage(self):
        gen = PRDescriptionGenerator()
        files = ["src/auth.py", "tests/test_auth.py", "src/login.py"]
        cov = gen._check_test_coverage(files)
        assert cov["source_files_changed"] == 2
        assert cov["test_files_changed"] == 1


class TestFormatPRDescription:
    """Tests for format_pr_description."""

    def test_format_md(self):
        desc = PRDescription(
            title="feat: add auth",
            summary="Added authentication.",
            changes=["- Add login endpoint"],
            risk_areas=[RiskArea(file="auth.py", reason="Security", severity="high")],
            test_coverage={"source_files_changed": 1, "test_files_changed": 1, "coverage_pct": 100},
            suggested_reviewers=[SuggestedReviewer(name="Bob", email="bob@test.com", blame_percentage=50)],
            diff_stats={"files": 2, "insertions": 50, "deletions": 10},
            commit_count=1,
        )
        output = format_pr_description(desc, "md")
        assert "feat: add auth" in output
        assert "Risk Areas" in output
        assert "Suggested Reviewers" in output
        assert "Bob" in output

    def test_format_json(self):
        desc = PRDescription(title="test", summary="s", commit_count=0, diff_stats={})
        output = format_pr_description(desc, "json")
        assert '"title": "test"' in output

    def test_format_empty(self):
        desc = PRDescription(title="", summary="", commit_count=0, diff_stats={})
        output = format_pr_description(desc, "md")
        assert "---" in output
