"""Historical bug pattern detector — learns from git history.

Scans git log for fix/bug commits, extracts removed->added line patterns,
and checks new diffs against known bug patterns to warn developers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.bug_patterns")

_DEFAULT_STORE = Path.home() / ".code-agents" / "bug_patterns.json"


@dataclass
class BugPattern:
    """A known bug pattern extracted from git history."""

    pattern: str  # regex pattern to match in diffs
    description: str
    occurrences: int = 1
    fix_applied: str = ""  # description of the fix
    commit_refs: list[str] = field(default_factory=list)


class BugPatternDetector:
    """Detect known bug patterns in diffs by learning from git history."""

    def __init__(self, repo_path: str = ".", store_path: str | Path | None = None):
        self.repo_path = repo_path
        self.store_path = Path(store_path) if store_path else _DEFAULT_STORE
        self.patterns: list[BugPattern] = []
        self._load()

    def _load(self) -> None:
        """Load patterns from persistent storage."""
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text())
                self.patterns = [
                    BugPattern(**p) for p in data.get("patterns", [])
                ]
                logger.info("Loaded %d bug patterns from %s", len(self.patterns), self.store_path)
            except Exception as exc:
                logger.warning("Failed to load bug patterns: %s", exc)

    def save(self) -> None:
        """Save patterns to persistent storage."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"patterns": [asdict(p) for p in self.patterns]}
        self.store_path.write_text(json.dumps(data, indent=2))
        logger.info("Saved %d bug patterns to %s", len(self.patterns), self.store_path)

    def learn_from_history(self, days: int = 90) -> int:
        """Scan git log for fix/bug commits and extract patterns.

        Args:
            days: Number of days of history to scan.

        Returns:
            Number of new patterns learned.
        """
        try:
            result = subprocess.run(
                ["git", "log", f"--since={days} days ago", "--all",
                 "--grep=fix", "--grep=bug", "--grep=hotfix",
                 "--format=%H %s", "--diff-filter=M"],
                capture_output=True, text=True, cwd=self.repo_path, timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("git command failed")
            return 0

        if result.returncode != 0:
            return 0

        new_count = 0
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            commit_hash, message = parts[0], parts[1]

            # Get the diff for this commit
            diff_result = subprocess.run(
                ["git", "diff", f"{commit_hash}~1", commit_hash, "--unified=0"],
                capture_output=True, text=True, cwd=self.repo_path, timeout=15,
            )
            if diff_result.returncode != 0:
                continue

            removed_lines = []
            for diff_line in diff_result.stdout.splitlines():
                if diff_line.startswith("-") and not diff_line.startswith("---"):
                    content = diff_line[1:].strip()
                    if content and len(content) > 10:
                        removed_lines.append(content)

            for removed in removed_lines:
                # Escape for regex, create a fuzzy pattern
                escaped = re.escape(removed)
                # Check if we already have this pattern
                existing = self._find_similar(escaped)
                if existing:
                    existing.occurrences += 1
                    if commit_hash not in existing.commit_refs:
                        existing.commit_refs.append(commit_hash)
                else:
                    self.patterns.append(BugPattern(
                        pattern=escaped,
                        description=f"Bug pattern from: {message}",
                        occurrences=1,
                        fix_applied=message,
                        commit_refs=[commit_hash],
                    ))
                    new_count += 1

        if new_count > 0:
            self.save()
        return new_count

    def _find_similar(self, pattern: str) -> Optional[BugPattern]:
        """Find an existing pattern that matches the given one."""
        for p in self.patterns:
            if p.pattern == pattern:
                return p
        return None

    def check_diff(self, diff: str) -> list[BugPattern]:
        """Check a diff against known bug patterns.

        Args:
            diff: Unified diff text.

        Returns:
            List of matched bug patterns.
        """
        matches = []
        added_lines = []
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:].strip())

        added_text = "\n".join(added_lines)

        for bp in self.patterns:
            try:
                if re.search(bp.pattern, added_text):
                    matches.append(bp)
            except re.error:
                logger.warning("Invalid pattern: %s", bp.pattern)
        return matches

    def add_pattern(self, pattern: str, description: str, fix_applied: str = "") -> BugPattern:
        """Manually add a bug pattern.

        Args:
            pattern: Regex pattern to detect.
            description: What the bug is.
            fix_applied: How it was fixed.

        Returns:
            The created BugPattern.
        """
        bp = BugPattern(
            pattern=pattern,
            description=description,
            fix_applied=fix_applied,
        )
        self.patterns.append(bp)
        self.save()
        return bp


def format_bug_warnings(matches: list[BugPattern]) -> str:
    """Format bug pattern matches for terminal display."""
    if not matches:
        return "  No known bug patterns detected."

    lines = []
    lines.append("  ╔══ BUG PATTERN WARNINGS ══╗")
    lines.append(f"  ║ {len(matches)} known pattern(s) detected")
    lines.append("  ╚═══════════════════════════╝")

    for i, bp in enumerate(matches, 1):
        lines.append(f"\n  {i}. {bp.description}")
        lines.append(f"     Seen {bp.occurrences} time(s) in history")
        if bp.fix_applied:
            lines.append(f"     Previous fix: {bp.fix_applied}")
        if bp.commit_refs:
            lines.append(f"     Commits: {', '.join(bp.commit_refs[:3])}")

    return "\n".join(lines)
