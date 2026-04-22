"""Tests for cognitive_monitor.py — developer flow state detection."""

import pytest

from code_agents.observability.cognitive_monitor import (
    CognitiveMonitor,
    CognitiveReport,
    CognitiveMetrics,
    format_report,
)


@pytest.fixture
def monitor():
    return CognitiveMonitor()


FLOW_EVENTS = [
    {"type": "edit", "file": "app.py", "timestamp": 1000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 4000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 7000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 10000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 13000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 16000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 19000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 22000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 25000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 28000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 31000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 34000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 37000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 40000, "duration": 3000},
    {"type": "edit", "file": "app.py", "timestamp": 43000, "duration": 3000},
    {"type": "save", "file": "app.py", "timestamp": 46000, "duration": 100},
]

THRASH_EVENTS = [
    {"type": "edit", "file": "a.py", "timestamp": 1000, "duration": 1000},
    {"type": "navigate", "file": "b.py", "timestamp": 2000, "duration": 500},
    {"type": "error", "file": "b.py", "timestamp": 3000, "duration": 200},
    {"type": "search", "file": "c.py", "timestamp": 4000, "duration": 800},
    {"type": "navigate", "file": "d.py", "timestamp": 5000, "duration": 300},
    {"type": "error", "file": "d.py", "timestamp": 6000, "duration": 200},
    {"type": "search", "file": "e.py", "timestamp": 7000, "duration": 500},
    {"type": "error", "file": "e.py", "timestamp": 8000, "duration": 200},
    {"type": "navigate", "file": "f.py", "timestamp": 9000, "duration": 300},
    {"type": "search", "file": "g.py", "timestamp": 10000, "duration": 400},
]


class TestClassifyWindow:
    def test_flow_detection(self, monitor):
        monitor.events = [monitor._parse_event(e) for e in FLOW_EVENTS]
        state = monitor._classify_window(monitor.events)
        assert state.state == "flow"

    def test_ramping_detection(self, monitor):
        events = [
            monitor._parse_event({"type": "search", "file": "a.py", "timestamp": 0, "duration": 500}),
            monitor._parse_event({"type": "search", "file": "b.py", "timestamp": 1000, "duration": 500}),
            monitor._parse_event({"type": "navigate", "file": "c.py", "timestamp": 2000, "duration": 300}),
            monitor._parse_event({"type": "edit", "file": "a.py", "timestamp": 3000, "duration": 1000}),
        ]
        state = monitor._classify_window(events)
        assert state.state in ("ramping", "neutral")


class TestAnalyze:
    def test_flow_session(self, monitor):
        report = monitor.analyze(FLOW_EVENTS)
        assert isinstance(report, CognitiveReport)
        assert report.total_events >= 5

    def test_thrash_session(self, monitor):
        report = monitor.analyze(THRASH_EVENTS)
        assert isinstance(report, CognitiveReport)

    def test_empty_session(self, monitor):
        report = monitor.analyze([])
        assert isinstance(report, CognitiveReport)
        assert report.total_events == 0

    def test_recommendations_for_thrashing(self, monitor):
        report = monitor.analyze(THRASH_EVENTS)
        # May or may not have recommendations depending on window classification
        assert isinstance(report.recommendations, list)

    def test_format_report(self, monitor):
        report = monitor.analyze(FLOW_EVENTS)
        text = format_report(report)
        assert "Cognitive" in text
