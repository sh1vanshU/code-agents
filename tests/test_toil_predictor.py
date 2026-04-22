"""Tests for toil_predictor.py — manual process cost and automation ROI."""

import pytest

from code_agents.domain.toil_predictor import (
    ToilPredictor,
    ToilReport,
    AutomationProposal,
    format_report,
)


@pytest.fixture
def predictor():
    return ToilPredictor(hourly_rate=100.0)


SAMPLE_PROCESSES = [
    {"name": "Manual deploy", "category": "deploy", "frequency_per_week": 5,
     "duration_min": 30, "people": 1, "error_rate": 0.1},
    {"name": "Test data setup", "category": "testing", "frequency_per_week": 3,
     "duration_min": 60, "people": 2, "error_rate": 0.05},
    {"name": "Weekly report", "category": "reporting", "frequency_per_week": 1,
     "duration_min": 120, "people": 1},
    {"name": "Log investigation", "category": "monitoring", "frequency_per_week": 10,
     "duration_min": 15, "people": 1},
]


class TestGenerateProposal:
    def test_creates_proposal(self, predictor):
        from code_agents.domain.toil_predictor import ToilProcess
        proc = ToilProcess(name="deploy", category="deploy",
                           frequency_per_week=5, duration_min=30, people_involved=1)
        proposal = predictor._generate_proposal(proc)
        assert proposal is not None
        assert proposal.annual_time_saved_hours > 0
        assert proposal.roi_months > 0


class TestAnalyze:
    def test_full_analysis(self, predictor):
        report = predictor.analyze(SAMPLE_PROCESSES)
        assert isinstance(report, ToilReport)
        assert report.total_weekly_hours > 0
        assert report.total_annual_hours > 0

    def test_proposals_generated(self, predictor):
        report = predictor.analyze(SAMPLE_PROCESSES)
        assert len(report.proposals) >= 3

    def test_top_roi(self, predictor):
        report = predictor.analyze(SAMPLE_PROCESSES)
        assert len(report.top_roi_proposals) >= 1
        # Should be sorted by ROI
        rois = [p.roi_months for p in report.top_roi_proposals]
        assert rois == sorted(rois)

    def test_automatable_percentage(self, predictor):
        report = predictor.analyze(SAMPLE_PROCESSES)
        assert 0.0 <= report.automatable_pct <= 100.0

    def test_format_report(self, predictor):
        report = predictor.analyze(SAMPLE_PROCESSES)
        text = format_report(report)
        assert "Toil" in text

    def test_custom_hourly_rate(self):
        predictor = ToilPredictor(hourly_rate=200.0)
        report = predictor.analyze(SAMPLE_PROCESSES)
        assert report.total_annual_hours > 0
