"""Changelog Generator — conventional commits to CHANGELOG.md."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.generators.changelog_gen")

# Conventional commit types
_COMMIT_TYPES = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "docs": "Documentation",
    "style": "Style",
    "refactor": "Refactoring",
    "test": "Tests",
    "chore": "Chores",
    "perf": "Performance",
    "ci": "CI/CD",
    "build": "Build",
    "breaking": "Breaking Changes",
}

_COMMIT_PATTERN = re.compile(
    r'^(?P<hash>[a-f0-9]+)\s+'
    r'(?:(?P<type>feat|fix|docs|style|refactor|test|chore|perf|ci|build)'
    r'(?:\((?P<scope>[^)]*)\))?'
    r'(?P<breaking>!)?:\s*)?'
    r'(?P<message>.*)',
    re.IGNORECASE,
)


@dataclass
class CommitEntry:
    """A parsed conventional commit."""

    hash: str
    type: str
    scope: str
    message: str
    breaking: bool = False


@dataclass
class ChangelogData:
    """Grouped commits for a changelog release."""

    version: str
    date: str
    commits: list[CommitEntry] = field(default_factory=list)

    @property
    def by_type(self) -> dict[str, list[CommitEntry]]:
        groups: dict[str, list[CommitEntry]] = {}
        for c in self.commits:
            groups.setdefault(c.type, []).append(c)
        return groups


class ChangelogGenerator:
    """Generates changelog from conventional commits since last tag."""

    def __init__(self, cwd: str, version: Optional[str] = None):
        self.cwd = cwd
        self.version = version or "Unreleased"
        logger.info("ChangelogGenerator initialized — repo=%s", cwd)

    def get_last_tag(self) -> Optional[str]:
        """Get the most recent git tag."""
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def get_commits_since_tag(self, tag: Optional[str] = None) -> list[str]:
        """Get commit lines since tag (or all if no tag)."""
        if tag:
            cmd = ["git", "log", f"{tag}..HEAD", "--oneline"]
        else:
            cmd = ["git", "log", "--oneline", "-100"]
        try:
            result = subprocess.run(
                cmd, cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return [l for l in result.stdout.strip().splitlines() if l.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    def parse_commits(self, raw_lines: list[str]) -> list[CommitEntry]:
        """Parse raw commit lines into CommitEntry objects."""
        entries: list[CommitEntry] = []
        for line in raw_lines:
            m = _COMMIT_PATTERN.match(line)
            if not m:
                continue
            commit_type = (m.group("type") or "chore").lower()
            breaking = bool(m.group("breaking"))
            if breaking:
                commit_type = "breaking"
            entries.append(CommitEntry(
                hash=m.group("hash"),
                type=commit_type,
                scope=m.group("scope") or "",
                message=m.group("message").strip(),
                breaking=breaking,
            ))
        return entries

    def generate(self) -> ChangelogData:
        """Generate changelog data from git history."""
        tag = self.get_last_tag()
        raw = self.get_commits_since_tag(tag)
        commits = self.parse_commits(raw)
        return ChangelogData(
            version=self.version,
            date=datetime.now().strftime("%Y-%m-%d"),
            commits=commits,
        )

    def format_markdown(self, data: ChangelogData) -> str:
        """Format changelog data as markdown."""
        lines: list[str] = []
        lines.append(f"## [{data.version}] - {data.date}")
        lines.append("")

        if not data.commits:
            lines.append("No conventional commits found.")
            return "\n".join(lines)

        by_type = data.by_type
        type_order = ["breaking", "feat", "fix", "perf", "refactor", "docs",
                       "test", "ci", "build", "style", "chore"]

        for t in type_order:
            items = by_type.get(t, [])
            if not items:
                continue
            label = _COMMIT_TYPES.get(t, t.capitalize())
            lines.append(f"### {label}")
            lines.append("")
            for c in items:
                scope_str = f"**{c.scope}**: " if c.scope else ""
                lines.append(f"- {scope_str}{c.message} ({c.hash})")
            lines.append("")

        return "\n".join(lines)

    def prepend_to_changelog(self, data: ChangelogData, filepath: Optional[str] = None):
        """Prepend new release to CHANGELOG.md."""
        path = filepath or os.path.join(self.cwd, "CHANGELOG.md")
        new_content = self.format_markdown(data)

        if os.path.exists(path):
            existing = open(path, "r").read()
            # Insert after the title line if present
            if existing.startswith("# "):
                first_newline = existing.index("\n") if "\n" in existing else len(existing)
                header = existing[:first_newline + 1]
                rest = existing[first_newline + 1:]
                content = header + "\n" + new_content + "\n" + rest
            else:
                content = new_content + "\n" + existing
        else:
            content = "# Changelog\n\n" + new_content

        with open(path, "w") as f:
            f.write(content)

        return path


def format_changelog_terminal(data: ChangelogData) -> str:
    """Format changelog for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"  Changelog — {data.version} ({data.date})")
    lines.append("  " + "=" * 50)
    lines.append("")

    if not data.commits:
        lines.append("  No conventional commits found since last tag.")
        return "\n".join(lines)

    by_type = data.by_type
    type_order = ["breaking", "feat", "fix", "perf", "refactor", "docs",
                   "test", "ci", "build", "style", "chore"]

    for t in type_order:
        items = by_type.get(t, [])
        if not items:
            continue
        label = _COMMIT_TYPES.get(t, t.capitalize())
        lines.append(f"  {label} ({len(items)})")
        lines.append("  " + "-" * 40)
        for c in items:
            scope_str = f"({c.scope}) " if c.scope else ""
            lines.append(f"    {c.hash[:7]} {scope_str}{c.message}")
        lines.append("")

    lines.append(f"  Total commits: {len(data.commits)}")
    return "\n".join(lines)
