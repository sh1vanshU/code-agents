"""Incident replay — replay past incidents with timeline, root cause, what-if analysis.

Reconstructs incident timelines from logs, git history, and deployment
records to enable post-incident learning and what-if scenario analysis.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("code_agents.observability.incident_replay")


@dataclass
class TimelineEvent:
    """A single event in an incident timeline."""

    timestamp: str = ""
    event_type: str = ""  # deploy | error | alert | config_change | recovery
    description: str = ""
    source: str = ""  # git | log | deploy | manual
    severity: str = "info"  # info | warning | error | critical
    metadata: dict = field(default_factory=dict)


@dataclass
class RootCauseAnalysis:
    """Root cause analysis for an incident."""

    primary_cause: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    blast_radius: str = ""  # narrow | moderate | wide
    category: str = ""  # code_bug | config | infra | dependency | human


@dataclass
class WhatIfScenario:
    """A what-if scenario for incident prevention."""

    scenario: str = ""
    prevention_likelihood: float = 0.0  # 0-1
    implementation_effort: str = "medium"
    description: str = ""


@dataclass
class IncidentReplayResult:
    """Result of incident replay analysis."""

    incident_id: str = ""
    timeline: list[TimelineEvent] = field(default_factory=list)
    root_cause: RootCauseAnalysis = field(default_factory=RootCauseAnalysis)
    what_if: list[WhatIfScenario] = field(default_factory=list)
    duration_minutes: float = 0.0
    commits_in_window: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)


class IncidentReplayer:
    """Replay and analyze past incidents."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("IncidentReplayer initialized for %s", cwd)

    def replay(
        self,
        start_time: str,
        end_time: str | None = None,
        incident_id: str = "",
        log_file: str | None = None,
    ) -> IncidentReplayResult:
        """Replay an incident within a time window.

        Args:
            start_time: Incident start (ISO format or git date).
            end_time: Incident end. Default: 2 hours after start.
            incident_id: Optional incident identifier.
            log_file: Path to log file for analysis.

        Returns:
            IncidentReplayResult with timeline and analysis.
        """
        result = IncidentReplayResult(incident_id=incident_id or f"INC-{start_time[:10]}")

        # Parse time window
        start_dt = self._parse_time(start_time)
        if end_time:
            end_dt = self._parse_time(end_time)
        else:
            end_dt = start_dt + timedelta(hours=2)

        result.duration_minutes = (end_dt - start_dt).total_seconds() / 60
        logger.info(
            "Replaying incident %s: %s to %s (%.0f min)",
            result.incident_id, start_dt, end_dt, result.duration_minutes,
        )

        # Build timeline from git history
        git_events = self._get_git_events(start_dt, end_dt)
        result.timeline.extend(git_events)
        result.commits_in_window = [e.metadata for e in git_events if e.event_type == "deploy"]

        # Analyze log file if provided
        if log_file and os.path.exists(log_file):
            log_events = self._parse_log_events(log_file, start_dt, end_dt)
            result.timeline.extend(log_events)

        # Sort timeline
        result.timeline.sort(key=lambda e: e.timestamp)

        # Perform root cause analysis
        result.root_cause = self._analyze_root_cause(result.timeline)

        # Generate what-if scenarios
        result.what_if = self._generate_what_ifs(result.root_cause, result.timeline)

        # Recommendations
        result.recommendations = self._generate_recommendations(
            result.root_cause, result.timeline,
        )

        result.summary = {
            "incident_id": result.incident_id,
            "duration_minutes": str(round(result.duration_minutes, 1)),
            "events_count": str(len(result.timeline)),
            "root_cause": result.root_cause.primary_cause,
            "blast_radius": result.root_cause.blast_radius,
        }
        return result

    def _parse_time(self, time_str: str) -> datetime:
        """Parse a time string into datetime."""
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # Fallback
        return datetime.now()

    def _run_git(self, *args: str) -> str:
        """Run a git command."""
        try:
            proc = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return proc.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_git_events(
        self, start: datetime, end: datetime,
    ) -> list[TimelineEvent]:
        """Get git events in the time window."""
        events: list[TimelineEvent] = []
        since = start.strftime("%Y-%m-%d %H:%M:%S")
        until = end.strftime("%Y-%m-%d %H:%M:%S")

        log = self._run_git(
            "log", "--all", f"--since={since}", f"--until={until}",
            "--format=%H|%ai|%s|%an", "--no-merges",
        )
        if not log:
            return events

        for line in log.splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            commit_hash, timestamp, message, author = parts
            event_type = "deploy"
            severity = "info"

            msg_lower = message.lower()
            if any(kw in msg_lower for kw in ("fix", "hotfix", "patch", "revert")):
                event_type = "recovery"
                severity = "warning"
            elif any(kw in msg_lower for kw in ("config", "env", "setting")):
                event_type = "config_change"

            events.append(TimelineEvent(
                timestamp=timestamp,
                event_type=event_type,
                description=message,
                source="git",
                severity=severity,
                metadata={"commit": commit_hash, "author": author, "message": message},
            ))

        return events

    def _parse_log_events(
        self, log_file: str, start: datetime, end: datetime,
    ) -> list[TimelineEvent]:
        """Parse events from a log file."""
        events: list[TimelineEvent] = []
        try:
            content = Path(log_file).read_text(errors="replace")
        except OSError:
            return events

        # Common log patterns
        log_re = re.compile(
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})\s+"
            r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
            r"(.*)",
        )

        for line in content.splitlines():
            match = log_re.match(line)
            if not match:
                continue

            timestamp_str, level, message = match.groups()
            try:
                ts = self._parse_time(timestamp_str)
            except Exception:
                continue

            if ts < start or ts > end:
                continue

            severity = level.lower()
            if severity == "critical":
                event_type = "error"
            elif severity == "error":
                event_type = "error"
            elif severity == "warning":
                event_type = "alert"
            else:
                continue  # Skip info/debug in incident replay

            events.append(TimelineEvent(
                timestamp=timestamp_str,
                event_type=event_type,
                description=message.strip(),
                source="log",
                severity=severity,
            ))

        return events

    def _analyze_root_cause(self, timeline: list[TimelineEvent]) -> RootCauseAnalysis:
        """Analyze root cause from timeline events."""
        rca = RootCauseAnalysis()

        errors = [e for e in timeline if e.severity in ("error", "critical")]
        deploys = [e for e in timeline if e.event_type == "deploy"]
        configs = [e for e in timeline if e.event_type == "config_change"]

        # Determine primary cause
        if deploys and errors:
            first_deploy = deploys[0].timestamp if deploys else ""
            first_error = errors[0].timestamp if errors else ""
            if first_deploy <= first_error:
                rca.primary_cause = f"Code deployment: {deploys[0].description}"
                rca.category = "code_bug"
        elif configs and errors:
            rca.primary_cause = f"Configuration change: {configs[0].description}"
            rca.category = "config"
        elif errors:
            rca.primary_cause = f"Runtime error: {errors[0].description}"
            rca.category = "code_bug"
        else:
            rca.primary_cause = "Unable to determine from available data"
            rca.category = "unknown"

        # Contributing factors
        if len(deploys) > 1:
            rca.contributing_factors.append("Multiple deployments in incident window")
        if configs:
            rca.contributing_factors.append("Configuration changes during incident")

        # Blast radius
        affected = set()
        for e in errors:
            words = re.findall(r"\b[A-Z]\w+(?:Service|Handler|Module)\b", e.description)
            affected.update(words)

        rca.affected_components = list(affected)
        if len(affected) > 5:
            rca.blast_radius = "wide"
        elif len(affected) > 2:
            rca.blast_radius = "moderate"
        else:
            rca.blast_radius = "narrow"

        return rca

    def _generate_what_ifs(
        self,
        rca: RootCauseAnalysis,
        timeline: list[TimelineEvent],
    ) -> list[WhatIfScenario]:
        """Generate what-if scenarios."""
        scenarios: list[WhatIfScenario] = []

        if rca.category == "code_bug":
            scenarios.append(WhatIfScenario(
                scenario="Pre-deployment integration tests caught the bug",
                prevention_likelihood=0.7,
                implementation_effort="medium",
                description="Add integration tests covering the failure scenario",
            ))
            scenarios.append(WhatIfScenario(
                scenario="Canary deployment detected the issue early",
                prevention_likelihood=0.8,
                implementation_effort="high",
                description="Implement canary releases with automatic rollback",
            ))

        if rca.category == "config":
            scenarios.append(WhatIfScenario(
                scenario="Config validation prevented invalid change",
                prevention_likelihood=0.9,
                implementation_effort="low",
                description="Add config validation and dry-run capability",
            ))

        # Generic scenarios
        scenarios.append(WhatIfScenario(
            scenario="Automated rollback triggered on error spike",
            prevention_likelihood=0.6,
            implementation_effort="medium",
            description="Set up automated rollback on error rate threshold",
        ))

        return scenarios

    def _generate_recommendations(
        self,
        rca: RootCauseAnalysis,
        timeline: list[TimelineEvent],
    ) -> list[str]:
        """Generate incident prevention recommendations."""
        recs: list[str] = []

        if rca.category == "code_bug":
            recs.append("Add regression test for the specific failure scenario")
            recs.append("Review code review process for similar patterns")
        if rca.category == "config":
            recs.append("Implement configuration change validation pipeline")
        if rca.blast_radius == "wide":
            recs.append("Implement circuit breakers for affected services")
        recs.append("Update runbook with incident timeline and resolution steps")

        return recs


def replay_incident(
    cwd: str,
    start_time: str,
    end_time: str | None = None,
    incident_id: str = "",
    log_file: str | None = None,
) -> dict:
    """Convenience function to replay an incident.

    Returns:
        Dict with timeline, root cause, what-if scenarios, and recommendations.
    """
    replayer = IncidentReplayer(cwd)
    result = replayer.replay(
        start_time=start_time, end_time=end_time,
        incident_id=incident_id, log_file=log_file,
    )
    return {
        "incident_id": result.incident_id,
        "duration_minutes": result.duration_minutes,
        "timeline": [
            {"timestamp": e.timestamp, "type": e.event_type,
             "description": e.description, "severity": e.severity}
            for e in result.timeline
        ],
        "root_cause": {
            "primary": result.root_cause.primary_cause,
            "category": result.root_cause.category,
            "blast_radius": result.root_cause.blast_radius,
            "affected_components": result.root_cause.affected_components,
        },
        "what_if": [
            {"scenario": w.scenario, "prevention_likelihood": w.prevention_likelihood,
             "effort": w.implementation_effort}
            for w in result.what_if
        ],
        "recommendations": result.recommendations,
        "summary": result.summary,
    }
