"""Tests for Code Review Buddy."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.reviews.review_buddy import (
    ReviewBuddy,
    ReviewBuddyReport,
    ReviewFinding,
    ReviewScore,
    format_review,
)


class TestReviewBuddy:
    """Tests for ReviewBuddy."""

    def test_init_defaults(self):
        buddy = ReviewBuddy()
        assert buddy.staged_only is True
        assert buddy.auto_fix is False

    def test_init_custom(self):
        buddy = ReviewBuddy(cwd="/tmp", staged_only=False, auto_fix=True)
        assert buddy.cwd == "/tmp"
        assert buddy.staged_only is False

    def test_check_security_eval(self):
        buddy = ReviewBuddy()
        content = "result = eval(user_input)"
        findings = buddy._check_security("test.py", content)
        assert any(f.severity == "critical" and "eval" in f.message.lower() for f in findings)

    def test_check_security_hardcoded_password(self):
        buddy = ReviewBuddy()
        content = 'password = "super_secret_123"'
        findings = buddy._check_security("config.py", content)
        assert any(f.category == "security" for f in findings)

    def test_check_security_clean(self):
        buddy = ReviewBuddy()
        content = "x = 1 + 2\nprint(x)"
        findings = buddy._check_security("clean.py", content)
        security_findings = [f for f in findings if f.category == "security"]
        assert len(security_findings) == 0

    def test_check_quality_bare_except(self):
        buddy = ReviewBuddy()
        content = "try:\n    pass\nexcept:\n    pass"
        findings = buddy._check_quality("test.py", content)
        assert any("except" in f.message.lower() for f in findings)

    def test_check_quality_wildcard_import(self):
        buddy = ReviewBuddy()
        content = "from os import *"
        findings = buddy._check_quality("test.py", content)
        assert any("wildcard" in f.message.lower() for f in findings)

    def test_check_file_conventions_long_line(self):
        buddy = ReviewBuddy()
        content = "x = " + "a" * 250
        findings = buddy._check_file_conventions("test.py", content)
        assert any("chars" in f.message for f in findings)

    def test_calculate_score_no_findings(self):
        buddy = ReviewBuddy()
        score = buddy._calculate_score([])
        assert score.score == 100.0
        assert score.grade == "A"
        assert score.total_findings == 0

    def test_calculate_score_critical(self):
        buddy = ReviewBuddy()
        findings = [
            ReviewFinding(file="a.py", line=1, category="security", severity="critical", message="Bad"),
        ]
        score = buddy._calculate_score(findings)
        assert score.score <= 80
        assert score.grade in ("B", "C", "D")

    def test_calculate_score_mixed(self):
        buddy = ReviewBuddy()
        findings = [
            ReviewFinding(file="a.py", line=1, category="security", severity="critical", message="x"),
            ReviewFinding(file="a.py", line=2, category="style", severity="warning", message="y"),
            ReviewFinding(file="a.py", line=3, category="style", severity="info", message="z"),
        ]
        score = buddy._calculate_score(findings)
        assert score.by_severity["critical"] == 1
        assert score.by_severity["warning"] == 1
        assert score.by_severity["info"] == 1

    def test_check_missing_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            buddy = ReviewBuddy(cwd=tmpdir)
            findings = buddy._check_missing_tests(["src/auth.py"])
            assert any(f.category == "missing-test" for f in findings)


class TestFormatReview:
    """Tests for format_review."""

    def test_format_clean_report(self):
        report = ReviewBuddyReport(
            files_reviewed=5,
            findings=[],
            score=ReviewScore(total_findings=0, score=100.0, grade="A"),
        )
        output = format_review(report)
        assert "100" in output
        assert "Grade: A" in output

    def test_format_with_findings(self):
        report = ReviewBuddyReport(
            files_reviewed=2,
            findings=[
                ReviewFinding(file="a.py", line=10, category="security",
                              severity="critical", message="eval() is dangerous"),
            ],
            score=ReviewScore(
                total_findings=1, score=80.0, grade="B",
                by_severity={"critical": 1}, by_category={"security": 1},
            ),
        )
        output = format_review(report)
        assert "eval" in output
        assert "Security" in output
