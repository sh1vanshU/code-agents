"""PR Writer — generate enhanced pull request descriptions.

Produces structured PR descriptions with what/why/how sections,
rollback plan, reviewer hints, and risk assessment.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.pr_writer")

# ---------------------------------------------------------------------------
# Risk keywords
# ---------------------------------------------------------------------------
_HIGH_RISK_PATTERNS = {"migration", "schema", "deploy", "infra", "security", "auth", "secret", "database"}
_MEDIUM_RISK_PATTERNS = {"config", "api", "route", "model", "middleware"}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileChange:
    """Summary of a changed file."""

    path: str
    additions: int = 0
    deletions: int = 0
    change_type: str = "modified"  # "added" | "modified" | "deleted" | "renamed"


@dataclass
class PRDescription:
    """Generated PR description."""

    title: str
    what: str
    why: str
    how: str
    rollback_plan: str
    reviewer_hints: list[str] = field(default_factory=list)
    risk_level: str = "low"
    testing_notes: str = ""
    breaking_changes: list[str] = field(default_factory=list)
    related_issues: list[str] = field(default_factory=list)
    files_changed: list[FileChange] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render as markdown PR body."""
        sections = [
            f"## What\n{self.what}",
            f"## Why\n{self.why}",
            f"## How\n{self.how}",
        ]
        if self.breaking_changes:
            items = "\n".join(f"- {c}" for c in self.breaking_changes)
            sections.append(f"## Breaking Changes\n{items}")
        if self.testing_notes:
            sections.append(f"## Testing\n{self.testing_notes}")
        sections.append(f"## Rollback Plan\n{self.rollback_plan}")
        if self.reviewer_hints:
            items = "\n".join(f"- {h}" for h in self.reviewer_hints)
            sections.append(f"## Reviewer Hints\n{items}")
        sections.append(f"\n**Risk Level:** {self.risk_level}")
        if self.related_issues:
            refs = ", ".join(self.related_issues)
            sections.append(f"**Related Issues:** {refs}")
        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# PR Writer
# ---------------------------------------------------------------------------


class PRWriter:
    """Generate enhanced PR descriptions from git diff analysis."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def generate(self, base: str = "main", head: str = "HEAD") -> PRDescription:
        """Generate a PR description by analyzing the diff between base and head."""
        commits = self._get_commits(base, head)
        file_changes = self._get_file_changes(base, head)
        diff_stat = self._get_diff_stat(base, head)

        title = self._generate_title(commits, file_changes)
        what = self._generate_what(commits, file_changes, diff_stat)
        why = self._generate_why(commits)
        how = self._generate_how(file_changes)
        risk = self._assess_risk(file_changes)
        rollback = self._generate_rollback(file_changes, risk)
        hints = self._generate_reviewer_hints(file_changes, diff_stat)
        testing = self._generate_testing_notes(file_changes)
        breaking = self._detect_breaking_changes(commits, file_changes)
        issues = self._extract_issues(commits)

        desc = PRDescription(
            title=title,
            what=what,
            why=why,
            how=how,
            rollback_plan=rollback,
            reviewer_hints=hints,
            risk_level=risk,
            testing_notes=testing,
            breaking_changes=breaking,
            related_issues=issues,
            files_changed=file_changes,
        )
        logger.info("Generated PR description: %s (%s risk)", title, risk)
        return desc

    # ── Git helpers ───────────────────────────────────────────────────────

    def _git(self, *args: str) -> str:
        """Run a git command and return stdout."""
        try:
            proc = subprocess.run(
                ["git", *args], capture_output=True, text=True,
                cwd=self.cwd, timeout=15,
            )
            return proc.stdout.strip() if proc.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _get_commits(self, base: str, head: str) -> list[str]:
        """Get commit messages between base and head."""
        output = self._git("log", f"{base}..{head}", "--pretty=format:%s")
        return [line for line in output.splitlines() if line.strip()] if output else []

    def _get_file_changes(self, base: str, head: str) -> list[FileChange]:
        """Get list of changed files with stats."""
        output = self._git("diff", "--numstat", f"{base}...{head}")
        changes = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                adds = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]
                change_type = "modified"
                changes.append(FileChange(
                    path=path, additions=adds, deletions=dels, change_type=change_type,
                ))

        # Detect added/deleted via --name-status
        status_output = self._git("diff", "--name-status", f"{base}...{head}")
        status_map: dict[str, str] = {}
        for line in status_output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                code = parts[0][0] if parts[0] else "M"
                fname = parts[-1]
                status_map[fname] = {"A": "added", "D": "deleted", "R": "renamed"}.get(code, "modified")
        for fc in changes:
            if fc.path in status_map:
                fc.change_type = status_map[fc.path]
        return changes

    def _get_diff_stat(self, base: str, head: str) -> str:
        """Get diff --stat summary."""
        return self._git("diff", "--stat", f"{base}...{head}")

    # ── Generation ────────────────────────────────────────────────────────

    def _generate_title(self, commits: list[str], files: list[FileChange]) -> str:
        """Generate a concise PR title."""
        if not commits:
            return "Update"
        # Use first commit as base, clean up
        title = commits[0]
        if len(title) > 72:
            title = title[:69] + "..."
        return title

    def _generate_what(self, commits: list[str], files: list[FileChange], stat: str) -> str:
        """Generate the 'what' section."""
        total_adds = sum(f.additions for f in files)
        total_dels = sum(f.deletions for f in files)
        parts = [f"This PR changes **{len(files)} files** (+{total_adds}/-{total_dels} lines)."]

        if commits:
            parts.append("\n**Commits:**")
            for c in commits[:10]:
                parts.append(f"- {c}")
            if len(commits) > 10:
                parts.append(f"- ... and {len(commits) - 10} more")
        return "\n".join(parts)

    def _generate_why(self, commits: list[str]) -> str:
        """Infer the 'why' from commit messages."""
        if not commits:
            return "See commit messages for context."
        # Categorize by conventional commit prefix
        categories: dict[str, list[str]] = {}
        for c in commits:
            m = re.match(r"^(feat|fix|refactor|docs|test|chore|perf|ci|style|build)[\(:]", c, re.IGNORECASE)
            cat = m.group(1).lower() if m else "other"
            categories.setdefault(cat, []).append(c)

        parts = []
        desc_map = {"feat": "New features", "fix": "Bug fixes", "refactor": "Code improvements",
                     "docs": "Documentation updates", "test": "Test improvements",
                     "perf": "Performance improvements", "ci": "CI/CD changes"}
        for cat, msgs in categories.items():
            label = desc_map.get(cat, cat.title())
            parts.append(f"**{label}:** {len(msgs)} commit(s)")
        return "\n".join(parts) if parts else "See commit messages for context."

    def _generate_how(self, files: list[FileChange]) -> str:
        """Generate the 'how' section grouping by directory."""
        dirs: dict[str, list[str]] = {}
        for f in files:
            d = os.path.dirname(f.path) or "(root)"
            dirs.setdefault(d, []).append(os.path.basename(f.path))

        parts = []
        for d in sorted(dirs.keys()):
            file_list = ", ".join(sorted(dirs[d])[:5])
            extra = f" (+{len(dirs[d]) - 5} more)" if len(dirs[d]) > 5 else ""
            parts.append(f"- `{d}/`: {file_list}{extra}")
        return "\n".join(parts) if parts else "No file changes detected."

    def _assess_risk(self, files: list[FileChange]) -> str:
        """Assess overall risk level."""
        for f in files:
            lower = f.path.lower()
            if any(p in lower for p in _HIGH_RISK_PATTERNS):
                return "high"
        for f in files:
            lower = f.path.lower()
            if any(p in lower for p in _MEDIUM_RISK_PATTERNS):
                return "medium"
        total_changes = sum(f.additions + f.deletions for f in files)
        if total_changes > 500:
            return "medium"
        return "low"

    def _generate_rollback(self, files: list[FileChange], risk: str) -> str:
        """Generate rollback plan based on changes."""
        has_migration = any("migration" in f.path.lower() for f in files)
        has_infra = any(kw in f.path.lower() for f in files for kw in ("terraform", "k8s", "helm", "deploy"))

        parts = ["1. Revert this PR: `git revert --mainline 1 <merge-commit>`"]
        if has_migration:
            parts.append("2. Run reverse migration before reverting code changes")
        if has_infra:
            parts.append("2. Revert infrastructure changes first, then application code")
        if risk == "high":
            parts.append("**Note:** High-risk change — consider deploying to staging first")
        return "\n".join(parts)

    def _generate_reviewer_hints(self, files: list[FileChange], stat: str) -> list[str]:
        """Generate hints for reviewers on where to focus."""
        hints = []
        # Largest files
        sorted_files = sorted(files, key=lambda f: f.additions + f.deletions, reverse=True)
        if sorted_files:
            top = sorted_files[0]
            hints.append(f"Start with `{top.path}` — largest change ({top.additions}+/{top.deletions}-)")

        test_files = [f for f in files if "test" in f.path.lower()]
        src_files = [f for f in files if "test" not in f.path.lower()]
        if src_files and not test_files:
            hints.append("No test files changed — verify test coverage")
        if len(files) > 10:
            hints.append(f"Large PR ({len(files)} files) — consider reviewing by directory")
        return hints

    def _generate_testing_notes(self, files: list[FileChange]) -> str:
        """Generate testing notes based on changed files."""
        test_files = [f for f in files if "test" in f.path.lower()]
        if test_files:
            return f"{len(test_files)} test file(s) updated. Run the full test suite."
        return "No test files changed. Consider adding tests for new logic."

    def _detect_breaking_changes(self, commits: list[str], files: list[FileChange]) -> list[str]:
        """Detect potential breaking changes."""
        breaking = []
        for c in commits:
            if "BREAKING" in c.upper() or "breaking change" in c.lower():
                breaking.append(c)
        for f in files:
            if f.change_type == "deleted" and any(kw in f.path for kw in ("api", "schema", "model", "proto")):
                breaking.append(f"Deleted {f.path} — may break dependents")
        return breaking

    def _extract_issues(self, commits: list[str]) -> list[str]:
        """Extract issue references from commit messages."""
        issues = set()
        for c in commits:
            # Match JIRA-style (PROJ-123) and GitHub-style (#123)
            for m in re.finditer(r"([A-Z]+-\d+|#\d+)", c):
                issues.add(m.group(1))
        return sorted(issues)
