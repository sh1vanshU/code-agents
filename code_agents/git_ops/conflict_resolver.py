"""Merge Conflict Resolver — semantic conflict analysis and resolution.

Parses git merge conflicts, understands the intent of both sides,
and suggests resolutions that preserve both changes where possible.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.conflict_resolver")

# ---------------------------------------------------------------------------
# Conflict markers
# ---------------------------------------------------------------------------
_OURS_START = re.compile(r"^<{7}\s*(.*)")
_SEPARATOR = re.compile(r"^={7}")
_THEIRS_END = re.compile(r"^>{7}\s*(.*)")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConflictHunk:
    """A single merge conflict within a file."""

    file_path: str
    start_line: int
    end_line: int
    ours_label: str
    theirs_label: str
    ours_lines: list[str] = field(default_factory=list)
    theirs_lines: list[str] = field(default_factory=list)
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)


@dataclass
class Resolution:
    """A suggested resolution for a conflict."""

    hunk: ConflictHunk
    strategy: str  # "ours" | "theirs" | "both" | "manual"
    resolved_lines: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0


@dataclass
class ConflictReport:
    """Report of all conflicts and suggested resolutions."""

    conflicts: list[ConflictHunk] = field(default_factory=list)
    resolutions: list[Resolution] = field(default_factory=list)
    unresolvable: list[ConflictHunk] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"{len(self.conflicts)} conflict(s) in {len(self.files_affected)} file(s), "
            f"{len(self.resolutions)} auto-resolvable"
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class ConflictResolver:
    """Parse and resolve git merge conflicts semantically."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self) -> ConflictReport:
        """Find and analyze all merge conflicts in the working tree."""
        conflicted_files = self._get_conflicted_files()
        report = ConflictReport(files_affected=conflicted_files)

        for fpath in conflicted_files:
            full_path = os.path.join(self.cwd, fpath)
            hunks = self._parse_conflicts(full_path)
            report.conflicts.extend(hunks)

        # Attempt resolution for each hunk
        for hunk in report.conflicts:
            resolution = self._resolve(hunk)
            if resolution.strategy != "manual":
                report.resolutions.append(resolution)
            else:
                report.unresolvable.append(hunk)

        logger.info("Conflict analysis: %s", report.summary)
        return report

    def analyze_file(self, file_path: str) -> list[ConflictHunk]:
        """Parse conflicts in a specific file."""
        return self._parse_conflicts(file_path)

    def apply_resolutions(self, resolutions: list[Resolution]) -> int:
        """Apply resolutions to files. Returns count of applied resolutions."""
        files_content: dict[str, list[str]] = {}
        applied = 0

        for res in resolutions:
            fpath = res.hunk.file_path
            if fpath not in files_content:
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    files_content[fpath] = content.splitlines(keepends=True)
                except OSError:
                    continue

        # Apply resolutions in reverse line order to preserve line numbers
        by_file: dict[str, list[Resolution]] = {}
        for res in resolutions:
            by_file.setdefault(res.hunk.file_path, []).append(res)

        for fpath, file_resolutions in by_file.items():
            if fpath not in files_content:
                continue
            lines = files_content[fpath]
            # Sort by start line descending
            for res in sorted(file_resolutions, key=lambda r: r.hunk.start_line, reverse=True):
                start = res.hunk.start_line - 1  # 0-indexed
                end = res.hunk.end_line
                resolved = [line + "\n" if not line.endswith("\n") else line
                            for line in res.resolved_lines]
                lines[start:end] = resolved
                applied += 1

            Path(fpath).write_text("".join(lines), encoding="utf-8")
            logger.info("Applied %d resolution(s) to %s", len(file_resolutions), fpath)

        return applied

    # ── Conflict parsing ──────────────────────────────────────────────────

    def _get_conflicted_files(self) -> list[str]:
        """Get list of files with merge conflicts."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                capture_output=True, text=True, cwd=self.cwd, timeout=10,
            )
            if proc.returncode == 0:
                return [f for f in proc.stdout.strip().splitlines() if f]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    def _parse_conflicts(self, file_path: str) -> list[ConflictHunk]:
        """Parse conflict markers in a file."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        lines = content.splitlines()
        hunks: list[ConflictHunk] = []
        i = 0

        while i < len(lines):
            m_start = _OURS_START.match(lines[i])
            if m_start:
                hunk = self._extract_hunk(lines, i, file_path, m_start.group(1).strip())
                if hunk:
                    hunks.append(hunk)
                    i = hunk.end_line
                    continue
            i += 1

        return hunks

    def _extract_hunk(self, lines: list[str], start: int, file_path: str,
                      ours_label: str) -> Optional[ConflictHunk]:
        """Extract a single conflict hunk starting from a <<<<<<< marker."""
        ours_lines = []
        theirs_lines = []
        in_ours = True
        theirs_label = ""

        for j in range(start + 1, min(start + 500, len(lines))):
            if _SEPARATOR.match(lines[j]):
                in_ours = False
                continue
            m_end = _THEIRS_END.match(lines[j])
            if m_end:
                theirs_label = m_end.group(1).strip()
                # Gather context
                ctx_before = lines[max(0, start - 3):start]
                ctx_after = lines[j + 1:min(j + 4, len(lines))]
                return ConflictHunk(
                    file_path=file_path,
                    start_line=start + 1,  # 1-indexed
                    end_line=j + 1,
                    ours_label=ours_label,
                    theirs_label=theirs_label,
                    ours_lines=ours_lines,
                    theirs_lines=theirs_lines,
                    context_before=ctx_before,
                    context_after=ctx_after,
                )
            if in_ours:
                ours_lines.append(lines[j])
            else:
                theirs_lines.append(lines[j])
        return None

    # ── Resolution strategies ─────────────────────────────────────────────

    def _resolve(self, hunk: ConflictHunk) -> Resolution:
        """Attempt to resolve a conflict hunk."""
        # Strategy 1: identical changes (trivial)
        if hunk.ours_lines == hunk.theirs_lines:
            return Resolution(
                hunk=hunk, strategy="ours",
                resolved_lines=hunk.ours_lines,
                explanation="Both sides made identical changes",
                confidence=1.0,
            )

        # Strategy 2: one side is empty (deletion vs addition)
        if not hunk.ours_lines:
            return Resolution(
                hunk=hunk, strategy="theirs",
                resolved_lines=hunk.theirs_lines,
                explanation="Our side deleted, theirs has content — keeping theirs",
                confidence=0.6,
            )
        if not hunk.theirs_lines:
            return Resolution(
                hunk=hunk, strategy="ours",
                resolved_lines=hunk.ours_lines,
                explanation="Their side deleted, ours has content — keeping ours",
                confidence=0.6,
            )

        # Strategy 3: non-overlapping additions (e.g., import statements)
        if self._are_independent_additions(hunk):
            combined = hunk.ours_lines + hunk.theirs_lines
            return Resolution(
                hunk=hunk, strategy="both",
                resolved_lines=combined,
                explanation="Independent additions — combining both sets of changes",
                confidence=0.7,
            )

        # Strategy 4: one side is a superset
        ours_set = set(line.strip() for line in hunk.ours_lines)
        theirs_set = set(line.strip() for line in hunk.theirs_lines)
        if ours_set.issuperset(theirs_set):
            return Resolution(
                hunk=hunk, strategy="ours",
                resolved_lines=hunk.ours_lines,
                explanation="Our changes are a superset of theirs",
                confidence=0.65,
            )
        if theirs_set.issuperset(ours_set):
            return Resolution(
                hunk=hunk, strategy="theirs",
                resolved_lines=hunk.theirs_lines,
                explanation="Their changes are a superset of ours",
                confidence=0.65,
            )

        # Cannot auto-resolve
        return Resolution(
            hunk=hunk, strategy="manual",
            resolved_lines=[],
            explanation="Conflicting changes require manual resolution",
            confidence=0.0,
        )

    def _are_independent_additions(self, hunk: ConflictHunk) -> bool:
        """Check if both sides add non-overlapping lines."""
        ours_stripped = {line.strip() for line in hunk.ours_lines if line.strip()}
        theirs_stripped = {line.strip() for line in hunk.theirs_lines if line.strip()}
        # No overlap = independent
        if not ours_stripped.intersection(theirs_stripped):
            # Also check they look like additive content (imports, config lines)
            all_lines = hunk.ours_lines + hunk.theirs_lines
            additive_patterns = (
                re.compile(r"^\s*(import|from|require|include|use)\s"),
                re.compile(r"^\s*[\w-]+\s*[:=]"),
            )
            additive_count = sum(
                1 for line in all_lines
                if any(p.match(line) for p in additive_patterns)
            )
            return additive_count > len(all_lines) * 0.5
        return False
