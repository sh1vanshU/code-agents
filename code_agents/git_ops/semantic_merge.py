"""Semantic merge — understand intent of both branches to resolve conflicts.

Goes beyond textual diff to understand the purpose of changes on each
branch and propose semantically correct conflict resolutions.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.git_ops.semantic_merge")


@dataclass
class ConflictRegion:
    """A single conflict region in a file."""

    file: str = ""
    start_line: int = 0
    end_line: int = 0
    ours: str = ""
    theirs: str = ""
    base: str = ""
    resolved: str = ""
    resolution_strategy: str = ""  # ours | theirs | combine | rewrite
    confidence: float = 0.0


@dataclass
class BranchIntent:
    """Inferred intent of changes on a branch."""

    branch: str = ""
    description: str = ""
    change_type: str = ""  # feature | bugfix | refactor | config
    files_changed: list[str] = field(default_factory=list)
    key_patterns: list[str] = field(default_factory=list)


@dataclass
class SemanticMergeResult:
    """Result of semantic merge analysis."""

    conflicts: list[ConflictRegion] = field(default_factory=list)
    ours_intent: BranchIntent = field(default_factory=BranchIntent)
    theirs_intent: BranchIntent = field(default_factory=BranchIntent)
    auto_resolved: int = 0
    manual_needed: int = 0
    merged_content: dict[str, str] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=dict)


# Conflict marker patterns
CONFLICT_START = re.compile(r"^<<<<<<<\s+(.*)", re.MULTILINE)
CONFLICT_MID = re.compile(r"^=======", re.MULTILINE)
CONFLICT_END = re.compile(r"^>>>>>>>\s+(.*)", re.MULTILINE)
CONFLICT_BASE = re.compile(r"^\|\|\|\|\|\|\|\s+(.*)", re.MULTILINE)


class SemanticMerger:
    """Resolve merge conflicts using semantic understanding."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("SemanticMerger initialized for %s", cwd)

    def analyze(
        self,
        ours_branch: str = "HEAD",
        theirs_branch: str = "main",
        files: list[str] | None = None,
    ) -> SemanticMergeResult:
        """Analyze merge conflicts between two branches.

        Args:
            ours_branch: Our branch ref.
            theirs_branch: Their branch ref.
            files: Specific files to analyze. None = all conflicted files.

        Returns:
            SemanticMergeResult with conflict analysis and resolutions.
        """
        result = SemanticMergeResult()

        # Analyze branch intents
        result.ours_intent = self._analyze_branch_intent(ours_branch, theirs_branch)
        result.theirs_intent = self._analyze_branch_intent(theirs_branch, ours_branch)

        # Find conflicted files
        conflict_files = files or self._find_conflict_files()
        logger.info("Analyzing %d conflicted files", len(conflict_files))

        for fpath in conflict_files:
            full_path = os.path.join(self.cwd, fpath) if not os.path.isabs(fpath) else fpath
            if not os.path.exists(full_path):
                continue

            try:
                content = Path(full_path).read_text(errors="replace")
            except OSError:
                continue

            rel = os.path.relpath(full_path, self.cwd)
            conflicts = self._parse_conflicts(content, rel)

            for conflict in conflicts:
                resolution = self._resolve_conflict(
                    conflict, result.ours_intent, result.theirs_intent,
                )
                conflict.resolved = resolution["content"]
                conflict.resolution_strategy = resolution["strategy"]
                conflict.confidence = resolution["confidence"]

                if conflict.confidence >= 0.8:
                    result.auto_resolved += 1
                else:
                    result.manual_needed += 1

            result.conflicts.extend(conflicts)

            # Build merged content
            if conflicts:
                result.merged_content[rel] = self._apply_resolutions(content, conflicts)

        result.summary = {
            "total_conflicts": len(result.conflicts),
            "auto_resolved": result.auto_resolved,
            "manual_needed": result.manual_needed,
            "files_affected": len(conflict_files),
        }
        logger.info(
            "Merge analysis: %d conflicts, %d auto-resolved",
            len(result.conflicts), result.auto_resolved,
        )
        return result

    def _run_git(self, *args: str) -> str:
        """Run a git command and return stdout."""
        try:
            proc = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return proc.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Git command failed: %s", exc)
            return ""

    def _find_conflict_files(self) -> list[str]:
        """Find files with merge conflicts."""
        output = self._run_git("diff", "--name-only", "--diff-filter=U")
        if not output:
            return []
        return [f.strip() for f in output.splitlines() if f.strip()]

    def _analyze_branch_intent(self, branch: str, base: str) -> BranchIntent:
        """Infer the intent of changes on a branch."""
        intent = BranchIntent(branch=branch)

        # Get commit messages
        log = self._run_git("log", "--oneline", f"{base}..{branch}", "--max-count=20")
        if log:
            messages = log.splitlines()
            intent.description = "; ".join(messages[:5])

            # Classify change type
            all_msgs = " ".join(messages).lower()
            if any(kw in all_msgs for kw in ("fix", "bug", "patch", "hotfix")):
                intent.change_type = "bugfix"
            elif any(kw in all_msgs for kw in ("refactor", "cleanup", "rename")):
                intent.change_type = "refactor"
            elif any(kw in all_msgs for kw in ("config", "env", "setting")):
                intent.change_type = "config"
            else:
                intent.change_type = "feature"

        # Get changed files
        diff_files = self._run_git("diff", "--name-only", f"{base}..{branch}")
        if diff_files:
            intent.files_changed = diff_files.splitlines()[:50]

        return intent

    def _parse_conflicts(self, content: str, rel_path: str) -> list[ConflictRegion]:
        """Parse conflict markers from file content."""
        conflicts: list[ConflictRegion] = []
        lines = content.splitlines(keepends=True)
        i = 0

        while i < len(lines):
            start_match = CONFLICT_START.match(lines[i])
            if not start_match:
                i += 1
                continue

            start_line = i + 1
            ours_lines: list[str] = []
            theirs_lines: list[str] = []
            section = "ours"
            j = i + 1

            while j < len(lines):
                if CONFLICT_MID.match(lines[j]):
                    section = "theirs"
                    j += 1
                    continue
                end_match = CONFLICT_END.match(lines[j])
                if end_match:
                    conflicts.append(ConflictRegion(
                        file=rel_path,
                        start_line=start_line,
                        end_line=j + 1,
                        ours="".join(ours_lines),
                        theirs="".join(theirs_lines),
                    ))
                    i = j + 1
                    break
                if section == "ours":
                    ours_lines.append(lines[j])
                else:
                    theirs_lines.append(lines[j])
                j += 1
            else:
                i += 1

        return conflicts

    def _resolve_conflict(
        self,
        conflict: ConflictRegion,
        ours_intent: BranchIntent,
        theirs_intent: BranchIntent,
    ) -> dict:
        """Resolve a single conflict region."""
        ours = conflict.ours.strip()
        theirs = conflict.theirs.strip()

        # Identical content — trivial resolution
        if ours == theirs:
            return {"content": ours, "strategy": "identical", "confidence": 1.0}

        # One side is empty — take the non-empty side
        if not ours:
            return {"content": theirs, "strategy": "theirs", "confidence": 0.9}
        if not theirs:
            return {"content": ours, "strategy": "ours", "confidence": 0.9}

        # Non-overlapping additions (both add different things)
        ours_lines = set(ours.splitlines())
        theirs_lines = set(theirs.splitlines())
        if not ours_lines & theirs_lines:
            combined = conflict.ours.rstrip("\n") + "\n" + conflict.theirs
            return {"content": combined, "strategy": "combine", "confidence": 0.7}

        # Bugfix takes priority over feature
        if ours_intent.change_type == "bugfix" and theirs_intent.change_type != "bugfix":
            return {"content": ours, "strategy": "ours", "confidence": 0.6}
        if theirs_intent.change_type == "bugfix" and ours_intent.change_type != "bugfix":
            return {"content": theirs, "strategy": "theirs", "confidence": 0.6}

        # Default: take theirs (main branch) with low confidence
        return {"content": theirs, "strategy": "theirs", "confidence": 0.4}

    def _apply_resolutions(
        self, content: str, conflicts: list[ConflictRegion],
    ) -> str:
        """Apply resolved conflicts back to file content."""
        lines = content.splitlines(keepends=True)
        result_lines: list[str] = []
        skip_until = -1

        for i, line in enumerate(lines):
            if i < skip_until:
                continue

            # Check if this line starts a conflict we resolved
            conflict = None
            for c in conflicts:
                if c.start_line == i + 1:
                    conflict = c
                    break

            if conflict and conflict.resolved:
                result_lines.append(conflict.resolved)
                if not conflict.resolved.endswith("\n"):
                    result_lines.append("\n")
                skip_until = conflict.end_line
            elif i >= skip_until:
                result_lines.append(line)

        return "".join(result_lines)


def semantic_merge(
    cwd: str,
    ours_branch: str = "HEAD",
    theirs_branch: str = "main",
    files: list[str] | None = None,
) -> dict:
    """Convenience function for semantic merge analysis.

    Returns:
        Dict with conflicts, resolutions, and summary.
    """
    merger = SemanticMerger(cwd)
    result = merger.analyze(ours_branch=ours_branch, theirs_branch=theirs_branch, files=files)
    return {
        "conflicts": [
            {"file": c.file, "start_line": c.start_line, "end_line": c.end_line,
             "strategy": c.resolution_strategy, "confidence": c.confidence}
            for c in result.conflicts
        ],
        "ours_intent": {"branch": result.ours_intent.branch,
                        "change_type": result.ours_intent.change_type,
                        "description": result.ours_intent.description},
        "theirs_intent": {"branch": result.theirs_intent.branch,
                          "change_type": result.theirs_intent.change_type,
                          "description": result.theirs_intent.description},
        "merged_content": result.merged_content,
        "summary": result.summary,
    }
