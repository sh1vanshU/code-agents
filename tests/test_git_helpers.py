"""Tests for the _git_helpers shared utility."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools._git_helpers import (
    _run_git, git_log, git_diff_files, git_branches,
    get_current_branch, CommitInfo, DiffFile, BranchInfo, PRInfo,
    find_pr_for_commit,
)


class TestRunGit:
    """Test git command execution."""

    @patch("code_agents.tools._git_helpers.subprocess.run")
    def test_run_git_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="output\n")
        result = _run_git("/tmp", ["status"])
        assert result == "output"

    @patch("code_agents.tools._git_helpers.subprocess.run")
    def test_run_git_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        result = _run_git("/tmp", ["log"])
        assert result == ""

    @patch("code_agents.tools._git_helpers.subprocess.run")
    def test_run_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        result = _run_git("/tmp", ["status"])
        assert result == ""


class TestGitLog:
    """Test structured git log."""

    @patch("code_agents.tools._git_helpers._run_git")
    def test_git_log_parses_output(self, mock_run):
        mock_run.return_value = (
            "abc123|Alice|alice@dev.com|2024-01-15T10:00:00|feat: add login\n"
            "def456|Bob|bob@dev.com|2024-01-14T09:00:00|fix: typo\n"
        )
        commits = git_log("/tmp", max_count=10)

        assert len(commits) == 2
        assert commits[0].sha == "abc123"
        assert commits[0].author == "Alice"
        assert commits[0].message == "feat: add login"
        assert commits[1].sha == "def456"

    @patch("code_agents.tools._git_helpers._run_git")
    def test_git_log_empty(self, mock_run):
        mock_run.return_value = ""
        commits = git_log("/tmp")
        assert commits == []


class TestGitDiffFiles:
    """Test structured diff output."""

    @patch("code_agents.tools._git_helpers._run_git")
    def test_diff_files(self, mock_run):
        mock_run.return_value = "10\t5\tsrc/api.py\n3\t1\ttests/test_api.py"
        files = git_diff_files("/tmp")

        assert len(files) == 2
        assert files[0].path == "src/api.py"
        assert files[0].insertions == 10
        assert files[0].deletions == 5

    @patch("code_agents.tools._git_helpers._run_git")
    def test_diff_empty(self, mock_run):
        mock_run.return_value = ""
        assert git_diff_files("/tmp") == []


class TestGitBranches:
    """Test branch listing."""

    @patch("code_agents.tools._git_helpers._run_git")
    def test_list_branches(self, mock_run):
        mock_run.return_value = "main|*|origin/main|2024-01-15|abc123\nfeat||| |def456"
        branches = git_branches("/tmp")
        assert len(branches) >= 1
        assert branches[0].name == "main"
        assert branches[0].is_current is True


class TestFindPRForCommit:
    """Test PR lookup."""

    @patch("code_agents.tools._git_helpers.subprocess")
    @patch("code_agents.tools._git_helpers._run_git")
    def test_find_pr_from_merge_commit(self, mock_run, mock_subprocess):
        mock_run.return_value = "abc1234 Merge pull request #42 from feat/login"
        pr = find_pr_for_commit("/tmp", "abc1234")
        assert pr is not None
        assert pr.number == "42"

    @patch("code_agents.tools._git_helpers._run_git")
    def test_find_pr_no_match(self, mock_run):
        mock_run.return_value = "abc1234 feat: regular commit"
        # Will try gh CLI which may not be available
        pr = find_pr_for_commit("/tmp", "abc1234")
        # May or may not find a PR, but shouldn't crash
        assert pr is None or isinstance(pr, PRInfo)
