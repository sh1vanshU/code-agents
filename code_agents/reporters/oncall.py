"""On-Call Handoff — weekly summary report for on-call handoffs."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.reporters.oncall")


@dataclass
class OncallReport:
    """Data container for an on-call handoff report."""

    period_start: str
    period_end: str
    repo_name: str

    # Git activity
    total_commits: int = 0
    commits_by_author: dict = field(default_factory=dict)
    branches_merged: list[str] = field(default_factory=list)

    # Deploys
    deploys: list[dict] = field(default_factory=list)  # version, time, status

    # Incidents
    incidents: list[dict] = field(default_factory=list)  # description, severity, resolved

    # Build health
    build_failures: int = 0
    test_failures: int = 0

    # Known issues
    flaky_areas: list[str] = field(default_factory=list)
    open_issues: list[str] = field(default_factory=list)

    # Watch items
    watch_items: list[str] = field(default_factory=list)


class OncallReporter:
    """Generates on-call handoff report from git, CI/CD, and Jira data."""

    def __init__(self, cwd: str, days: int = 7):
        self.cwd = cwd
        self.days = days
        self.since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        self.repo_name = os.path.basename(cwd)
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self.report = OncallReport(
            period_start=self.since,
            period_end=datetime.now().strftime("%Y-%m-%d"),
            repo_name=self.repo_name,
        )

    def generate(self) -> OncallReport:
        """Generate the full report by running all collection steps."""
        steps = [
            self._collect_git_activity,
            self._collect_deploy_history,
            self._collect_build_health,
            self._collect_incidents,
            self._identify_flaky_areas,
            self._collect_open_issues,
            self._generate_watch_items,
        ]
        for step in steps:
            try:
                step()
            except Exception as e:
                logger.warning("Report step %s failed: %s", step.__name__, e)
        return self.report

    def _collect_git_activity(self):
        """Git commits, authors, merged branches in the period."""
        # Total commits
        result = subprocess.run(
            ["git", "log", f"--since={self.since}", "--oneline"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=self.cwd,
        )
        if result.returncode == 0:
            commits = [line for line in result.stdout.strip().split("\n") if line]
            self.report.total_commits = len(commits)

        # Commits by author
        result = subprocess.run(
            ["git", "shortlog", "-sn", f"--since={self.since}"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=self.cwd,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        self.report.commits_by_author[parts[1]] = int(parts[0])

        # Merged branches (merge commits)
        result = subprocess.run(
            ["git", "log", f"--since={self.since}", "--merges", "--oneline"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=self.cwd,
        )
        if result.returncode == 0:
            self.report.branches_merged = [
                line
                for line in result.stdout.strip().split("\n")
                if line
            ][:20]

    def _collect_deploy_history(self):
        """Check ArgoCD for recent deploy status."""
        import urllib.request

        try:
            app_name = os.getenv("ARGOCD_APP_NAME", self.repo_name)
            url = f"{self.server_url}/argocd/apps/{app_name}/status"
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self.report.deploys.append(
                    {
                        "app": data.get("app", self.repo_name),
                        "status": data.get("health_status", "unknown"),
                        "sync": data.get("sync_status", "unknown"),
                        "revision": data.get("revision", ""),
                    }
                )
        except Exception:
            logger.debug("Deploy history collection skipped (ArgoCD not reachable)")

    def _collect_build_health(self):
        """Collect build/test failure counts from telemetry."""
        try:
            from code_agents.observability.telemetry import get_summary

            summary = get_summary(days=self.days)
            self.report.build_failures = summary.get("build_failures", 0)
            self.report.test_failures = summary.get("test_failures", 0)
        except Exception:
            logger.debug("Build health collection skipped (telemetry unavailable)")

    def _collect_incidents(self):
        """Collect incidents from Jira (bugs created this week)."""
        import urllib.request

        jira_url = os.getenv("JIRA_URL", "")
        jira_project = os.getenv("JIRA_PROJECT_KEY", "")
        if not (jira_url and jira_project):
            return
        try:
            jql = f"project={jira_project} AND type=Bug AND created >= -{self.days}d"
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for issue in data.get("issues", [])[:10]:
                    self.report.incidents.append(
                        {
                            "key": issue.get("key", ""),
                            "summary": issue.get("summary", ""),
                            "status": issue.get("status", ""),
                            "priority": issue.get("priority", ""),
                        }
                    )
        except Exception:
            logger.debug("Incident collection skipped (Jira not reachable)")

    def _identify_flaky_areas(self):
        """Identify flaky test areas from recent commit messages."""
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={self.since}",
                "--oneline",
                "--grep=flaky",
                "--grep=retry",
                "--grep=intermittent",
                "--all-match",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=self.cwd,
        )
        if result.returncode == 0 and result.stdout.strip():
            self.report.flaky_areas = result.stdout.strip().split("\n")[:5]

    def _collect_open_issues(self):
        """Open Jira bug issues for the project."""
        import urllib.request

        jira_project = os.getenv("JIRA_PROJECT_KEY", "")
        if not jira_project:
            return
        try:
            jql = (
                f"project={jira_project} AND status!=Done AND type=Bug "
                "ORDER BY priority"
            )
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for issue in data.get("issues", [])[:10]:
                    self.report.open_issues.append(
                        f"{issue.get('key', '')}: {issue.get('summary', '')}"
                    )
        except Exception:
            logger.debug("Open issues collection skipped (Jira not reachable)")

    def _generate_watch_items(self):
        """Auto-generate watch items based on collected data."""
        items: list[str] = []
        if self.report.build_failures > 0:
            items.append(f"Build failures this week: {self.report.build_failures}")
        if self.report.test_failures > 0:
            items.append(f"Test failures this week: {self.report.test_failures}")
        for deploy in self.report.deploys:
            if deploy.get("status") not in ("Healthy", "healthy"):
                items.append(
                    f"Deploy unhealthy: {deploy.get('app', '?')} "
                    f"-- {deploy.get('status', '?')}"
                )
        if self.report.flaky_areas:
            items.append(
                f"Flaky test areas detected ({len(self.report.flaky_areas)})"
            )
        if len(self.report.open_issues) > 5:
            items.append(f"High open bug count: {len(self.report.open_issues)}")
        self.report.watch_items = items


def format_oncall_report(report: OncallReport) -> str:
    """Format report for terminal display."""
    lines: list[str] = []
    header = f"ON-CALL HANDOFF: {report.repo_name}"
    lines.append(f"  +== {header} ==+")
    lines.append(f"  | Period: {report.period_start} -> {report.period_end}")
    lines.append(f"  +{'=' * (len(header) + 8)}+")

    # Git Activity
    lines.append(f"\n  Git Activity ({report.total_commits} commits)")
    if report.commits_by_author:
        for author, count in sorted(
            report.commits_by_author.items(), key=lambda x: -x[1]
        ):
            lines.append(f"    {author}: {count} commits")
    if report.branches_merged:
        lines.append(f"  Merged: {len(report.branches_merged)} branches")

    # Deploys
    if report.deploys:
        lines.append("\n  Deploys")
        for d in report.deploys:
            icon = "[ok]" if d.get("status") in ("Healthy", "healthy") else "[!]"
            lines.append(
                f"    {icon} {d.get('app', '?')} -- "
                f"{d.get('status', '?')} (sync: {d.get('sync', '?')})"
            )

    # Incidents
    if report.incidents:
        lines.append(f"\n  Incidents ({len(report.incidents)})")
        for inc in report.incidents:
            lines.append(
                f"    - {inc.get('key', '')}: "
                f"{inc.get('summary', '')} [{inc.get('status', '')}]"
            )

    # Build Health
    lines.append("\n  Build Health")
    lines.append(f"    Build failures: {report.build_failures}")
    lines.append(f"    Test failures: {report.test_failures}")

    # Known Flaky Areas
    if report.flaky_areas:
        lines.append("\n  Known Flaky Areas")
        for area in report.flaky_areas:
            lines.append(f"    ! {area}")

    # Open Issues
    if report.open_issues:
        lines.append(f"\n  Open Bugs ({len(report.open_issues)})")
        for issue in report.open_issues[:10]:
            lines.append(f"    - {issue}")

    # Watch Items
    if report.watch_items:
        lines.append("\n  Watch Items for Next Oncall")
        for item in report.watch_items:
            lines.append(f"    -> {item}")

    return "\n".join(lines)


def generate_oncall_markdown(report: OncallReport) -> str:
    """Generate markdown report for Slack/Confluence."""
    contributors = "\n".join(
        f"- {author}: {count}"
        for author, count in sorted(
            report.commits_by_author.items(), key=lambda x: -x[1]
        )[:5]
    ) or "- No commits"

    deploys = "\n".join(
        f'- {d.get("app", "?")}: {d.get("status", "?")} '
        f'(sync: {d.get("sync", "?")})'
        for d in report.deploys
    ) or "- No deploy data"

    incidents = "\n".join(
        f'- **{inc.get("key", "")}**: {inc.get("summary", "")} '
        f'[{inc.get("status", "")}]'
        for inc in report.incidents
    ) or "- No incidents this period"

    open_bugs = "\n".join(
        f"- {issue}" for issue in report.open_issues[:10]
    ) or "- None"

    watch = "\n".join(
        f"- {item}" for item in report.watch_items
    ) or "- All clear"

    return f"""# On-Call Handoff -- {report.repo_name}
**Period:** {report.period_start} -> {report.period_end}

## Git Activity
- **{report.total_commits} commits** from {len(report.commits_by_author)} authors
- **{len(report.branches_merged)} branches** merged

### Top Contributors
{contributors}

## Deploys
{deploys}

## Incidents
{incidents}

## Build Health
- Build failures: {report.build_failures}
- Test failures: {report.test_failures}

## Open Bugs ({len(report.open_issues)})
{open_bugs}

## Watch Items
{watch}
"""
