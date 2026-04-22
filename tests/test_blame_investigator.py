"""Tests for blame_investigator.py — deep blame investigation."""

from __future__ import annotations

import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from code_agents.git_ops.blame_investigator import (
    BlameInvestigator,
    BlameResult,
    format_blame,
)


class TestBlameResult:
    """BlameResult dataclass defaults and fields."""

    def test_defaults(self):
        r = BlameResult(file="app.py", line=42)
        assert r.file == "app.py"
        assert r.line == 42
        assert r.commit_hash == ""
        assert r.author == ""
        assert r.pr_number is None
        assert r.jira_ticket is None
        assert r.change_count == 0
        assert r.previous_versions == []
        assert r.surrounding_lines == []

    def test_fields_set(self):
        r = BlameResult(
            file="main.py", line=10,
            commit_hash="abc1234", author="Alice",
            pr_number="55", jira_ticket="PROJ-123",
        )
        assert r.commit_hash == "abc1234"
        assert r.pr_number == "55"
        assert r.jira_ticket == "PROJ-123"


class TestExtractPrInfo:
    """PR extraction from commit messages and merge commits."""

    def _investigator(self):
        return BlameInvestigator(cwd="/tmp")

    def test_pr_from_commit_message(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="Fix auth flow (PR #42)")
        inv._extract_pr_info(result)
        assert result.pr_number == "42"

    def test_pr_merge_format(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="Merge pull request #99 from feature/foo")
        inv._extract_pr_info(result)
        assert result.pr_number == "99"

    def test_no_pr_in_message(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="fix typo in readme")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            inv._extract_pr_info(result)
        assert result.pr_number is None

    def test_no_commit_hash_skips(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="")
        inv._extract_pr_info(result)
        assert result.pr_number is None

    def test_pr_from_merge_commit_log(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="small fix")
        merge_output = "def5678 Merge pull request #77 from feature/bar"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=merge_output, stderr="")
            inv._extract_pr_info(result)
        assert result.pr_number == "77"
        assert "Merge pull request #77" in result.pr_title


class TestExtractJiraTicket:
    """Jira ticket extraction from commit messages and branches."""

    def _investigator(self):
        return BlameInvestigator(cwd="/tmp")

    def test_jira_from_commit_message(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="PROJ-456: add validation")
        inv._extract_jira_ticket(result)
        assert result.jira_ticket == "PROJ-456"

    def test_jira_from_branch(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="add validation")
        branch_output = "feature/TEAM-789-auth-flow\nmain"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=branch_output, stderr="")
            inv._extract_jira_ticket(result)
        assert result.jira_ticket == "TEAM-789"

    def test_no_jira_ticket(self):
        inv = self._investigator()
        result = BlameResult(file="x.py", line=1, commit_hash="abc1234",
                             commit_message="fix typo")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
            inv._extract_jira_ticket(result)
        assert result.jira_ticket is None

    def test_jira_various_formats(self):
        inv = self._investigator()
        for msg, expected in [
            ("AB-1 init", "AB-1"),
            ("[PAYMENTS-999] fix", "PAYMENTS-999"),
            ("feat(CORE-42): add", "CORE-42"),
        ]:
            result = BlameResult(file="x.py", line=1, commit_hash="abc", commit_message=msg)
            inv._extract_jira_ticket(result)
            assert result.jira_ticket == expected, f"Failed for: {msg}"


class TestGetLineContent:
    """Line content reading and surrounding context."""

    def _investigator(self, tmp_path):
        return BlameInvestigator(cwd=str(tmp_path))

    def test_reads_correct_line(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        inv = self._investigator(tmp_path)
        result = BlameResult(file="test.py", line=3)
        inv._get_line_content(result)
        assert result.line_content == "line3"

    def test_surrounding_lines(self, tmp_path):
        f = tmp_path / "big.py"
        content = "\n".join(f"line {i}" for i in range(1, 21))
        f.write_text(content)
        inv = self._investigator(tmp_path)
        result = BlameResult(file="big.py", line=10)
        inv._get_line_content(result)
        assert any(">>>" in s and "line 10" in s for s in result.surrounding_lines)
        # Should have context lines before and after
        assert len(result.surrounding_lines) >= 5

    def test_file_not_found(self, tmp_path):
        inv = self._investigator(tmp_path)
        result = BlameResult(file="nonexistent.py", line=1)
        inv._get_line_content(result)
        assert result.line_content == ""
        assert result.surrounding_lines == []

    def test_line_out_of_range(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("only one line\n")
        inv = self._investigator(tmp_path)
        result = BlameResult(file="short.py", line=999)
        inv._get_line_content(result)
        assert result.line_content == ""

    def test_first_line(self, tmp_path):
        f = tmp_path / "first.py"
        f.write_text("first\nsecond\nthird\n")
        inv = self._investigator(tmp_path)
        result = BlameResult(file="first.py", line=1)
        inv._get_line_content(result)
        assert result.line_content == "first"
        assert any(">>>" in s and "first" in s for s in result.surrounding_lines)


class TestFormatBlame:
    """format_blame output formatting."""

    def test_basic_format(self):
        r = BlameResult(
            file="app.py", line=42,
            commit_hash="abc12345678", author="Alice", author_email="alice@co.com",
            date="2025-01-15 10:30", commit_message="Fix auth bug",
        )
        output = format_blame(r)
        assert "BLAME: app.py:42" in output
        assert "Alice" in output
        assert "alice@co.com" in output
        assert "abc12345" in output
        assert "Fix auth bug" in output

    def test_format_with_jira(self):
        r = BlameResult(file="x.py", line=1, jira_ticket="PROJ-123",
                        commit_hash="abc12345", commit_message="fix")
        output = format_blame(r)
        assert "Jira: PROJ-123" in output

    def test_format_with_pr(self):
        r = BlameResult(file="x.py", line=1, pr_number="42", pr_title="Add feature",
                        commit_hash="abc12345", commit_message="fix")
        output = format_blame(r)
        assert "PR #42" in output
        assert "Add feature" in output

    def test_format_with_history(self):
        r = BlameResult(
            file="x.py", line=1, commit_hash="abc12345", commit_message="fix",
            change_count=3,
            previous_versions=[
                {"commit": "abc12", "author": "Alice", "date": "2025-01-01", "content": "old code"},
                {"commit": "def34", "author": "Bob", "date": "2025-02-01"},
            ],
        )
        output = format_blame(r)
        assert "Line History (3 changes)" in output
        assert "Alice" in output
        assert "old code" in output

    def test_format_with_context(self):
        r = BlameResult(
            file="x.py", line=5, commit_hash="abc12345", commit_message="fix",
            surrounding_lines=["      4 | line4", ">>>   5 | line5", "      6 | line6"],
        )
        output = format_blame(r)
        assert "Code Context:" in output
        assert ">>> " in output


class TestInvestigate:
    """Full investigate flow with mocked subprocess."""

    def test_investigate_mocked(self, tmp_path):
        # Create file
        f = tmp_path / "app.py"
        f.write_text("import os\ndef main():\n    print('hello')\n")

        blame_output = textwrap.dedent("""\
            abc1234567890 3 3 1
            author Alice
            author-mail <alice@co.com>
            author-time 1700000000
            author-tz +0000
            committer Alice
            committer-mail <alice@co.com>
            committer-time 1700000000
            committer-tz +0000
            summary PROJ-42: add greeting
            filename app.py
            \tprint('hello')
        """)

        log_output = textwrap.dedent("""\
            commit abc1234567890
            Author: Alice <alice@co.com>
            Date:   2024-01-15

            +    print('hello')
        """)

        def mock_run(cmd, **kwargs):
            if "blame" in cmd:
                return MagicMock(returncode=0, stdout=blame_output, stderr="")
            elif "log" in cmd and "--merges" in cmd:
                return MagicMock(returncode=0, stdout="def5678 Merge pull request #55 from feature/greet\n", stderr="")
            elif "log" in cmd:
                return MagicMock(returncode=0, stdout=log_output, stderr="")
            elif "branch" in cmd:
                return MagicMock(returncode=0, stdout="main\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        inv = BlameInvestigator(cwd=str(tmp_path))
        with patch("subprocess.run", side_effect=mock_run):
            result = inv.investigate("app.py", 3)

        assert result.author == "Alice"
        assert result.jira_ticket == "PROJ-42"
        assert result.pr_number == "55"
        assert result.line_content == "    print('hello')"
        assert result.change_count >= 1

    def test_investigate_git_blame_fails(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("code\n")
        inv = BlameInvestigator(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repo")
            result = inv.investigate("x.py", 1)
        assert result.commit_hash == ""
        assert result.line_content == "code"


class TestSlashCommand:
    """Test /blame slash command integration."""

    def test_blame_no_args(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        state = {"agent": "code-reasoning", "history": []}
        result = _handle_command("/blame", state, "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_blame_missing_line(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        state = {"agent": "code-reasoning", "history": []}
        result = _handle_command("/blame app.py", state, "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_blame_invalid_line(self, capsys):
        from code_agents.chat.chat_slash import _handle_command
        state = {"agent": "code-reasoning", "history": []}
        result = _handle_command("/blame app.py abc", state, "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Invalid line number" in out

    def test_blame_valid_args(self, tmp_path):
        from code_agents.chat.chat_slash import _handle_command
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\n")
        state = {"agent": "code-reasoning", "history": [], "repo_path": str(tmp_path)}

        def mock_run(cmd, **kwargs):
            return MagicMock(returncode=1, stdout="", stderr="not a git repo")

        with patch("subprocess.run", side_effect=mock_run):
            result = _handle_command(f"/blame test.py 1", state, "http://localhost:8000")

        assert result == "exec_feedback"
        assert "_exec_feedback" in state
        assert "BLAME: test.py:1" in state["_exec_feedback"]["output"]


class TestGetLineContentException:
    """Cover lines 111-112: exception during file read in _get_line_content."""

    def test_file_read_error(self, tmp_path):
        from code_agents.git_ops.blame_investigator import BlameInvestigator, BlameResult
        bi = BlameInvestigator(cwd=str(tmp_path))
        result = BlameResult(file="test.py", line=1, commit_hash="abc123")
        # Create a file so os.path.exists passes
        f = tmp_path / "test.py"
        f.write_text("line 1\n")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            bi._get_line_content(result)
        assert result.surrounding_lines == []
