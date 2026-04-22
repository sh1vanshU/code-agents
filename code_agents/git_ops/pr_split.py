"""PR Size Optimizer — split large diffs into reviewable PR groups."""

from __future__ import annotations

import logging
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.git_ops.pr_split")

# ── Risk keywords ────────────────────────────────────────────────────────────
_HIGH_RISK_PATTERNS = {"migration", "schema", "deploy", "config", "secret", "auth", "security"}
_MEDIUM_RISK_PATTERNS = {"test", "spec", "fixture", "mock"}


@dataclass
class SplitGroup:
    """A logical group of files that should go in the same PR."""

    name: str
    files: list[str]
    description: str
    risk: str  # "low" | "medium" | "high"
    estimated_review_min: int = 0


class PRSplitter:
    """Analyze a branch diff and suggest how to split it into smaller PRs."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    # ── Public API ───────────────────────────────────────────────────────

    def analyze(self, base: str = "main") -> list[SplitGroup]:
        """Analyze changed files and return suggested PR splits.

        Tries grouping by independence first; falls back to directory grouping
        if independence detection yields too few groups.
        """
        files = self._get_changed_files(base)
        if not files:
            logger.info("No changed files detected against base=%s", base)
            return []

        groups = self._group_by_independence(files)
        if len(groups) <= 1:
            groups = self._group_by_directory(files)

        # Estimate review time for each group
        for group in groups:
            group.estimated_review_min = self._estimate_review_time(group.files)

        logger.info(
            "Split %d files into %d groups (base=%s)", len(files), len(groups), base
        )
        return groups

    # ── Git helpers ──────────────────────────────────────────────────────

    def _get_changed_files(self, base: str) -> list[str]:
        """Return list of changed file paths relative to *base*."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git diff failed: %s", result.stderr.strip())
                return []
            return [f for f in result.stdout.strip().splitlines() if f]
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get changed files: %s", exc)
            return []

    def _get_diff_stat(self, files: list[str]) -> int:
        """Return total lines changed (additions + deletions) for *files*."""
        if not files:
            return 0
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "--", *files],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            total = 0
            for line in result.stdout.strip().splitlines():
                # e.g. " file.py | 10 ++++----"
                parts = line.split("|")
                if len(parts) == 2:
                    num = parts[1].strip().split()[0] if parts[1].strip() else "0"
                    if num.isdigit():
                        total += int(num)
            return total
        except Exception:  # noqa: BLE001
            return len(files) * 30  # rough fallback

    # ── Grouping strategies ──────────────────────────────────────────────

    def _group_by_directory(self, files: list[str]) -> list[SplitGroup]:
        """Group files by their top-level directory."""
        buckets: dict[str, list[str]] = defaultdict(list)
        for f in files:
            parts = Path(f).parts
            key = parts[0] if len(parts) > 1 else "(root)"
            buckets[key].append(f)

        groups: list[SplitGroup] = []
        for dirname, group_files in sorted(buckets.items()):
            risk = self._assess_risk(group_files)
            groups.append(
                SplitGroup(
                    name=f"{dirname}/",
                    files=sorted(group_files),
                    description=f"Changes in {dirname}/ ({len(group_files)} files)",
                    risk=risk,
                )
            )
        return groups

    def _group_by_independence(self, files: list[str]) -> list[SplitGroup]:
        """Group files that share no cross-imports into separate groups.

        Simple heuristic: files that import each other belong together.
        """
        # Build adjacency: which files reference which others
        basename_to_path: dict[str, str] = {}
        for f in files:
            stem = Path(f).stem
            basename_to_path[stem] = f

        adjacency: dict[str, set[str]] = defaultdict(set)
        for f in files:
            full = os.path.join(self.cwd, f)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, "r", errors="replace") as fh:
                    content = fh.read(8192)  # first 8KB
            except OSError:
                continue
            for stem, path in basename_to_path.items():
                if path == f:
                    continue
                if stem in content:
                    adjacency[f].add(path)
                    adjacency[path].add(f)

        # Union-find to cluster connected components
        parent: dict[str, str] = {f: f for f in files}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for f, neighbours in adjacency.items():
            for n in neighbours:
                union(f, n)

        clusters: dict[str, list[str]] = defaultdict(list)
        for f in files:
            clusters[find(f)].append(f)

        groups: list[SplitGroup] = []
        for idx, (_, cluster_files) in enumerate(sorted(clusters.items()), 1):
            risk = self._assess_risk(cluster_files)
            groups.append(
                SplitGroup(
                    name=f"group-{idx}",
                    files=sorted(cluster_files),
                    description=f"Independent change set ({len(cluster_files)} files)",
                    risk=risk,
                )
            )
        return groups

    # ── Estimation & risk ────────────────────────────────────────────────

    def _estimate_review_time(self, files: list[str]) -> int:
        """Estimate review time in minutes based on diff size."""
        total_lines = self._get_diff_stat(files)
        # ~50 lines/min for easy code, slower for complex
        minutes = max(1, total_lines // 40)
        return minutes

    def _assess_risk(self, files: list[str]) -> str:
        """Assess risk level for a group of files."""
        lower_paths = " ".join(f.lower() for f in files)
        if any(p in lower_paths for p in _HIGH_RISK_PATTERNS):
            return "high"
        if any(p in lower_paths for p in _MEDIUM_RISK_PATTERNS):
            return "medium"
        return "low"


# ── Formatting helpers ───────────────────────────────────────────────────────


def format_split_report(groups: list[SplitGroup]) -> str:
    """Return a human-readable report of the suggested PR split."""
    if not groups:
        return "  No changes detected — nothing to split."

    risk_icon = {"low": ".", "medium": "~", "high": "!"}
    lines: list[str] = ["", "  PR Split Suggestions", "  " + "-" * 50]
    total_files = sum(len(g.files) for g in groups)
    total_time = sum(g.estimated_review_min for g in groups)

    for i, g in enumerate(groups, 1):
        icon = risk_icon.get(g.risk, "?")
        lines.append(f"  [{icon}] PR {i}: {g.name}")
        lines.append(f"      {g.description}")
        lines.append(f"      Risk: {g.risk}  |  Est. review: ~{g.estimated_review_min} min")
        for f in g.files[:10]:
            lines.append(f"        - {f}")
        if len(g.files) > 10:
            lines.append(f"        ... and {len(g.files) - 10} more")
        lines.append("")

    lines.append(f"  Total: {len(groups)} PRs, {total_files} files, ~{total_time} min review")
    lines.append("")
    return "\n".join(lines)
