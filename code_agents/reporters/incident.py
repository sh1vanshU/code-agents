"""Incident Runbook — automated incident investigation and RCA generation."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger("code_agents.reporters.incident")


@dataclass
class IncidentReport:
    """Collected data from an incident investigation."""

    service: str
    timestamp: str
    pod_status: list[dict] = field(default_factory=list)
    recent_logs: list[str] = field(default_factory=list)
    recent_deploys: list[dict] = field(default_factory=list)
    kibana_errors: list[dict] = field(default_factory=list)
    git_changes: list[str] = field(default_factory=list)
    health_check: dict = field(default_factory=dict)
    suggested_actions: list[str] = field(default_factory=list)
    severity: str = "unknown"  # P1/P2/P3/P4


class IncidentRunner:
    """Runs incident investigation steps and collects results."""

    def __init__(self, service: str, cwd: str):
        self.service = service
        self.cwd = cwd
        self.report = IncidentReport(
            service=service, timestamp=datetime.now().isoformat()
        )
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )

    def run_all(self) -> IncidentReport:
        """Run all investigation steps, collect results."""
        steps: list[tuple[str, object]] = [
            ("Checking pod status", self.check_pods),
            ("Fetching recent logs", self.fetch_logs),
            ("Checking recent deploys", self.check_deploys),
            ("Checking git changes", self.check_git_changes),
            ("Running health check", self.health_check_step),
            ("Analyzing and suggesting", self.analyze),
        ]
        for step_name, step_fn in steps:
            try:
                step_fn()
            except Exception as e:
                logger.warning("Step '%s' failed: %s", step_name, e)
        return self.report

    # ------------------------------------------------------------------
    # Individual investigation steps
    # ------------------------------------------------------------------

    def check_pods(self):
        """Check pod status via ArgoCD API, falling back to kubectl."""
        argocd_app = os.getenv("ARGOCD_APP_NAME", self.service)
        url = f"{self.server_url}/argocd/apps/{argocd_app}/pods"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for pod in data.get("pods", []):
                    self.report.pod_status.append({
                        "name": pod.get("name", "unknown"),
                        "status": pod.get("status", "unknown"),
                        "restarts": pod.get("restarts", 0),
                        "image": pod.get("image", ""),
                    })
        except Exception as e:
            logger.debug("ArgoCD pods check failed: %s", e)
            self._check_pods_kubectl()

    def _check_pods_kubectl(self):
        """Fallback: check pods via kubectl."""
        try:
            ns = os.getenv("K8S_NAMESPACE", "default")
            result = subprocess.run(
                [
                    "kubectl", "get", "pods", "-n", ns,
                    "-l", f"app={self.service}", "-o", "json",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                pods_data = json.loads(result.stdout)
                for item in pods_data.get("items", []):
                    name = item.get("metadata", {}).get("name", "")
                    phase = item.get("status", {}).get("phase", "")
                    containers = item.get("status", {}).get("containerStatuses", [])
                    restarts = sum(c.get("restartCount", 0) for c in containers)
                    self.report.pod_status.append({
                        "name": name, "status": phase, "restarts": restarts,
                    })
        except Exception as e:
            logger.debug("kubectl pods check failed: %s", e)

    def fetch_logs(self):
        """Fetch recent error logs from Kibana via the server API."""
        try:
            url = (
                f"{self.server_url}/kibana/search"
                f"?service={self.service}&level=ERROR&last=1h&limit=20"
            )
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self.report.recent_logs = [
                    hit.get("message", "") for hit in data.get("hits", [])
                ][:20]
        except Exception as e:
            logger.debug("Kibana log fetch failed: %s", e)

    def check_deploys(self):
        """Check recent deployments via ArgoCD."""
        argocd_app = os.getenv("ARGOCD_APP_NAME", self.service)
        try:
            url = f"{self.server_url}/argocd/apps/{argocd_app}/status"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self.report.recent_deploys.append({
                    "app": argocd_app,
                    "sync_status": data.get("sync_status", "unknown"),
                    "health": data.get("health_status", "unknown"),
                    "revision": data.get("revision", ""),
                })
        except Exception as e:
            logger.debug("Deploy check failed: %s", e)

    def check_git_changes(self):
        """Check recent git commits that may have affected this service."""
        try:
            since = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            result = subprocess.run(
                [
                    "git", "log", f"--since={since}", "--oneline",
                    "--", f"*{self.service}*", f"*/{self.service}/*",
                ],
                capture_output=True, text=True, timeout=10, cwd=self.cwd,
            )
            if result.returncode == 0 and result.stdout.strip():
                self.report.git_changes = result.stdout.strip().split("\n")[:10]
        except Exception as e:
            logger.debug("Git changes check failed: %s", e)

    def health_check_step(self):
        """Try hitting the service health endpoint."""
        base = os.getenv(
            f"{self.service.upper().replace('-', '_')}_URL", ""
        )
        if not base:
            return
        for path in ("/health", "/actuator/health", "/api/health", "/status"):
            try:
                url = f"{base.rstrip('/')}{path}"
                start = time.time()
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    elapsed = time.time() - start
                    self.report.health_check = {
                        "endpoint": url,
                        "status": resp.status,
                        "response_time_ms": round(elapsed * 1000),
                    }
                    return
            except Exception as e:
                logger.debug("Health check failed for %s: %s", url, e)
                continue

    def analyze(self):
        """Analyze collected data and determine severity + suggestions."""
        suggestions: list[str] = []

        # Crash-looping pods
        for pod in self.report.pod_status:
            if pod.get("restarts", 0) > 3:
                suggestions.append(
                    f"Pod {pod['name']} has {pod['restarts']} restarts "
                    "— check OOM or startup errors"
                )
                self.report.severity = "P2"

        # Unhealthy deploy
        for deploy in self.report.recent_deploys:
            if deploy.get("health") not in ("Healthy", "healthy"):
                suggestions.append(
                    f"ArgoCD app unhealthy ({deploy.get('health')}) "
                    "— consider rollback"
                )
                self.report.severity = "P1"

        # High error volume
        if len(self.report.recent_logs) > 10:
            suggestions.append(
                f"High error volume ({len(self.report.recent_logs)} errors in last hour)"
            )
            if self.report.severity == "unknown":
                self.report.severity = "P2"

        # Recent code changes
        if self.report.git_changes:
            suggestions.append(
                f"Recent code changes detected "
                f"— review last {len(self.report.git_changes)} commits"
            )

        if not suggestions:
            suggestions.append(
                "No obvious issues detected — check application metrics manually"
            )
            self.report.severity = "P4"

        self.report.suggested_actions = suggestions


# ======================================================================
# Formatting
# ======================================================================


def format_incident_report(report: IncidentReport) -> str:
    """Format report for terminal display."""
    lines: list[str] = []
    header = f"INCIDENT REPORT: {report.service}"
    lines.append(f"  +{'=' * (len(header) + 4)}+")
    lines.append(f"  |  {header}  |")
    lines.append(f"  |  Time: {report.timestamp:<{len(header) - 4}}|")
    lines.append(f"  |  Severity: {report.severity:<{len(header) - 8}}|")
    lines.append(f"  +{'=' * (len(header) + 4)}+")

    # Pod Status
    if report.pod_status:
        lines.append("\n  Pod Status:")
        for pod in report.pod_status:
            ok = pod["status"] in ("Running", "Healthy")
            icon = "[ok]" if ok else "[!!]"
            lines.append(
                f"    {icon} {pod['name']} — {pod['status']} "
                f"(restarts: {pod.get('restarts', 0)})"
            )

    # Recent Errors
    if report.recent_logs:
        lines.append(f"\n  Recent Errors ({len(report.recent_logs)}):")
        for log_line in report.recent_logs[:5]:
            lines.append(f"    - {log_line[:120]}")
        if len(report.recent_logs) > 5:
            lines.append(f"    ... and {len(report.recent_logs) - 5} more")

    # Deploy Status
    if report.recent_deploys:
        lines.append("\n  Recent Deploys:")
        for d in report.recent_deploys:
            lines.append(
                f"    - {d.get('app', '?')} — sync: {d.get('sync_status', '?')}, "
                f"health: {d.get('health', '?')}"
            )

    # Git Changes
    if report.git_changes:
        lines.append("\n  Git Changes (last 2 days):")
        for c in report.git_changes[:5]:
            lines.append(f"    - {c}")

    # Health Check
    if report.health_check:
        hc = report.health_check
        lines.append("\n  Health Check:")
        lines.append(
            f"    {hc['endpoint']} -> {hc['status']} ({hc['response_time_ms']}ms)"
        )

    # Suggestions
    lines.append("\n  Suggested Actions:")
    for i, action in enumerate(report.suggested_actions, 1):
        lines.append(f"    {i}. {action}")

    return "\n".join(lines)


def generate_rca_template(report: IncidentReport) -> str:
    """Generate an RCA markdown template pre-filled with investigation data."""
    pod_lines = "\n".join(
        f"- {p['name']}: {p['status']} (restarts: {p.get('restarts', 0)})"
        for p in report.pod_status
    ) or "- No pod data available"

    error_lines = "\n".join(
        f"- {log[:150]}" for log in report.recent_logs[:10]
    ) or "- No errors captured"

    deploy_lines = "\n".join(
        f"- {d.get('app', '?')}: sync={d.get('sync_status', '?')}, "
        f"health={d.get('health', '?')}"
        for d in report.recent_deploys
    ) or "- No deploy data"

    change_lines = "\n".join(
        f"- {c}" for c in report.git_changes[:10]
    ) or "- No recent changes"

    return f"""# RCA — {report.service} Incident
**Date:** {report.timestamp}
**Severity:** {report.severity}
**Service:** {report.service}

## Timeline
| Time | Event |
|------|-------|
| {report.timestamp} | Incident detected |
| | Investigation started |
| | Root cause identified |
| | Fix deployed |
| | Incident resolved |

## Impact
- Users affected:
- Duration:
- Data loss: None / Describe

## Root Cause
<!-- Describe the root cause -->

## Pod Status at Investigation
{pod_lines}

## Recent Errors
{error_lines}

## Recent Deploys
{deploy_lines}

## Recent Code Changes
{change_lines}

## Fix
<!-- What was done to fix it -->

## Action Items
| # | Action | Owner | Due |
|---|--------|-------|-----|
| 1 | | | |
| 2 | | | |

## Lessons Learned
-
"""


def build_rca_agent_prompt(report: IncidentReport) -> str:
    """Build a prompt for the AI agent to analyze incident findings and produce RCA."""
    sections: list[str] = []
    sections.append(f"## Incident Investigation: {report.service}")
    sections.append(f"Severity: {report.severity}")
    sections.append("")

    if report.pod_status:
        sections.append("### Pod Status")
        for pod in report.pod_status[:10]:
            sections.append(f"- {pod}")

    if report.recent_logs:
        sections.append("### Error Logs (last hour)")
        for log in report.recent_logs[:20]:
            sections.append(f"- {log}")

    if report.recent_deploys:
        sections.append("### Deployment Status")
        for deploy in report.recent_deploys[:10]:
            sections.append(f"- {deploy}")

    if report.git_changes:
        sections.append("### Recent Git Changes")
        for change in report.git_changes[:10]:
            sections.append(f"- {change}")

    if report.health_check:
        sections.append("### Health Check")
        sections.append(str(report.health_check))

    sections.append("")
    sections.append("Based on the above findings, provide:")
    sections.append("1. **Root Cause Analysis** — what is the most likely cause?")
    sections.append("2. **Immediate Fix** — what should be done right now?")
    sections.append("3. **Action Items** — what follow-up tasks are needed?")
    sections.append("4. **Prevention** — how to prevent this in future?")

    return "\n".join(sections)
