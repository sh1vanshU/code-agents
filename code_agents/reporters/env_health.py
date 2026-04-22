"""Environment Health — dashboard-style status of all integrations."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reporters.env_health")


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    status: str  # ok, warning, error, unknown
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class EnvironmentHealth:
    """Full environment health report."""

    checks: list[HealthCheck] = field(default_factory=list)

    @property
    def overall(self) -> str:
        statuses = [c.status for c in self.checks]
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        if not statuses:
            return "unknown"
        return "ok"


class EnvironmentHealthChecker:
    """Checks health of all configured integrations via server API."""

    def __init__(self):
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self.report = EnvironmentHealth()
        logger.info("EnvironmentHealthChecker initialized — server=%s", self.server_url)

    def run_all(self) -> EnvironmentHealth:
        """Run all health checks."""
        steps = [
            ("ArgoCD App Health", self._check_argocd),
            ("Jenkins Build", self._check_jenkins),
            ("Jira Open Bugs", self._check_jira),
            ("Kibana Error Rate", self._check_kibana),
            ("Server Health", self._check_server),
        ]
        for name, fn in steps:
            try:
                fn()
            except Exception as e:
                self.report.checks.append(HealthCheck(
                    name=name, status="error", message=str(e),
                ))
                logger.debug("Health check '%s' failed: %s", name, e)
        return self.report

    def _api_get(self, path: str, timeout: int = 10) -> Optional[dict]:
        """GET from server API, return parsed JSON or None."""
        url = f"{self.server_url}{path}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.debug("API GET %s failed: %s", path, e)
            return None

    def _check_server(self):
        data = self._api_get("/health")
        if data:
            self.report.checks.append(HealthCheck(
                name="Server Health", status="ok",
                message=f"Server running — {data.get('status', 'ok')}",
                details=data,
            ))
        else:
            self.report.checks.append(HealthCheck(
                name="Server Health", status="error",
                message="Server not reachable",
            ))

    def _check_argocd(self):
        app_name = os.getenv("ARGOCD_APP_NAME", "")
        if not app_name:
            self.report.checks.append(HealthCheck(
                name="ArgoCD App Health", status="unknown",
                message="ARGOCD_APP_NAME not configured",
            ))
            return
        data = self._api_get(f"/argocd/apps/{app_name}/status")
        if data:
            health = data.get("health", {}).get("status", "unknown")
            sync = data.get("sync", {}).get("status", "unknown")
            pods = data.get("pod_count", 0)
            status = "ok" if health == "Healthy" and sync == "Synced" else "warning"
            self.report.checks.append(HealthCheck(
                name="ArgoCD App Health", status=status,
                message=f"Health={health}, Sync={sync}, Pods={pods}",
                details=data,
            ))
        else:
            self.report.checks.append(HealthCheck(
                name="ArgoCD App Health", status="error",
                message="ArgoCD API not reachable",
            ))

    def _check_jenkins(self):
        jenkins_url = os.getenv("JENKINS_URL", "")
        if not jenkins_url:
            self.report.checks.append(HealthCheck(
                name="Jenkins Build", status="unknown",
                message="JENKINS_URL not configured",
            ))
            return
        data = self._api_get("/jenkins/last-build")
        if data:
            result = data.get("result", "unknown")
            build_num = data.get("number", "?")
            status = "ok" if result == "SUCCESS" else "warning" if result == "UNSTABLE" else "error"
            self.report.checks.append(HealthCheck(
                name="Jenkins Build", status=status,
                message=f"Build #{build_num}: {result}",
                details=data,
            ))
        else:
            self.report.checks.append(HealthCheck(
                name="Jenkins Build", status="error",
                message="Jenkins API not reachable",
            ))

    def _check_jira(self):
        jira_url = os.getenv("JIRA_URL", "")
        if not jira_url:
            self.report.checks.append(HealthCheck(
                name="Jira Open Bugs", status="unknown",
                message="JIRA_URL not configured",
            ))
            return
        project = os.getenv("JIRA_PROJECT_KEY", "")
        jql = f"project={project} AND type=Bug AND status!=Done" if project else "type=Bug AND status!=Done"
        data = self._api_get(f"/jira/search?jql={jql}&max_results=1")
        if data:
            total = data.get("total", 0)
            status = "ok" if total < 5 else "warning" if total < 15 else "error"
            self.report.checks.append(HealthCheck(
                name="Jira Open Bugs", status=status,
                message=f"{total} open bugs",
                details={"total": total},
            ))
        else:
            self.report.checks.append(HealthCheck(
                name="Jira Open Bugs", status="error",
                message="Jira API not reachable",
            ))

    def _check_kibana(self):
        kibana_url = os.getenv("KIBANA_URL", "")
        if not kibana_url:
            self.report.checks.append(HealthCheck(
                name="Kibana Error Rate", status="unknown",
                message="KIBANA_URL not configured",
            ))
            return
        data = self._api_get("/kibana/error-rate?minutes=60")
        if data:
            rate = data.get("error_rate", 0)
            count = data.get("error_count", 0)
            status = "ok" if rate < 1 else "warning" if rate < 5 else "error"
            self.report.checks.append(HealthCheck(
                name="Kibana Error Rate", status=status,
                message=f"{rate:.1f}% error rate ({count} errors in last hour)",
                details=data,
            ))
        else:
            self.report.checks.append(HealthCheck(
                name="Kibana Error Rate", status="error",
                message="Kibana API not reachable",
            ))


def format_env_health(report: EnvironmentHealth) -> str:
    """Format environment health as dashboard display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Environment Health Dashboard")
    lines.append("  " + "=" * 50)
    lines.append("")

    status_icons = {
        "ok": "[OK]",
        "warning": "[!!]",
        "error": "[XX]",
        "unknown": "[??]",
    }

    overall_icon = status_icons.get(report.overall, "[??]")
    lines.append(f"  Overall: {overall_icon} {report.overall.upper()}")
    lines.append("")

    for check in report.checks:
        icon = status_icons.get(check.status, "[??]")
        lines.append(f"  {icon} {check.name:<25} {check.message}")

    lines.append("")
    return "\n".join(lines)
