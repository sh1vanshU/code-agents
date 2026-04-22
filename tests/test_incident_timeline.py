"""Tests for the incident timeline builder."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from code_agents.domain.incident_timeline import (
    IncidentTimelineBuilder, TimelineEvent, IncidentTimeline, Phase,
    EVENT_ALERT, EVENT_DEPLOY, EVENT_MESSAGE, EVENT_ACTION, EVENT_RESOLUTION,
)


class TestTimelineEvent:
    """Test TimelineEvent dataclass."""

    def test_time_str(self):
        ev = TimelineEvent(
            timestamp=datetime(2026, 1, 15, 10, 30, 0),
            event_type=EVENT_ALERT, source="pagerduty", title="CPU High",
        )
        assert "2026-01-15 10:30:00" in ev.time_str

    def test_default_severity(self):
        ev = TimelineEvent(
            timestamp=datetime.now(), event_type=EVENT_MESSAGE,
            source="slack", title="Investigating",
        )
        assert ev.severity == "info"


class TestPhase:
    """Test Phase dataclass."""

    def test_duration(self):
        start = datetime(2026, 1, 15, 10, 0)
        end = datetime(2026, 1, 15, 10, 30)
        phase = Phase(name="Detection", start=start, end=end)
        assert phase.duration == timedelta(minutes=30)

    def test_duration_none(self):
        phase = Phase(name="Open", start=datetime.now())
        assert phase.duration is None


class TestIncidentTimeline:
    """Test IncidentTimeline."""

    def test_summary(self):
        t = IncidentTimeline(title="Test", events=[
            TimelineEvent(timestamp=datetime.now(), event_type=EVENT_ALERT, source="pd", title="a"),
        ], impact_duration=timedelta(hours=1))
        assert "1 events" in t.summary
        assert "1:00:00" in t.summary

    def test_to_markdown(self):
        t = IncidentTimeline(
            title="DB Outage",
            events=[],
            phases=[Phase(
                name="Detection",
                start=datetime(2026, 1, 15, 10, 0),
                end=datetime(2026, 1, 15, 10, 5),
                events=[TimelineEvent(
                    timestamp=datetime(2026, 1, 15, 10, 0),
                    event_type=EVENT_ALERT, source="datadog", title="DB latency spike",
                    severity="high",
                )],
            )],
            root_cause="Connection pool exhaustion",
            lessons=["Add connection pool monitoring"],
        )
        md = t.to_markdown()
        assert "# Incident: DB Outage" in md
        assert "Detection" in md
        assert "Connection pool" in md


class TestIncidentTimelineBuilder:
    """Test IncidentTimelineBuilder."""

    def _make_events(self):
        base = datetime(2026, 1, 15, 10, 0)
        return [
            TimelineEvent(timestamp=base, event_type=EVENT_DEPLOY, source="jenkins",
                          title="Deploy v2.1"),
            TimelineEvent(timestamp=base + timedelta(minutes=5), event_type=EVENT_ALERT,
                          source="pagerduty", title="Error rate spike", severity="high"),
            TimelineEvent(timestamp=base + timedelta(minutes=10), event_type=EVENT_MESSAGE,
                          source="slack", title="Team investigating"),
            TimelineEvent(timestamp=base + timedelta(minutes=20), event_type=EVENT_ACTION,
                          source="ops", title="Rolled back to v2.0"),
            TimelineEvent(timestamp=base + timedelta(minutes=30), event_type=EVENT_RESOLUTION,
                          source="ops", title="Service recovered"),
        ]

    def test_build_basic(self):
        builder = IncidentTimelineBuilder(title="Test Incident")
        builder.add_events(self._make_events())
        timeline = builder.build()
        assert timeline.title == "Test Incident"
        assert len(timeline.events) == 5
        assert len(timeline.phases) >= 2

    def test_build_empty(self):
        builder = IncidentTimelineBuilder()
        timeline = builder.build()
        assert len(timeline.events) == 0
        assert len(timeline.phases) == 0

    def test_add_convenience_methods(self):
        builder = IncidentTimelineBuilder()
        now = datetime.now()
        builder.add_alert(now, "pd", "CPU high", severity="critical")
        builder.add_deploy(now, "jenkins", "Deploy v1")
        builder.add_message(now, "slack", "Looking into it")
        timeline = builder.build()
        assert len(timeline.events) == 3

    def test_parse_log_lines(self):
        builder = IncidentTimelineBuilder()
        lines = [
            "2026-01-15 10:00:00 Alert fired: CPU > 90%",
            "2026-01-15 10:05:00 Deploy v2.1 started",
            "invalid line without timestamp",
            "2026-01-15 10:10:00 Service recovered and resolving",
        ]
        count = builder.parse_log_lines(lines, source="syslog")
        assert count == 3
        timeline = builder.build()
        assert len(timeline.events) == 3

    def test_metrics_calculation(self):
        builder = IncidentTimelineBuilder()
        builder.add_events(self._make_events())
        timeline = builder.build()
        assert timeline.impact_duration is not None
        assert timeline.impact_duration == timedelta(minutes=30)

    def test_lessons_deploy_before_alert(self):
        builder = IncidentTimelineBuilder()
        builder.add_events(self._make_events())
        timeline = builder.build()
        assert any("deploy" in l.lower() for l in timeline.lessons)

    def test_infer_severity(self):
        assert IncidentTimelineBuilder._infer_severity("CRITICAL: system down") == "critical"
        assert IncidentTimelineBuilder._infer_severity("Error in auth") == "high"
        assert IncidentTimelineBuilder._infer_severity("Warning: slow query") == "medium"
        assert IncidentTimelineBuilder._infer_severity("Info: startup complete") == "info"

    def test_infer_event_type(self):
        assert IncidentTimelineBuilder._infer_event_type("Alert firing") == EVENT_ALERT
        assert IncidentTimelineBuilder._infer_event_type("Deploy v2") == EVENT_DEPLOY
        assert IncidentTimelineBuilder._infer_event_type("Issue resolved") == EVENT_RESOLUTION
        assert IncidentTimelineBuilder._infer_event_type("Service restarted") == EVENT_ACTION
