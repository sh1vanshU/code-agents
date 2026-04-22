"""Tests for prompt_evolver.py — evolve prompts from user corrections."""

import pytest

from code_agents.agent_system.prompt_evolver import (
    PromptEvolver,
    EvolutionReport,
    PromptPatch,
    format_report,
)


@pytest.fixture
def evolver():
    return PromptEvolver(agent_name="test-agent")


SAMPLE_CORRECTIONS = [
    {"original": "Here is the JSON", "corrected": "```json\n{}\n```", "context": "format json"},
    {"original": "Result:", "corrected": "```json\n[]\n```", "context": "format structured"},
    {"original": "The answer is wrong", "corrected": "The correct value is 42", "context": "fix error"},
    {"original": "Wrong output", "corrected": "Correct output", "context": "wrong incorrect"},
    {"original": "Too verbose", "corrected": "Concise", "context": "too much scope"},
]


class TestClassifyCorrection:
    def test_classifies_format(self, evolver):
        from code_agents.agent_system.prompt_evolver import Correction
        c = Correction(original_output="plain", corrected_output="json formatted", context="json")
        result = evolver._classify_correction(c)
        assert result in ("format", "style", "accuracy")

    def test_classifies_accuracy(self, evolver):
        from code_agents.agent_system.prompt_evolver import Correction
        c = Correction(original_output="wrong", corrected_output="correct", context="incorrect mistake")
        result = evolver._classify_correction(c)
        assert result == "accuracy"


class TestIdentifyPatterns:
    def test_finds_patterns(self, evolver):
        evolver.corrections = [evolver._parse_correction(c) for c in SAMPLE_CORRECTIONS]
        patterns = evolver._identify_patterns()
        assert len(patterns) >= 1

    def test_pattern_frequency(self, evolver):
        evolver.corrections = [evolver._parse_correction(c) for c in SAMPLE_CORRECTIONS]
        patterns = evolver._identify_patterns()
        for p in patterns:
            assert p["count"] >= 2


class TestAnalyze:
    def test_full_analysis(self, evolver):
        report = evolver.analyze(SAMPLE_CORRECTIONS)
        assert isinstance(report, EvolutionReport)
        assert report.corrections_analyzed == len(SAMPLE_CORRECTIONS)

    def test_generates_patches(self, evolver):
        report = evolver.analyze(SAMPLE_CORRECTIONS)
        assert len(report.patches) >= 1
        assert all(isinstance(p, PromptPatch) for p in report.patches)

    def test_effectiveness_score(self, evolver):
        report = evolver.analyze(SAMPLE_CORRECTIONS)
        assert 0.0 <= report.effectiveness_score <= 1.0

    def test_empty_corrections(self, evolver):
        report = evolver.analyze([])
        assert report.corrections_analyzed == 0

    def test_format_report(self, evolver):
        report = evolver.analyze(SAMPLE_CORRECTIONS)
        text = format_report(report)
        assert "Evolution" in text
