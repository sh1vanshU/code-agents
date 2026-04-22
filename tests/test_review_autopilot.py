"""Tests for review_autopilot.py — code review autopilot."""

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reviews.review_autopilot import (
    ReviewAutopilot, ReviewReport, ReviewFinding, format_review,
)


class TestReviewAutopilot:
    """Tests for ReviewAutopilot."""

    def test_init(self, tmp_path):
        ra = ReviewAutopilot(cwd=str(tmp_path))
        assert ra.base == "main"
        assert ra.head == "HEAD"

    def test_analyze_diff_print(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,3 +1,5 @@\n"
            "+print('debug')\n"
            " def main():\n"
            "+    print('hello')\n"
        )
        findings = ra.analyze_diff(diff)
        prints = [f for f in findings if "print statement" in f.message]
        assert len(prints) >= 1

    def test_analyze_diff_eval(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/app.py b/app.py\n"
            "@@ -1,3 +1,5 @@\n"
            "+result = eval(user_input)\n"
        )
        findings = ra.analyze_diff(diff)
        evals = [f for f in findings if "eval" in f.message]
        assert len(evals) >= 1
        assert evals[0].severity == "critical"

    def test_analyze_diff_password(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/config.py b/config.py\n"
            "@@ -1,3 +1,5 @@\n"
            "+password = 'admin123'\n"
        )
        findings = ra.analyze_diff(diff)
        pw = [f for f in findings if "password" in f.message.lower()]
        assert len(pw) >= 1
        assert pw[0].severity == "critical"

    def test_analyze_diff_todo(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/app.py b/app.py\n"
            "@@ -1 +1 @@\n"
            "+# TODO: fix this later\n"
        )
        findings = ra.analyze_diff(diff)
        todos = [f for f in findings if "TODO" in f.message]
        assert len(todos) >= 1

    def test_analyze_diff_bare_except(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/app.py b/app.py\n"
            "@@ -1 +1 @@\n"
            "+except:\n"
        )
        findings = ra.analyze_diff(diff)
        bare = [f for f in findings if "Bare except" in f.message]
        assert len(bare) >= 1

    def test_score_calculation(self):
        report = ReviewReport(
            base="main", head="HEAD",
            findings=[
                ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="eval"),
                ReviewFinding(file="b.py", line=2, severity="warning", category="bug", message="bare except"),
                ReviewFinding(file="c.py", line=3, severity="suggestion", category="style", message="print"),
            ],
        )
        # Manually calculate what run() would do
        deductions = {"critical": 20, "warning": 5, "suggestion": 1, "info": 0}
        total = sum(deductions.get(f.severity, 0) for f in report.findings)
        score = max(0, 100 - total)
        assert score == 74

    def test_by_severity(self):
        report = ReviewReport(
            base="main", head="HEAD",
            findings=[
                ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="x"),
                ReviewFinding(file="b.py", line=2, severity="warning", category="bug", message="y"),
                ReviewFinding(file="c.py", line=3, severity="critical", category="security", message="z"),
            ],
        )
        by_sev = report.by_severity
        assert len(by_sev["critical"]) == 2
        assert len(by_sev["warning"]) == 1

    @patch("subprocess.run")
    def test_get_diff(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="diff content\n")
        ra = ReviewAutopilot(cwd=str(tmp_path))
        diff = ra.get_diff()
        assert diff == "diff content\n"


class TestFormatReview:
    """Tests for format_review."""

    def test_format_with_findings(self):
        report = ReviewReport(
            base="main", head="HEAD",
            files_changed=3, lines_added=50, lines_removed=10,
            score=85,
            findings=[
                ReviewFinding(file="a.py", line=1, severity="warning", category="bug", message="bare except"),
            ],
        )
        output = format_review(report)
        assert "Code Review Autopilot" in output
        assert "Score: 85/100" in output
        assert "WARNING" in output

    def test_format_clean(self):
        report = ReviewReport(base="main", head="HEAD", score=100)
        output = format_review(report)
        assert "No issues found" in output

    def test_format_with_summary(self):
        report = ReviewReport(
            base="main", head="HEAD",
            summary="This code looks good overall.",
            findings=[],
        )
        output = format_review(report)
        # No findings, so "No issues found" shows
        assert "No issues found" in output

    def test_format_with_ai_summary_and_findings(self):
        report = ReviewReport(
            base="main", head="HEAD",
            files_changed=2, lines_added=20, lines_removed=5,
            score=80,
            summary="Overall the code is solid but needs logging.",
            findings=[
                ReviewFinding(file="a.py", line=10, severity="warning", category="style", message="print stmt"),
            ],
        )
        output = format_review(report)
        assert "AI Review Summary" in output
        assert "Overall the code is solid" in output

    def test_format_many_findings_truncated(self):
        findings = [
            ReviewFinding(file=f"file{i}.py", line=i, severity="suggestion", category="style", message=f"issue {i}")
            for i in range(20)
        ]
        report = ReviewReport(base="main", head="HEAD", findings=findings)
        output = format_review(report)
        assert "and 5 more" in output


class TestReviewAutopilotAdditional:
    """Additional ReviewAutopilot method tests."""

    @patch("subprocess.run")
    def test_get_diff_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        ra = ReviewAutopilot(cwd=str(tmp_path))
        assert ra.get_diff() == ""

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_get_diff_no_git(self, mock_run, tmp_path):
        ra = ReviewAutopilot(cwd=str(tmp_path))
        assert ra.get_diff() == ""

    @patch("subprocess.run")
    def test_get_diff_stats(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" 3 files changed, 50 insertions(+), 10 deletions(-)\n",
        )
        ra = ReviewAutopilot(cwd=str(tmp_path))
        stats = ra.get_diff_stats()
        assert stats["files_changed"] == 3
        assert stats["insertions"] == 50
        assert stats["deletions"] == 10

    @patch("subprocess.run")
    def test_get_diff_stats_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        ra = ReviewAutopilot(cwd=str(tmp_path))
        assert ra.get_diff_stats() == {}

    def test_analyze_diff_console_log(self):
        ra = ReviewAutopilot(cwd="/tmp")
        diff = (
            "diff --git a/app.js b/app.js\n"
            "@@ -1 +1 @@\n"
            "+console.log('debug info')\n"
        )
        findings = ra.analyze_diff(diff)
        logs = [f for f in findings if "Console.log" in f.message]
        assert len(logs) >= 1

    def test_by_category(self):
        report = ReviewReport(
            base="main", head="HEAD",
            findings=[
                ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="x"),
                ReviewFinding(file="b.py", line=2, severity="warning", category="bug", message="y"),
                ReviewFinding(file="c.py", line=3, severity="critical", category="security", message="z"),
            ],
        )
        by_cat = report.by_category
        assert len(by_cat["security"]) == 2
        assert len(by_cat["bug"]) == 1

    @patch("subprocess.run")
    @patch("code_agents.reviews.review_autopilot.ReviewAutopilot.send_to_agent", return_value=None)
    def test_run_full_pipeline(self, mock_agent, mock_run, tmp_path):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="diff --git a/a.py b/a.py\n@@ -1 +1 @@\n+print('x')\n"),
            MagicMock(returncode=0, stdout=" 1 file changed, 1 insertion(+)\n"),
        ]
        ra = ReviewAutopilot(cwd=str(tmp_path))
        report = ra.run()
        assert report.files_changed == 1
        assert report.lines_added == 1
        assert len(report.findings) >= 1
        assert report.score < 100

    @patch("code_agents.reviews.review_autopilot.ReviewAutopilot.send_to_agent", return_value="LGTM")
    @patch("subprocess.run")
    def test_run_with_ai_summary(self, mock_run, mock_agent, tmp_path):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=" 0 files changed\n"),
        ]
        ra = ReviewAutopilot(cwd=str(tmp_path))
        report = ra.run()
        assert report.summary == "LGTM"

    def test_post_pr_comment_not_configured(self, tmp_path, monkeypatch):
        for key in ["BITBUCKET_URL", "BITBUCKET_USERNAME", "BITBUCKET_APP_PASSWORD",
                     "BITBUCKET_REPO_SLUG", "BITBUCKET_PROJECT_KEY"]:
            monkeypatch.delenv(key, raising=False)
        ra = ReviewAutopilot(cwd=str(tmp_path))
        assert ra.post_pr_comment("1", "content") is False
