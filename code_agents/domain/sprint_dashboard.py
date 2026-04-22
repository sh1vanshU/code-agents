"""Sprint Velocity Dashboard — velocity + cycle time + blockers report."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.sprint_dashboard")


@dataclass
class CycleTimeMetrics:
    avg_days: float = 0.0
    p50_days: float = 0.0
    p90_days: float = 0.0
    min_days: float = 0.0
    max_days: float = 0.0
    sample_size: int = 0


@dataclass
class ThroughputMetrics:
    commits: int = 0
    prs_merged: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    authors: int = 0


@dataclass
class ContributorStats:
    name: str
    commits: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class BlockerInfo:
    description: str
    source: str = ""  # "stale_pr", "failing_test", "dependency"
    severity: str = "medium"  # high, medium, low
    days_blocked: int = 0


@dataclass
class SprintDashboardReport:
    sprint_name: str = ""
    period_days: int = 14
    start_date: str = ""
    end_date: str = ""
    throughput: ThroughputMetrics = field(default_factory=ThroughputMetrics)
    cycle_time: CycleTimeMetrics = field(default_factory=CycleTimeMetrics)
    contributors: list[ContributorStats] = field(default_factory=list)
    blockers: list[BlockerInfo] = field(default_factory=list)
    weekly_summary: str = ""
    top_files: list[dict] = field(default_factory=list)
    commit_activity: dict = field(default_factory=dict)  # day -> count


class SprintDashboard:
    """Generates sprint velocity dashboards from git data."""

    def __init__(self, cwd: str = ".", period_days: int = 14, sprint: str = "current"):
        self.cwd = os.path.abspath(cwd)
        self.period_days = period_days
        self.sprint = sprint

    def generate(self) -> SprintDashboardReport:
        """Generate a complete sprint dashboard."""
        end = datetime.now()
        start = end - timedelta(days=self.period_days)

        throughput = self._calculate_throughput(start, end)
        cycle_time = self._calculate_cycle_time(start, end)
        contributors = self._get_contributors(start, end)
        blockers = self._find_blockers()
        top_files = self._get_top_files(start, end)
        activity = self._get_daily_activity(start, end)
        summary = self._generate_summary(throughput, cycle_time, contributors, blockers)

        return SprintDashboardReport(
            sprint_name=self.sprint,
            period_days=self.period_days,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            throughput=throughput,
            cycle_time=cycle_time,
            contributors=contributors,
            blockers=blockers,
            weekly_summary=summary,
            top_files=top_files,
            commit_activity=activity,
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

    def _calculate_throughput(self, start: datetime, end: datetime) -> ThroughputMetrics:
        """Calculate throughput metrics from git."""
        since = start.strftime("%Y-%m-%d")
        until = end.strftime("%Y-%m-%d")

        # Count commits
        log = self._run_git("log", f"--since={since}", f"--until={until}",
                            "--oneline", "--no-merges")
        commits = len(log.strip().split("\n")) if log.strip() else 0

        # Count merge commits (proxy for PRs merged)
        merges = self._run_git("log", f"--since={since}", f"--until={until}",
                               "--oneline", "--merges")
        prs = len(merges.strip().split("\n")) if merges.strip() else 0

        # File stats
        stat = self._run_git("log", f"--since={since}", f"--until={until}",
                             "--stat", "--no-merges", "--format=")
        lines_added = lines_removed = files_changed = 0
        file_set = set()
        for line in stat.split("\n"):
            m = re.search(r"(\d+) files? changed", line)
            if m:
                files_changed += int(m.group(1))
            m = re.search(r"(\d+) insertions?", line)
            if m:
                lines_added += int(m.group(1))
            m = re.search(r"(\d+) deletions?", line)
            if m:
                lines_removed += int(m.group(1))

        # Count unique authors
        authors_out = self._run_git("log", f"--since={since}", f"--until={until}",
                                    "--format=%aN", "--no-merges")
        authors = len(set(authors_out.strip().split("\n"))) if authors_out.strip() else 0

        return ThroughputMetrics(
            commits=commits,
            prs_merged=prs,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            authors=authors,
        )

    def _calculate_cycle_time(self, start: datetime, end: datetime) -> CycleTimeMetrics:
        """Calculate cycle time from merge commits."""
        since = start.strftime("%Y-%m-%d")
        until = end.strftime("%Y-%m-%d")

        # Get merge commit timestamps and their first parent (branch point)
        merges = self._run_git("log", f"--since={since}", f"--until={until}",
                               "--merges", "--format=%H|%aI")
        if not merges.strip():
            return CycleTimeMetrics()

        cycle_times = []
        for line in merges.strip().split("\n"):
            parts = line.split("|")
            if len(parts) < 2:
                continue
            merge_hash, merge_time = parts[0], parts[1]
            try:
                merge_dt = datetime.fromisoformat(merge_time.replace("Z", "+00:00"))
            except ValueError:
                continue

            # Find the branch point (first commit in the branch)
            first_commit = self._run_git("log", f"{merge_hash}^..{merge_hash}",
                                          "--format=%aI", "--reverse")
            if first_commit:
                first_line = first_commit.strip().split("\n")[0]
                try:
                    first_dt = datetime.fromisoformat(first_line.replace("Z", "+00:00"))
                    days = max((merge_dt - first_dt).total_seconds() / 86400, 0)
                    cycle_times.append(days)
                except ValueError:
                    continue

        if not cycle_times:
            return CycleTimeMetrics()

        cycle_times.sort()
        n = len(cycle_times)

        return CycleTimeMetrics(
            avg_days=round(sum(cycle_times) / n, 1),
            p50_days=round(cycle_times[n // 2], 1),
            p90_days=round(cycle_times[int(n * 0.9)], 1) if n > 1 else round(cycle_times[0], 1),
            min_days=round(cycle_times[0], 1),
            max_days=round(cycle_times[-1], 1),
            sample_size=n,
        )

    def _get_contributors(self, start: datetime, end: datetime) -> list[ContributorStats]:
        """Get contributor statistics."""
        since = start.strftime("%Y-%m-%d")
        until = end.strftime("%Y-%m-%d")

        shortlog = self._run_git("shortlog", "-sne", f"--since={since}",
                                  f"--until={until}", "--no-merges", "HEAD")
        if not shortlog.strip():
            return []

        contributors = []
        for line in shortlog.strip().split("\n"):
            m = re.match(r"\s*(\d+)\s+(.+?)\s*<", line)
            if m:
                count = int(m.group(1))
                name = m.group(2).strip()
                contributors.append(ContributorStats(name=name, commits=count))

        # Get per-author stats
        for contrib in contributors:
            stat = self._run_git("log", f"--since={since}", f"--until={until}",
                                 f"--author={contrib.name}", "--stat", "--no-merges", "--format=")
            for line in stat.split("\n"):
                m = re.search(r"(\d+) insertions?", line)
                if m:
                    contrib.lines_added += int(m.group(1))
                m = re.search(r"(\d+) deletions?", line)
                if m:
                    contrib.lines_removed += int(m.group(1))

        return sorted(contributors, key=lambda c: c.commits, reverse=True)

    def _find_blockers(self) -> list[BlockerInfo]:
        """Find potential blockers from git state."""
        blockers = []

        # Check for stale branches (no commits in 7+ days)
        branches = self._run_git("branch", "--sort=-committerdate",
                                  "--format=%(refname:short)|%(committerdate:relative)")
        if branches:
            for line in branches.strip().split("\n")[:20]:
                parts = line.split("|")
                if len(parts) == 2:
                    branch, age = parts
                    if any(w in age for w in ("week", "month", "year")):
                        if branch not in ("main", "master", "develop"):
                            blockers.append(BlockerInfo(
                                description=f"Stale branch: {branch} (last activity: {age})",
                                source="stale_pr",
                                severity="low",
                            ))

        # Check for unresolved merge conflicts
        status = self._run_git("status", "--porcelain")
        if status:
            conflict_files = [l[3:] for l in status.split("\n")
                              if l.startswith("UU") or l.startswith("AA")]
            if conflict_files:
                blockers.append(BlockerInfo(
                    description=f"Unresolved merge conflicts in {len(conflict_files)} file(s)",
                    source="merge_conflict",
                    severity="high",
                ))

        return blockers

    def _get_top_files(self, start: datetime, end: datetime) -> list[dict]:
        """Get most frequently changed files."""
        since = start.strftime("%Y-%m-%d")
        until = end.strftime("%Y-%m-%d")

        log = self._run_git("log", f"--since={since}", f"--until={until}",
                            "--name-only", "--no-merges", "--format=")
        if not log.strip():
            return []

        counts = Counter(f for f in log.strip().split("\n") if f.strip())
        return [{"file": f, "changes": c} for f, c in counts.most_common(10)]

    def _get_daily_activity(self, start: datetime, end: datetime) -> dict[str, int]:
        """Get commit count per day."""
        since = start.strftime("%Y-%m-%d")
        until = end.strftime("%Y-%m-%d")

        log = self._run_git("log", f"--since={since}", f"--until={until}",
                            "--format=%ad", "--date=short", "--no-merges")
        if not log.strip():
            return {}

        return dict(Counter(log.strip().split("\n")))

    def _generate_summary(self, throughput: ThroughputMetrics,
                          cycle_time: CycleTimeMetrics,
                          contributors: list[ContributorStats],
                          blockers: list[BlockerInfo]) -> str:
        """Generate a weekly summary text."""
        lines = [f"Sprint summary ({self.period_days} days):"]
        lines.append(f"- {throughput.commits} commits by {throughput.authors} contributor(s)")
        lines.append(f"- {throughput.prs_merged} PRs merged")
        lines.append(f"- +{throughput.lines_added}/-{throughput.lines_removed} lines")

        if cycle_time.sample_size > 0:
            lines.append(f"- Avg cycle time: {cycle_time.avg_days}d (p50: {cycle_time.p50_days}d)")

        if blockers:
            high = [b for b in blockers if b.severity == "high"]
            if high:
                lines.append(f"- Blockers: {len(high)} high-severity issue(s)")

        if contributors:
            top = contributors[0]
            lines.append(f"- Top contributor: {top.name} ({top.commits} commits)")

        return "\n".join(lines)


def format_sprint_dashboard(report: SprintDashboardReport) -> str:
    """Format sprint dashboard for display."""
    t = report.throughput
    c = report.cycle_time

    lines = [
        "## Sprint Dashboard",
        "",
        f"**Sprint:** {report.sprint_name}",
        f"**Period:** {report.start_date} → {report.end_date} ({report.period_days} days)",
        "",
        "### Throughput",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Commits | {t.commits} |",
        f"| PRs Merged | {t.prs_merged} |",
        f"| Files Changed | {t.files_changed} |",
        f"| Lines Added | +{t.lines_added} |",
        f"| Lines Removed | -{t.lines_removed} |",
        f"| Contributors | {t.authors} |",
        "",
    ]

    if c.sample_size > 0:
        lines.extend([
            "### Cycle Time",
            "",
            f"| Metric | Days |",
            f"|--------|------|",
            f"| Average | {c.avg_days} |",
            f"| P50 | {c.p50_days} |",
            f"| P90 | {c.p90_days} |",
            f"| Min | {c.min_days} |",
            f"| Max | {c.max_days} |",
            f"| Sample Size | {c.sample_size} |",
            "",
        ])

    if report.contributors:
        lines.extend(["### Contributors", ""])
        lines.append("| Name | Commits | +Lines | -Lines |")
        lines.append("|------|---------|--------|--------|")
        for c in report.contributors[:10]:
            lines.append(f"| {c.name} | {c.commits} | +{c.lines_added} | -{c.lines_removed} |")
        lines.append("")

    if report.top_files:
        lines.extend(["### Hotspot Files", ""])
        for f in report.top_files[:10]:
            lines.append(f"- `{f['file']}` ({f['changes']} changes)")
        lines.append("")

    if report.blockers:
        lines.extend(["### Blockers", ""])
        for b in report.blockers:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(b.severity, "⚪")
            lines.append(f"- {icon} {b.description}")
        lines.append("")

    if report.commit_activity:
        lines.extend(["### Daily Activity", ""])
        for day, count in sorted(report.commit_activity.items()):
            bar = "█" * min(count, 30)
            lines.append(f"  {day}: {bar} ({count})")
        lines.append("")

    if report.weekly_summary:
        lines.extend(["### Summary", "", "```", report.weekly_summary, "```", ""])

    return "\n".join(lines)
