"""Incident Postmortem Writer — time range → structured postmortem report."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.domain.postmortem")


@dataclass
class TimelineEvent:
    timestamp: str
    description: str
    source: str  # "git", "deploy", "log", "manual"
    severity: str = "info"  # info, warning, critical


@dataclass
class ActionItem:
    action: str
    owner: str = ""
    priority: str = "medium"  # high, medium, low
    due: str = ""


@dataclass
class PostmortemReport:
    title: str
    time_range_start: str
    time_range_end: str
    service: str
    timeline: list[TimelineEvent] = field(default_factory=list)
    root_cause: str = ""
    impact: str = ""
    action_items: list[ActionItem] = field(default_factory=list)
    commits_in_range: list[dict] = field(default_factory=list)
    deploys_in_range: list[dict] = field(default_factory=list)
    error_patterns: list[dict] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    severity_level: str = "P2"  # P0-P4


class PostmortemWriter:
    """Generates incident postmortem reports from git + deploy + log data."""

    def __init__(self, cwd: str = ".", time_from: str = "", time_to: str = "",
                 service: str = "", server_url: str = ""):
        self.cwd = os.path.abspath(cwd)
        self.time_from = time_from
        self.time_to = time_to or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.service = service
        self.server_url = server_url

    def generate(self) -> PostmortemReport:
        """Generate a postmortem report."""
        commits = self._collect_commits()
        deploys = self._collect_deploys()
        errors = self._collect_error_patterns()
        timeline = self._build_timeline(commits, deploys, errors)

        root_cause = self._infer_root_cause(commits, errors, timeline)
        impact = self._estimate_impact(errors, timeline)
        actions = self._generate_action_items(root_cause, errors)
        lessons = self._extract_lessons(root_cause, timeline)
        severity = self._assess_severity(errors, timeline)

        title = self._generate_title(errors, commits)

        return PostmortemReport(
            title=title,
            time_range_start=self.time_from,
            time_range_end=self.time_to,
            service=self.service,
            timeline=timeline,
            root_cause=root_cause,
            impact=impact,
            action_items=actions,
            commits_in_range=commits,
            deploys_in_range=deploys,
            error_patterns=errors,
            lessons_learned=lessons,
            severity_level=severity,
        )

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _collect_commits(self) -> list[dict]:
        """Get commits in the time range."""
        args = ["log", "--pretty=format:%H|%aI|%an|%s", "--no-merges"]
        if self.time_from:
            args.extend(["--since", self.time_from])
        if self.time_to:
            args.extend(["--until", self.time_to])

        output = self._run_git(*args)
        if not output:
            return []

        commits = []
        for line in output.split("\n"):
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:8],
                    "timestamp": parts[1],
                    "author": parts[2],
                    "subject": parts[3],
                })
        return commits

    def _collect_deploys(self) -> list[dict]:
        """Collect deploy info — via server API or git tags."""
        deploys = []
        # Try git tags with deploy/release patterns
        tags = self._run_git("tag", "--sort=-creatordate", "--format=%(refname:short)|%(creatordate:iso)")
        if tags:
            for line in tags.split("\n")[:20]:
                parts = line.split("|", 1)
                if len(parts) == 2:
                    tag, ts = parts
                    if any(p in tag.lower() for p in ("deploy", "release", "v")):
                        deploys.append({"tag": tag, "timestamp": ts.strip()})
        return deploys

    def _collect_error_patterns(self) -> list[dict]:
        """Collect error patterns from logs or git."""
        patterns = []
        # Search git log for error/fix/hotfix commits in range
        args = ["log", "--pretty=format:%s", "--no-merges", "--grep=fix", "-i"]
        if self.time_from:
            args.extend(["--since", self.time_from])
        if self.time_to:
            args.extend(["--until", self.time_to])
        output = self._run_git(*args)
        if output:
            for line in output.split("\n"):
                line = line.strip()
                if line:
                    patterns.append({"source": "git", "pattern": line, "count": 1})
        return patterns

    def _build_timeline(self, commits: list[dict], deploys: list[dict],
                        errors: list[dict]) -> list[TimelineEvent]:
        """Build a unified timeline from all sources."""
        events = []
        for c in commits:
            sev = "warning" if any(k in c["subject"].lower()
                                   for k in ("fix", "hotfix", "revert", "rollback")) else "info"
            events.append(TimelineEvent(
                timestamp=c["timestamp"],
                description=f"Commit by {c['author']}: {c['subject']}",
                source="git",
                severity=sev,
            ))

        for d in deploys:
            events.append(TimelineEvent(
                timestamp=d.get("timestamp", ""),
                description=f"Deploy: {d.get('tag', 'unknown')}",
                source="deploy",
                severity="info",
            ))

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)
        return events

    def _infer_root_cause(self, commits: list[dict], errors: list[dict],
                          timeline: list[TimelineEvent]) -> str:
        """Infer root cause from commits and errors."""
        fix_commits = [c for c in commits if any(
            k in c["subject"].lower() for k in ("fix", "hotfix", "revert", "bug")
        )]
        if fix_commits:
            causes = [c["subject"] for c in fix_commits]
            return f"Based on {len(fix_commits)} fix commit(s): {'; '.join(causes[:3])}"

        if errors:
            return f"Detected {len(errors)} error pattern(s) in the time range"

        if commits:
            return f"Changes from {len(commits)} commit(s) may have introduced the issue"

        return "Root cause could not be determined from available data"

    def _estimate_impact(self, errors: list[dict], timeline: list[TimelineEvent]) -> str:
        """Estimate incident impact."""
        critical_events = [e for e in timeline if e.severity == "critical"]
        warning_events = [e for e in timeline if e.severity == "warning"]

        parts = []
        if critical_events:
            parts.append(f"{len(critical_events)} critical event(s)")
        if warning_events:
            parts.append(f"{len(warning_events)} warning(s)")
        if errors:
            parts.append(f"{len(errors)} error pattern(s) detected")

        if timeline and len(timeline) >= 2:
            duration = f"Duration: {timeline[0].timestamp} to {timeline[-1].timestamp}"
            parts.append(duration)

        return ". ".join(parts) if parts else "Impact assessment requires additional data"

    def _generate_action_items(self, root_cause: str, errors: list[dict]) -> list[ActionItem]:
        """Generate action items from findings."""
        items = []
        if root_cause and "fix" in root_cause.lower():
            items.append(ActionItem(
                action="Verify the fix is deployed and monitoring shows improvement",
                priority="high",
            ))
        if errors:
            items.append(ActionItem(
                action=f"Investigate {len(errors)} error pattern(s) and add alerting",
                priority="high",
            ))
        items.append(ActionItem(
            action="Add or improve monitoring/alerting for affected service",
            priority="medium",
        ))
        items.append(ActionItem(
            action="Update runbooks with learnings from this incident",
            priority="low",
        ))
        return items

    def _extract_lessons(self, root_cause: str, timeline: list[TimelineEvent]) -> list[str]:
        """Extract lessons learned."""
        lessons = []
        warning_count = sum(1 for e in timeline if e.severity in ("warning", "critical"))
        if warning_count > 3:
            lessons.append("Consider adding automated rollback for high-severity changes")
        if any("revert" in e.description.lower() for e in timeline):
            lessons.append("Revert was needed — ensure changes have feature flags or canary deploys")
        lessons.append("Review and update monitoring thresholds for early detection")
        return lessons

    def _assess_severity(self, errors: list[dict], timeline: list[TimelineEvent]) -> str:
        """Assess incident severity level."""
        critical = sum(1 for e in timeline if e.severity == "critical")
        if critical > 0:
            return "P1"
        warnings = sum(1 for e in timeline if e.severity == "warning")
        if warnings > 5:
            return "P2"
        if warnings > 0:
            return "P3"
        return "P4"

    def _generate_title(self, errors: list[dict], commits: list[dict]) -> str:
        """Generate postmortem title."""
        if self.service:
            base = f"[{self.service}] Incident"
        else:
            base = "Incident"

        date_str = ""
        if self.time_from:
            try:
                dt = datetime.fromisoformat(self.time_from.replace(" ", "T"))
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                date_str = self.time_from[:10]

        if date_str:
            return f"{base} Postmortem — {date_str}"
        return f"{base} Postmortem"


def format_postmortem(report: PostmortemReport, fmt: str = "md") -> str:
    """Format postmortem report."""
    if fmt == "json":
        import json
        from dataclasses import asdict
        return json.dumps(asdict(report), indent=2)

    lines = [
        f"# {report.title}",
        "",
        f"**Severity:** {report.severity_level}  ",
        f"**Service:** {report.service or 'N/A'}  ",
        f"**Time Range:** {report.time_range_start} → {report.time_range_end}",
        "",
    ]

    if report.impact:
        lines.extend(["## Impact", "", report.impact, ""])

    if report.timeline:
        lines.extend(["## Timeline", ""])
        for e in report.timeline:
            icon = {"critical": "🔴", "warning": "🟡", "info": "⚪"}.get(e.severity, "⚪")
            lines.append(f"- {icon} `{e.timestamp}` [{e.source}] {e.description}")
        lines.append("")

    if report.root_cause:
        lines.extend(["## Root Cause", "", report.root_cause, ""])

    if report.action_items:
        lines.extend(["## Action Items", ""])
        for i, a in enumerate(report.action_items, 1):
            pri = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(a.priority, "⚪")
            owner = f" (@{a.owner})" if a.owner else ""
            lines.append(f"{i}. {pri} {a.action}{owner}")
        lines.append("")

    if report.lessons_learned:
        lines.extend(["## Lessons Learned", ""])
        for lesson in report.lessons_learned:
            lines.append(f"- {lesson}")
        lines.append("")

    if report.commits_in_range:
        lines.extend(["## Commits in Range", ""])
        for c in report.commits_in_range[:20]:
            lines.append(f"- `{c['hash']}` {c['subject']} ({c['author']})")
        lines.append("")

    return "\n".join(lines)
