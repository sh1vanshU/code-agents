"""Tests for error_immunizer.py — bug fix to prevention checks."""

import pytest

from code_agents.testing.error_immunizer import (
    ErrorImmunizer,
    ImmunizationReport,
    PreventionCheck,
    format_report,
)


@pytest.fixture
def immunizer(tmp_path):
    return ErrorImmunizer(str(tmp_path))


SAMPLE_FIXES = [
    {"sha": "abc123", "file": "auth.py", "description": "Fix NoneType error, added is not None check",
     "diff": "if user is not None:"},
    {"sha": "def456", "file": "api.py", "description": "Fix NoneType AttributeError on empty response",
     "diff": "if response is None: return"},
    {"sha": "ghi789", "file": "db.py", "description": "Fix IndexError off by one in range",
     "diff": "range(len(items) - 1)"},
    {"sha": "jkl012", "file": "handler.py", "description": "Fix resource leak, added with open",
     "diff": "with open(path) as f:"},
]


class TestClassifyBug:
    def test_null_deref(self, immunizer):
        from code_agents.testing.error_immunizer import BugFix
        fix = BugFix(description="NoneType AttributeError", diff_content="if user is None: return")
        assert immunizer._classify_bug(fix) == "null_deref"

    def test_off_by_one(self, immunizer):
        from code_agents.testing.error_immunizer import BugFix
        fix = BugFix(description="IndexError out of range", diff_content="len(x) - 1")
        assert immunizer._classify_bug(fix) == "off_by_one"

    def test_resource_leak(self, immunizer):
        from code_agents.testing.error_immunizer import BugFix
        fix = BugFix(description="ResourceWarning file descriptor", diff_content="with open")
        assert immunizer._classify_bug(fix) == "resource_leak"


class TestAnalyze:
    def test_generates_checks(self, immunizer):
        report = immunizer.analyze(SAMPLE_FIXES)
        assert isinstance(report, ImmunizationReport)
        assert len(report.prevention_checks) >= 1

    def test_counts_bug_classes(self, immunizer):
        report = immunizer.analyze(SAMPLE_FIXES)
        assert "null_deref" in report.bug_classes_found
        assert report.bug_classes_found["null_deref"] >= 2

    def test_check_has_code(self, immunizer):
        report = immunizer.analyze(SAMPLE_FIXES)
        for check in report.prevention_checks:
            assert check.code
            assert check.bug_class

    def test_respects_existing_checks(self, immunizer):
        report = immunizer.analyze(SAMPLE_FIXES, existing_checks=["null_safety_check"])
        names = [c.name for c in report.prevention_checks]
        assert "null_safety_check" not in names

    def test_format_report(self, immunizer):
        report = immunizer.analyze(SAMPLE_FIXES)
        text = format_report(report)
        assert "Immunization" in text
