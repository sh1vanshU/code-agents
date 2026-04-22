"""Tests for the Code Archaeology module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from code_agents.knowledge.code_archaeology import (
    ArchaeologyReport,
    CodeArchaeologist,
    format_report_rich,
)


@pytest.fixture
def archaeologist(tmp_path):
    """Create a CodeArchaeologist with a temp working directory."""
    # Create a sample file
    sample = tmp_path / "src" / "api.py"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("def process_payment(amount):\n    return amount\n")
    return CodeArchaeologist(cwd=str(tmp_path))


class TestArchaeologyReport:
    """Test ArchaeologyReport dataclass."""

    def test_default_values(self):
        report = ArchaeologyReport(file_path="test.py", line=10, function="foo")
        assert report.file_path == "test.py"
        assert report.line == 10
        assert report.function == "foo"
        assert report.blame == {}
        assert report.pr is None
        assert report.issue is None
        assert report.history == []
        assert report.intent == ""
        assert report.error == ""

    def test_to_dict(self):
        report = ArchaeologyReport(
            file_path="x.py", line=5, function="bar",
            blame={"commit": "abc123", "author": "Alice"},
            issue="PROJ-42",
        )
        d = report.to_dict()
        assert d["file_path"] == "x.py"
        assert d["blame"]["commit"] == "abc123"
        assert d["issue"] == "PROJ-42"

    def test_summary_with_blame(self):
        report = ArchaeologyReport(
            file_path="x.py", line=5, function="",
            blame={"commit": "abc123def", "author": "Alice", "date": "2025-01-15", "message": "fix bug"},
        )
        s = report.summary()
        assert "x.py" in s
        assert "Alice" in s
        assert "abc123def" in s

    def test_summary_with_history(self):
        report = ArchaeologyReport(
            file_path="x.py", line=0, function="foo",
            history=[
                {"commit": "aaa", "author": "Bob", "date": "2025-01-10", "message": "init"},
                {"commit": "bbb", "author": "Carol", "date": "2025-01-11", "message": "refactor"},
            ],
        )
        s = report.summary()
        assert "Change History" in s
        assert "2 commits" in s

    def test_summary_error(self):
        report = ArchaeologyReport(file_path="x.py", line=0, function="", error="File not found")
        s = report.summary()
        assert "File not found" in s

    def test_summary_with_pr(self):
        report = ArchaeologyReport(
            file_path="x.py", line=5, function="",
            pr={"number": 42, "title": "Fix payment flow", "url": "https://github.com/pr/42"},
        )
        s = report.summary()
        assert "#42" in s
        assert "Fix payment flow" in s


class TestCodeArchaeologist:
    """Test CodeArchaeologist methods."""

    def test_investigate_file_not_found(self, archaeologist):
        report = archaeologist.investigate("nonexistent.py", line=1)
        assert report.error == "File not found: nonexistent.py"

    @patch("code_agents.knowledge.code_archaeology.subprocess.run")
    def test_git_blame_success(self, mock_run, archaeologist):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "abc123def456 10 10 1\n"
                "author Alice\n"
                "author-time 1700000000\n"
                "summary fix payment processing\n"
                "\tcode line here\n"
            ),
        )
        blame = archaeologist._git_blame("src/api.py", 10)
        assert blame["commit"] == "abc123def456"
        assert blame["author"] == "Alice"
        assert "fix payment" in blame["message"]

    @patch("code_agents.knowledge.code_archaeology.subprocess.run")
    def test_git_blame_failure(self, mock_run, archaeologist):
        mock_run.return_value = MagicMock(returncode=128, stderr="fatal: no such path")
        blame = archaeologist._git_blame("nonexistent.py", 1)
        assert blame == {}

    def test_find_issue_jira(self, archaeologist):
        assert archaeologist._find_issue("PROJ-123: fix bug") == "PROJ-123"
        assert archaeologist._find_issue("PAYMENT-42 add retry") == "PAYMENT-42"

    def test_find_issue_github(self, archaeologist):
        assert archaeologist._find_issue("fixes #789") == "#789"
        assert archaeologist._find_issue("closes #42") == "#42"
        assert archaeologist._find_issue("ref #100") == "#100"

    def test_find_issue_no_match(self, archaeologist):
        assert archaeologist._find_issue("just a commit message") is None
        assert archaeologist._find_issue("") is None

    @patch("code_agents.knowledge.code_archaeology.subprocess.run")
    def test_find_pr_with_gh(self, mock_run, archaeologist):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"number": 42, "title": "Fix payment", "url": "https://github.com/pr/42", "author": {"login": "alice"}}]',
        )
        pr = archaeologist._find_pr("abc123")
        assert pr is not None
        assert pr["number"] == 42
        assert pr["title"] == "Fix payment"

    @patch("code_agents.knowledge.code_archaeology.subprocess.run")
    def test_find_pr_not_found(self, mock_run, archaeologist):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        pr = archaeologist._find_pr("abc123")
        assert pr is None

    @patch("code_agents.knowledge.code_archaeology.subprocess.run")
    def test_trace_file_history(self, mock_run, archaeologist):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123|Alice|2025-01-10 10:00:00|init\ndef456|Bob|2025-01-11 11:00:00|refactor\n",
        )
        history = archaeologist._trace_file_history("src/api.py")
        assert len(history) == 2
        assert history[0]["author"] == "Alice"
        assert history[1]["author"] == "Bob"

    def test_reconstruct_intent_with_blame(self, archaeologist):
        blame = {"author": "Alice", "date": "2025-01-15", "message": "fix payment bug", "full_message": "fix payment bug"}
        intent = archaeologist._reconstruct_intent(blame, None, None, [])
        assert "Alice" in intent
        assert "fix payment bug" in intent

    def test_reconstruct_intent_hotspot(self, archaeologist):
        history = [{"author": f"dev{i}", "commit": f"sha{i}"} for i in range(6)]
        intent = archaeologist._reconstruct_intent({}, None, None, history)
        assert "hotspot" in intent.lower()

    def test_reconstruct_intent_empty(self, archaeologist):
        intent = archaeologist._reconstruct_intent({}, None, None, [])
        assert "Unable to reconstruct" in intent


class TestFormatReportRich:
    """Test rich formatting of reports."""

    def test_format_error_report(self):
        report = ArchaeologyReport(file_path="x.py", line=0, function="", error="Not found")
        output = format_report_rich(report)
        assert "Not found" in output
        assert "x.py" in output

    def test_format_full_report(self):
        report = ArchaeologyReport(
            file_path="api.py", line=45, function="process",
            blame={"commit": "abc123", "author": "Alice", "date": "2025-01-15", "message": "fix"},
            pr={"number": 42, "title": "Fix payment", "url": ""},
            issue="PROJ-123",
            history=[{"commit": "aaa", "author": "Bob", "date": "2025-01-10", "message": "init"}],
            intent="This was a bug fix.",
        )
        output = format_report_rich(report)
        assert "api.py" in output
        assert "Alice" in output
        assert "#42" in output
        assert "PROJ-123" in output
        assert "bug fix" in output
