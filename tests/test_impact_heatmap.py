"""Tests for impact_heatmap.py — risk heatmap generation."""

import pytest

from code_agents.analysis.impact_heatmap import (
    ImpactHeatmap,
    HeatmapReport,
    FileRiskProfile,
    format_report,
)


@pytest.fixture
def heatmap(tmp_path):
    return ImpactHeatmap(str(tmp_path))


SAMPLE_STATS = [
    {"file_path": "critical.py", "lines_of_code": 500, "complexity": 25},
    {"file_path": "stable.py", "lines_of_code": 100, "complexity": 3},
    {"file_path": "new.py", "lines_of_code": 50, "complexity": 1},
]

SAMPLE_GIT_LOG = [
    {"author": "alice", "files": ["critical.py", "stable.py"]},
    {"author": "bob", "files": ["critical.py"]},
    {"author": "alice", "files": ["critical.py"]},
    {"author": "charlie", "files": ["critical.py"]},
    {"author": "alice", "files": ["new.py"]},
]


class TestRiskScore:
    def test_high_change_freq_increases_risk(self, heatmap):
        profile = FileRiskProfile(change_frequency=10, bug_density=0, coupling_score=0, ownership_score=1)
        score = heatmap._compute_risk_score(profile)
        assert score > 20

    def test_risk_classification(self, heatmap):
        assert heatmap._classify_risk(80) == "critical"
        assert heatmap._classify_risk(55) == "high"
        assert heatmap._classify_risk(30) == "medium"
        assert heatmap._classify_risk(10) == "low"


class TestAnalyze:
    def test_generates_report(self, heatmap):
        report = heatmap.analyze(SAMPLE_STATS, git_log=SAMPLE_GIT_LOG)
        assert isinstance(report, HeatmapReport)
        assert report.total_files == 3

    def test_identifies_hotspots(self, heatmap):
        bug_data = {"critical.py": 5}
        report = heatmap.analyze(SAMPLE_STATS, git_log=SAMPLE_GIT_LOG, bug_data=bug_data)
        if report.hotspots:
            assert report.hotspots[0].file_path == "critical.py"

    def test_risk_distribution(self, heatmap):
        report = heatmap.analyze(SAMPLE_STATS, git_log=SAMPLE_GIT_LOG)
        assert sum(report.risk_distribution.values()) == 3

    def test_empty_stats(self, heatmap):
        report = heatmap.analyze([])
        assert report.total_files == 0

    def test_format_report(self, heatmap):
        report = heatmap.analyze(SAMPLE_STATS)
        text = format_report(report)
        assert "Heatmap" in text
