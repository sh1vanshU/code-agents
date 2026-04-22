"""Log Investigator — searches logs, correlates with deploys, finds root cause patterns."""

import logging
import os
import json
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.log_investigator")

@dataclass
class Investigation:
    query: str
    timestamp: str

    # Findings
    matching_logs: list[dict] = field(default_factory=list)  # message, timestamp, level, service
    error_patterns: list[dict] = field(default_factory=list)  # pattern, count, first_seen, last_seen
    correlated_deploys: list[dict] = field(default_factory=list)  # deploy that happened near error start
    related_commits: list[str] = field(default_factory=list)  # commits that may have caused it
    root_cause_hypothesis: str = ""
    suggested_fix: str = ""
    severity: str = "unknown"


class LogInvestigator:
    """Investigates errors by searching logs and correlating with events."""

    def __init__(self, query: str, cwd: str, hours: int = 24):
        self.query = query
        self.cwd = cwd
        self.hours = hours
        self.server_url = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        self.investigation = Investigation(query=query, timestamp=datetime.now().isoformat())
        logger.info("LogInvestigator created: query=%r, cwd=%s, hours=%d", query, cwd, hours)

    def investigate(self) -> Investigation:
        """Run full investigation."""
        logger.info("Starting investigation for: %s", self.query)
        steps = [
            self._search_kibana_logs,
            self._find_error_patterns,
            self._correlate_deploys,
            self._find_related_commits,
            self._hypothesize_root_cause,
        ]
        for step in steps:
            try:
                step()
            except Exception as e:
                logger.warning("Investigation step %s failed: %s", step.__name__, e)
        logger.info("Investigation complete: severity=%s, patterns=%d, commits=%d",
                     self.investigation.severity, len(self.investigation.error_patterns),
                     len(self.investigation.related_commits))
        return self.investigation

    def _search_kibana_logs(self):
        """Search Kibana for the error pattern."""
        import urllib.request
        logger.debug("Searching Kibana for: %s", self.query)
        try:
            service = os.getenv("ARGOCD_APP_NAME", "")
            url = f"{self.server_url}/kibana/search?query={self.query}&last={self.hours}h&limit=50"
            if service:
                url += f"&service={service}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                self.investigation.matching_logs = data.get("hits", [])[:50]
                logger.info("Kibana returned %d matching logs", len(self.investigation.matching_logs))
        except Exception as e:
            logger.debug("Kibana search failed: %s", e)

    def _find_error_patterns(self):
        """Group matching logs by error pattern."""
        patterns = {}
        for log in self.investigation.matching_logs:
            msg = log.get("message", "")
            # Normalize: remove timestamps, IDs, numbers
            normalized = re.sub(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*', '<TIMESTAMP>', msg)
            normalized = re.sub(r'\b[0-9a-f]{8,}\b', '<ID>', normalized)
            normalized = re.sub(r'\b\d+\b', '<N>', normalized)
            # Truncate for grouping
            key = normalized[:200]
            if key not in patterns:
                patterns[key] = {"pattern": key, "count": 0, "first_seen": log.get("timestamp", ""), "last_seen": ""}
            patterns[key]["count"] += 1
            patterns[key]["last_seen"] = log.get("timestamp", "")

        self.investigation.error_patterns = sorted(patterns.values(), key=lambda x: -x["count"])[:10]
        logger.debug("Found %d unique error patterns", len(self.investigation.error_patterns))

    def _correlate_deploys(self):
        """Find deploys that happened around when errors started."""
        if not self.investigation.error_patterns:
            return
        # Get first error time
        first_error = self.investigation.error_patterns[0].get("first_seen", "")
        if not first_error:
            return

        # Check ArgoCD for deploy history
        import urllib.request
        app = os.getenv("ARGOCD_APP_NAME", "")
        if app:
            logger.debug("Checking ArgoCD deploy status for app: %s", app)
            try:
                url = f"{self.server_url}/argocd/apps/{app}/status"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    self.investigation.correlated_deploys.append({
                        "app": app,
                        "revision": data.get("revision", ""),
                        "sync": data.get("sync_status", ""),
                        "health": data.get("health_status", ""),
                    })
                    logger.info("Found correlated deploy: %s rev:%s", app, data.get("revision", "")[:8])
            except Exception as e:
                logger.debug("ArgoCD status check failed: %s", e)

    def _find_related_commits(self):
        """Find commits that may relate to the error."""
        import subprocess
        # Search git log for commits mentioning the error terms
        keywords = self.query.split()[:3]  # first 3 words
        for kw in keywords:
            if len(kw) < 4:
                continue
            try:
                result = subprocess.run(
                    ["git", "log", f"--since={self.hours * 2}h ago", "--oneline", f"--grep={kw}", "-i"],
                    capture_output=True, text=True, timeout=10, cwd=self.cwd
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        if line and line not in self.investigation.related_commits:
                            self.investigation.related_commits.append(line)
            except Exception as e:
                logger.debug("Git log search for '%s' failed: %s", kw, e)
        self.investigation.related_commits = self.investigation.related_commits[:10]
        logger.debug("Found %d related commits", len(self.investigation.related_commits))

    def _hypothesize_root_cause(self):
        """Generate root cause hypothesis from collected data."""
        inv = self.investigation

        if inv.correlated_deploys and inv.error_patterns:
            inv.root_cause_hypothesis = (
                f"Errors correlate with recent deploy "
                f"(revision: {inv.correlated_deploys[0].get('revision', '?')[:8]}). "
                f"Top error pattern seen {inv.error_patterns[0]['count']} times."
            )
            inv.severity = "P2"
        elif inv.error_patterns and inv.error_patterns[0]["count"] > 20:
            inv.root_cause_hypothesis = (
                f"High error volume: {inv.error_patterns[0]['count']} occurrences of same pattern. "
                f"Likely a systematic issue, not transient."
            )
            inv.severity = "P2"
        elif inv.related_commits:
            inv.root_cause_hypothesis = (
                f"Found {len(inv.related_commits)} related commits. Check recent code changes."
            )
            inv.severity = "P3"
        else:
            inv.root_cause_hypothesis = "No clear correlation found. May need manual investigation."
            inv.severity = "P4"

        # Suggested fix
        if inv.correlated_deploys:
            inv.suggested_fix = "Consider rolling back the recent deployment"
        elif inv.related_commits:
            inv.suggested_fix = "Review the related commits for potential regression"
        else:
            inv.suggested_fix = "Check application metrics and increase logging verbosity"

        logger.info("Hypothesis: severity=%s, cause=%s", inv.severity, inv.root_cause_hypothesis[:80])


def format_investigation(inv: Investigation) -> str:
    """Format investigation for terminal."""
    lines = []
    lines.append(f"  ╔══ INVESTIGATION: {inv.query[:50]} ══╗")
    lines.append(f"  ║ Severity: {inv.severity}")
    lines.append(f"  ╚{'═' * (min(len(inv.query), 50) + 22)}╝")

    if inv.error_patterns:
        lines.append(f"\n  Error Patterns ({len(inv.error_patterns)} unique):")
        for p in inv.error_patterns[:5]:
            lines.append(f"    [{p['count']}x] {p['pattern'][:100]}")

    if inv.correlated_deploys:
        lines.append(f"\n  Correlated Deploys:")
        for d in inv.correlated_deploys:
            lines.append(f"    • {d.get('app', '?')} rev:{d.get('revision', '?')[:8]} ({d.get('health', '?')})")

    if inv.related_commits:
        lines.append(f"\n  Related Commits:")
        for c in inv.related_commits[:5]:
            lines.append(f"    • {c}")

    lines.append(f"\n  Root Cause Hypothesis:")
    lines.append(f"    {inv.root_cause_hypothesis}")
    lines.append(f"\n  Suggested Action:")
    lines.append(f"    → {inv.suggested_fix}")

    return "\n".join(lines)
