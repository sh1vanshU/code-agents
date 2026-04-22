"""Incident Postmortem Auto-Generator — collect signals, build structured postmortem."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.domain.postmortem_gen")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TimelineEvent:
    """Single event in the incident timeline."""
    timestamp: str
    source: str  # git, deploy, alert, jira, grafana, manual
    description: str
    severity: str = "info"  # info, warning, critical


@dataclass
class PostmortemData:
    """Structured postmortem report data."""
    incident_id: str = ""
    title: str = ""
    severity: str = "P2"  # P0-P4
    timeline: list[TimelineEvent] = field(default_factory=list)
    root_cause: str = ""
    impact: dict = field(default_factory=lambda: {
        "affected_users": 0,
        "txn_count": 0,
        "tpv": 0,
        "duration_minutes": 0,
    })
    remediation: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    service: str = ""
    time_range_start: str = ""
    time_range_end: str = ""


# ---------------------------------------------------------------------------
# Time-range parser
# ---------------------------------------------------------------------------

_RELATIVE_RE = re.compile(r"^(\d+)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|d|day|days)\s*ago$", re.IGNORECASE)


def _parse_relative_time(spec: str) -> Optional[str]:
    """Parse '2h ago', '30m ago', '1d ago' into ISO timestamp."""
    m = _RELATIVE_RE.match(spec.strip())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        delta = timedelta(hours=amount)
    elif unit.startswith("m"):
        delta = timedelta(minutes=amount)
    else:
        delta = timedelta(days=amount)
    dt = datetime.now() - delta
    return dt.strftime("%Y-%m-%d %H:%M")


def _resolve_time(spec: str) -> str:
    """Resolve a time spec (absolute or relative) into a usable string."""
    if not spec:
        return ""
    relative = _parse_relative_time(spec)
    return relative if relative else spec


def _parse_range(time_range: str) -> tuple[str, str]:
    """Parse 'from..to' range string into (start, end)."""
    if ".." in time_range:
        parts = time_range.split("..", 1)
        return _resolve_time(parts[0].strip()), _resolve_time(parts[1].strip())
    # Single value treated as start
    return _resolve_time(time_range.strip()), ""


# ---------------------------------------------------------------------------
# PostmortemGenerator
# ---------------------------------------------------------------------------

class PostmortemGenerator:
    """Generates structured incident postmortems from available data sources.

    Works gracefully when external services (Jira, Grafana, Elasticsearch) are
    unavailable — falls back to git data alone.
    """

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
        logger.debug("PostmortemGenerator initialized for %s", self.cwd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        incident_id: str = "",
        time_range: str = "",
        title: str = "",
        severity: str = "P2",
    ) -> PostmortemData:
        """Generate a postmortem by collecting data from available sources.

        Args:
            incident_id: Optional incident/Jira ticket ID.
            time_range: Time range as 'from..to' (e.g. '2h ago..now').
            title: Incident title (auto-generated if empty).
            severity: Severity level (P0-P4).

        Returns:
            Populated PostmortemData.
        """
        start, end = _parse_range(time_range) if time_range else ("", "")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d %H:%M")

        events: list[TimelineEvent] = []

        # Collect from git (always available)
        events.extend(self._pull_git_deploys(start, end))
        events.extend(self._pull_git_commits(start, end))

        # Collect from optional sources (graceful fallback)
        events.extend(self._pull_jira_events(incident_id))
        events.extend(self._pull_grafana_alerts(start, end))
        events.extend(self._pull_elasticsearch_errors(start, end))

        timeline = self._build_timeline(events)
        root_cause = self._analyze_root_cause(timeline)
        impact = self._estimate_impact(timeline, start, end)
        remediation = self._suggest_remediation(root_cause, timeline)
        action_items = self._suggest_action_items(root_cause, timeline)
        contributing = self._find_contributing_factors(timeline)
        lessons = self._extract_lessons(timeline, root_cause)

        if not title:
            title = self._auto_title(incident_id, timeline, start)

        return PostmortemData(
            incident_id=incident_id,
            title=title,
            severity=severity,
            timeline=timeline,
            root_cause=root_cause,
            impact=impact,
            remediation=remediation,
            action_items=action_items,
            contributing_factors=contributing,
            lessons_learned=lessons,
            time_range_start=start,
            time_range_end=end,
        )

    def generate_from_data(
        self,
        events: list[dict],
        title: str = "",
        severity: str = "P2",
    ) -> PostmortemData:
        """Build postmortem from raw event data (offline / manual mode).

        Args:
            events: List of dicts with keys: timestamp, source, description,
                    and optional severity.
            title: Incident title.
            severity: Severity level.

        Returns:
            Populated PostmortemData.
        """
        parsed: list[TimelineEvent] = []
        for ev in events:
            parsed.append(TimelineEvent(
                timestamp=ev.get("timestamp", ""),
                source=ev.get("source", "manual"),
                description=ev.get("description", ""),
                severity=ev.get("severity", "info"),
            ))

        timeline = self._build_timeline(parsed)
        root_cause = self._analyze_root_cause(timeline)
        impact = self._estimate_impact(timeline, "", "")
        remediation = self._suggest_remediation(root_cause, timeline)
        action_items = self._suggest_action_items(root_cause, timeline)
        contributing = self._find_contributing_factors(timeline)
        lessons = self._extract_lessons(timeline, root_cause)

        start = timeline[0].timestamp if timeline else ""
        end = timeline[-1].timestamp if timeline else ""

        return PostmortemData(
            title=title or "Incident Postmortem",
            severity=severity,
            timeline=timeline,
            root_cause=root_cause,
            impact=impact,
            remediation=remediation,
            action_items=action_items,
            contributing_factors=contributing,
            lessons_learned=lessons,
            time_range_start=start,
            time_range_end=end,
        )

    # ------------------------------------------------------------------
    # Data collection helpers
    # ------------------------------------------------------------------

    def _run_git(self, *args: str) -> str:
        """Run a git command, return stdout or empty string on failure."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("git command failed: %s", exc)
            return ""

    def _pull_git_deploys(self, start: str, end: str) -> list[TimelineEvent]:
        """Extract deploy-related events from git tags."""
        events: list[TimelineEvent] = []
        tags_raw = self._run_git(
            "tag", "--sort=-creatordate",
            "--format=%(refname:short)|%(creatordate:iso-strict)",
        )
        if not tags_raw:
            return events

        for line in tags_raw.split("\n")[:50]:
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            tag, ts = parts[0].strip(), parts[1].strip()
            if not any(p in tag.lower() for p in ("deploy", "release", "v")):
                continue
            if start and ts < start:
                continue
            if end and ts > end:
                continue
            events.append(TimelineEvent(
                timestamp=ts,
                source="deploy",
                description=f"Deploy tag: {tag}",
                severity="info",
            ))
        return events

    def _pull_git_commits(self, start: str, end: str) -> list[TimelineEvent]:
        """Extract commit events in the time range."""
        events: list[TimelineEvent] = []
        args = ["log", "--pretty=format:%H|%aI|%an|%s", "--no-merges"]
        if start:
            args.extend(["--since", start])
        if end:
            args.extend(["--until", end])

        output = self._run_git(*args)
        if not output:
            return events

        for line in output.split("\n"):
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, ts, author, subject = parts[0][:8], parts[1], parts[2], parts[3]
            sev = "info"
            lower_subj = subject.lower()
            if any(k in lower_subj for k in ("hotfix", "revert", "rollback", "emergency")):
                sev = "critical"
            elif any(k in lower_subj for k in ("fix", "patch", "bug")):
                sev = "warning"
            events.append(TimelineEvent(
                timestamp=ts,
                source="git",
                description=f"[{sha}] {author}: {subject}",
                severity=sev,
            ))
        return events

    def _pull_jira_events(self, incident_id: str) -> list[TimelineEvent]:
        """Pull events from Jira if configured. Graceful no-op otherwise."""
        if not incident_id:
            return []
        try:
            jira_url = os.environ.get("JIRA_URL", "")
            jira_token = os.environ.get("JIRA_API_TOKEN", "")
            if not jira_url or not jira_token:
                logger.debug("Jira not configured, skipping")
                return []

            import urllib.request
            import json

            url = f"{jira_url.rstrip('/')}/rest/api/2/issue/{incident_id}?fields=summary,status,created,updated,comment"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {jira_token}",
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            events: list[TimelineEvent] = []
            fields = data.get("fields", {})

            # Issue creation
            created = fields.get("created", "")
            if created:
                events.append(TimelineEvent(
                    timestamp=created,
                    source="jira",
                    description=f"Jira {incident_id} created: {fields.get('summary', '')}",
                    severity="warning",
                ))

            # Comments as timeline events
            for comment in (fields.get("comment", {}).get("comments", []))[:10]:
                events.append(TimelineEvent(
                    timestamp=comment.get("created", ""),
                    source="jira",
                    description=f"Jira comment by {comment.get('author', {}).get('displayName', 'unknown')}: {comment.get('body', '')[:100]}",
                    severity="info",
                ))

            return events
        except Exception as exc:
            logger.debug("Jira fetch failed (graceful): %s", exc)
            return []

    def _pull_grafana_alerts(self, start: str, end: str) -> list[TimelineEvent]:
        """Pull firing alerts from Grafana if configured."""
        try:
            grafana_url = os.environ.get("GRAFANA_URL", "")
            grafana_token = os.environ.get("GRAFANA_API_KEY", "")
            if not grafana_url or not grafana_token:
                logger.debug("Grafana not configured, skipping")
                return []

            import urllib.request
            import json

            url = f"{grafana_url.rstrip('/')}/api/alerts?state=alerting"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {grafana_token}",
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                alerts = json.loads(resp.read())

            events: list[TimelineEvent] = []
            for alert in alerts[:20]:
                events.append(TimelineEvent(
                    timestamp=alert.get("newStateDate", ""),
                    source="grafana",
                    description=f"Alert: {alert.get('name', 'unknown')} — {alert.get('state', '')}",
                    severity="critical",
                ))
            return events
        except Exception as exc:
            logger.debug("Grafana fetch failed (graceful): %s", exc)
            return []

    def _pull_elasticsearch_errors(self, start: str, end: str) -> list[TimelineEvent]:
        """Pull error logs from Elasticsearch if configured."""
        try:
            es_url = os.environ.get("ELASTICSEARCH_URL", "")
            if not es_url:
                logger.debug("Elasticsearch not configured, skipping")
                return []

            import urllib.request
            import json

            query = {
                "size": 20,
                "sort": [{"@timestamp": "desc"}],
                "query": {
                    "bool": {
                        "must": [{"match": {"level": "ERROR"}}],
                        "filter": [],
                    }
                },
            }
            if start or end:
                range_filter: dict = {"@timestamp": {}}
                if start:
                    range_filter["@timestamp"]["gte"] = start
                if end:
                    range_filter["@timestamp"]["lte"] = end
                query["query"]["bool"]["filter"].append({"range": range_filter})

            url = f"{es_url.rstrip('/')}/_search"
            body = json.dumps(query).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
            }, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            events: list[TimelineEvent] = []
            for hit in data.get("hits", {}).get("hits", []):
                src = hit.get("_source", {})
                events.append(TimelineEvent(
                    timestamp=src.get("@timestamp", ""),
                    source="elasticsearch",
                    description=f"Error: {src.get('message', '')[:120]}",
                    severity="warning",
                ))
            return events
        except Exception as exc:
            logger.debug("Elasticsearch fetch failed (graceful): %s", exc)
            return []

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _build_timeline(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
        """Sort events by timestamp and deduplicate."""
        seen: set[str] = set()
        deduped: list[TimelineEvent] = []
        for ev in events:
            key = f"{ev.timestamp}|{ev.source}|{ev.description}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ev)

        deduped.sort(key=lambda e: e.timestamp or "")
        return deduped

    def _analyze_root_cause(self, timeline: list[TimelineEvent]) -> str:
        """Pattern-match to infer root cause."""
        deploy_events = [e for e in timeline if e.source == "deploy"]
        critical_events = [e for e in timeline if e.severity == "critical"]
        git_fixes = [e for e in timeline if e.source == "git" and e.severity in ("warning", "critical")]

        # Pattern: deploy followed by errors
        if deploy_events and critical_events:
            deploy_ts = deploy_events[-1].timestamp
            post_deploy_errors = [e for e in critical_events if e.timestamp >= deploy_ts]
            if post_deploy_errors:
                return (
                    f"Deployment ({deploy_events[-1].description}) likely introduced the issue. "
                    f"{len(post_deploy_errors)} critical event(s) occurred after deployment."
                )

        # Pattern: revert/hotfix indicates known bad change
        reverts = [e for e in timeline if any(k in e.description.lower() for k in ("revert", "rollback"))]
        if reverts:
            return (
                f"A code change required revert/rollback: {reverts[0].description}. "
                "The original change likely introduced a regression."
            )

        # Pattern: multiple fixes suggest cascading failure
        if len(git_fixes) > 2:
            return (
                f"Multiple fix commits ({len(git_fixes)}) suggest a cascading or multi-faceted issue. "
                f"First fix: {git_fixes[0].description}"
            )

        # Pattern: config change
        config_events = [e for e in timeline if any(
            k in e.description.lower() for k in ("config", "env", "setting", "flag", "toggle")
        )]
        if config_events:
            return f"Configuration change detected: {config_events[0].description}"

        # Pattern: dependency failure
        dep_events = [e for e in timeline if any(
            k in e.description.lower() for k in ("dependency", "timeout", "connection", "upstream", "downstream")
        )]
        if dep_events:
            return f"External dependency issue: {dep_events[0].description}"

        if git_fixes:
            return f"Based on {len(git_fixes)} fix commit(s): {git_fixes[0].description}"

        if timeline:
            return f"Root cause analysis from {len(timeline)} event(s) — manual review recommended"

        return "Insufficient data to determine root cause"

    def _estimate_impact(self, timeline: list[TimelineEvent], start: str, end: str) -> dict:
        """Estimate impact metrics from timeline data."""
        duration = 0
        if start and end:
            try:
                fmt_candidates = ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"]
                t_start = t_end = None
                for fmt in fmt_candidates:
                    try:
                        t_start = datetime.strptime(start[:19], fmt[:min(len(fmt), 19)])
                        break
                    except ValueError:
                        continue
                for fmt in fmt_candidates:
                    try:
                        t_end = datetime.strptime(end[:19], fmt[:min(len(fmt), 19)])
                        break
                    except ValueError:
                        continue
                if t_start and t_end:
                    duration = max(0, int((t_end - t_start).total_seconds() / 60))
            except Exception:
                pass
        elif len(timeline) >= 2:
            # Estimate from first/last event
            try:
                t0 = datetime.fromisoformat(timeline[0].timestamp[:19])
                t1 = datetime.fromisoformat(timeline[-1].timestamp[:19])
                duration = max(0, int((t1 - t0).total_seconds() / 60))
            except (ValueError, TypeError):
                pass

        critical_count = sum(1 for e in timeline if e.severity == "critical")
        warning_count = sum(1 for e in timeline if e.severity == "warning")

        return {
            "affected_users": 0,  # requires external data
            "txn_count": 0,       # requires external data
            "tpv": 0,             # requires external data
            "duration_minutes": duration,
            "critical_events": critical_count,
            "warning_events": warning_count,
            "total_events": len(timeline),
        }

    def _suggest_remediation(self, root_cause: str, timeline: list[TimelineEvent]) -> list[str]:
        """Suggest remediation steps."""
        steps: list[str] = []
        rc_lower = root_cause.lower()

        if "deploy" in rc_lower:
            steps.append("Rollback to the last known good deployment")
            steps.append("Verify service health after rollback")
        if "revert" in rc_lower or "rollback" in rc_lower:
            steps.append("Confirm revert is deployed to all environments")
            steps.append("Validate fix with canary deployment before full rollout")
        if "config" in rc_lower:
            steps.append("Revert configuration change")
            steps.append("Add configuration validation before apply")
        if "dependency" in rc_lower or "timeout" in rc_lower:
            steps.append("Check upstream service health")
            steps.append("Enable circuit breaker if not already active")

        if not steps:
            steps.append("Identify and isolate the failing component")
            steps.append("Apply targeted fix and validate in staging")

        steps.append("Monitor dashboards for 30 minutes post-remediation")
        steps.append("Update status page / notify stakeholders")
        return steps

    def _suggest_action_items(self, root_cause: str, timeline: list[TimelineEvent]) -> list[str]:
        """Generate action items for follow-up."""
        items: list[str] = []
        rc_lower = root_cause.lower()

        if "deploy" in rc_lower:
            items.append("Add pre-deploy smoke tests for critical paths")
            items.append("Implement canary deployment strategy")
        if "revert" in rc_lower:
            items.append("Add regression tests for the reverted change")
        if "config" in rc_lower:
            items.append("Implement config change review process")

        items.append("Improve monitoring and alerting for early detection")
        items.append("Update runbooks with this incident's learnings")
        items.append("Schedule follow-up review in 1 week")

        return items

    def _find_contributing_factors(self, timeline: list[TimelineEvent]) -> list[str]:
        """Identify contributing factors from the timeline."""
        factors: list[str] = []

        deploy_count = sum(1 for e in timeline if e.source == "deploy")
        if deploy_count > 1:
            factors.append(f"Multiple deployments ({deploy_count}) in the incident window")

        critical = [e for e in timeline if e.severity == "critical"]
        if len(critical) > 3:
            factors.append(f"High volume of critical events ({len(critical)})")

        sources = {e.source for e in timeline}
        if len(sources) >= 3:
            factors.append(f"Multiple systems involved: {', '.join(sorted(sources))}")

        if any("after hours" in e.description.lower() or "weekend" in e.description.lower() for e in timeline):
            factors.append("Incident occurred during off-hours")

        if not factors:
            factors.append("No additional contributing factors identified from available data")

        return factors

    def _extract_lessons(self, timeline: list[TimelineEvent], root_cause: str) -> list[str]:
        """Extract lessons learned."""
        lessons: list[str] = []
        if any("revert" in e.description.lower() for e in timeline):
            lessons.append("Feature flags or canary deploys could have limited blast radius")
        if sum(1 for e in timeline if e.severity == "critical") > 2:
            lessons.append("Automated rollback on critical alert threshold should be considered")
        if "config" in root_cause.lower():
            lessons.append("Configuration changes should go through the same review process as code")

        lessons.append("Review and update monitoring thresholds based on this incident")
        return lessons

    def _auto_title(self, incident_id: str, timeline: list[TimelineEvent], start: str) -> str:
        """Generate a title for the postmortem."""
        prefix = f"[{incident_id}] " if incident_id else ""
        date_str = ""
        if start:
            try:
                dt = datetime.fromisoformat(start.replace(" ", "T")[:19])
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                date_str = start[:10]

        critical = [e for e in timeline if e.severity == "critical"]
        if critical:
            snippet = critical[0].description[:60]
            return f"{prefix}Incident Postmortem — {snippet}"

        if date_str:
            return f"{prefix}Incident Postmortem — {date_str}"
        return f"{prefix}Incident Postmortem"

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_markdown(self, pm: PostmortemData) -> str:
        """Format postmortem as Markdown document."""
        lines: list[str] = []
        lines.append(f"## Incident Postmortem: {pm.title}")
        lines.append("")

        if pm.incident_id:
            lines.append(f"**Incident ID:** {pm.incident_id}  ")
        lines.append(f"**Severity:** {pm.severity}  ")
        if pm.service:
            lines.append(f"**Service:** {pm.service}  ")
        if pm.time_range_start or pm.time_range_end:
            lines.append(f"**Time Range:** {pm.time_range_start} to {pm.time_range_end}  ")
        lines.append("")

        # Summary
        lines.append("### Summary")
        lines.append("")
        duration = pm.impact.get("duration_minutes", 0)
        lines.append(
            f"Incident lasted approximately {duration} minute(s) with "
            f"{pm.impact.get('critical_events', 0)} critical and "
            f"{pm.impact.get('warning_events', 0)} warning event(s) across "
            f"{pm.impact.get('total_events', len(pm.timeline))} total events."
        )
        lines.append("")

        # Timeline
        if pm.timeline:
            lines.append("### Timeline")
            lines.append("")
            for ev in pm.timeline:
                icon = {"critical": "!!!", "warning": "(!)", "info": "   "}.get(ev.severity, "   ")
                lines.append(f"- `{ev.timestamp}` [{ev.source}] {icon} {ev.description}")
            lines.append("")

        # Root Cause
        if pm.root_cause:
            lines.append("### Root Cause")
            lines.append("")
            lines.append(pm.root_cause)
            lines.append("")

        # Contributing Factors
        if pm.contributing_factors:
            lines.append("### Contributing Factors")
            lines.append("")
            for f in pm.contributing_factors:
                lines.append(f"- {f}")
            lines.append("")

        # Impact
        lines.append("### Impact")
        lines.append("")
        lines.append(f"- **Duration:** {duration} minutes")
        if pm.impact.get("affected_users"):
            lines.append(f"- **Affected Users:** {pm.impact['affected_users']:,}")
        if pm.impact.get("txn_count"):
            lines.append(f"- **Transaction Count:** {pm.impact['txn_count']:,}")
        if pm.impact.get("tpv"):
            lines.append(f"- **TPV:** {pm.impact['tpv']:,}")
        lines.append(f"- **Critical Events:** {pm.impact.get('critical_events', 0)}")
        lines.append(f"- **Warning Events:** {pm.impact.get('warning_events', 0)}")
        lines.append("")

        # Remediation
        if pm.remediation:
            lines.append("### Remediation")
            lines.append("")
            for i, step in enumerate(pm.remediation, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        # Action Items
        if pm.action_items:
            lines.append("### Action Items")
            lines.append("")
            for i, item in enumerate(pm.action_items, 1):
                lines.append(f"{i}. [ ] {item}")
            lines.append("")

        # Lessons Learned
        if pm.lessons_learned:
            lines.append("### Lessons Learned")
            lines.append("")
            for lesson in pm.lessons_learned:
                lines.append(f"- {lesson}")
            lines.append("")

        return "\n".join(lines)

    def format_terminal(self, pm: PostmortemData) -> str:
        """Format postmortem for terminal display (plain text with structure)."""
        sep = "-" * 60
        lines: list[str] = []
        lines.append(sep)
        lines.append(f"  INCIDENT POSTMORTEM: {pm.title}")
        lines.append(sep)
        lines.append("")

        if pm.incident_id:
            lines.append(f"  Incident ID : {pm.incident_id}")
        lines.append(f"  Severity    : {pm.severity}")
        if pm.service:
            lines.append(f"  Service     : {pm.service}")
        if pm.time_range_start or pm.time_range_end:
            lines.append(f"  Time Range  : {pm.time_range_start} -> {pm.time_range_end}")

        duration = pm.impact.get("duration_minutes", 0)
        lines.append(f"  Duration    : {duration} min")
        lines.append("")

        # Timeline
        if pm.timeline:
            lines.append("  TIMELINE")
            lines.append("  " + "-" * 40)
            for ev in pm.timeline:
                marker = {"critical": "[!!!]", "warning": "[!]", "info": "[.]"}.get(ev.severity, "[.]")
                lines.append(f"  {ev.timestamp}  {marker} [{ev.source}] {ev.description}")
            lines.append("")

        # Root Cause
        if pm.root_cause:
            lines.append("  ROOT CAUSE")
            lines.append("  " + "-" * 40)
            lines.append(f"  {pm.root_cause}")
            lines.append("")

        # Contributing Factors
        if pm.contributing_factors:
            lines.append("  CONTRIBUTING FACTORS")
            lines.append("  " + "-" * 40)
            for f in pm.contributing_factors:
                lines.append(f"  * {f}")
            lines.append("")

        # Impact
        lines.append("  IMPACT")
        lines.append("  " + "-" * 40)
        lines.append(f"  Duration       : {duration} min")
        lines.append(f"  Critical Events: {pm.impact.get('critical_events', 0)}")
        lines.append(f"  Warning Events : {pm.impact.get('warning_events', 0)}")
        lines.append(f"  Total Events   : {pm.impact.get('total_events', 0)}")
        lines.append("")

        # Remediation
        if pm.remediation:
            lines.append("  REMEDIATION")
            lines.append("  " + "-" * 40)
            for i, step in enumerate(pm.remediation, 1):
                lines.append(f"  {i}. {step}")
            lines.append("")

        # Action Items
        if pm.action_items:
            lines.append("  ACTION ITEMS")
            lines.append("  " + "-" * 40)
            for i, item in enumerate(pm.action_items, 1):
                lines.append(f"  {i}. {item}")
            lines.append("")

        # Lessons Learned
        if pm.lessons_learned:
            lines.append("  LESSONS LEARNED")
            lines.append("  " + "-" * 40)
            for lesson in pm.lessons_learned:
                lines.append(f"  - {lesson}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def format_postmortem_summary(pm: PostmortemData) -> str:
    """One-line summary suitable for chat / CLI output."""
    duration = pm.impact.get("duration_minutes", 0)
    events = pm.impact.get("total_events", len(pm.timeline))
    return (
        f"[{pm.severity}] {pm.title} — "
        f"{duration}min, {events} events, "
        f"root cause: {pm.root_cause[:80]}{'...' if len(pm.root_cause) > 80 else ''}"
    )
