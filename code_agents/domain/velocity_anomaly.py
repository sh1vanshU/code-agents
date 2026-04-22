"""Velocity Anomaly — detect team slowdowns from engineering signals."""

import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.velocity_anomaly")


@dataclass
class SprintMetrics:
    """Metrics for a single sprint/period."""
    period: str = ""
    commits: int = 0
    prs_merged: int = 0
    prs_open: int = 0
    avg_pr_time_hours: float = 0.0
    bugs_filed: int = 0
    bugs_resolved: int = 0
    story_points_completed: float = 0.0
    ci_failures: int = 0
    incidents: int = 0
    review_turnaround_hours: float = 0.0


@dataclass
class Anomaly:
    """A detected velocity anomaly."""
    metric: str = ""
    period: str = ""
    value: float = 0.0
    baseline: float = 0.0
    deviation_pct: float = 0.0
    severity: str = "info"  # info, warning, critical
    possible_causes: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class VelocityReport:
    """Complete velocity anomaly report."""
    anomalies: list[Anomaly] = field(default_factory=list)
    periods_analyzed: int = 0
    trend: str = "stable"  # improving, stable, declining
    health_score: float = 0.0  # 0-100
    systemic_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


CAUSE_MAP = {
    "commits": ["Team capacity reduced", "Large refactoring in progress", "Planning/design phase"],
    "prs_merged": ["Review bottleneck", "Large PRs taking longer", "Team size change"],
    "avg_pr_time_hours": ["Review backlog", "Complex changes", "Reviewer availability"],
    "bugs_filed": ["Quality regression", "New feature instability", "Testing debt"],
    "ci_failures": ["Flaky tests", "Infrastructure issues", "Dependency breakage"],
    "incidents": ["Reliability degradation", "Scaling issues", "Deploy problems"],
    "story_points_completed": ["Scope creep", "Estimation mismatch", "Technical debt payoff"],
}


class VelocityAnomalyDetector:
    """Detects anomalies in team engineering velocity."""

    def __init__(self, threshold_pct: float = 25.0):
        self.threshold_pct = threshold_pct

    def analyze(self, metrics: list[dict]) -> VelocityReport:
        """Analyze sprint metrics for velocity anomalies."""
        logger.info("Analyzing %d periods for velocity anomalies", len(metrics))

        sprints = [self._parse_metrics(m) for m in metrics]
        if len(sprints) < 2:
            return VelocityReport(warnings=["Need at least 2 periods for analysis"])

        # Detect anomalies per metric
        anomalies = []
        metric_fields = ["commits", "prs_merged", "avg_pr_time_hours", "bugs_filed",
                         "ci_failures", "incidents", "story_points_completed"]

        for field_name in metric_fields:
            values = [getattr(s, field_name, 0) for s in sprints]
            field_anomalies = self._detect_anomalies(field_name, sprints, values)
            anomalies.extend(field_anomalies)

        # Determine trend
        trend = self._compute_trend(sprints)

        # Identify systemic issues
        systemic = self._find_systemic_issues(anomalies, sprints)

        # Health score
        health = self._compute_health(anomalies, sprints)

        report = VelocityReport(
            anomalies=sorted(anomalies, key=lambda a: -a.deviation_pct),
            periods_analyzed=len(sprints),
            trend=trend,
            health_score=round(health, 1),
            systemic_issues=systemic,
            recommendations=self._generate_recommendations(anomalies, systemic),
            warnings=self._generate_warnings(anomalies),
        )
        logger.info("Velocity: %d anomalies, trend=%s, health=%.0f",
                     len(anomalies), trend, health)
        return report

    def _parse_metrics(self, raw: dict) -> SprintMetrics:
        return SprintMetrics(
            period=raw.get("period", raw.get("sprint", "")),
            commits=int(raw.get("commits", 0)),
            prs_merged=int(raw.get("prs_merged", 0)),
            prs_open=int(raw.get("prs_open", 0)),
            avg_pr_time_hours=float(raw.get("avg_pr_time_hours", 0)),
            bugs_filed=int(raw.get("bugs_filed", 0)),
            bugs_resolved=int(raw.get("bugs_resolved", 0)),
            story_points_completed=float(raw.get("story_points_completed", raw.get("points", 0))),
            ci_failures=int(raw.get("ci_failures", 0)),
            incidents=int(raw.get("incidents", 0)),
            review_turnaround_hours=float(raw.get("review_turnaround_hours", 0)),
        )

    def _detect_anomalies(self, field_name: str,
                          sprints: list[SprintMetrics],
                          values: list[float]) -> list[Anomaly]:
        """Detect anomalies in a single metric."""
        anomalies = []
        if len(values) < 3:
            # With few data points, compare latest to average
            baseline = sum(values[:-1]) / len(values[:-1]) if len(values) > 1 else values[0]
            latest = values[-1]
        else:
            baseline = statistics.mean(values[:-1])
            latest = values[-1]

        if baseline == 0:
            return anomalies

        deviation = ((latest - baseline) / abs(baseline)) * 100

        # Higher is worse for: bugs, ci_failures, incidents, avg_pr_time
        inverted = field_name in ("bugs_filed", "ci_failures", "incidents", "avg_pr_time_hours")
        is_anomaly = abs(deviation) > self.threshold_pct

        if is_anomaly:
            severity = "critical" if abs(deviation) > 50 else "warning"
            if inverted and deviation > 0:
                severity = "critical" if deviation > 50 else "warning"
            elif not inverted and deviation < 0:
                severity = "critical" if abs(deviation) > 50 else "warning"
            else:
                severity = "info"

            anomalies.append(Anomaly(
                metric=field_name,
                period=sprints[-1].period,
                value=latest,
                baseline=round(baseline, 1),
                deviation_pct=round(deviation, 1),
                severity=severity,
                possible_causes=CAUSE_MAP.get(field_name, ["Unknown"]),
            ))
        return anomalies

    def _compute_trend(self, sprints: list[SprintMetrics]) -> str:
        """Compute overall velocity trend."""
        if len(sprints) < 3:
            return "stable"
        points = [s.story_points_completed for s in sprints[-3:]]
        if points[-1] > points[0] * 1.1:
            return "improving"
        if points[-1] < points[0] * 0.9:
            return "declining"
        return "stable"

    def _find_systemic_issues(self, anomalies: list[Anomaly],
                              sprints: list[SprintMetrics]) -> list[str]:
        """Find systemic issues from anomaly patterns."""
        issues = []
        critical = [a for a in anomalies if a.severity == "critical"]
        if len(critical) >= 3:
            issues.append("Multiple critical anomalies — possible systemic problem")

        # Bug accumulation
        if len(sprints) >= 2:
            recent = sprints[-1]
            if recent.bugs_filed > recent.bugs_resolved * 1.5:
                issues.append("Bug accumulation — filing outpacing resolution")

        return issues

    def _compute_health(self, anomalies: list[Anomaly],
                        sprints: list[SprintMetrics]) -> float:
        """Compute overall health score 0-100."""
        score = 80.0
        for a in anomalies:
            if a.severity == "critical":
                score -= 15
            elif a.severity == "warning":
                score -= 8
            else:
                score -= 3
        return max(0, min(100, score))

    def _generate_recommendations(self, anomalies: list[Anomaly],
                                  systemic: list[str]) -> list[str]:
        recs = []
        for a in anomalies:
            if a.severity in ("critical", "warning"):
                recs.append(f"Investigate {a.metric}: {a.deviation_pct:+.0f}% from baseline")
        if systemic:
            recs.append("Schedule team retrospective to address systemic issues")
        return recs

    def _generate_warnings(self, anomalies: list[Anomaly]) -> list[str]:
        warnings = []
        critical = [a for a in anomalies if a.severity == "critical"]
        if critical:
            warnings.append(f"{len(critical)} critical anomalies require attention")
        return warnings


def format_report(report: VelocityReport) -> str:
    lines = [
        "# Velocity Anomaly Report",
        f"Trend: {report.trend} | Health: {report.health_score:.0f}/100",
        f"Periods: {report.periods_analyzed} | Anomalies: {len(report.anomalies)}",
        "",
    ]
    for a in report.anomalies:
        lines.append(f"  [{a.severity}] {a.metric}: {a.value} (baseline {a.baseline}, {a.deviation_pct:+.0f}%)")
    return "\n".join(lines)
