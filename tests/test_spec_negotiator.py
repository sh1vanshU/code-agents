"""Tests for spec_negotiator.py — alternative specs with tradeoffs."""

import pytest

from code_agents.knowledge.spec_negotiator import (
    SpecNegotiator,
    NegotiationReport,
    SpecAlternative,
    format_report,
)


@pytest.fixture
def negotiator():
    return SpecNegotiator()


class TestDetectAmbiguities:
    def test_detects_scope_ambiguity(self, negotiator):
        ambs = negotiator._detect_ambiguities("The system should possibly handle etc.")
        types = [a.ambiguity_type for a in ambs]
        assert "scope" in types

    def test_detects_constraint_ambiguity(self, negotiator):
        ambs = negotiator._detect_ambiguities("The API must be fast and scalable")
        types = [a.ambiguity_type for a in ambs]
        assert "constraint" in types

    def test_detects_behavior_ambiguity(self, negotiator):
        ambs = negotiator._detect_ambiguities("The UI should be intuitive and modern")
        types = [a.ambiguity_type for a in ambs]
        assert "behavior" in types

    def test_no_ambiguity(self, negotiator):
        ambs = negotiator._detect_ambiguities("Create endpoint POST /api/users returning 201")
        assert len(ambs) == 0


class TestGenerateAlternatives:
    def test_three_alternatives(self, negotiator):
        report = negotiator.analyze("Build a user authentication system")
        assert len(report.alternatives) == 3

    def test_effort_ordering(self, negotiator):
        report = negotiator.analyze("Build a payment processing pipeline")
        efforts = [a.estimated_effort_days for a in report.alternatives]
        assert efforts[0] < efforts[1] < efforts[2]


class TestAnalyze:
    def test_full_analysis(self, negotiator):
        report = negotiator.analyze(
            "Build a scalable notification system that should handle email etc.",
            constraints={"max_days": 20},
        )
        assert isinstance(report, NegotiationReport)
        assert len(report.ambiguities) >= 1
        assert len(report.alternatives) == 3
        assert report.recommendation

    def test_comparison_matrix(self, negotiator):
        report = negotiator.analyze("Build API")
        assert len(report.comparison_matrix) == 3

    def test_format_report(self, negotiator):
        report = negotiator.analyze("Build something fast and scalable")
        text = format_report(report)
        assert "Negotiation Report" in text
