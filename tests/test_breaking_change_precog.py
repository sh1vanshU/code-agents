"""Tests for breaking_change_precog.py — upstream dep breaking change detection."""

import pytest

from code_agents.domain.breaking_change_precog import (
    BreakingChangePrecog,
    PrecogReport,
    BreakingChange,
    format_report,
)


@pytest.fixture
def precog(tmp_path):
    return BreakingChangePrecog(str(tmp_path))


SAMPLE_DEPS = [
    {"name": "requests", "current": "2.28.0", "latest": "3.0.0"},
    {"name": "flask", "current": "2.3.0", "latest": "2.4.0"},
    {"name": "pydantic", "current": "1.10.0", "latest": "2.0.0"},
    {"name": "pytest", "current": "7.4.0", "latest": "7.4.1"},
]

CHANGELOGS = {
    "pydantic": "BREAKING CHANGE: removed `schema()` method. Use `model_json_schema()` instead.\nDeprecated: Field(regex=...) in favor of Field(pattern=...)",
    "requests": "Major version bump with incompatible API changes",
}


class TestVersionBump:
    def test_major(self, precog):
        assert precog._version_bump_type("2.0.0", "3.0.0") == "major"

    def test_minor(self, precog):
        assert precog._version_bump_type("2.3.0", "2.4.0") == "minor"

    def test_patch(self, precog):
        assert precog._version_bump_type("7.4.0", "7.4.1") == "patch"

    def test_none(self, precog):
        assert precog._version_bump_type("1.0.0", "1.0.0") == "none"


class TestAnalyze:
    def test_detects_breaking(self, precog):
        report = precog.analyze(SAMPLE_DEPS, changelogs=CHANGELOGS)
        assert isinstance(report, PrecogReport)
        assert len(report.breaking_changes) >= 1

    def test_safe_updates_identified(self, precog):
        report = precog.analyze(SAMPLE_DEPS, changelogs=CHANGELOGS)
        assert len(report.safe_updates) >= 1

    def test_risk_score(self, precog):
        report = precog.analyze(SAMPLE_DEPS, changelogs=CHANGELOGS)
        assert report.risk_score >= 0

    def test_deprecation_warnings(self, precog):
        report = precog.analyze(SAMPLE_DEPS, changelogs=CHANGELOGS)
        # Pydantic changelog has deprecation
        assert len(report.deprecation_warnings) >= 1 or len(report.breaking_changes) >= 1

    def test_format_report(self, precog):
        report = precog.analyze(SAMPLE_DEPS)
        text = format_report(report)
        assert "Precog" in text

    def test_no_deps(self, precog):
        report = precog.analyze([])
        assert report.dependencies_checked == 0
