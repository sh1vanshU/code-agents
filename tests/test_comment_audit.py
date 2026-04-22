"""Tests for code_agents.comment_audit — Comment Quality Analyzer."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reviews.comment_audit import (
    CommentAuditor,
    CommentFinding,
    CommentAuditReport,
    format_comment_report,
    comment_report_to_json,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo with source files."""
    (tmp_path / ".git").mkdir()  # Fake git dir

    src = tmp_path / "src"
    src.mkdir()

    # File with obvious comments
    (src / "obvious.py").write_text(textwrap.dedent("""\
        # increment i
        i += 1
        # return the result
        return result
        # initialize counter
        counter = 0
        # loop through items
        for item in items:
            pass
    """))

    # File with TODOs
    (src / "todos.py").write_text(textwrap.dedent("""\
        # TODO: fix this later
        # FIXME: handle edge case
        # TODO JIRA-123: this is fine
        # HACK: temporary workaround
    """))

    # File with commented-out code
    (src / "commented.py").write_text(textwrap.dedent("""\
        def foo():
            pass
        # def old_foo():
        #     x = 1
        #     return x
        #     print("done")
        def bar():
            pass
    """))

    # Clean file
    (src / "clean.py").write_text(textwrap.dedent("""\
        def foo():
            # Business rule: discount applies only to premium users
            if user.is_premium:
                apply_discount()
    """))

    return tmp_path


class TestCommentAuditor:
    def test_finds_obvious_comments(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit(target="src/obvious.py")
        obvious = [f for f in report.findings if f.category == "obvious"]
        assert len(obvious) >= 3

    def test_finds_todo_without_ticket(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit(target="src/todos.py")
        todos = [f for f in report.findings if f.category == "todo_no_ticket"]
        # JIRA-123 TODO should not be flagged
        assert len(todos) >= 2
        messages = [f.comment_text for f in todos]
        assert not any("JIRA-123" in m for m in messages)

    def test_finds_commented_code(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit(target="src/commented.py")
        code_blocks = [f for f in report.findings if f.category == "commented_code"]
        assert len(code_blocks) >= 1
        assert code_blocks[0].severity == "high"

    def test_clean_file_no_findings(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit(target="src/clean.py")
        assert len(report.findings) == 0

    def test_audit_whole_repo(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit()
        assert report.files_scanned >= 4
        assert len(report.findings) >= 5

    def test_files_scanned_count(self, tmp_repo):
        auditor = CommentAuditor(cwd=str(tmp_repo))
        report = auditor.audit(target="src")
        assert report.files_scanned == 4


class TestCommentAuditReport:
    def test_by_category(self):
        report = CommentAuditReport(findings=[
            CommentFinding(file="a.py", line=1, category="obvious", severity="low", message="test"),
            CommentFinding(file="a.py", line=2, category="obvious", severity="low", message="test"),
            CommentFinding(file="a.py", line=3, category="todo_no_ticket", severity="medium", message="test"),
        ])
        assert report.by_category == {"obvious": 2, "todo_no_ticket": 1}

    def test_by_severity(self):
        report = CommentAuditReport(findings=[
            CommentFinding(file="a.py", line=1, category="obvious", severity="low", message="test"),
            CommentFinding(file="a.py", line=2, category="todo_no_ticket", severity="medium", message="test"),
            CommentFinding(file="a.py", line=3, category="commented_code", severity="high", message="test"),
        ])
        assert report.by_severity == {"low": 1, "medium": 1, "high": 1}


class TestCheckOutdated:
    @patch("subprocess.run")
    def test_outdated_git_failure(self, mock_run, tmp_repo):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        auditor = CommentAuditor(cwd=str(tmp_repo))
        fpath = tmp_repo / "src" / "obvious.py"
        result = auditor._check_outdated("src/obvious.py", fpath)
        assert isinstance(result, list)


class TestFormatting:
    def test_empty_report(self):
        report = CommentAuditReport()
        result = format_comment_report(report)
        assert "No comment quality issues" in result

    def test_report_with_findings(self):
        report = CommentAuditReport(
            findings=[
                CommentFinding(
                    file="test.py", line=5, category="obvious",
                    severity="low", message="Obvious comment",
                    comment_text="# increment i",
                ),
            ],
            files_scanned=1,
        )
        result = format_comment_report(report)
        assert "test.py" in result
        assert "Obvious" in result

    def test_json_export(self):
        report = CommentAuditReport(
            findings=[
                CommentFinding(
                    file="test.py", line=5, category="obvious",
                    severity="low", message="test",
                ),
            ],
            files_scanned=3,
        )
        data = comment_report_to_json(report)
        assert data["files_scanned"] == 3
        assert data["total_findings"] == 1
        assert len(data["findings"]) == 1
        assert data["findings"][0]["category"] == "obvious"


class TestEdgeCases:
    def test_nonexistent_target(self, tmp_path):
        auditor = CommentAuditor(cwd=str(tmp_path))
        report = auditor.audit(target="nonexistent")
        assert report.files_scanned == 0
        assert len(report.findings) == 0

    def test_binary_file_skipped(self, tmp_path):
        (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02\x03")
        auditor = CommentAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        # Should not crash
        assert isinstance(report.findings, list)

    def test_js_obvious_comments(self, tmp_path):
        (tmp_path / "test.js").write_text("// increment counter\ncounter++;\n")
        auditor = CommentAuditor(cwd=str(tmp_path))
        report = auditor.audit()
        obvious = [f for f in report.findings if f.category == "obvious"]
        assert len(obvious) >= 1
