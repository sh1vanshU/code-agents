"""Tests for decision_fatigue_reducer.py — auto-resolve micro-decisions."""

import pytest

from code_agents.agent_system.decision_fatigue_reducer import (
    DecisionFatigueReducer,
    FatigueReport,
    Decision,
    format_report,
)


@pytest.fixture
def reducer():
    return DecisionFatigueReducer()


SAMPLE_CODE = {
    "app.py": '''
def processData(x):
    try:
        return x.value
    except:
        pass

import os
import sys
from pathlib import Path
import json
''',
}


class TestDetectDecisions:
    def test_detects_naming(self, reducer):
        decisions = reducer._detect_decisions(SAMPLE_CODE)
        naming = [d for d in decisions if d.category == "naming"]
        assert len(naming) >= 1

    def test_detects_error_handling(self, reducer):
        decisions = reducer._detect_decisions(SAMPLE_CODE)
        err = [d for d in decisions if d.category == "error_handling"]
        assert len(err) >= 1

    def test_detects_import_order(self, reducer):
        decisions = reducer._detect_decisions(SAMPLE_CODE)
        imports = [d for d in decisions if d.category == "import_order"]
        assert len(imports) >= 1


class TestAutoResolve:
    def test_resolves_naming(self, reducer):
        d = Decision(category="naming", options=["snake_case", "keep"])
        reducer._try_auto_resolve(d)
        assert d.auto_resolved is True
        assert d.chosen_option == "snake_case"

    def test_resolves_error_handling(self, reducer):
        d = Decision(category="error_handling", options=["catch_specific", "keep"])
        reducer._try_auto_resolve(d)
        assert d.auto_resolved is True

    def test_novel_marked(self, reducer):
        d = Decision(category="unknown_category", options=[])
        reducer._try_auto_resolve(d)
        assert d.is_novel is True


class TestAnalyze:
    def test_full_analysis(self, reducer):
        report = reducer.analyze(SAMPLE_CODE)
        assert isinstance(report, FatigueReport)
        assert report.total_decisions >= 2
        assert report.auto_resolved >= 1

    def test_savings_calculated(self, reducer):
        report = reducer.analyze(SAMPLE_CODE)
        assert report.savings_pct >= 0

    def test_with_history(self, reducer):
        history = [{"category": "formatting", "chosen": "black", "confidence": 0.9}]
        report = reducer.analyze(SAMPLE_CODE, decision_history=history)
        assert len(reducer.history) >= 1

    def test_format_report(self, reducer):
        report = reducer.analyze(SAMPLE_CODE)
        text = format_report(report)
        assert "Fatigue" in text
