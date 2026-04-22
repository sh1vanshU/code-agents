"""Tests for PR Thread Agent — review comment responder."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.git_ops.pr_thread_agent import (
    PRThreadAgent,
    ReviewComment,
    ThreadResponse,
    format_thread_responses,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GH_COMMENTS = [
    {
        "id": 101,
        "body": "Rename `foo` to `bar`",
        "path": "src/utils.py",
        "line": 10,
        "user": {"login": "reviewer1"},
        "created_at": "2026-04-09T10:00:00Z",
    },
    {
        "id": 102,
        "body": "Add error handling here",
        "path": "src/main.py",
        "line": 25,
        "user": {"login": "reviewer2"},
        "created_at": "2026-04-09T10:05:00Z",
    },
    {
        "id": 103,
        "body": "LGTM",
        "path": "",
        "line": None,
        "user": {"login": "approver"},
        "created_at": "2026-04-09T10:10:00Z",
    },
    {
        "id": 104,
        "body": "Why did you choose this approach?",
        "path": "src/utils.py",
        "line": 5,
        "user": {"login": "reviewer1"},
        "created_at": "2026-04-09T10:15:00Z",
    },
    {
        "id": 105,
        "body": "Remove this line",
        "path": "src/config.py",
        "line": 3,
        "user": {"login": "reviewer2"},
        "created_at": "2026-04-09T10:20:00Z",
    },
    {
        "id": 106,
        "body": "Add type hint to this function",
        "path": "src/handler.py",
        "line": 1,
        "user": {"login": "reviewer1"},
        "created_at": "2026-04-09T10:25:00Z",
    },
    {
        "id": 107,
        "body": "Add docstring",
        "path": "src/handler.py",
        "line": 1,
        "user": {"login": "reviewer1"},
        "created_at": "2026-04-09T10:30:00Z",
    },
]


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo directory with sample files."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "utils.py").write_text(
        "def foo():\n    return foo + 1\n\ndef baz():\n    pass\n",
        encoding="utf-8",
    )
    (src / "main.py").write_text(
        "import os\n\n" + "\n".join(f"line_{i} = {i}" for i in range(30)) + "\n",
        encoding="utf-8",
    )
    (src / "config.py").write_text(
        "A = 1\nB = 2\nDEBUG = True\nC = 3\n",
        encoding="utf-8",
    )
    (src / "handler.py").write_text(
        "def process(data):\n    return data\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def agent(tmp_repo):
    """Create a PRThreadAgent pointed at the temp repo."""
    a = PRThreadAgent(cwd=str(tmp_repo))
    a._owner = "testorg"
    a._repo = "testrepo"
    return a


def _mock_run_gh_comments(comments_json):
    """Create a mock for subprocess.run that returns gh api comments."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(comments_json)
    mock_result.stderr = ""
    return mock_result


# ---------------------------------------------------------------------------
# TestFetchComments
# ---------------------------------------------------------------------------


class TestFetchComments:
    """Test fetching review comments from GitHub."""

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_fetch_parses_comments(self, mock_run, agent):
        mock_run.return_value = _mock_run_gh_comments(SAMPLE_GH_COMMENTS)
        comments = agent._fetch_review_comments(42)
        assert len(comments) == len(SAMPLE_GH_COMMENTS)
        assert comments[0].id == 101
        assert comments[0].body == "Rename `foo` to `bar`"
        assert comments[0].author == "reviewer1"

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_fetch_handles_api_error(self, mock_run, agent):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Not Found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            agent._fetch_review_comments(999)

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_fetch_handles_invalid_json(self, mock_run, agent):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not json"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        with pytest.raises(RuntimeError, match="Invalid JSON"):
            agent._fetch_review_comments(42)

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_fetch_empty_comments(self, mock_run, agent):
        mock_run.return_value = _mock_run_gh_comments([])
        comments = agent._fetch_review_comments(42)
        assert comments == []


# ---------------------------------------------------------------------------
# TestIsActionable
# ---------------------------------------------------------------------------


class TestIsActionable:
    """Test actionable comment classification."""

    def test_rename_is_actionable(self, agent):
        c = ReviewComment(id=1, body="Rename `foo` to `bar`", path="a.py",
                          line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True

    def test_add_error_handling_is_actionable(self, agent):
        c = ReviewComment(id=2, body="Add error handling here", path="a.py",
                          line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True

    def test_remove_is_actionable(self, agent):
        c = ReviewComment(id=3, body="Remove this line", path="a.py",
                          line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True

    def test_add_type_hint_is_actionable(self, agent):
        c = ReviewComment(id=4, body="Add type hint to this function", path="a.py",
                          line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True

    def test_lgtm_not_actionable(self, agent):
        c = ReviewComment(id=5, body="LGTM", path="", line=0,
                          author="x", created_at="")
        assert agent._is_actionable(c) is False

    def test_question_not_actionable(self, agent):
        c = ReviewComment(id=6, body="Why did you choose this approach?",
                          path="a.py", line=1, author="x", created_at="")
        assert agent._is_actionable(c) is False

    def test_approval_not_actionable(self, agent):
        c = ReviewComment(id=7, body="Looks good to me!", path="",
                          line=0, author="x", created_at="")
        assert agent._is_actionable(c) is False

    def test_empty_body_not_actionable(self, agent):
        c = ReviewComment(id=8, body="", path="a.py",
                          line=1, author="x", created_at="")
        assert agent._is_actionable(c) is False

    def test_no_path_not_actionable(self, agent):
        c = ReviewComment(id=9, body="Fix this bug", path="",
                          line=0, author="x", created_at="")
        assert agent._is_actionable(c) is False

    def test_consider_using_is_actionable(self, agent):
        c = ReviewComment(id=10, body="Should use a list comprehension here",
                          path="a.py", line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True

    def test_missing_keyword_actionable(self, agent):
        c = ReviewComment(id=11, body="This import is unused",
                          path="a.py", line=1, author="x", created_at="")
        assert agent._is_actionable(c) is True


# ---------------------------------------------------------------------------
# TestApplyFix
# ---------------------------------------------------------------------------


class TestApplyFix:
    """Test automatic fix application."""

    def test_rename_fix(self, agent, tmp_repo):
        c = ReviewComment(id=101, body="Rename `foo` to `bar`",
                          path="src/utils.py", line=1, author="x", created_at="")
        with patch.object(agent, "_get_file_diff", return_value="mock diff"):
            diff = agent._apply_fix(c)
        assert diff == "mock diff"
        content = (tmp_repo / "src" / "utils.py").read_text()
        assert "bar" in content
        assert "foo" not in content

    def test_remove_fix(self, agent, tmp_repo):
        c = ReviewComment(id=105, body="Remove this line",
                          path="src/config.py", line=3, author="x", created_at="")
        with patch.object(agent, "_get_file_diff", return_value="mock diff"):
            diff = agent._apply_fix(c)
        assert diff == "mock diff"
        content = (tmp_repo / "src" / "config.py").read_text()
        assert "DEBUG = True" not in content
        assert "A = 1" in content

    def test_add_error_handling_fix(self, agent, tmp_repo):
        c = ReviewComment(id=102, body="Add error handling here",
                          path="src/main.py", line=25, author="x", created_at="")
        with patch.object(agent, "_get_file_diff", return_value="mock diff"):
            diff = agent._apply_fix(c)
        assert diff == "mock diff"
        content = (tmp_repo / "src" / "main.py").read_text()
        assert "try:" in content
        assert "except Exception" in content

    def test_add_type_hint_fix(self, agent, tmp_repo):
        c = ReviewComment(id=106, body="Add type hint to this function",
                          path="src/handler.py", line=1, author="x", created_at="")
        with patch.object(agent, "_get_file_diff", return_value="mock diff"):
            diff = agent._apply_fix(c)
        assert diff == "mock diff"
        content = (tmp_repo / "src" / "handler.py").read_text()
        assert "-> None:" in content

    def test_add_docstring_fix(self, agent, tmp_repo):
        c = ReviewComment(id=107, body="Add docstring",
                          path="src/handler.py", line=1, author="x", created_at="")
        with patch.object(agent, "_get_file_diff", return_value="mock diff"):
            diff = agent._apply_fix(c)
        assert diff == "mock diff"
        content = (tmp_repo / "src" / "handler.py").read_text()
        assert '"""TODO: Add docstring."""' in content

    def test_no_fix_for_unknown_pattern(self, agent, tmp_repo):
        c = ReviewComment(id=200, body="Consider using a different algorithm",
                          path="src/utils.py", line=1, author="x", created_at="")
        diff = agent._apply_fix(c)
        assert diff == ""

    def test_file_not_found(self, agent, tmp_repo):
        c = ReviewComment(id=300, body="Rename `a` to `b`",
                          path="nonexistent.py", line=1, author="x", created_at="")
        diff = agent._apply_fix(c)
        assert diff == ""


# ---------------------------------------------------------------------------
# TestReply
# ---------------------------------------------------------------------------


class TestReply:
    """Test replying in thread."""

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_reply_success(self, mock_run, agent):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "{}"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        ok = agent._reply_in_thread(101, "Fixed!", 42)
        assert ok is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "101" in str(call_args)

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_reply_failure(self, mock_run, agent):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Forbidden"
        mock_run.return_value = mock_result
        ok = agent._reply_in_thread(101, "Fixed!", 42)
        assert ok is False


# ---------------------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------------------


class TestDryRun:
    """Test that dry-run mode does not commit or reply."""

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_dry_run_no_commits_no_replies(self, mock_run, agent, tmp_repo):
        # Mock gh api to return comments
        def side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if "gh" in cmd and "api" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = json.dumps(SAMPLE_GH_COMMENTS[:2])  # rename + error handling
                mock_result.stderr = ""
            elif "git" in cmd and "diff" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "+ new line\n- old line"
                mock_result.stderr = ""
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = side_effect

        responses = agent.respond_to_reviews(pr_number=42, auto_fix=True, dry_run=True)

        # Should have processed actionable comments
        assert len(responses) >= 1

        # Verify no reply calls were made (no gh api POST to /replies)
        for call in mock_run.call_args_list:
            cmd = call[0][0] if call[0] else call[1].get("args", [])
            cmd_str = " ".join(str(c) for c in cmd)
            assert "replies" not in cmd_str, "Dry-run should not reply"
            assert "git commit" not in cmd_str, "Dry-run should not commit"
            assert "git push" not in cmd_str, "Dry-run should not push"


# ---------------------------------------------------------------------------
# TestFormatResponses
# ---------------------------------------------------------------------------


class TestFormatResponses:
    """Test the format_thread_responses helper."""

    def test_empty_responses(self):
        out = format_thread_responses([])
        assert "No actionable" in out

    def test_mixed_responses(self):
        responses = [
            ThreadResponse(comment_id=1, fix_applied=True, reply="Fixed", diff="+new\n-old"),
            ThreadResponse(comment_id=2, fix_applied=False, reply="Ack"),
            ThreadResponse(comment_id=3, fix_applied=False, reply="Error", error="file not found"),
        ]
        out = format_thread_responses(responses)
        assert "3 actionable" in out
        assert "Fixed:        1" in out
        assert "Acknowledged: 1" in out
        assert "Errors:       1" in out
        assert "FIXED" in out
        assert "ACK" in out
        assert "ERROR" in out

    def test_all_fixed(self):
        responses = [
            ThreadResponse(comment_id=1, fix_applied=True, reply="Fixed", diff="+x"),
            ThreadResponse(comment_id=2, fix_applied=True, reply="Fixed", diff="+y"),
        ]
        out = format_thread_responses(responses)
        assert "Fixed:        2" in out
        assert "Errors" not in out


# ---------------------------------------------------------------------------
# TestPushFixes
# ---------------------------------------------------------------------------


class TestPushFixes:
    """Test the push workflow."""

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_push_stages_and_commits(self, mock_run, agent):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        agent._changed_files = ["src/utils.py", "src/main.py"]
        result = agent._push_fixes(42)

        assert "2 fixed file(s)" in result
        # Should have called git add, git commit, git push
        calls = [" ".join(str(c) for c in call[0][0]) for call in mock_run.call_args_list]
        assert any("git add" in c for c in calls)
        assert any("git commit" in c for c in calls)
        assert any("git push" in c for c in calls)
        # Never force push
        for c in calls:
            assert "--force" not in c

    @patch("code_agents.git_ops.pr_thread_agent.subprocess.run")
    def test_push_no_files(self, mock_run, agent):
        agent._changed_files = []
        result = agent._push_fixes(42)
        assert "No files" in result
        mock_run.assert_not_called()
