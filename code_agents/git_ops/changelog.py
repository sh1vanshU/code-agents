"""Automated Changelog Generator — commits + PRs to structured changelog.

Parses git history and merged PRs between two refs, categorizes by
conventional commit prefixes and PR labels, outputs markdown or terminal.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.changelog")

# ── Category mapping ─────────────────────────────────────────────────────────

_PREFIX_MAP: dict[str, str] = {
    "feat": "feature",
    "fix": "fix",
    "docs": "docs",
    "refactor": "refactor",
    "style": "refactor",
    "perf": "feature",
    "test": "other",
    "chore": "other",
    "ci": "other",
    "build": "other",
    "breaking": "breaking",
    "breaking change": "breaking",
}

_LABEL_MAP: dict[str, str] = {
    "bug": "fix",
    "enhancement": "feature",
    "feature": "feature",
    "documentation": "docs",
    "breaking": "breaking",
    "refactor": "refactor",
    "breaking-change": "breaking",
}

_CATEGORY_HEADERS: dict[str, str] = {
    "feature": "Features",
    "fix": "Bug Fixes",
    "breaking": "Breaking Changes",
    "docs": "Documentation",
    "refactor": "Refactoring",
    "other": "Other Changes",
}

_CATEGORY_ICONS: dict[str, str] = {
    "feature": "+",
    "fix": "*",
    "breaking": "!",
    "docs": "#",
    "refactor": "~",
    "other": "-",
}

_PREFIX_PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|test|chore|perf|ci|build|breaking(?:\s+change)?)"
    r"(?:\([^)]*\))?"
    r"(?P<bang>!)?"
    r":\s*(?P<rest>.*)",
    re.IGNORECASE,
)


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class CommitInfo:
    """A single git commit."""

    sha: str
    message: str
    author: str
    date: str
    files_changed: int = 0


@dataclass
class PRInfo:
    """A merged pull request."""

    number: int
    title: str
    body: str
    labels: list[str]
    author: str
    merged_at: str = ""


@dataclass
class ChangelogEntry:
    """One line item in the changelog."""

    category: str  # "feature", "fix", "breaking", "docs", "refactor", "other"
    description: str
    pr_number: int = 0
    commit_sha: str = ""
    author: str = ""


@dataclass
class Changelog:
    """A complete changelog for one version."""

    version: str
    date: str
    features: list[ChangelogEntry] = field(default_factory=list)
    fixes: list[ChangelogEntry] = field(default_factory=list)
    breaking: list[ChangelogEntry] = field(default_factory=list)
    docs: list[ChangelogEntry] = field(default_factory=list)
    refactoring: list[ChangelogEntry] = field(default_factory=list)
    other: list[ChangelogEntry] = field(default_factory=list)

    @property
    def all_entries(self) -> list[ChangelogEntry]:
        return self.features + self.fixes + self.breaking + self.docs + self.refactoring + self.other

    def _bucket(self, entry: ChangelogEntry) -> None:
        """Place entry into the correct bucket by category."""
        buckets = {
            "feature": self.features,
            "fix": self.fixes,
            "breaking": self.breaking,
            "docs": self.docs,
            "refactor": self.refactoring,
            "other": self.other,
        }
        buckets.get(entry.category, self.other).append(entry)


# ── Generator ────────────────────────────────────────────────────────────────


class ChangelogGenerator:
    """Generate a changelog from git commits and merged PRs between two refs."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("ChangelogGenerator initialized — repo=%s", cwd)

    # ── Public API ───────────────────────────────────────────────────────

    def generate(self, from_ref: str, to_ref: str = "HEAD") -> Changelog:
        """Build a Changelog from commits and PRs between *from_ref* and *to_ref*."""
        commits = self._get_commits(from_ref, to_ref)
        prs = self._get_merged_prs(from_ref, to_ref)
        changelog = self._categorize(commits, prs)
        logger.info(
            "Generated changelog: %d features, %d fixes, %d breaking, %d docs, %d refactor, %d other",
            len(changelog.features), len(changelog.fixes), len(changelog.breaking),
            len(changelog.docs), len(changelog.refactoring), len(changelog.other),
        )
        return changelog

    # ── Git helpers ──────────────────────────────────────────────────────

    def _get_commits(self, from_ref: str, to_ref: str) -> list[CommitInfo]:
        """Return commits between two refs via ``git log``."""
        fmt = "%H|%s|%an|%aI"
        cmd = ["git", "log", f"--format={fmt}", f"{from_ref}..{to_ref}"]
        try:
            result = subprocess.run(
                cmd, cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git log failed: %s", result.stderr.strip())
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("git log error: %s", exc)
            return []

        commits: list[CommitInfo] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, message, author, date = parts
            commits.append(CommitInfo(
                sha=sha.strip(), message=message.strip(),
                author=author.strip(), date=date.strip(),
            ))

        # Optionally enrich with file counts (best-effort)
        for ci in commits:
            ci.files_changed = self._count_files_changed(ci.sha)

        return commits

    def _count_files_changed(self, sha: str) -> int:
        """Return the number of files changed in a single commit."""
        cmd = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha]
        try:
            result = subprocess.run(
                cmd, cwd=self.cwd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return len([l for l in result.stdout.strip().splitlines() if l.strip()])
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return 0

    def _get_merged_prs(self, from_ref: str, to_ref: str) -> list[PRInfo]:
        """Return merged PRs between two refs using ``gh pr list``.

        Falls back gracefully to an empty list when ``gh`` is unavailable.
        """
        # Determine merge date range from the refs
        date_range = self._ref_date_range(from_ref, to_ref)

        fields = "number,title,body,labels,author,mergedAt"
        cmd = [
            "gh", "pr", "list",
            "--state", "merged",
            "--json", fields,
            "--limit", "200",
        ]
        try:
            result = subprocess.run(
                cmd, cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                logger.debug("gh pr list failed (gh may not be installed): %s", result.stderr.strip())
                return []
        except FileNotFoundError:
            logger.debug("gh CLI not found — skipping PR enrichment")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("gh pr list timed out")
            return []

        try:
            raw = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse gh pr list output")
            return []

        prs: list[PRInfo] = []
        for item in raw:
            labels = []
            for lbl in (item.get("labels") or []):
                if isinstance(lbl, dict):
                    labels.append(lbl.get("name", ""))
                else:
                    labels.append(str(lbl))

            author = ""
            author_raw = item.get("author")
            if isinstance(author_raw, dict):
                author = author_raw.get("login", "")
            elif isinstance(author_raw, str):
                author = author_raw

            merged_at = item.get("mergedAt", "")

            # Filter by date range if available
            if date_range and merged_at:
                start, end = date_range
                if merged_at < start or merged_at > end:
                    continue

            prs.append(PRInfo(
                number=item.get("number", 0),
                title=item.get("title", ""),
                body=item.get("body", ""),
                labels=labels,
                author=author,
                merged_at=merged_at,
            ))

        return prs

    def _ref_date_range(self, from_ref: str, to_ref: str) -> Optional[tuple[str, str]]:
        """Return (start_date, end_date) ISO strings for the two refs."""
        dates: list[str] = []
        for ref in (from_ref, to_ref):
            cmd = ["git", "log", "-1", "--format=%aI", ref]
            try:
                result = subprocess.run(
                    cmd, cwd=self.cwd, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    dates.append(result.stdout.strip())
                else:
                    return None
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return None
        if len(dates) == 2:
            return (min(dates), max(dates))
        return None

    # ── Categorization ───────────────────────────────────────────────────

    def _categorize(self, commits: list[CommitInfo], prs: list[PRInfo]) -> Changelog:
        """Build a Changelog by categorizing commits and PRs."""
        today = datetime.now().strftime("%Y-%m-%d")
        changelog = Changelog(version="Unreleased", date=today)

        # Track PR numbers we've already seen (to avoid duplicates)
        seen_pr_numbers: set[int] = set()

        # First, categorize PRs (richer metadata)
        for pr in prs:
            category = self._category_from_pr(pr)
            entry = ChangelogEntry(
                category=category,
                description=pr.title,
                pr_number=pr.number,
                author=pr.author,
            )
            changelog._bucket(entry)
            seen_pr_numbers.add(pr.number)

        # Then, categorize commits (skip those already covered by a PR)
        for commit in commits:
            # Check if commit message references a PR we already have
            pr_ref = self._extract_pr_number(commit.message)
            if pr_ref and pr_ref in seen_pr_numbers:
                continue

            category = self._category_from_message(commit.message)
            desc = self._clean_message(commit.message)
            entry = ChangelogEntry(
                category=category,
                description=desc,
                commit_sha=commit.sha[:7],
                author=commit.author,
                pr_number=pr_ref or 0,
            )
            changelog._bucket(entry)

        return changelog

    def _category_from_message(self, message: str) -> str:
        """Derive category from a conventional commit message."""
        m = _PREFIX_PATTERN.match(message)
        if not m:
            return "other"
        ctype = m.group("type").lower()
        if m.group("bang"):
            return "breaking"
        return _PREFIX_MAP.get(ctype, "other")

    def _category_from_pr(self, pr: PRInfo) -> str:
        """Derive category from PR labels, falling back to title prefix."""
        for label in pr.labels:
            cat = _LABEL_MAP.get(label.lower())
            if cat:
                return cat
        # Fall back to parsing the title as a conventional commit
        return self._category_from_message(pr.title)

    def _clean_message(self, message: str) -> str:
        """Strip conventional commit prefix from message for display."""
        m = _PREFIX_PATTERN.match(message)
        if m:
            return m.group("rest").strip()
        return message.strip()

    def _extract_pr_number(self, message: str) -> Optional[int]:
        """Extract PR number from commit message like ``(#123)``."""
        m = re.search(r"\(#(\d+)\)", message)
        if m:
            return int(m.group(1))
        return None

    # ── Formatters ───────────────────────────────────────────────────────

    def format_markdown(self, changelog: Changelog) -> str:
        """Format a Changelog as markdown."""
        lines: list[str] = []
        lines.append(f"## {changelog.version} ({changelog.date})")
        lines.append("")

        if not changelog.all_entries:
            lines.append("No changes found.")
            return "\n".join(lines)

        sections = [
            ("breaking", changelog.breaking),
            ("feature", changelog.features),
            ("fix", changelog.fixes),
            ("docs", changelog.docs),
            ("refactor", changelog.refactoring),
            ("other", changelog.other),
        ]

        for cat_key, entries in sections:
            if not entries:
                continue
            header = _CATEGORY_HEADERS.get(cat_key, cat_key.capitalize())
            lines.append(f"### {header}")
            lines.append("")
            for e in entries:
                suffix = ""
                if e.pr_number:
                    suffix = f" (#{e.pr_number})"
                elif e.commit_sha:
                    suffix = f" ({e.commit_sha})"
                author_str = f" — @{e.author}" if e.author else ""
                lines.append(f"- {e.description}{suffix}{author_str}")
            lines.append("")

        return "\n".join(lines)

    def format_terminal(self, changelog: Changelog) -> str:
        """Format a Changelog with colored terminal output."""
        lines: list[str] = []
        lines.append("")
        lines.append(f"  Changelog — {changelog.version} ({changelog.date})")
        lines.append("  " + "=" * 50)
        lines.append("")

        if not changelog.all_entries:
            lines.append("  No changes found.")
            return "\n".join(lines)

        sections = [
            ("breaking", changelog.breaking),
            ("feature", changelog.features),
            ("fix", changelog.fixes),
            ("docs", changelog.docs),
            ("refactor", changelog.refactoring),
            ("other", changelog.other),
        ]

        for cat_key, entries in sections:
            if not entries:
                continue
            header = _CATEGORY_HEADERS.get(cat_key, cat_key.capitalize())
            icon = _CATEGORY_ICONS.get(cat_key, "-")
            lines.append(f"  [{icon}] {header} ({len(entries)})")
            lines.append("  " + "-" * 40)
            for e in entries:
                ref = ""
                if e.pr_number:
                    ref = f" (#{e.pr_number})"
                elif e.commit_sha:
                    ref = f" ({e.commit_sha})"
                lines.append(f"    {e.description}{ref}")
            lines.append("")

        total = len(changelog.all_entries)
        lines.append(f"  Total entries: {total}")
        return "\n".join(lines)

    def write_markdown(self, changelog: Changelog, filepath: Optional[str] = None) -> str:
        """Write changelog markdown to a file (prepend to existing or create new)."""
        path = filepath or os.path.join(self.cwd, "CHANGELOG.md")
        new_content = self.format_markdown(changelog)

        if os.path.exists(path):
            existing = open(path, "r").read()
            if existing.startswith("# "):
                first_nl = existing.index("\n") if "\n" in existing else len(existing)
                header = existing[: first_nl + 1]
                rest = existing[first_nl + 1 :]
                content = header + "\n" + new_content + "\n" + rest
            else:
                content = new_content + "\n" + existing
        else:
            content = "# Changelog\n\n" + new_content

        with open(path, "w") as f:
            f.write(content)

        logger.info("Changelog written to %s", path)
        return path
