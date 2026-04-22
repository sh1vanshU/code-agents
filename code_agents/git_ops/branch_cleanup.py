"""Branch Cleanup — find stale/merged branches with safety checks.

Identifies branches that are merged, stale, or orphaned and suggests
cleanup actions with safety validation.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.branch_cleanup")

# ---------------------------------------------------------------------------
# Protected branch patterns
# ---------------------------------------------------------------------------
_PROTECTED_PATTERNS = re.compile(
    r"^(main|master|develop|release/.+|hotfix/.+|production|staging)$"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BranchInfo:
    """Information about a git branch."""

    name: str
    last_commit_date: Optional[datetime] = None
    last_commit_sha: str = ""
    last_commit_message: str = ""
    author: str = ""
    is_merged: bool = False
    is_remote: bool = False
    days_inactive: int = 0
    status: str = "active"  # "active" | "stale" | "merged" | "orphaned"
    is_protected: bool = False


@dataclass
class CleanupAction:
    """A suggested cleanup action."""

    branch: BranchInfo
    action: str  # "delete_local" | "delete_remote" | "archive" | "skip"
    reason: str
    safe: bool = True
    command: str = ""


@dataclass
class CleanupReport:
    """Report of branch cleanup analysis."""

    branches: list[BranchInfo] = field(default_factory=list)
    actions: list[CleanupAction] = field(default_factory=list)
    protected_count: int = 0
    stale_count: int = 0
    merged_count: int = 0

    @property
    def summary(self) -> str:
        return (
            f"{len(self.branches)} branches analyzed: "
            f"{self.merged_count} merged, {self.stale_count} stale, "
            f"{self.protected_count} protected, {len(self.actions)} actions suggested"
        )


# ---------------------------------------------------------------------------
# Cleanup analyzer
# ---------------------------------------------------------------------------


class BranchCleanup:
    """Analyze branches and suggest safe cleanup actions."""

    def __init__(self, cwd: Optional[str] = None, stale_days: int = 90):
        self.cwd = cwd or os.getcwd()
        self.stale_days = stale_days

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self, include_remote: bool = False) -> CleanupReport:
        """Analyze all branches and generate cleanup report."""
        report = CleanupReport()

        # Get local branches
        branches = self._get_local_branches()
        if include_remote:
            branches.extend(self._get_remote_branches())

        merged_branches = self._get_merged_branches()
        current = self._get_current_branch()

        for branch in branches:
            branch.is_merged = branch.name in merged_branches
            branch.is_protected = self._is_protected(branch.name)

            if branch.is_protected:
                report.protected_count += 1
                branch.status = "active"
            elif branch.is_merged:
                report.merged_count += 1
                branch.status = "merged"
            elif branch.days_inactive > self.stale_days:
                report.stale_count += 1
                branch.status = "stale"

            report.branches.append(branch)

            # Generate cleanup action
            if branch.name == current:
                continue  # Skip current branch
            action = self._suggest_action(branch)
            if action:
                report.actions.append(action)

        report.actions.sort(key=lambda a: (a.safe, a.action))
        logger.info("Branch cleanup: %s", report.summary)
        return report

    def execute_actions(self, actions: list[CleanupAction], dry_run: bool = True) -> list[str]:
        """Execute cleanup actions. Returns list of executed commands."""
        executed = []
        for action in actions:
            if not action.safe:
                logger.warning("Skipping unsafe action: %s", action.command)
                continue
            if dry_run:
                executed.append(f"[DRY RUN] {action.command}")
            else:
                result = self._git_raw(action.command)
                executed.append(f"{action.command} -> {result}")
        return executed

    def generate_script(self, report: CleanupReport) -> str:
        """Generate a cleanup shell script from the report."""
        lines = [
            "#!/bin/bash",
            "# Branch cleanup script — review before running!",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"# {report.summary}",
            "",
            "set -e",
            "",
        ]
        for action in report.actions:
            if not action.safe:
                lines.append(f"# SKIPPED (unsafe): {action.command}  # {action.reason}")
            else:
                lines.append(f"{action.command}  # {action.reason}")
        return "\n".join(lines)

    # ── Git helpers ───────────────────────────────────────────────────────

    def _git(self, *args: str) -> str:
        """Run git command and return stdout."""
        try:
            proc = subprocess.run(
                ["git", *args], capture_output=True, text=True,
                cwd=self.cwd, timeout=15,
            )
            return proc.stdout.strip() if proc.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _git_raw(self, command: str) -> str:
        """Run a raw git command string."""
        try:
            proc = subprocess.run(
                command.split(), capture_output=True, text=True,
                cwd=self.cwd, timeout=15,
            )
            return proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "error: command failed"

    def _get_current_branch(self) -> str:
        """Get the current branch name."""
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def _get_local_branches(self) -> list[BranchInfo]:
        """Get all local branches with their info."""
        output = self._git(
            "for-each-ref", "--sort=-committerdate",
            "--format=%(refname:short)\t%(committerdate:iso)\t%(objectname:short)\t%(subject)\t%(authorname)",
            "refs/heads/",
        )
        branches = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 5:
                name, date_str, sha, msg, author = parts[0], parts[1], parts[2], parts[3], parts[4]
                try:
                    commit_date = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                    days = (datetime.now() - commit_date).days
                except ValueError:
                    commit_date = None
                    days = 0
                branches.append(BranchInfo(
                    name=name, last_commit_date=commit_date,
                    last_commit_sha=sha, last_commit_message=msg,
                    author=author, days_inactive=days, is_remote=False,
                ))
            elif len(parts) >= 1 and parts[0].strip():
                branches.append(BranchInfo(name=parts[0].strip()))
        return branches

    def _get_remote_branches(self) -> list[BranchInfo]:
        """Get remote branches."""
        output = self._git(
            "for-each-ref", "--sort=-committerdate",
            "--format=%(refname:short)\t%(committerdate:iso)\t%(objectname:short)\t%(subject)\t%(authorname)",
            "refs/remotes/origin/",
        )
        branches = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 5:
                name = parts[0].replace("origin/", "", 1)
                if name == "HEAD":
                    continue
                date_str, sha, msg, author = parts[1], parts[2], parts[3], parts[4]
                try:
                    commit_date = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                    days = (datetime.now() - commit_date).days
                except ValueError:
                    commit_date = None
                    days = 0
                branches.append(BranchInfo(
                    name=name, last_commit_date=commit_date,
                    last_commit_sha=sha, last_commit_message=msg,
                    author=author, days_inactive=days, is_remote=True,
                ))
        return branches

    def _get_merged_branches(self) -> set[str]:
        """Get set of branch names that are merged into current branch."""
        output = self._git("branch", "--merged")
        merged = set()
        for line in output.splitlines():
            name = line.strip().lstrip("* ")
            if name:
                merged.add(name)
        return merged

    # ── Classification ────────────────────────────────────────────────────

    def _is_protected(self, name: str) -> bool:
        """Check if a branch is protected."""
        return bool(_PROTECTED_PATTERNS.match(name))

    def _suggest_action(self, branch: BranchInfo) -> Optional[CleanupAction]:
        """Suggest a cleanup action for a branch."""
        if branch.is_protected:
            return None

        if branch.is_merged:
            cmd = f"git branch -d {branch.name}" if not branch.is_remote else f"git push origin --delete {branch.name}"
            return CleanupAction(
                branch=branch,
                action="delete_local" if not branch.is_remote else "delete_remote",
                reason=f"Already merged (last activity: {branch.days_inactive}d ago)",
                safe=True,
                command=cmd,
            )

        if branch.days_inactive > self.stale_days:
            return CleanupAction(
                branch=branch,
                action="archive",
                reason=f"Stale: {branch.days_inactive} days since last commit",
                safe=False,  # Stale but unmerged = potentially has work
                command=f"git branch -D {branch.name}",
            )

        return None
