"""Tests for the TechDebtScanner module."""

import textwrap
import pytest
from code_agents.reviews.techdebt_scanner import (
    TechDebtScanner, TechDebtScannerConfig, TechDebtScannerReport, format_techdebt_report,
)


class TestTechDebtScanner:
    def test_detect_todo(self, tmp_path):
        source = '# TODO: refactor this function\ndef old(): pass\n'
        (tmp_path / "legacy.py").write_text(source)
        scanner = TechDebtScanner(TechDebtScannerConfig(cwd=str(tmp_path), min_priority=0))
        report = scanner.scan()
        assert report.total_items >= 1
        assert any(i.category == "todo" for i in report.items)

    def test_detect_fixme(self, tmp_path):
        source = '# FIXME: broken edge case\ndef buggy(): pass\n'
        (tmp_path / "bug.py").write_text(source)
        scanner = TechDebtScanner(TechDebtScannerConfig(cwd=str(tmp_path), min_priority=0))
        report = scanner.scan()
        assert any(i.description == "FIXME indicates known broken behaviour" for i in report.items)

    def test_detect_broad_except(self, tmp_path):
        source = textwrap.dedent('''\
            try:
                risky()
            except Exception:
                pass
        ''')
        (tmp_path / "risky.py").write_text(source)
        scanner = TechDebtScanner(TechDebtScannerConfig(cwd=str(tmp_path), min_priority=0))
        report = scanner.scan()
        assert any(i.category == "error_handling" for i in report.items)
        assert any("except" in i.description.lower() or "Exception" in i.description for i in report.items)

    def test_priority_scoring(self, tmp_path):
        source = '# FIXME: critical bug\n# TODO: nice to have\n'
        (tmp_path / "mixed.py").write_text(source)
        scanner = TechDebtScanner(TechDebtScannerConfig(cwd=str(tmp_path), min_priority=0))
        report = scanner.scan()
        for item in report.items:
            assert item.priority_score > 0
        # Items should be sorted by priority (ROI) descending
        scores = [i.priority_score for i in report.items]
        assert scores == sorted(scores, reverse=True)

    def test_effort_estimation(self, tmp_path):
        source = '# HACK: workaround\n'
        (tmp_path / "hack.py").write_text(source)
        scanner = TechDebtScanner(TechDebtScannerConfig(cwd=str(tmp_path), min_priority=0))
        report = scanner.scan()
        assert report.total_effort_hours > 0

    def test_format_report(self):
        report = TechDebtScannerReport(
            files_scanned=20, total_items=8, total_effort_hours=15.0,
            category_breakdown={"todo": 3, "complexity": 5},
            severity_breakdown={"medium": 5, "high": 3},
            summary="done",
        )
        output = format_techdebt_report(report)
        assert "Tech Debt Scanner" in output
        assert "Total effort" in output
        assert "By category" in output
