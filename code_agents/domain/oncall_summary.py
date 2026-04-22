"""On-Call Log Summarizer — alerts → grouped summary + standup text."""

from __future__ import annotations

import logging
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.domain.oncall_summary")


@dataclass
class AlertEntry:
    timestamp: str
    service: str
    alert_type: str
    message: str
    severity: str = "warning"  # critical, warning, info
    source: str = ""  # slack, log_file, kibana


@dataclass
class AlertGroup:
    service: str
    alert_type: str
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_messages: list[str] = field(default_factory=list)
    severity: str = "warning"


@dataclass
class OncallSummaryReport:
    period_hours: int = 12
    source: str = "log_file"
    total_alerts: int = 0
    alert_groups: list[AlertGroup] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    top_services: list[dict] = field(default_factory=list)
    standup_update: str = ""
    action_items: list[str] = field(default_factory=list)
    time_from: str = ""
    time_to: str = ""


# Common alert patterns for classification
_ALERT_PATTERNS = {
    r"(?:OOM|out of memory|memory limit)": ("memory", "critical"),
    r"(?:timeout|timed out|deadline exceeded)": ("timeout", "warning"),
    r"(?:5\d{2}|internal server error|502|503|504)": ("http_error", "critical"),
    r"(?:connection refused|ECONNREFUSED|connection reset)": ("connection", "critical"),
    r"(?:disk space|disk full|no space left)": ("disk", "critical"),
    r"(?:CPU|high load|load average)": ("cpu", "warning"),
    r"(?:latency|slow|p99|p95)": ("latency", "warning"),
    r"(?:rate limit|throttl)": ("rate_limit", "warning"),
    r"(?:authentication|auth fail|unauthorized|401|403)": ("auth", "warning"),
    r"(?:deploy|deployment|rollout)": ("deploy", "info"),
}


class OncallSummarizer:
    """Summarizes on-call alerts from various sources."""

    def __init__(self, cwd: str = ".", hours: int = 12, channel: str = "oncall",
                 log_path: str = "", server_url: str = ""):
        self.cwd = os.path.abspath(cwd)
        self.hours = hours
        self.channel = channel
        self.log_path = log_path
        self.server_url = server_url

    def generate(self) -> OncallSummaryReport:
        """Generate on-call summary report."""
        alerts = self._collect_alerts()
        groups = self._group_alerts(alerts)
        patterns = self._detect_patterns(groups)
        top_services = self._rank_services(alerts)
        action_items = self._generate_action_items(groups, patterns)
        standup = self._generate_standup(groups, patterns, top_services)

        now = datetime.now()
        return OncallSummaryReport(
            period_hours=self.hours,
            source=self._detect_source(),
            total_alerts=len(alerts),
            alert_groups=groups,
            patterns=patterns,
            top_services=top_services,
            standup_update=standup,
            action_items=action_items,
            time_from=(now - timedelta(hours=self.hours)).isoformat(),
            time_to=now.isoformat(),
        )

    def _detect_source(self) -> str:
        if self.log_path:
            return "log_file"
        if self.server_url:
            return "server_api"
        return "log_file"

    def _collect_alerts(self) -> list[AlertEntry]:
        """Collect alerts from available sources."""
        alerts = []

        # Try log file first
        if self.log_path and os.path.exists(self.log_path):
            alerts.extend(self._parse_log_file(self.log_path))
        else:
            # Try common log locations
            for log_dir in ["/var/log", os.path.join(self.cwd, "logs"),
                            os.path.join(self.cwd, "log")]:
                if os.path.isdir(log_dir):
                    for f in os.listdir(log_dir):
                        if any(p in f.lower() for p in ("error", "alert", "oncall", "incident")):
                            path = os.path.join(log_dir, f)
                            alerts.extend(self._parse_log_file(path))

        # Try git log for deploy-related events
        alerts.extend(self._collect_from_git())

        return alerts

    def _parse_log_file(self, path: str) -> list[AlertEntry]:
        """Parse a log file for alert entries."""
        alerts = []
        try:
            with open(path, "r", errors="replace") as f:
                for line in f:
                    entry = self._parse_log_line(line.strip())
                    if entry:
                        alerts.append(entry)
        except OSError as exc:
            logger.debug("Could not read log file %s: %s", path, exc)
        return alerts

    def _parse_log_line(self, line: str) -> Optional[AlertEntry]:
        """Parse a single log line into an alert entry."""
        if not line:
            return None

        # Detect severity from log level
        severity = "info"
        if re.search(r"\b(ERROR|CRITICAL|FATAL)\b", line, re.IGNORECASE):
            severity = "critical"
        elif re.search(r"\b(WARN|WARNING)\b", line, re.IGNORECASE):
            severity = "warning"
        elif not re.search(r"\b(ERROR|WARN|WARNING|CRITICAL|FATAL|ALERT)\b", line, re.IGNORECASE):
            return None  # Skip non-alert lines

        # Extract timestamp
        ts_match = re.search(
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line
        )
        timestamp = ts_match.group(1) if ts_match else datetime.now().isoformat()

        # Classify alert type
        alert_type = "unknown"
        for pattern, (atype, default_sev) in _ALERT_PATTERNS.items():
            if re.search(pattern, line, re.IGNORECASE):
                alert_type = atype
                if default_sev == "critical":
                    severity = "critical"
                break

        # Extract service name (heuristic)
        service = "unknown"
        svc_match = re.search(r"\[(\w[\w.-]+)\]", line)
        if svc_match:
            service = svc_match.group(1)

        return AlertEntry(
            timestamp=timestamp,
            service=service,
            alert_type=alert_type,
            message=line[:200],
            severity=severity,
            source="log_file",
        )

    def _collect_from_git(self) -> list[AlertEntry]:
        """Collect deploy/incident events from git."""
        import subprocess
        alerts = []
        try:
            since = (datetime.now() - timedelta(hours=self.hours)).isoformat()
            result = subprocess.run(
                ["git", "log", "--since", since, "--pretty=format:%aI|%s", "--no-merges"],
                cwd=self.cwd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        ts, msg = parts
                        if any(k in msg.lower() for k in ("fix", "hotfix", "revert", "rollback", "incident")):
                            alerts.append(AlertEntry(
                                timestamp=ts, service="git", alert_type="deploy",
                                message=msg, severity="warning", source="git",
                            ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return alerts

    def _group_alerts(self, alerts: list[AlertEntry]) -> list[AlertGroup]:
        """Group alerts by service + type."""
        groups: dict[tuple[str, str], list[AlertEntry]] = defaultdict(list)
        for a in alerts:
            groups[(a.service, a.alert_type)].append(a)

        result = []
        for (service, atype), items in sorted(groups.items(), key=lambda x: -len(x[1])):
            sorted_items = sorted(items, key=lambda a: a.timestamp)
            max_sev = "info"
            for item in items:
                if item.severity == "critical":
                    max_sev = "critical"
                elif item.severity == "warning" and max_sev != "critical":
                    max_sev = "warning"

            result.append(AlertGroup(
                service=service,
                alert_type=atype,
                count=len(items),
                first_seen=sorted_items[0].timestamp if sorted_items else "",
                last_seen=sorted_items[-1].timestamp if sorted_items else "",
                sample_messages=[a.message for a in sorted_items[:3]],
                severity=max_sev,
            ))

        return result

    def _detect_patterns(self, groups: list[AlertGroup]) -> list[str]:
        """Detect recurring patterns."""
        patterns = []
        for g in groups:
            if g.count >= 5:
                patterns.append(
                    f"Recurring: {g.service}/{g.alert_type} — {g.count} occurrences"
                )
        # Check for service concentration
        svc_counts = Counter(g.service for g in groups)
        for svc, count in svc_counts.most_common(3):
            if count >= 3:
                patterns.append(f"Service hotspot: {svc} has {count} distinct alert types")
        return patterns

    def _rank_services(self, alerts: list[AlertEntry]) -> list[dict]:
        """Rank services by alert count."""
        counts = Counter(a.service for a in alerts)
        return [{"service": svc, "alert_count": cnt}
                for svc, cnt in counts.most_common(10)]

    def _generate_action_items(self, groups: list[AlertGroup],
                                patterns: list[str]) -> list[str]:
        """Generate action items from findings."""
        items = []
        critical_groups = [g for g in groups if g.severity == "critical"]
        if critical_groups:
            for g in critical_groups[:3]:
                items.append(f"Investigate critical alerts in {g.service} ({g.alert_type})")
        for p in patterns:
            if "Recurring" in p:
                items.append(f"Address recurring issue: {p}")
        if not items:
            items.append("No critical items — continue monitoring")
        return items

    def _generate_standup(self, groups: list[AlertGroup], patterns: list[str],
                          top_services: list[dict]) -> str:
        """Generate standup update text."""
        total = sum(g.count for g in groups)
        critical = sum(g.count for g in groups if g.severity == "critical")
        warning = sum(g.count for g in groups if g.severity == "warning")

        lines = [f"On-call summary (last {self.hours}h):"]
        lines.append(f"- {total} total alerts ({critical} critical, {warning} warnings)")

        if top_services:
            top = top_services[0]
            lines.append(f"- Top service: {top['service']} ({top['alert_count']} alerts)")

        if patterns:
            lines.append(f"- Patterns: {patterns[0]}")

        critical_groups = [g for g in groups if g.severity == "critical"]
        if critical_groups:
            lines.append("- Action needed:")
            for g in critical_groups[:3]:
                lines.append(f"  - {g.service}/{g.alert_type}: {g.count} occurrences")

        return "\n".join(lines)


def format_oncall_summary(report: OncallSummaryReport) -> str:
    """Format on-call summary for display."""
    lines = [
        "## On-Call Summary",
        "",
        f"**Period:** Last {report.period_hours} hours",
        f"**Source:** {report.source}",
        f"**Total Alerts:** {report.total_alerts}",
        "",
    ]

    if report.top_services:
        lines.extend(["### Top Services", ""])
        for s in report.top_services[:5]:
            lines.append(f"- **{s['service']}**: {s['alert_count']} alerts")
        lines.append("")

    if report.alert_groups:
        lines.extend(["### Alert Groups", ""])
        for g in report.alert_groups[:15]:
            icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(g.severity, "⚪")
            lines.append(f"- {icon} **{g.service}** / {g.alert_type}: {g.count}x "
                         f"({g.first_seen} → {g.last_seen})")
        lines.append("")

    if report.patterns:
        lines.extend(["### Patterns Detected", ""])
        for p in report.patterns:
            lines.append(f"- {p}")
        lines.append("")

    if report.action_items:
        lines.extend(["### Action Items", ""])
        for i, item in enumerate(report.action_items, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    if report.standup_update:
        lines.extend(["### Standup Update", "", "```", report.standup_update, "```", ""])

    return "\n".join(lines)
