"""Tests for swarm_debugger.py — parallel debug hypothesis coordination."""

import pytest

from code_agents.agent_system.swarm_debugger import (
    SwarmDebugger,
    SwarmReport,
    Hypothesis,
    format_report,
)


@pytest.fixture
def debugger(tmp_path):
    return SwarmDebugger(str(tmp_path))


class TestGenerateHypotheses:
    def test_logic_hypothesis(self, debugger):
        hyps = debugger._generate_hypotheses("wrong return value in condition", None, None)
        categories = [h.category for h in hyps]
        assert "logic" in categories

    def test_data_hypothesis(self, debugger):
        hyps = debugger._generate_hypotheses("NoneType error null value", None, None)
        categories = [h.category for h in hyps]
        assert "data" in categories

    def test_fallback_hypothesis(self, debugger):
        hyps = debugger._generate_hypotheses("something broke", None, None)
        assert len(hyps) >= 1


class TestAnalyze:
    def test_basic_analysis(self, debugger):
        report = debugger.analyze(
            "NoneType error when processing empty input",
            error_logs="TypeError: NoneType has no attribute 'get'",
        )
        assert isinstance(report, SwarmReport)
        assert len(report.hypotheses) >= 1
        assert len(report.findings) >= 1

    def test_with_code_context(self, debugger):
        report = debugger.analyze(
            "Race condition in concurrent access",
            code_context={"handler.py": "import threading\nlock = threading.Lock()"},
        )
        assert len(report.hypotheses) >= 1

    def test_with_stack_trace(self, debugger):
        report = debugger.analyze(
            "Application crash",
            stack_trace="Traceback (most recent call last):\n  File 'app.py'\nValueError: invalid",
        )
        assert isinstance(report, SwarmReport)

    def test_root_cause_identified(self, debugger):
        report = debugger.analyze(
            "null pointer: NoneType error missing data invalid format empty",
            error_logs="NoneType null empty None missing invalid corrupt",
        )
        # Data hypothesis should rank high with many keyword matches
        assert report.hypotheses[0].confidence > 0.3

    def test_format_report(self, debugger):
        report = debugger.analyze("test bug")
        text = format_report(report)
        assert "Swarm Debug" in text
