"""Cherry-Pick Advisor — find commits, check deps, suggest clean cherry-picks.

Searches for commits across branches, analyzes dependencies between commits,
and provides guidance for clean cherry-pick operations.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.cherry_pick_advisor")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommitInfo:
    """Information about a git commit."""

    sha: str
    short_sha: str = ""
    message: str = ""
    author: str = ""
    date: str = ""
    files: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


@dataclass
class Dependency:
    """A dependency between two commits."""

    commit_sha: str
    depends_on_sha: str
    reason: str  # "same_file" | "same_function" | "sequential_change"
    files: list[str] = field(default_factory=list)


@dataclass
class CherryPickPlan:
    """A plan for cherry-picking a commit."""

    target_commit: CommitInfo
    target_branch: str
    dependencies: list[Dependency] = field(default_factory=list)
    prerequisite_commits: list[CommitInfo] = field(default_factory=list)
    conflicts_likely: bool = False
    conflict_files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe: bool = True

    @property
    def summary(self) -> str:
        deps = len(self.dependencies)
        prereqs = len(self.prerequisite_commits)
        safe_str = "safe" if self.safe else "RISKY"
        return f"Cherry-pick {self.target_commit.short_sha} -> {self.target_branch}: {deps} deps, {prereqs} prereqs ({safe_str})"


@dataclass
class SearchResult:
    """Result of searching for commits."""

    commits: list[CommitInfo] = field(default_factory=list)
    query: str = ""

    @property
    def summary(self) -> str:
        return f"Found {len(self.commits)} commits matching '{self.query}'"


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------


class CherryPickAdvisor:
    """Analyze and advise on cherry-pick operations."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def search_commits(self, query: str, branches: Optional[list[str]] = None,
                       max_results: int = 20) -> SearchResult:
        """Search for commits matching a query across branches."""
        result = SearchResult(query=query)

        if branches:
            for branch in branches:
                commits = self._search_in_branch(query, branch, max_results)
                result.commits.extend(commits)
        else:
            result.commits = self._search_all(query, max_results)

        # Deduplicate by SHA
        seen = set()
        unique = []
        for c in result.commits:
            if c.sha not in seen:
                seen.add(c.sha)
                unique.append(c)
        result.commits = unique[:max_results]

        # Find which branches contain each commit
        for commit in result.commits:
            commit.branches = self._find_branches_containing(commit.sha)

        logger.info("Search: %s", result.summary)
        return result

    def plan_cherry_pick(self, commit_sha: str, target_branch: str) -> CherryPickPlan:
        """Create a cherry-pick plan for a specific commit."""
        commit = self._get_commit_info(commit_sha)
        plan = CherryPickPlan(target_commit=commit, target_branch=target_branch)

        # Check if already on target branch
        target_commits = self._get_branch_commits(target_branch, limit=500)
        if commit.sha in {c.sha for c in target_commits}:
            plan.warnings.append(f"Commit {commit.short_sha} is already on {target_branch}")
            plan.safe = False
            return plan

        # Find dependencies
        plan.dependencies = self._find_dependencies(commit)

        # Check which deps are missing from target
        target_shas = {c.sha for c in target_commits}
        for dep in plan.dependencies:
            if dep.depends_on_sha not in target_shas:
                prereq = self._get_commit_info(dep.depends_on_sha)
                plan.prerequisite_commits.append(prereq)

        # Check for likely conflicts
        plan.conflict_files = self._check_conflicts(commit, target_branch)
        plan.conflicts_likely = len(plan.conflict_files) > 0

        # Generate commands
        plan.commands = self._generate_commands(plan)

        # Safety assessment
        if plan.prerequisite_commits:
            plan.warnings.append(
                f"{len(plan.prerequisite_commits)} prerequisite commit(s) not on {target_branch}"
            )
        if plan.conflicts_likely:
            plan.warnings.append(
                f"Conflicts likely in: {', '.join(plan.conflict_files[:5])}"
            )
            plan.safe = len(plan.prerequisite_commits) == 0

        logger.info("Plan: %s", plan.summary)
        return plan

    def find_commit_on_branches(self, commit_sha: str) -> list[str]:
        """Find all branches containing a specific commit."""
        return self._find_branches_containing(commit_sha)

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

    def _get_commit_info(self, sha: str) -> CommitInfo:
        """Get detailed info about a commit."""
        fmt = "%H\t%h\t%s\t%an\t%ci"
        output = self._git("log", "-1", f"--pretty=format:{fmt}", sha)
        if not output:
            return CommitInfo(sha=sha, short_sha=sha[:8])

        parts = output.split("\t")
        commit = CommitInfo(
            sha=parts[0] if len(parts) > 0 else sha,
            short_sha=parts[1] if len(parts) > 1 else sha[:8],
            message=parts[2] if len(parts) > 2 else "",
            author=parts[3] if len(parts) > 3 else "",
            date=parts[4] if len(parts) > 4 else "",
        )

        # Get files
        numstat = self._git("diff-tree", "--no-commit-id", "--numstat", "-r", sha)
        for line in numstat.splitlines():
            stat_parts = line.split("\t")
            if len(stat_parts) >= 3:
                commit.files.append(stat_parts[2])
                adds = int(stat_parts[0]) if stat_parts[0] != "-" else 0
                dels = int(stat_parts[1]) if stat_parts[1] != "-" else 0
                commit.additions += adds
                commit.deletions += dels
        return commit

    def _search_in_branch(self, query: str, branch: str, limit: int) -> list[CommitInfo]:
        """Search for commits in a specific branch."""
        output = self._git(
            "log", branch, f"--grep={query}", "-i",
            f"-{limit}", "--pretty=format:%H\t%h\t%s\t%an\t%ci",
        )
        return self._parse_log_output(output)

    def _search_all(self, query: str, limit: int) -> list[CommitInfo]:
        """Search for commits across all branches."""
        output = self._git(
            "log", "--all", f"--grep={query}", "-i",
            f"-{limit}", "--pretty=format:%H\t%h\t%s\t%an\t%ci",
        )
        return self._parse_log_output(output)

    def _parse_log_output(self, output: str) -> list[CommitInfo]:
        """Parse git log output into CommitInfo list."""
        commits = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 5:
                commits.append(CommitInfo(
                    sha=parts[0], short_sha=parts[1], message=parts[2],
                    author=parts[3], date=parts[4],
                ))
        return commits

    def _find_branches_containing(self, sha: str) -> list[str]:
        """Find branches that contain a commit."""
        output = self._git("branch", "-a", "--contains", sha)
        branches = []
        for line in output.splitlines():
            name = line.strip().lstrip("* ")
            if name and " -> " not in name:
                branches.append(name)
        return branches

    def _get_branch_commits(self, branch: str, limit: int = 100) -> list[CommitInfo]:
        """Get recent commits on a branch."""
        output = self._git(
            "log", branch, f"-{limit}", "--pretty=format:%H\t%h\t%s\t%an\t%ci",
        )
        return self._parse_log_output(output)

    # ── Dependency analysis ───────────────────────────────────────────────

    def _find_dependencies(self, commit: CommitInfo) -> list[Dependency]:
        """Find commits that this commit depends on."""
        if not commit.files:
            commit = self._get_commit_info(commit.sha)

        deps = []
        for fpath in commit.files:
            # Find recent commits that touched the same file
            output = self._git(
                "log", "--pretty=format:%H", "-5",
                f"{commit.sha}~1", "--", fpath,
            )
            for line in output.splitlines():
                dep_sha = line.strip()
                if dep_sha and dep_sha != commit.sha:
                    deps.append(Dependency(
                        commit_sha=commit.sha,
                        depends_on_sha=dep_sha,
                        reason="same_file",
                        files=[fpath],
                    ))
                    break  # Only the most recent

        # Deduplicate
        seen = set()
        unique = []
        for d in deps:
            if d.depends_on_sha not in seen:
                seen.add(d.depends_on_sha)
                unique.append(d)
        return unique

    def _check_conflicts(self, commit: CommitInfo, target_branch: str) -> list[str]:
        """Check which files might have conflicts when cherry-picking."""
        if not commit.files:
            commit = self._get_commit_info(commit.sha)

        conflict_files = []
        for fpath in commit.files:
            # Check if the file has diverged on target branch
            target_ver = self._git("log", "-1", "--pretty=format:%H", target_branch, "--", fpath)
            source_parent = self._git("log", "-1", "--pretty=format:%H", f"{commit.sha}~1", "--", fpath)
            if target_ver and source_parent and target_ver != source_parent:
                conflict_files.append(fpath)
        return conflict_files

    def _generate_commands(self, plan: CherryPickPlan) -> list[str]:
        """Generate the sequence of git commands for the cherry-pick."""
        commands = [f"git checkout {plan.target_branch}"]

        # Cherry-pick prerequisites first
        for prereq in plan.prerequisite_commits:
            commands.append(f"git cherry-pick {prereq.sha}  # prerequisite: {prereq.message[:50]}")

        # Main cherry-pick
        if plan.conflicts_likely:
            commands.append(f"git cherry-pick {plan.target_commit.sha}  # may have conflicts")
            commands.append("# If conflicts: resolve, then git cherry-pick --continue")
        else:
            commands.append(f"git cherry-pick {plan.target_commit.sha}")

        return commands
