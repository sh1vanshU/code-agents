"""Commit Splitter — analyze large commits and suggest atomic splits.

Analyzes a commit's changed files, groups them by logical concern, and
suggests how to split into smaller, focused commits with messages.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.commit_splitter")

# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------
_CATEGORY_PATTERNS = {
    "test": re.compile(r"(test[_/]|_test\.|\.test\.|spec[_/]|_spec\.)"),
    "ci": re.compile(r"(\.github/|\.gitlab-ci|jenkinsfile|\.circleci|\.travis)"),
    "migration": re.compile(r"(migrat|schema|alembic|flyway)"),
    "docs": re.compile(r"(\.md$|\.rst$|\.txt$|docs/|readme|changelog|license)"),
    "config": re.compile(r"(\.ya?ml$|\.json$|\.toml$|\.ini$|\.cfg$|\.env|makefile$|dockerfile$)"),
    "style": re.compile(r"(\.css$|\.scss$|\.less$|\.styled\.)"),
    "infra": re.compile(r"(terraform/|\.tf$|k8s/|helm/|deploy/)"),
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileInfo:
    """Info about a changed file in the commit."""

    path: str
    additions: int = 0
    deletions: int = 0
    category: str = "source"
    change_type: str = "modified"


@dataclass
class SplitSuggestion:
    """A suggested atomic commit."""

    order: int
    message: str
    files: list[str] = field(default_factory=list)
    category: str = "source"
    rationale: str = ""
    total_lines: int = 0


@dataclass
class SplitAnalysis:
    """Result of commit split analysis."""

    original_message: str = ""
    total_files: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    suggestions: list[SplitSuggestion] = field(default_factory=list)
    should_split: bool = False
    reason: str = ""

    @property
    def summary(self) -> str:
        if not self.should_split:
            return f"Commit is already focused ({self.total_files} files)"
        return (
            f"Suggest splitting into {len(self.suggestions)} commits "
            f"(from {self.total_files} files, +{self.total_additions}/-{self.total_deletions})"
        )


# ---------------------------------------------------------------------------
# Splitter
# ---------------------------------------------------------------------------


class CommitSplitter:
    """Analyze a commit and suggest atomic splits."""

    def __init__(self, cwd: Optional[str] = None, max_files_per_commit: int = 10):
        self.cwd = cwd or os.getcwd()
        self.max_files = max_files_per_commit

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self, commit: str = "HEAD") -> SplitAnalysis:
        """Analyze a commit and suggest how to split it."""
        message = self._get_commit_message(commit)
        files = self._get_commit_files(commit)

        analysis = SplitAnalysis(
            original_message=message,
            total_files=len(files),
            total_additions=sum(f.additions for f in files),
            total_deletions=sum(f.deletions for f in files),
        )

        if len(files) <= 3:
            analysis.should_split = False
            analysis.reason = "Commit is small enough — no split needed"
            return analysis

        # Categorize files
        for f in files:
            f.category = self._categorize_file(f.path)

        # Group by category
        groups = self._group_by_category(files)

        # Further split large groups by directory
        split_groups = self._refine_groups(groups)

        if len(split_groups) <= 1:
            analysis.should_split = False
            analysis.reason = "All changes are in the same logical group"
            return analysis

        analysis.should_split = True
        analysis.reason = f"Mixed concerns: {', '.join(g['category'] for g in split_groups)}"
        analysis.suggestions = self._generate_suggestions(split_groups, message)

        logger.info("Split analysis: %s", analysis.summary)
        return analysis

    def generate_script(self, analysis: SplitAnalysis, commit: str = "HEAD") -> str:
        """Generate a shell script to perform the split."""
        if not analysis.should_split:
            return "# No split needed"

        lines = [
            "#!/bin/bash",
            "# Auto-generated commit split script",
            f"# Original commit: {commit}",
            f"# Original message: {analysis.original_message}",
            "",
            "set -e",
            "",
            f"# Reset the commit but keep changes staged",
            f"git reset --soft HEAD~1",
            "git reset HEAD .",
            "",
        ]

        for sug in analysis.suggestions:
            lines.append(f"# Split {sug.order}: {sug.category}")
            for f in sug.files:
                lines.append(f"git add {f}")
            lines.append(f'git commit -m "{sug.message}"')
            lines.append("")

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

    def _get_commit_message(self, commit: str) -> str:
        """Get the commit message."""
        return self._git("log", "-1", "--pretty=format:%s", commit)

    def _get_commit_files(self, commit: str) -> list[FileInfo]:
        """Get files changed in the commit with stats."""
        output = self._git("diff-tree", "--no-commit-id", "--numstat", "-r", commit)
        files = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                adds = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                files.append(FileInfo(path=parts[2], additions=adds, deletions=dels))
        return files

    # ── Categorization ────────────────────────────────────────────────────

    def _categorize_file(self, path: str) -> str:
        """Categorize a file by its path pattern."""
        for category, pattern in _CATEGORY_PATTERNS.items():
            if pattern.search(path.lower()):
                return category
        return "source"

    def _group_by_category(self, files: list[FileInfo]) -> dict[str, list[FileInfo]]:
        """Group files by their category."""
        groups: dict[str, list[FileInfo]] = defaultdict(list)
        for f in files:
            groups[f.category].append(f)
        return dict(groups)

    def _refine_groups(self, groups: dict[str, list[FileInfo]]) -> list[dict]:
        """Refine groups — split large groups by directory."""
        refined = []
        for category, files in groups.items():
            if len(files) <= self.max_files:
                refined.append({
                    "category": category,
                    "files": files,
                })
            else:
                # Sub-group by top-level directory
                dir_groups: dict[str, list[FileInfo]] = defaultdict(list)
                for f in files:
                    top_dir = f.path.split("/")[0] if "/" in f.path else "(root)"
                    dir_groups[top_dir].append(f)
                for dir_name, dir_files in dir_groups.items():
                    refined.append({
                        "category": f"{category}/{dir_name}",
                        "files": dir_files,
                    })
        return refined

    # ── Suggestion generation ─────────────────────────────────────────────

    def _generate_suggestions(self, groups: list[dict], original_message: str) -> list[SplitSuggestion]:
        """Generate commit suggestions for each group."""
        # Define ordering priority
        priority = {"infra": 0, "migration": 1, "config": 2, "source": 3,
                     "style": 4, "test": 5, "docs": 6, "ci": 7}
        sorted_groups = sorted(groups, key=lambda g: priority.get(g["category"].split("/")[0], 5))

        suggestions = []
        for i, group in enumerate(sorted_groups, 1):
            files = group["files"]
            category = group["category"]
            total = sum(f.additions + f.deletions for f in files)
            message = self._generate_message(category, files, original_message)

            suggestions.append(SplitSuggestion(
                order=i,
                message=message,
                files=[f.path for f in files],
                category=category,
                rationale=f"{len(files)} {category} file(s), {total} lines changed",
                total_lines=total,
            ))
        return suggestions

    def _generate_message(self, category: str, files: list[FileInfo], original: str) -> str:
        """Generate a commit message for a split group."""
        base_cat = category.split("/")[0]
        prefix_map = {
            "test": "test",
            "docs": "docs",
            "config": "chore",
            "ci": "ci",
            "migration": "feat",
            "infra": "infra",
            "style": "style",
            "source": "feat",
        }
        prefix = prefix_map.get(base_cat, "chore")

        # Try to extract scope from directory
        dirs = set()
        for f in files:
            parts = f.path.split("/")
            if len(parts) > 1:
                dirs.add(parts[0])
        scope = f"({next(iter(dirs))})" if len(dirs) == 1 else ""

        # Use original message as context but adjust
        short_original = original[:50] if original else "update"
        return f"{prefix}{scope}: {short_original}"
