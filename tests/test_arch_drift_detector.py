"""Tests for arch_drift_detector.py — architectural violation detection."""

import pytest

from code_agents.analysis.arch_drift_detector import (
    ArchDriftDetector,
    ArchRule,
    DriftReport,
    Violation,
    format_report,
)


@pytest.fixture
def detector(tmp_path):
    return ArchDriftDetector(str(tmp_path))


SAMPLE_FILES = {
    "code_agents/routers/user_router.py": "from code_agents.cli import something\nimport psycopg2\n",
    "code_agents/services/user_service.py": "import logging\nlogger = logging.getLogger(__name__)\n",
    "code_agents/utils.py": 'print("debug output")\nlogger.info("proper")\n',
    "tests/test_user.py": "def test_user(): pass\n",
    "tests/user_tests.py": "def test_user(): pass\n",
}


class TestImportRule:
    def test_detects_forbidden_import(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        violations = [v for v in report.violations if v.rule_id == "layer_separation"]
        assert len(violations) >= 1

    def test_detects_direct_db(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        violations = [v for v in report.violations if v.rule_id == "no_direct_db_in_router"]
        assert len(violations) >= 1


class TestPatternRule:
    def test_detects_print(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        violations = [v for v in report.violations if v.rule_id == "no_print_in_lib"]
        assert len(violations) >= 1


class TestCustomRules:
    def test_custom_rule(self, tmp_path):
        rule = ArchRule(
            id="no_star_import",
            name="No Star Import",
            rule_type="pattern",
            source_pattern=r".*\.py$",
            constraint="no_pattern:^import \\*",
            severity="warning",
        )
        detector = ArchDriftDetector(str(tmp_path), custom_rules=[rule])
        report = detector.analyze({"a.py": "import *\n"})
        assert any(v.rule_id == "no_star_import" for v in report.violations)


class TestAnalyze:
    def test_computes_drift_score(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        assert isinstance(report, DriftReport)
        assert 0.0 <= report.drift_score <= 1.0

    def test_counts_compliant(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        assert report.compliant_files + report.non_compliant_files == len(SAMPLE_FILES)

    def test_format_report(self, detector):
        report = detector.analyze(SAMPLE_FILES)
        text = format_report(report)
        assert "Drift" in text
