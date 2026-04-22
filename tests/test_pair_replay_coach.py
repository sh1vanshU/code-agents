"""Tests for pair_replay_coach.py — coding session pattern analysis."""

import pytest

from code_agents.knowledge.pair_replay_coach import (
    PairReplayCoach,
    CoachingReport,
    EfficiencyMetrics,
    format_report,
)


@pytest.fixture
def coach():
    return PairReplayCoach()


PRODUCTIVE_SESSION = [
    {"type": "edit", "file": "app.py", "duration_ms": 5000},
    {"type": "edit", "file": "app.py", "duration_ms": 3000},
    {"type": "save", "file": "app.py", "duration_ms": 100},
    {"type": "edit", "file": "app.py", "duration_ms": 4000},
    {"type": "run", "file": "app.py", "duration_ms": 2000},
]

THRASHING_SESSION = [
    {"type": "edit", "file": "a.py", "duration_ms": 1000},
    {"type": "navigate", "file": "b.py", "duration_ms": 500},
    {"type": "edit", "file": "c.py", "duration_ms": 800},
    {"type": "navigate", "file": "d.py", "duration_ms": 500},
    {"type": "error", "file": "d.py", "duration_ms": 200},
    {"type": "undo", "file": "d.py", "duration_ms": 100},
    {"type": "edit", "file": "e.py", "duration_ms": 600},
    {"type": "error", "file": "e.py", "duration_ms": 200},
    {"type": "edit", "file": "f.py", "duration_ms": 500},
    {"type": "navigate", "file": "g.py", "duration_ms": 300},
    {"type": "undo", "file": "g.py", "duration_ms": 100},
    {"type": "undo", "file": "g.py", "duration_ms": 100},
    {"type": "undo", "file": "g.py", "duration_ms": 100},
    {"type": "undo", "file": "g.py", "duration_ms": 100},
    {"type": "undo", "file": "g.py", "duration_ms": 100},
]


class TestComputeMetrics:
    def test_counts_files(self, coach):
        coach.events = [coach._parse_event(e) for e in PRODUCTIVE_SESSION]
        metrics = coach._compute_metrics()
        assert metrics.files_touched >= 1

    def test_counts_undos(self, coach):
        coach.events = [coach._parse_event(e) for e in THRASHING_SESSION]
        metrics = coach._compute_metrics()
        assert metrics.undo_redo_count >= 5


class TestDetectPatterns:
    def test_detects_excessive_undo(self, coach):
        coach.events = [coach._parse_event(e) for e in THRASHING_SESSION]
        patterns = coach._detect_patterns()
        pattern_names = [p.pattern_name for p in patterns]
        assert "excessive_undo" in pattern_names


class TestAnalyze:
    def test_productive_session(self, coach):
        report = coach.analyze(PRODUCTIVE_SESSION)
        assert isinstance(report, CoachingReport)
        assert report.productivity_score >= 50

    def test_thrashing_session(self, coach):
        report = coach.analyze(THRASHING_SESSION)
        assert len(report.patterns) >= 1

    def test_empty_session(self, coach):
        report = coach.analyze([])
        assert isinstance(report, CoachingReport)

    def test_strengths_identified(self, coach):
        report = coach.analyze(PRODUCTIVE_SESSION)
        assert len(report.strengths) >= 1

    def test_format_report(self, coach):
        report = coach.analyze(PRODUCTIVE_SESSION)
        text = format_report(report)
        assert "Coaching Report" in text
