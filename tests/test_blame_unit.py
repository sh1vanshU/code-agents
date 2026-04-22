"""Unit tests for code_agents/blame_investigator.py."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from code_agents.git_ops.blame_investigator import (
    BlameInvestigator,
    BlameResult,
    format_blame,
)


# ---------------------------------------------------------------------------
# BlameResult dataclass
# ---------------------------------------------------------------------------

class TestBlameResult:
    def test_defaults(self):
        r = BlameResult(file="foo.py", line=10)
        assert r.commit_hash == ""
        assert r.author == ""
        assert r.pr_number is None
        assert r.jira_ticket is None
        assert r.change_count == 0
        assert r.previous_versions == []


# ---------------------------------------------------------------------------
# _git_blame
# ---------------------------------------------------------------------------

class TestGitBlame:
    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_parses_porcelain_output(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "abc1234def5678 10 10 1\n"
                "author John Doe\n"
                "author-mail <john@example.com>\n"
                "author-time 1700000000\n"
                "summary Fix the login bug\n"
                "\tsome code here\n"
            ),
            stderr="",
        )
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="foo.py", line=10)
        inv._git_blame(result)
        assert result.author == "John Doe"
        assert result.author_email == "john@example.com"
        assert result.commit_hash == "abc1234def5678"
        assert result.commit_message == "Fix the login bug"
        assert result.date  # should be set

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_nonzero_returncode(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="foo.py", line=10)
        inv._git_blame(result)
        assert result.author == ""

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_exception_handled(self, mock_run, tmp_path):
        mock_run.side_effect = OSError("no git")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="foo.py", line=10)
        inv._git_blame(result)
        assert result.author == ""


# ---------------------------------------------------------------------------
# _get_line_content
# ---------------------------------------------------------------------------

class TestGetLineContent:
    def test_reads_line(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10\n")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="code.py", line=3)
        inv._get_line_content(result)
        assert result.line_content == "line3"
        assert len(result.surrounding_lines) > 0
        assert any(">>>" in sl for sl in result.surrounding_lines)

    def test_file_not_found(self, tmp_path):
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="missing.py", line=1)
        inv._get_line_content(result)
        assert result.line_content == ""

    def test_line_out_of_range(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("only one line\n")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="short.py", line=999)
        inv._get_line_content(result)
        assert result.line_content == ""


# ---------------------------------------------------------------------------
# _extract_pr_info
# ---------------------------------------------------------------------------

class TestExtractPRInfo:
    def test_no_commit_hash(self, tmp_path):
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="")
        inv._extract_pr_info(result)
        assert result.pr_number is None

    def test_pr_from_commit_message(self, tmp_path):
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc123",
                             commit_message="Merge pull request #42 from feat/x")
        with patch("code_agents.git_ops.blame_investigator.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            inv._extract_pr_info(result)
        assert result.pr_number == "42"

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_pr_from_merge_log(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="def456 Merge pull request #99 from feature/y\n",
        )
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc123",
                             commit_message="some change")
        inv._extract_pr_info(result)
        assert result.pr_number == "99"

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_pr_extraction_exception(self, mock_run, tmp_path):
        mock_run.side_effect = OSError("fail")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc123",
                             commit_message="no pr ref")
        inv._extract_pr_info(result)
        assert result.pr_number is None


# ---------------------------------------------------------------------------
# _extract_jira_ticket
# ---------------------------------------------------------------------------

class TestExtractJiraTicket:
    def test_from_commit_message(self, tmp_path):
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc",
                             commit_message="PROJ-1234 fix bug")
        inv._extract_jira_ticket(result)
        assert result.jira_ticket == "PROJ-1234"

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_from_branch_name(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="feature/JIRA-567-add-feature\nmain\n",
        )
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc",
                             commit_message="add feature")
        inv._extract_jira_ticket(result)
        assert result.jira_ticket == "JIRA-567"

    def test_no_ticket(self, tmp_path):
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="",
                             commit_message="just a fix")
        inv._extract_jira_ticket(result)
        assert result.jira_ticket is None

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_branch_lookup_exception(self, mock_run, tmp_path):
        mock_run.side_effect = OSError("fail")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=1, commit_hash="abc",
                             commit_message="no ticket")
        inv._extract_jira_ticket(result)
        assert result.jira_ticket is None


# ---------------------------------------------------------------------------
# _get_line_history
# ---------------------------------------------------------------------------

class TestGetLineHistory:
    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_parses_history(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "commit abc12\n"
                "Author: Jane <jane@ex.com>\n"
                "Date:   2024-01-15 10:00\n"
                "+new code here\n"
                "commit def34\n"
                "Author: Bob <bob@ex.com>\n"
                "Date:   2024-01-10 09:00\n"
                "+old code here\n"
            ),
        )
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=5)
        inv._get_line_history(result)
        assert result.change_count == 2
        assert len(result.previous_versions) == 2

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_nonzero_returncode(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=5)
        inv._get_line_history(result)
        assert result.change_count == 0

    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_exception(self, mock_run, tmp_path):
        mock_run.side_effect = OSError("fail")
        inv = BlameInvestigator(str(tmp_path))
        result = BlameResult(file="x.py", line=5)
        inv._get_line_history(result)
        assert result.change_count == 0


# ---------------------------------------------------------------------------
# investigate (integration)
# ---------------------------------------------------------------------------

class TestInvestigate:
    @patch("code_agents.git_ops.blame_investigator.subprocess.run")
    def test_full_investigation(self, mock_run, tmp_path):
        # Create a file for _get_line_content
        (tmp_path / "code.py").write_text("line1\nline2\nline3\n")
        # All subprocess calls return something reasonable
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "abc1234 1 1 1\n"
                "author Test User\n"
                "author-mail <test@test.com>\n"
                "author-time 1700000000\n"
                "summary PROJ-100 fix something via PR #5\n"
            ),
            stderr="",
        )
        inv = BlameInvestigator(str(tmp_path))
        result = inv.investigate("code.py", 2)
        assert isinstance(result, BlameResult)
        assert result.file == "code.py"
        assert result.line == 2


# ---------------------------------------------------------------------------
# format_blame
# ---------------------------------------------------------------------------

class TestFormatBlame:
    def test_minimal(self):
        r = BlameResult(file="x.py", line=10, commit_hash="abc12345", author="Dev", author_email="dev@x.com", date="2024-01-01")
        out = format_blame(r)
        assert "x.py:10" in out
        assert "Dev" in out
        assert "abc12345" in out

    def test_with_jira_and_pr(self):
        r = BlameResult(
            file="x.py", line=5, commit_hash="abc12345",
            author="Dev", author_email="dev@x.com", date="2024-01-01",
            commit_message="fix bug",
            jira_ticket="PROJ-123", pr_number="42", pr_title="Fix the thing",
        )
        out = format_blame(r)
        assert "PROJ-123" in out
        assert "PR #42" in out
        assert "Fix the thing" in out

    def test_with_history(self):
        r = BlameResult(
            file="x.py", line=5, commit_hash="abc12345",
            author="Dev", author_email="dev@x.com", date="2024-01-01",
            commit_message="change",
            change_count=3,
            previous_versions=[
                {"commit": "aaa", "author": "Alice", "date": "2024-01-01", "content": "old code"},
                {"commit": "bbb", "author": "Bob", "date": "2024-01-02"},
            ],
        )
        out = format_blame(r)
        assert "3 changes" in out
        assert "Alice" in out

    def test_with_surrounding_lines(self):
        r = BlameResult(
            file="x.py", line=5, commit_hash="abc12345",
            author="Dev", author_email="dev@x.com", date="2024-01-01",
            commit_message="change",
            surrounding_lines=[">>>    5 | code here", "      6 | more code"],
        )
        out = format_blame(r)
        assert "Code Context" in out
        assert "code here" in out
