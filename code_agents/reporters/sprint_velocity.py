"""Sprint Velocity Tracker — track velocity across sprints from Jira."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.reporters.sprint_velocity")


@dataclass
class SprintData:
    """Data for a single sprint."""

    sprint_id: int
    name: str
    start_date: str
    end_date: str
    goal: str = ""
    state: str = "active"  # active, closed, future
    completed_points: int = 0
    committed_points: int = 0
    issues: list[dict] = field(default_factory=list)
    carry_overs: list[dict] = field(default_factory=list)
    bugs_created: int = 0
    bugs_resolved: int = 0


@dataclass
class VelocityReport:
    """Aggregated velocity report across sprints."""

    project_key: str
    repo_name: str
    current_sprint: Optional[SprintData] = None
    sprints: list[SprintData] = field(default_factory=list)
    avg_velocity: float = 0.0
    trend: str = "stable"  # up, down, stable
    total_carry_overs: list[dict] = field(default_factory=list)
    total_bugs_created: int = 0
    total_bugs_resolved: int = 0
    source: str = "jira"  # jira or git


class SprintVelocityTracker:
    """Track sprint velocity from Jira or git fallback."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.repo_name = os.path.basename(cwd)
        self.jira_url = os.getenv("JIRA_URL", "").strip()
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "").strip()
        self._server_url = self._get_server_url()

    def _get_server_url(self) -> str:
        host = os.getenv("HOST", "127.0.0.1")
        port = os.getenv("PORT", "8000")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", f"http://{host}:{port}")

    def _jira_search(self, jql: str, max_results: int = 50) -> list[dict]:
        """Search Jira issues via the code-agents server."""
        import httpx
        try:
            r = httpx.get(
                f"{self._server_url}/jira/search",
                params={"jql": jql, "max_results": max_results},
                timeout=15.0,
            )
            if r.status_code == 200:
                return r.json().get("issues", [])
        except Exception as e:
            logger.debug("Jira search failed: %s", e)
        return []

    def get_current_sprint(self) -> Optional[SprintData]:
        """Get the current active sprint from Jira."""
        if not self.jira_url or not self.project_key:
            return None

        jql = f"project={self.project_key} AND sprint in openSprints()"
        issues = self._jira_search(jql)

        if not issues:
            return None

        # Extract sprint info from the first issue
        sprint_info = self._extract_sprint_info(issues)
        if not sprint_info:
            return None

        sprint = SprintData(
            sprint_id=sprint_info.get("id", 0),
            name=sprint_info.get("name", "Current Sprint"),
            start_date=sprint_info.get("startDate", ""),
            end_date=sprint_info.get("endDate", ""),
            goal=sprint_info.get("goal", ""),
            state="active",
        )

        # Populate issues and points
        for issue in issues:
            fields = issue.get("fields", {})
            story_points = fields.get("story_points") or fields.get("customfield_10028") or 0
            issue_data = {
                "key": issue.get("key", ""),
                "summary": (fields.get("summary") or "")[:60],
                "status": (fields.get("status", {}) or {}).get("name", "Unknown"),
                "type": (fields.get("issuetype", {}) or {}).get("name", "Task"),
                "points": story_points,
            }
            sprint.issues.append(issue_data)
            if issue_data["status"] in ("Done", "Closed", "Resolved"):
                sprint.completed_points += int(story_points)
            sprint.committed_points += int(story_points)

        return sprint

    def get_sprint_issues(self, sprint_id: int) -> list[dict]:
        """Get all issues for a specific sprint."""
        if not self.jira_url or not self.project_key:
            return []

        jql = f"project={self.project_key} AND sprint={sprint_id}"
        issues = self._jira_search(jql, max_results=100)
        result = []
        for issue in issues:
            fields = issue.get("fields", {})
            story_points = fields.get("story_points") or fields.get("customfield_10028") or 0
            result.append({
                "key": issue.get("key", ""),
                "summary": (fields.get("summary") or "")[:60],
                "status": (fields.get("status", {}) or {}).get("name", "Unknown"),
                "type": (fields.get("issuetype", {}) or {}).get("name", "Task"),
                "points": story_points,
            })
        return result

    def calculate_velocity(self, sprints: int = 5) -> VelocityReport:
        """Calculate velocity across the last N sprints."""
        if self.jira_url and self.project_key:
            return self._velocity_from_jira(sprints)
        return self._velocity_from_git(sprints)

    def _velocity_from_jira(self, num_sprints: int) -> VelocityReport:
        """Calculate velocity from Jira sprint data."""
        report = VelocityReport(
            project_key=self.project_key,
            repo_name=self.repo_name,
            source="jira",
        )

        # Get current sprint
        report.current_sprint = self.get_current_sprint()

        # Get recently closed sprints
        jql = (
            f"project={self.project_key} AND sprint in closedSprints() "
            f"ORDER BY created DESC"
        )
        issues = self._jira_search(jql, max_results=200)

        # Group issues by sprint
        sprint_map: dict[str, SprintData] = {}
        for issue in issues:
            fields = issue.get("fields", {})
            sprint_info = self._extract_sprint_info([issue])
            if not sprint_info:
                continue

            s_name = sprint_info.get("name", "Unknown")
            if s_name not in sprint_map:
                sprint_map[s_name] = SprintData(
                    sprint_id=sprint_info.get("id", 0),
                    name=s_name,
                    start_date=sprint_info.get("startDate", ""),
                    end_date=sprint_info.get("endDate", ""),
                    goal=sprint_info.get("goal", ""),
                    state="closed",
                )

            sd = sprint_map[s_name]
            story_points = fields.get("story_points") or fields.get("customfield_10028") or 0
            status = (fields.get("status", {}) or {}).get("name", "Unknown")
            issue_type = (fields.get("issuetype", {}) or {}).get("name", "Task")

            issue_data = {
                "key": issue.get("key", ""),
                "summary": (fields.get("summary") or "")[:60],
                "status": status,
                "type": issue_type,
                "points": story_points,
            }
            sd.issues.append(issue_data)

            if status in ("Done", "Closed", "Resolved"):
                sd.completed_points += int(story_points)
            else:
                sd.carry_overs.append(issue_data)

            sd.committed_points += int(story_points)

            if issue_type == "Bug":
                sd.bugs_created += 1
                if status in ("Done", "Closed", "Resolved"):
                    sd.bugs_resolved += 1

        # Sort sprints by start date and take last N
        sorted_sprints = sorted(
            sprint_map.values(),
            key=lambda s: s.start_date or "",
        )
        report.sprints = sorted_sprints[-num_sprints:]

        # Add current sprint at the end if it exists
        if report.current_sprint:
            report.sprints.append(report.current_sprint)

        # Calculate averages and trend
        self._compute_stats(report)

        return report

    def _velocity_from_git(self, num_sprints: int) -> VelocityReport:
        """Fallback: estimate velocity from git activity (PRs merged per week)."""
        report = VelocityReport(
            project_key=self.project_key or "N/A",
            repo_name=self.repo_name,
            source="git",
        )

        weeks = num_sprints * 2  # assume 2-week sprints
        try:
            result = subprocess.run(
                [
                    "git", "log", "--oneline", "--merges",
                    f"--since={weeks} weeks ago",
                    "--format=%H|%ai|%s",
                ],
                cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            logger.debug("Git log failed: %s", e)
            return report

        if not result.stdout.strip():
            return report

        # Group merges by 2-week windows
        lines = result.stdout.strip().splitlines()
        now = datetime.now()
        for i in range(num_sprints):
            end = now - timedelta(weeks=i * 2)
            start = end - timedelta(weeks=2)
            sprint_name = f"Week {start.strftime('%b %d')} - {end.strftime('%b %d')}"

            count = 0
            for line in lines:
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    try:
                        date_str = parts[1].strip()[:10]
                        commit_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if start.date() <= commit_date.date() <= end.date():
                            count += 1
                    except (ValueError, IndexError):
                        continue

            sprint = SprintData(
                sprint_id=i,
                name=sprint_name,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                completed_points=count,
                committed_points=count,
                state="closed" if i > 0 else "active",
            )
            report.sprints.append(sprint)

        report.sprints.reverse()

        # Add current as the last sprint
        if report.sprints:
            report.current_sprint = report.sprints[-1]

        self._compute_stats(report)
        return report

    def get_carry_overs(self) -> list[dict]:
        """Get issues not completed that rolled to the next sprint."""
        if not self.jira_url or not self.project_key:
            return []

        jql = (
            f"project={self.project_key} AND sprint in openSprints() "
            f"AND sprint in closedSprints()"
        )
        issues = self._jira_search(jql, max_results=50)
        carry_overs = []
        for issue in issues:
            fields = issue.get("fields", {})
            status = (fields.get("status", {}) or {}).get("name", "Unknown")
            if status not in ("Done", "Closed", "Resolved"):
                story_points = fields.get("story_points") or fields.get("customfield_10028") or 0
                carry_overs.append({
                    "key": issue.get("key", ""),
                    "summary": (fields.get("summary") or "")[:60],
                    "points": int(story_points),
                })
        return carry_overs

    def get_bug_rate(self) -> dict:
        """Get bugs created vs resolved in the current sprint."""
        if not self.jira_url or not self.project_key:
            return {"created": 0, "resolved": 0, "net": 0}

        # Bugs created in current sprint
        jql_created = (
            f"project={self.project_key} AND issuetype=Bug "
            f"AND sprint in openSprints()"
        )
        created = self._jira_search(jql_created)

        resolved = [
            i for i in created
            if (i.get("fields", {}).get("status", {}) or {}).get("name", "")
            in ("Done", "Closed", "Resolved")
        ]

        return {
            "created": len(created),
            "resolved": len(resolved),
            "net": len(created) - len(resolved),
        }

    def format_velocity_report(self) -> str:
        """Generate the full terminal display report."""
        report = self.calculate_velocity()
        return format_report(report)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_sprint_info(issues: list[dict]) -> Optional[dict]:
        """Extract sprint metadata from Jira issue fields."""
        for issue in issues:
            fields = issue.get("fields", {})
            # Sprint field is typically customfield_10020 or similar
            sprint_field = (
                fields.get("sprint")
                or fields.get("customfield_10020")
            )
            if isinstance(sprint_field, dict):
                return sprint_field
            if isinstance(sprint_field, list) and sprint_field:
                # Return the last (most recent) sprint
                return sprint_field[-1] if isinstance(sprint_field[-1], dict) else {}
        return None

    @staticmethod
    def predict_velocity(sprints: list[SprintData], num_future: int = 3) -> list[float]:
        """Predict future sprint velocity using simple linear regression.

        Uses completed_points from closed sprints. Returns predicted velocity
        for the next *num_future* sprints. No numpy required.
        """
        closed = [s for s in sprints if s.state == "closed"]
        if len(closed) < 2:
            # Not enough data — return average repeated
            avg = sum(s.completed_points for s in closed) / max(len(closed), 1)
            return [round(avg, 1)] * num_future

        n = len(closed)
        xs = list(range(n))
        ys = [s.completed_points for s in closed]

        x_mean = sum(xs) / n
        y_mean = sum(ys) / n

        numerator = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return [round(y_mean, 1)] * num_future

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        predictions = []
        for j in range(num_future):
            pred = slope * (n + j) + intercept
            predictions.append(round(max(pred, 0), 1))  # velocity can't be negative
        return predictions

    @staticmethod
    def estimate_completion(backlog_points: int, avg_velocity: float, sprints: list[SprintData] | None = None) -> dict:
        """Estimate how many sprints to complete the backlog.

        Returns {"estimated_sprints": int, "confidence": "low"|"medium"|"high"}.
        Confidence is based on velocity variance across closed sprints.
        """
        if avg_velocity <= 0:
            return {"estimated_sprints": -1, "confidence": "low"}

        import math
        estimated = math.ceil(backlog_points / avg_velocity)

        # Determine confidence from variance
        confidence = "medium"
        if sprints:
            closed = [s.completed_points for s in sprints if s.state == "closed"]
            if len(closed) >= 3:
                mean = sum(closed) / len(closed)
                variance = sum((v - mean) ** 2 for v in closed) / len(closed)
                std_dev = variance ** 0.5
                cv = std_dev / mean if mean > 0 else 999
                if cv < 0.2:
                    confidence = "high"
                elif cv > 0.5:
                    confidence = "low"
                else:
                    confidence = "medium"
            elif len(closed) < 2:
                confidence = "low"

        return {"estimated_sprints": estimated, "confidence": confidence}

    @staticmethod
    def _compute_stats(report: VelocityReport):
        """Compute averages and trend from sprint data."""
        # Factor carry-overs into effective velocity
        completed = [
            s.completed_points - len(s.carry_overs)
            for s in report.sprints if s.state == "closed"
        ]
        if completed:
            report.avg_velocity = sum(completed) / len(completed)
        else:
            report.avg_velocity = 0.0

        # Trend: compare last 2 vs first 2
        if len(completed) >= 4:
            first_half = sum(completed[: len(completed) // 2]) / (len(completed) // 2)
            second_half = sum(completed[len(completed) // 2:]) / (len(completed) - len(completed) // 2)
            diff = second_half - first_half
            if diff > 2:
                report.trend = "up"
            elif diff < -2:
                report.trend = "down"
            else:
                report.trend = "stable"
        elif len(completed) >= 2:
            if completed[-1] > completed[0] + 2:
                report.trend = "up"
            elif completed[-1] < completed[0] - 2:
                report.trend = "down"
            else:
                report.trend = "stable"

        # Aggregate carry-overs and bug counts
        for s in report.sprints:
            report.total_carry_overs.extend(s.carry_overs)
            report.total_bugs_created += s.bugs_created
            report.total_bugs_resolved += s.bugs_resolved


def format_report(report: VelocityReport) -> str:
    """Format a VelocityReport as a terminal-friendly string."""
    lines: list[str] = []
    unit = "pts" if report.source == "jira" else "PRs"

    # Header
    lines.append(f"  Sprint Velocity — {report.repo_name}")
    lines.append("  " + "=" * 40)
    lines.append("")

    # Current sprint
    if report.current_sprint:
        cs = report.current_sprint
        state_label = "(in progress)" if cs.state == "active" else ""
        lines.append(f"  Current Sprint: {cs.name} ({cs.start_date} - {cs.end_date})")
        if cs.goal:
            lines.append(f"  Goal: {cs.goal}")
        lines.append("")

    # Velocity bar chart
    max_pts = max((s.completed_points for s in report.sprints), default=1) or 1
    bar_width = 16

    if report.source == "git":
        lines.append(f"  Velocity (last {len(report.sprints)} periods, estimated from git merges):")
    else:
        lines.append(f"  Velocity (last {len(report.sprints)} sprints):")

    for sprint in report.sprints:
        pts = sprint.completed_points
        filled = int((pts / max_pts) * bar_width)
        empty = bar_width - filled
        bar = "\u2588" * filled + "\u2591" * empty

        label = f"{pts:>3} {unit}"
        extra = ""
        if sprint.state == "active":
            extra = " (in progress)"
        elif sprint.carry_overs:
            extra = f" <- carry-over: {len(sprint.carry_overs)} stories"

        lines.append(f"    {sprint.name:<20} {bar} {label}{extra}")

    lines.append("")
    trend_symbol = {"up": "^ improving", "down": "v declining", "stable": "~ stable"}
    lines.append(
        f"  Average: {report.avg_velocity:.0f} {unit}/sprint | "
        f"Trend: {trend_symbol.get(report.trend, '~ stable')}"
    )
    lines.append("")

    # Bug rate (jira only)
    if report.source == "jira":
        net = report.total_bugs_created - report.total_bugs_resolved
        net_label = "improving" if net < 0 else ("increasing" if net > 0 else "stable")
        lines.append("  Bug Rate:")
        lines.append(
            f"    Created: {report.total_bugs_created} | "
            f"Resolved: {report.total_bugs_resolved} | "
            f"Net: {net:+d} ({net_label})"
        )
        lines.append("")

    # Carry-overs
    if report.total_carry_overs:
        total_co_pts = sum(c.get("points", 0) for c in report.total_carry_overs)
        lines.append(f"  Carry-Overs: {len(report.total_carry_overs)} stories ({total_co_pts} {unit})")
        for co in report.total_carry_overs[:5]:
            pts_str = f" ({co['points']} {unit})" if co.get("points") else ""
            lines.append(f"    * {co['key']}: {co['summary']}{pts_str}")
        if len(report.total_carry_overs) > 5:
            lines.append(f"    ... and {len(report.total_carry_overs) - 5} more")
        lines.append("")

    # Predictions section
    closed_sprints = [s for s in report.sprints if s.state == "closed"]
    if len(closed_sprints) >= 2:
        predictions = SprintVelocityTracker.predict_velocity(report.sprints, num_future=3)
        lines.append("  Predictions (next 3 sprints):")
        for i, pred in enumerate(predictions, 1):
            lines.append(f"    Sprint +{i}: ~{pred:.0f} {unit}")
        lines.append("")

    if report.source == "git":
        lines.append("  (Jira not configured — using git merge count as proxy)")
        lines.append("  Tip: code-agents init --jira")
        lines.append("")

    return "\n".join(lines)
