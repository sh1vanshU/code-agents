"""Tests for self_tuning_ci.py — CI pipeline optimization."""

import pytest

from code_agents.devops.self_tuning_ci import (
    SelfTuningCI,
    CITuningReport,
    TestInfo,
    format_report,
)


@pytest.fixture
def tuner(tmp_path):
    return SelfTuningCI(str(tmp_path))


SAMPLE_CATALOG = [
    {"name": "test_auth", "file": "tests/test_auth.py", "avg_duration_ms": 100,
     "dependencies": ["src/auth.py"]},
    {"name": "test_db", "file": "tests/test_db.py", "avg_duration_ms": 2000,
     "dependencies": ["src/db.py"]},
    {"name": "test_api", "file": "tests/test_api.py", "avg_duration_ms": 500,
     "dependencies": ["src/api.py"]},
    {"name": "test_utils", "file": "tests/test_utils.py", "avg_duration_ms": 50,
     "dependencies": ["src/utils.py"]},
    {"name": "test_integration", "file": "tests/test_int.py", "avg_duration_ms": 10000,
     "dependencies": ["src/auth.py", "src/db.py", "src/api.py"]},
]


class TestFilterRelevant:
    def test_filters_by_dependency(self, tuner):
        tests = [tuner._parse_test(t) for t in SAMPLE_CATALOG]
        relevant = tuner._filter_relevant(tests, ["src/auth.py"])
        names = [t.name for t in relevant]
        assert "test_auth" in names
        assert "test_integration" in names

    def test_infers_relevance(self, tuner):
        tests = [tuner._parse_test(t) for t in SAMPLE_CATALOG]
        relevant = tuner._filter_relevant(tests, ["src/utils.py"])
        names = [t.name for t in relevant]
        assert "test_utils" in names


class TestPriority:
    def test_high_failure_high_priority(self, tuner):
        t = TestInfo(name="flaky", failure_rate=0.8, avg_duration_ms=100, dependencies=["a.py"])
        priority = tuner._compute_priority(t, ["a.py"])
        assert priority > 30

    def test_fast_test_bonus(self, tuner):
        fast = TestInfo(name="fast", avg_duration_ms=50, dependencies=[])
        slow = TestInfo(name="slow", avg_duration_ms=5000, dependencies=[])
        assert tuner._compute_priority(fast, []) > tuner._compute_priority(slow, [])


class TestAnalyze:
    def test_generates_plan(self, tuner):
        report = tuner.analyze(["src/auth.py"], SAMPLE_CATALOG)
        assert isinstance(report, CITuningReport)
        assert report.relevant_tests >= 1
        assert report.plan.savings_pct >= 0

    def test_stages_created(self, tuner):
        report = tuner.analyze(["src/auth.py", "src/db.py", "src/api.py"], SAMPLE_CATALOG)
        assert len(report.plan.stages) >= 1

    def test_no_changes(self, tuner):
        report = tuner.analyze(["nonexistent.py"], SAMPLE_CATALOG)
        assert report.relevant_tests == 0

    def test_format_report(self, tuner):
        report = tuner.analyze(["src/auth.py"], SAMPLE_CATALOG)
        text = format_report(report)
        assert "CI Tuning" in text
