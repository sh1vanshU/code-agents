"""Morning Autopilot — one command to start your day."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.reporters.morning")


@dataclass
class MorningStep:
    """Result of a single morning check step."""

    name: str
    status: str  # ok, warning, error, skipped
    output: str = ""


@dataclass
class MorningReport:
    """Full morning autopilot report."""

    timestamp: str = ""
    steps: list[MorningStep] = field(default_factory=list)

    @property
    def summary(self) -> str:
        ok = sum(1 for s in self.steps if s.status == "ok")
        warn = sum(1 for s in self.steps if s.status == "warning")
        err = sum(1 for s in self.steps if s.status == "error")
        skip = sum(1 for s in self.steps if s.status == "skipped")
        return f"{ok} ok, {warn} warnings, {err} errors, {skip} skipped"


class MorningAutopilot:
    """Runs morning routine: git pull, build status, Jira, tests, alerts."""

    def __init__(self, cwd: str, timeout: int = 30):
        self.cwd = cwd
        self.timeout = timeout
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self.report = MorningReport(timestamp=datetime.now().isoformat())
        logger.info("MorningAutopilot initialized — cwd=%s", cwd)

    def run_all(self) -> MorningReport:
        """Run all morning steps with graceful failure."""
        steps = [
            ("Git Pull", self._git_pull),
            ("Build Status", self._build_status),
            ("Jira Board", self._jira_board),
            ("Run Tests", self._run_tests),
            ("Kibana Alerts", self._kibana_alerts),
            ("Standup Summary", self._standup_summary),
            ("Open PRs", self._check_open_prs),
            ("Deploy Status", self._check_deploy_status),
            ("Blockers", self._check_blockers),
        ]
        for name, fn in steps:
            try:
                fn()
            except Exception as e:
                self.report.steps.append(MorningStep(
                    name=name, status="error", output=str(e),
                ))
                logger.debug("Morning step '%s' failed: %s", name, e)
        return self.report

    def _api_get(self, path: str) -> Optional[dict]:
        url = f"{self.server_url}{path}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _git_pull(self):
        try:
            result = subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=self.cwd, capture_output=True, text=True, timeout=self.timeout,
            )
            if result.returncode == 0:
                output = result.stdout.strip() or "Already up to date."
                self.report.steps.append(MorningStep(
                    name="Git Pull", status="ok", output=output,
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Git Pull", status="warning",
                    output=result.stderr.strip() or "Pull failed",
                ))
        except subprocess.TimeoutExpired:
            self.report.steps.append(MorningStep(
                name="Git Pull", status="error", output="Timeout",
            ))

    def _build_status(self):
        jenkins_url = os.getenv("JENKINS_URL", "")
        if not jenkins_url:
            self.report.steps.append(MorningStep(
                name="Build Status", status="skipped",
                output="Jenkins not configured",
            ))
            return
        data = self._api_get("/jenkins/last-build")
        if data:
            result = data.get("result", "unknown")
            build_num = data.get("number", "?")
            status = "ok" if result == "SUCCESS" else "warning"
            self.report.steps.append(MorningStep(
                name="Build Status", status=status,
                output=f"Build #{build_num}: {result}",
            ))
        else:
            self.report.steps.append(MorningStep(
                name="Build Status", status="error",
                output="Jenkins not reachable",
            ))

    def _jira_board(self):
        jira_url = os.getenv("JIRA_URL", "")
        if not jira_url:
            self.report.steps.append(MorningStep(
                name="Jira Board", status="skipped",
                output="Jira not configured",
            ))
            return
        data = self._api_get("/jira/search?jql=assignee=currentUser() AND status='In Progress'&max_results=10")
        if data:
            issues = data.get("issues", [])
            if issues:
                items = []
                for issue in issues[:5]:
                    key = issue.get("key", "")
                    summary = issue.get("fields", {}).get("summary", "")
                    items.append(f"{key}: {summary[:50]}")
                self.report.steps.append(MorningStep(
                    name="Jira Board", status="ok",
                    output=f"{len(issues)} in progress:\n" + "\n".join(f"  - {i}" for i in items),
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Jira Board", status="ok",
                    output="No tickets in progress",
                ))
        else:
            self.report.steps.append(MorningStep(
                name="Jira Board", status="error",
                output="Jira not reachable",
            ))

    def _run_tests(self):
        # Detect test command
        test_cmd = os.getenv("CODE_AGENTS_TEST_CMD", "")
        if not test_cmd:
            if os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
                test_cmd = "pytest --tb=no -q"
            elif os.path.exists(os.path.join(self.cwd, "pom.xml")):
                test_cmd = "mvn test -q"
            elif os.path.exists(os.path.join(self.cwd, "package.json")):
                test_cmd = "npm test"
            else:
                self.report.steps.append(MorningStep(
                    name="Run Tests", status="skipped",
                    output="No test command detected",
                ))
                return

        try:
            result = subprocess.run(
                test_cmd.split(),
                cwd=self.cwd, capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                # Extract last few lines as summary
                out_lines = result.stdout.strip().splitlines()
                summary = "\n".join(out_lines[-3:]) if out_lines else "Tests passed"
                self.report.steps.append(MorningStep(
                    name="Run Tests", status="ok", output=summary,
                ))
            else:
                err_lines = result.stderr.strip().splitlines() or result.stdout.strip().splitlines()
                summary = "\n".join(err_lines[-3:]) if err_lines else "Tests failed"
                self.report.steps.append(MorningStep(
                    name="Run Tests", status="error", output=summary,
                ))
        except subprocess.TimeoutExpired:
            self.report.steps.append(MorningStep(
                name="Run Tests", status="warning", output="Test run timed out (120s)",
            ))

    def _kibana_alerts(self):
        kibana_url = os.getenv("KIBANA_URL", "")
        if not kibana_url:
            self.report.steps.append(MorningStep(
                name="Kibana Alerts", status="skipped",
                output="Kibana not configured",
            ))
            return
        data = self._api_get("/kibana/error-rate?minutes=60")
        if data:
            rate = data.get("error_rate", 0)
            count = data.get("error_count", 0)
            status = "ok" if rate < 1 else "warning" if rate < 5 else "error"
            self.report.steps.append(MorningStep(
                name="Kibana Alerts", status=status,
                output=f"{rate:.1f}% error rate ({count} errors in last hour)",
            ))
        else:
            self.report.steps.append(MorningStep(
                name="Kibana Alerts", status="error",
                output="Kibana not reachable",
            ))

    def _standup_summary(self):
        """Generate brief standup from git log."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--since=yesterday", "-10"],
                cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                commits = result.stdout.strip().splitlines()
                self.report.steps.append(MorningStep(
                    name="Standup Summary", status="ok",
                    output=f"{len(commits)} commits yesterday:\n" +
                           "\n".join(f"  - {c}" for c in commits[:5]),
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Standup Summary", status="ok",
                    output="No commits since yesterday",
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.report.steps.append(MorningStep(
                name="Standup Summary", status="error",
                output="Git not available",
            ))


    def _check_open_prs(self):
        """Check for recent open PRs / remote branch activity."""
        data = self._api_get("/git/branches")
        if data:
            branches = data if isinstance(data, list) else data.get("branches", [])
            if branches:
                items = [b if isinstance(b, str) else b.get("name", "") for b in branches[:10]]
                self.report.steps.append(MorningStep(
                    name="Open PRs", status="ok",
                    output=f"{len(branches)} remote branches:\n" +
                           "\n".join(f"  - {b}" for b in items),
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Open PRs", status="ok",
                    output="No remote branches found",
                ))
            return

        # Fallback to git log for recent remote activity
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--remotes", "--since=1.day.ago"],
                cwd=self.cwd, capture_output=True, text=True, timeout=self.timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().splitlines()
                self.report.steps.append(MorningStep(
                    name="Open PRs", status="ok",
                    output=f"{len(lines)} recent remote commits:\n" +
                           "\n".join(f"  - {l}" for l in lines[:5]),
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Open PRs", status="ok",
                    output="No recent remote activity",
                ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.report.steps.append(MorningStep(
                name="Open PRs", status="error",
                output="Could not check remote activity",
            ))

    def _check_deploy_status(self):
        """Check ArgoCD deployment status."""
        argocd_url = os.getenv("ARGOCD_URL", "")
        if not argocd_url:
            self.report.steps.append(MorningStep(
                name="Deploy Status", status="skipped",
                output="ArgoCD not configured",
            ))
            return
        data = self._api_get("/argocd/status")
        if data:
            sync = data.get("sync_status", "Unknown")
            health = data.get("health_status", "Unknown")
            app = data.get("app_name", "")
            status = "ok" if sync == "Synced" and health == "Healthy" else "warning"
            self.report.steps.append(MorningStep(
                name="Deploy Status", status=status,
                output=f"{app}: sync={sync}, health={health}",
            ))
        else:
            self.report.steps.append(MorningStep(
                name="Deploy Status", status="error",
                output="ArgoCD not reachable",
            ))

    def _check_blockers(self):
        """Check for blocked Jira tickets assigned to current user."""
        jira_url = os.getenv("JIRA_URL", "")
        if not jira_url:
            self.report.steps.append(MorningStep(
                name="Blockers", status="skipped",
                output="Jira not configured",
            ))
            return
        data = self._api_get("/jira/search?jql=status=Blocked AND assignee=currentUser()&max_results=10")
        if data:
            issues = data.get("issues", [])
            if issues:
                items = []
                for issue in issues[:5]:
                    key = issue.get("key", "")
                    summary = issue.get("fields", {}).get("summary", "")
                    items.append(f"{key}: {summary[:50]}")
                self.report.steps.append(MorningStep(
                    name="Blockers", status="warning",
                    output=f"{len(issues)} blocked tickets:\n" +
                           "\n".join(f"  - {i}" for i in items),
                ))
            else:
                self.report.steps.append(MorningStep(
                    name="Blockers", status="ok",
                    output="No blocked tickets",
                ))
        else:
            self.report.steps.append(MorningStep(
                name="Blockers", status="error",
                output="Jira not reachable",
            ))


def format_morning_report(report: MorningReport) -> str:
    """Format morning report for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Morning Autopilot Report")
    lines.append("  " + "=" * 50)
    lines.append(f"  {report.timestamp}")
    lines.append("")

    status_icons = {
        "ok": "[OK]",
        "warning": "[!!]",
        "error": "[XX]",
        "skipped": "[--]",
    }

    for step in report.steps:
        icon = status_icons.get(step.status, "[??]")
        lines.append(f"  {icon} {step.name}")
        if step.output:
            for out_line in step.output.splitlines():
                lines.append(f"      {out_line}")
        lines.append("")

    lines.append(f"  Summary: {report.summary}")
    lines.append("")
    return "\n".join(lines)
