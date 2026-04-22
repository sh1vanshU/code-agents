"""Incident Timeline Builder — reconstruct incident timelines from events.

Combines alerts, deployments, messages, and metrics into a chronological
timeline for incident review and postmortem generation.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.domain.incident_timeline")

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
EVENT_ALERT = "alert"
EVENT_DEPLOY = "deploy"
EVENT_MESSAGE = "message"
EVENT_METRIC = "metric"
EVENT_ACTION = "action"
EVENT_RESOLUTION = "resolution"

# Severity ordering
_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TimelineEvent:
    """A single event in the incident timeline."""

    timestamp: datetime
    event_type: str  # alert, deploy, message, metric, action, resolution
    source: str  # "pagerduty", "jenkins", "slack", "datadog", etc.
    title: str
    description: str = ""
    severity: str = "info"
    metadata: dict = field(default_factory=dict)

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class Phase:
    """A phase of the incident (detection, investigation, mitigation, resolution)."""

    name: str
    start: datetime
    end: Optional[datetime] = None
    events: list[TimelineEvent] = field(default_factory=list)

    @property
    def duration(self) -> Optional[timedelta]:
        if self.end:
            return self.end - self.start
        return None


@dataclass
class IncidentTimeline:
    """Complete incident timeline with phases and analysis."""

    title: str
    events: list[TimelineEvent] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    root_cause: str = ""
    impact_duration: Optional[timedelta] = None
    time_to_detect: Optional[timedelta] = None
    time_to_mitigate: Optional[timedelta] = None
    lessons: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        total = len(self.events)
        dur = str(self.impact_duration) if self.impact_duration else "unknown"
        return f"{total} events, impact duration: {dur}, phases: {len(self.phases)}"

    def to_markdown(self) -> str:
        """Render timeline as markdown."""
        lines = [f"# Incident: {self.title}", ""]
        if self.impact_duration:
            lines.append(f"**Impact Duration:** {self.impact_duration}")
        if self.time_to_detect:
            lines.append(f"**Time to Detect:** {self.time_to_detect}")
        if self.time_to_mitigate:
            lines.append(f"**Time to Mitigate:** {self.time_to_mitigate}")
        lines.extend(["", "## Timeline", ""])

        for phase in self.phases:
            dur = f" ({phase.duration})" if phase.duration else ""
            lines.append(f"### {phase.name}{dur}")
            for ev in phase.events:
                sev = f" [{ev.severity.upper()}]" if ev.severity != "info" else ""
                lines.append(f"- **{ev.time_str}** [{ev.source}]{sev} {ev.title}")
                if ev.description:
                    lines.append(f"  {ev.description}")
            lines.append("")

        if self.root_cause:
            lines.extend(["## Root Cause", self.root_cause, ""])
        if self.lessons:
            lines.append("## Lessons Learned")
            for lesson in self.lessons:
                lines.append(f"- {lesson}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class IncidentTimelineBuilder:
    """Build incident timelines from heterogeneous event sources."""

    def __init__(self, title: str = "Incident"):
        self.title = title
        self._events: list[TimelineEvent] = []

    # ── Event ingestion ───────────────────────────────────────────────────

    def add_event(self, event: TimelineEvent) -> None:
        """Add a single event to the timeline."""
        self._events.append(event)

    def add_events(self, events: list[TimelineEvent]) -> None:
        """Add multiple events."""
        self._events.extend(events)

    def add_alert(self, timestamp: datetime, source: str, title: str,
                  severity: str = "high", description: str = "", **metadata) -> None:
        """Convenience: add an alert event."""
        self._events.append(TimelineEvent(
            timestamp=timestamp, event_type=EVENT_ALERT, source=source,
            title=title, severity=severity, description=description, metadata=metadata,
        ))

    def add_deploy(self, timestamp: datetime, source: str, title: str,
                   description: str = "", **metadata) -> None:
        """Convenience: add a deploy event."""
        self._events.append(TimelineEvent(
            timestamp=timestamp, event_type=EVENT_DEPLOY, source=source,
            title=title, severity="info", description=description, metadata=metadata,
        ))

    def add_message(self, timestamp: datetime, source: str, title: str,
                    description: str = "", **metadata) -> None:
        """Convenience: add a message/communication event."""
        self._events.append(TimelineEvent(
            timestamp=timestamp, event_type=EVENT_MESSAGE, source=source,
            title=title, severity="info", description=description, metadata=metadata,
        ))

    # ── Parse from text ───────────────────────────────────────────────────

    def parse_log_lines(self, lines: list[str], source: str = "log") -> int:
        """Parse timestamped log lines into events.

        Expected format: YYYY-MM-DD HH:MM:SS <message>
        Returns number of events parsed.
        """
        count = 0
        ts_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})\s+(.*)"
        )
        for line in lines:
            m = ts_pattern.match(line.strip())
            if m:
                ts_str = m.group(1).replace("T", " ")
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                msg = m.group(2)
                severity = self._infer_severity(msg)
                event_type = self._infer_event_type(msg)
                self._events.append(TimelineEvent(
                    timestamp=ts, event_type=event_type, source=source,
                    title=msg, severity=severity,
                ))
                count += 1
        return count

    # ── Build timeline ────────────────────────────────────────────────────

    def build(self) -> IncidentTimeline:
        """Build the complete incident timeline."""
        if not self._events:
            return IncidentTimeline(title=self.title)

        # Sort chronologically
        sorted_events = sorted(self._events, key=lambda e: e.timestamp)
        phases = self._identify_phases(sorted_events)
        timeline = IncidentTimeline(
            title=self.title,
            events=sorted_events,
            phases=phases,
        )

        # Calculate metrics
        self._calculate_metrics(timeline, sorted_events)
        timeline.lessons = self._extract_lessons(sorted_events)

        logger.info("Built timeline: %s", timeline.summary)
        return timeline

    # ── Phase identification ──────────────────────────────────────────────

    def _identify_phases(self, events: list[TimelineEvent]) -> list[Phase]:
        """Identify incident phases from events."""
        if not events:
            return []

        phases: list[Phase] = []
        first_alert = None
        first_action = None
        resolution_event = None

        for ev in events:
            if ev.event_type == EVENT_ALERT and first_alert is None:
                first_alert = ev
            if ev.event_type == EVENT_ACTION and first_action is None:
                first_action = ev
            if ev.event_type == EVENT_RESOLUTION:
                resolution_event = ev

        # Detection phase: before first alert to first alert
        if first_alert:
            pre_events = [e for e in events if e.timestamp <= first_alert.timestamp]
            phases.append(Phase(
                name="Detection",
                start=events[0].timestamp,
                end=first_alert.timestamp,
                events=pre_events,
            ))

        # Investigation phase: alert to first action
        if first_alert and first_action:
            inv_events = [e for e in events
                          if first_alert.timestamp <= e.timestamp <= first_action.timestamp]
            phases.append(Phase(
                name="Investigation",
                start=first_alert.timestamp,
                end=first_action.timestamp,
                events=inv_events,
            ))

        # Mitigation phase: first action to resolution
        if first_action:
            end = resolution_event.timestamp if resolution_event else events[-1].timestamp
            mit_events = [e for e in events if first_action.timestamp <= e.timestamp <= end]
            phases.append(Phase(
                name="Mitigation",
                start=first_action.timestamp,
                end=end,
                events=mit_events,
            ))

        # Resolution phase
        if resolution_event:
            res_events = [e for e in events if e.timestamp >= resolution_event.timestamp]
            phases.append(Phase(
                name="Resolution",
                start=resolution_event.timestamp,
                end=events[-1].timestamp,
                events=res_events,
            ))

        # Fallback: if no phases identified, single phase
        if not phases:
            phases.append(Phase(
                name="Incident",
                start=events[0].timestamp,
                end=events[-1].timestamp,
                events=events,
            ))

        return phases

    def _calculate_metrics(self, timeline: IncidentTimeline, events: list[TimelineEvent]) -> None:
        """Calculate incident metrics."""
        alerts = [e for e in events if e.event_type == EVENT_ALERT]
        actions = [e for e in events if e.event_type == EVENT_ACTION]
        resolutions = [e for e in events if e.event_type == EVENT_RESOLUTION]

        if len(events) >= 2:
            timeline.impact_duration = events[-1].timestamp - events[0].timestamp

        # Time to detect: first event to first alert
        if alerts and events:
            first_event = events[0]
            if first_event.event_type != EVENT_ALERT:
                timeline.time_to_detect = alerts[0].timestamp - first_event.timestamp

        # Time to mitigate: first alert to resolution
        if alerts and resolutions:
            timeline.time_to_mitigate = resolutions[0].timestamp - alerts[0].timestamp

    def _extract_lessons(self, events: list[TimelineEvent]) -> list[str]:
        """Extract lessons learned from event patterns."""
        lessons = []
        alerts = [e for e in events if e.event_type == EVENT_ALERT]
        deploys = [e for e in events if e.event_type == EVENT_DEPLOY]

        # Check if deploy preceded alerts
        if deploys and alerts:
            for deploy in deploys:
                close_alerts = [a for a in alerts
                                if timedelta(0) < (a.timestamp - deploy.timestamp) < timedelta(minutes=30)]
                if close_alerts:
                    lessons.append("Alert triggered within 30 minutes of a deploy — consider canary deployments")
                    break

        if len(alerts) > 3:
            lessons.append("Multiple alerts triggered — review alert correlation and deduplication")

        if not any(e.event_type == EVENT_ACTION for e in events):
            lessons.append("No explicit actions recorded — improve incident response runbooks")

        return lessons

    # ── Inference helpers ─────────────────────────────────────────────────

    @staticmethod
    def _infer_severity(message: str) -> str:
        """Infer severity from message content."""
        lower = message.lower()
        if any(kw in lower for kw in ("critical", "fatal", "down", "outage")):
            return "critical"
        if any(kw in lower for kw in ("error", "fail", "exception")):
            return "high"
        if any(kw in lower for kw in ("warn", "slow", "degraded", "timeout")):
            return "medium"
        return "info"

    @staticmethod
    def _infer_event_type(message: str) -> str:
        """Infer event type from message content."""
        lower = message.lower()
        if any(kw in lower for kw in ("alert", "alarm", "pagerduty", "firing")):
            return EVENT_ALERT
        if any(kw in lower for kw in ("deploy", "release", "rollout", "rollback")):
            return EVENT_DEPLOY
        if any(kw in lower for kw in ("resolv", "fixed", "recover", "restored")):
            return EVENT_RESOLUTION
        if any(kw in lower for kw in ("restarted", "scaled", "reverted", "patched")):
            return EVENT_ACTION
        return EVENT_MESSAGE
