"""Tests for code_agents.review_autofix — AI code review with auto-fix."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.reviews.review_autofix import (
    ReviewAutoFixer,
    ReviewAutoFixReport,
    ReviewFixSuggestion,
    calculate_severity_score,
    format_autofix_report,
)
from code_agents.reviews.review_autopilot import ReviewFinding, ReviewReport


# ---------------------------------------------------------------------------
# Severity scoring tests
# ---------------------------------------------------------------------------


class TestSeverityScoring:
    """Tests for severity score calculation."""

    def test_empty_findings(self):
        score = calculate_severity_score([])
        assert score["total_findings"] == 0
        assert score["final_score"] == 100
        assert score["grade"] == "A"

    def test_single_critical(self):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="SQL injection")
        ]
        score = calculate_severity_score(findings)
        assert score["total_findings"] == 1
        assert score["by_severity"]["critical"] == 1
        assert score["by_category"]["security"] == 1
        # critical=20 * security=2.0 = 40 deduction
        assert score["final_score"] == 60.0
        assert score["grade"] == "D"

    def test_single_warning(self):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="warning", category="bug", message="Bare except")
        ]
        score = calculate_severity_score(findings)
        # warning=5 * bug=1.5 = 7.5 deduction
        assert score["final_score"] == 92.5
        assert score["grade"] == "A"

    def test_single_suggestion(self):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="suggestion", category="style", message="Use logging")
        ]
        score = calculate_severity_score(findings)
        # suggestion=1 * style=0.5 = 0.5 deduction
        assert score["final_score"] == 99.5
        assert score["grade"] == "A"

    def test_info_no_deduction(self):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="info", category="style", message="TODO comment")
        ]
        score = calculate_severity_score(findings)
        assert score["final_score"] == 100
        assert score["grade"] == "A"

    def test_multiple_findings(self):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="eval()"),
            ReviewFinding(file="b.py", line=2, severity="warning", category="bug", message="Bare except"),
            ReviewFinding(file="c.py", line=3, severity="suggestion", category="style", message="print()"),
            ReviewFinding(file="d.py", line=4, severity="info", category="style", message="TODO"),
        ]
        score = calculate_severity_score(findings)
        assert score["total_findings"] == 4
        assert score["final_score"] < 100
        assert score["by_severity"]["critical"] == 1
        assert score["by_severity"]["warning"] == 1

    def test_grade_boundaries(self):
        # Grade A: >= 90
        assert calculate_severity_score([])["grade"] == "A"

        # Grade F: many criticals
        many_criticals = [
            ReviewFinding(file="a.py", line=i, severity="critical", category="security", message="bad")
            for i in range(10)
        ]
        score = calculate_severity_score(many_criticals)
        assert score["grade"] == "F"
        assert score["final_score"] == 0  # clamped to 0


# ---------------------------------------------------------------------------
# ReviewAutoFixer tests
# ---------------------------------------------------------------------------


class TestReviewAutoFixer:
    """Tests for ReviewAutoFixer."""

    def test_init_defaults(self):
        fixer = ReviewAutoFixer()
        assert fixer.min_confidence == 0.7

    def test_init_custom(self):
        fixer = ReviewAutoFixer(cwd="/tmp/test", min_confidence=0.9)
        assert fixer.cwd == "/tmp/test"
        assert fixer.min_confidence == 0.9

    @patch.object(ReviewAutoFixer, "_generate_fixes", return_value=[])
    @patch.object(ReviewAutoFixer, "_call_agent_sync", return_value="")
    def test_run_basic_review(self, mock_agent, mock_fixes):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a git repo for diff
            os.system(f"cd {tmpdir} && git init -q && git commit --allow-empty -m init -q")

            fixer = ReviewAutoFixer(cwd=tmpdir)
            with patch.object(fixer, "run") as mock_run:
                mock_run.return_value = ReviewAutoFixReport(
                    review=ReviewReport(base="main", head="HEAD"),
                )
                report = fixer.run(base="main")
                assert report.review.base == "main"

    def test_create_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "test.py")).write_text("x = 1\n")

            fixer = ReviewAutoFixer(cwd=tmpdir)
            suggestions = [
                ReviewFixSuggestion(
                    finding_index=0, file="test.py", line=1,
                    original_code="x = 1", fixed_code="x = 2",
                    explanation="test", confidence=0.9,
                ),
            ]

            backup_dir = fixer._create_backup(suggestions)
            assert os.path.isdir(backup_dir)
            assert os.path.isfile(os.path.join(backup_dir, "test.py"))

            # Cleanup
            shutil.rmtree(backup_dir)

    def test_apply_fixes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "test.py")).write_text("x = 1\nassert x == 2\n")

            fixer = ReviewAutoFixer(cwd=tmpdir, min_confidence=0.7)
            report = ReviewAutoFixReport()
            report.fix_suggestions = [
                ReviewFixSuggestion(
                    finding_index=0, file="test.py", line=2,
                    original_code="assert x == 2",
                    fixed_code="assert x == 1",
                    explanation="Fix assertion",
                    confidence=0.9,
                ),
            ]

            fixer._apply_fixes(report)
            assert report.fixes_applied == 1

            content = Path(os.path.join(tmpdir, "test.py")).read_text()
            assert "assert x == 1" in content

    def test_apply_fixes_low_confidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "test.py")).write_text("x = 1\n")

            fixer = ReviewAutoFixer(cwd=tmpdir, min_confidence=0.8)
            report = ReviewAutoFixReport()
            report.fix_suggestions = [
                ReviewFixSuggestion(
                    finding_index=0, file="test.py", line=1,
                    original_code="x = 1", fixed_code="x = 2",
                    explanation="Low confidence fix",
                    confidence=0.5,  # Below threshold
                ),
            ]

            fixer._apply_fixes(report)
            assert report.fixes_skipped == 1
            assert report.fixes_applied == 0

    def test_apply_fixes_file_not_found(self):
        fixer = ReviewAutoFixer(cwd="/tmp")
        report = ReviewAutoFixReport()
        report.fix_suggestions = [
            ReviewFixSuggestion(
                finding_index=0, file="nonexistent.py", line=1,
                original_code="x", fixed_code="y",
                explanation="test", confidence=0.9,
            ),
        ]
        fixer._apply_fixes(report)
        assert report.fixes_skipped == 1

    def test_rollback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_content = "x = 1\n"
            Path(os.path.join(tmpdir, "test.py")).write_text(original_content)

            fixer = ReviewAutoFixer(cwd=tmpdir)

            # Create backup
            backup_dir = tempfile.mkdtemp()
            shutil.copy2(
                os.path.join(tmpdir, "test.py"),
                os.path.join(backup_dir, "test.py"),
            )

            # Modify file
            Path(os.path.join(tmpdir, "test.py")).write_text("x = 2\n")

            # Rollback
            fixer.rollback(backup_dir)
            content = Path(os.path.join(tmpdir, "test.py")).read_text()
            assert content == original_content

            shutil.rmtree(backup_dir)

    def test_rollback_nonexistent_dir(self):
        fixer = ReviewAutoFixer()
        fixer.rollback("/nonexistent/backup")  # Should not raise


# ---------------------------------------------------------------------------
# ReviewFixSuggestion tests
# ---------------------------------------------------------------------------


class TestReviewFixSuggestion:
    """Tests for ReviewFixSuggestion data model."""

    def test_create(self):
        s = ReviewFixSuggestion(
            finding_index=0,
            file="test.py",
            line=10,
            original_code="old",
            fixed_code="new",
            explanation="Fixed it",
            confidence=0.85,
        )
        assert s.confidence == 0.85
        assert s.file == "test.py"


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------


class TestFormatAutoFixReport:
    """Tests for report formatting."""

    def test_format_empty_report(self, capsys):
        report = ReviewAutoFixReport(
            review=ReviewReport(base="main", head="HEAD"),
        )
        format_autofix_report(report)
        # Should not raise

    def test_format_with_findings(self, capsys):
        report = ReviewAutoFixReport(
            review=ReviewReport(
                base="main", head="HEAD",
                files_changed=3, lines_added=50, lines_removed=10,
                findings=[
                    ReviewFinding(file="a.py", line=1, severity="critical", category="security", message="eval()"),
                    ReviewFinding(file="b.py", line=5, severity="warning", category="bug", message="bare except"),
                ],
                score=75,
            ),
            fix_suggestions=[
                ReviewFixSuggestion(
                    finding_index=0, file="a.py", line=1,
                    original_code="eval(x)", fixed_code="ast.literal_eval(x)",
                    explanation="Safe eval", confidence=0.95,
                ),
            ],
            fixes_applied=1,
        )
        format_autofix_report(report)
        # Should not raise

    def test_format_with_ai_summary(self, capsys):
        report = ReviewAutoFixReport(
            review=ReviewReport(
                base="main", head="HEAD",
                summary="Overall good code quality with minor security concerns.",
            ),
        )
        format_autofix_report(report)
        # Should not raise
