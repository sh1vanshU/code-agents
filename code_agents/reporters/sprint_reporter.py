"""Sprint Reporter — generates sprint summary from Jira, git, and build data."""

import logging
import os
import re
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.reporters.sprint_reporter")


@dataclass
class SprintReport:
    sprint_name: str = ""
    start_date: str = ""
    end_date: str = ""
    goal: str = ""
    repo_name: str = ""

    # Stories
    stories_completed: list[dict] = field(default_factory=list)  # key, summary, points, assignee
    stories_in_progress: list[dict] = field(default_factory=list)
    stories_carry_over: list[dict] = field(default_factory=list)

    # Bugs
    bugs_created: int = 0
    bugs_resolved: int = 0
    bugs_open: list[dict] = field(default_factory=list)

    # Git stats
    total_commits: int = 0
    total_prs_merged: int = 0
    commits_by_author: dict = field(default_factory=dict)
    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0

    # Build/Deploy
    builds_triggered: int = 0
    deploys: list[dict] = field(default_factory=list)

    # Points
    points_committed: int = 0
    points_completed: int = 0
    velocity: float = 0.0


class SprintReporter:
    def __init__(self, cwd: str, sprint_days: int = 14):
        self.cwd = cwd
        self.sprint_days = sprint_days
        self.repo_name = os.path.basename(cwd)
        self.server_url = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        self.report = SprintReport(repo_name=self.repo_name)
        self.since = (datetime.now() - timedelta(days=sprint_days)).strftime("%Y-%m-%d")

    def generate(self) -> SprintReport:
        """Generate full sprint report."""
        steps = [
            self._collect_jira_data,
            self._collect_git_stats,
            self._collect_build_data,
            self._calculate_velocity,
        ]
        for step in steps:
            try:
                step()
            except Exception as e:
                logger.warning("Sprint report step failed: %s", e)
        return self.report

    def _collect_jira_data(self):
        """Collect sprint data from Jira."""
        import urllib.request
        jira_project = os.getenv("JIRA_PROJECT_KEY", "")
        if not jira_project:
            return

        # Stories completed this sprint
        try:
            jql = f"project={jira_project} AND status=Done AND updated>=-{self.sprint_days}d AND type=Story"
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for issue in data.get("issues", []):
                    self.report.stories_completed.append({
                        "key": issue.get("key", ""),
                        "summary": issue.get("summary", ""),
                        "points": issue.get("story_points", 0),
                        "assignee": issue.get("assignee", ""),
                    })
        except Exception as e:
            logger.debug("Jira completed stories failed: %s", e)

        # In progress
        try:
            jql = f"project={jira_project} AND status='In Progress' AND type=Story"
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for issue in data.get("issues", []):
                    self.report.stories_in_progress.append({
                        "key": issue.get("key", ""),
                        "summary": issue.get("summary", ""),
                        "points": issue.get("story_points", 0),
                        "assignee": issue.get("assignee", ""),
                    })
        except Exception:
            pass

        # Bugs created
        try:
            jql = f"project={jira_project} AND type=Bug AND created>=-{self.sprint_days}d"
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self.report.bugs_created = len(data.get("issues", []))
        except Exception:
            pass

        # Bugs resolved
        try:
            jql = f"project={jira_project} AND type=Bug AND status=Done AND updated>=-{self.sprint_days}d"
            url = f"{self.server_url}/jira/search?jql={jql}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self.report.bugs_resolved = len(data.get("issues", []))
        except Exception:
            pass

    def _collect_git_stats(self):
        """Collect git statistics for the sprint period."""
        r = self.report

        # Commit count
        result = subprocess.run(
            ["git", "log", f"--since={self.since}", "--oneline"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        if result.returncode == 0:
            commits = [l for l in result.stdout.strip().split("\n") if l]
            r.total_commits = len(commits)

        # Commits by author
        result = subprocess.run(
            ["git", "shortlog", "-sn", f"--since={self.since}"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        r.commits_by_author[parts[1]] = int(parts[0])

        # Diff stats via git log --numstat
        result = subprocess.run(
            ["git", "log", f"--since={self.since}", "--pretty=tformat:", "--numstat"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        if result.returncode == 0:
            files = set()
            for line in result.stdout.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) == 3:
                    try:
                        r.lines_added += int(parts[0]) if parts[0] != "-" else 0
                        r.lines_deleted += int(parts[1]) if parts[1] != "-" else 0
                        files.add(parts[2])
                    except ValueError:
                        pass
            r.files_changed = len(files)

        # Merged PRs (merge commits)
        result = subprocess.run(
            ["git", "log", f"--since={self.since}", "--merges", "--oneline"],
            capture_output=True, text=True, timeout=15, cwd=self.cwd,
        )
        if result.returncode == 0:
            merges = [l for l in result.stdout.strip().split("\n") if l]
            r.total_prs_merged = len(merges)

    def _collect_build_data(self):
        """Collect build/deploy data from telemetry."""
        try:
            from code_agents.observability.telemetry import get_summary
            summary = get_summary(days=self.sprint_days)
            self.report.builds_triggered = summary.get("build_count", 0)
        except Exception:
            pass

    def _calculate_velocity(self):
        """Calculate sprint velocity from completed stories."""
        r = self.report
        r.points_completed = sum(s.get("points", 0) for s in r.stories_completed)
        r.points_committed = r.points_completed + sum(s.get("points", 0) for s in r.stories_in_progress)
        r.velocity = r.points_completed  # current sprint velocity


def format_sprint_report(report: SprintReport) -> str:
    """Format for terminal display."""
    lines = []
    lines.append(f"  ╔══ SPRINT REPORT ══╗")
    lines.append(f"  ║ Repo: {report.repo_name}")
    if report.sprint_name:
        lines.append(f"  ║ Sprint: {report.sprint_name}")
    if report.goal:
        lines.append(f"  ║ Goal: {report.goal}")
    lines.append(f"  ╚{'═' * 21}╝")

    # Stories
    lines.append(f"\n  Stories:")
    lines.append(f"    Completed: {len(report.stories_completed)} ({report.points_completed} pts)")
    for s in report.stories_completed[:10]:
        pts = f" [{s.get('points', 0)} pts]" if s.get('points') else ""
        lines.append(f"      - {s.get('key', '')}: {s.get('summary', '')}{pts}")

    if report.stories_in_progress:
        lines.append(f"    In Progress: {len(report.stories_in_progress)}")
        for s in report.stories_in_progress[:5]:
            lines.append(f"      - {s.get('key', '')}: {s.get('summary', '')}")

    if report.stories_carry_over:
        lines.append(f"    Carry-over: {len(report.stories_carry_over)}")
        for s in report.stories_carry_over[:5]:
            lines.append(f"      - {s.get('key', '')}: {s.get('summary', '')}")

    # Bugs
    lines.append(f"\n  Bugs:")
    lines.append(f"    Created: {report.bugs_created} | Resolved: {report.bugs_resolved}")
    net = report.bugs_resolved - report.bugs_created
    trend = "improving" if net > 0 else "worsening" if net < 0 else "stable"
    lines.append(f"    Net: {'+' if net > 0 else ''}{net} ({trend})")

    # Git
    lines.append(f"\n  Git Activity:")
    lines.append(f"    Commits: {report.total_commits} | PRs Merged: {report.total_prs_merged}")
    lines.append(f"    Files changed: {report.files_changed} | +{report.lines_added} -{report.lines_deleted}")
    if report.commits_by_author:
        lines.append(f"    Top contributors:")
        for author, count in sorted(report.commits_by_author.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"      {author}: {count}")

    # Velocity
    lines.append(f"\n  Velocity: {report.points_completed} pts")

    return "\n".join(lines)


def generate_sprint_markdown(report: SprintReport) -> str:
    """Generate markdown for Slack/Confluence."""
    completed_lines = "\n".join(
        f'- **{s.get("key", "")}**: {s.get("summary", "")} ({s.get("points", 0)} pts)'
        for s in report.stories_completed
    ) or "- None"

    md = f"""# Sprint Report — {report.repo_name}
{f'**Sprint:** {report.sprint_name}' if report.sprint_name else ''}
{f'**Goal:** {report.goal}' if report.goal else ''}

## Stories
- **Completed:** {len(report.stories_completed)} ({report.points_completed} story points)
- **In Progress:** {len(report.stories_in_progress)}
- **Carry-over:** {len(report.stories_carry_over)}

### Completed
{completed_lines}

## Bugs
- Created: {report.bugs_created} | Resolved: {report.bugs_resolved} | Net: {report.bugs_resolved - report.bugs_created}

## Git Activity
- {report.total_commits} commits, {report.total_prs_merged} PRs merged
- {report.files_changed} files changed (+{report.lines_added} -{report.lines_deleted})

## Velocity
- **{report.points_completed} story points** completed
"""
    return md
