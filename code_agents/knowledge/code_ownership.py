"""Code Ownership Map — analyze git blame to identify owners and knowledge silos.

Uses git blame statistics to determine primary owners, contributors,
and bus factor for each path. Can generate CODEOWNERS file content.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.code_ownership")

# File patterns to skip in ownership analysis
_SKIP_PATTERNS = re.compile(
    r"(\.lock$|\.min\.(js|css)$|package-lock\.json|yarn\.lock|"
    r"\.svg$|\.png$|\.jpg$|\.ico$|\.woff|\.ttf|\.eot|"
    r"node_modules/|\.git/|__pycache__/|\.pyc$|dist/|build/|\.egg-info/)",
    re.IGNORECASE,
)


@dataclass
class OwnershipInfo:
    """Ownership information for a file or directory."""

    path: str
    primary_owner: str
    contributors: list[str] = field(default_factory=list)
    bus_factor: int = 0


class CodeOwnershipMapper:
    """Analyze code ownership via git blame statistics."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CodeOwnershipMapper initialized, cwd=%s", cwd)

    def analyze(self) -> list[OwnershipInfo]:
        """Analyze ownership across the entire repository.

        Returns:
            List of OwnershipInfo for each top-level directory and key files.
        """
        logger.info("Analyzing code ownership in %s", self.cwd)
        tracked = self._get_tracked_files()
        if not tracked:
            logger.warning("No tracked files found")
            return []

        # Group files by top-level directory
        dir_stats: dict[str, Counter] = defaultdict(Counter)
        file_results: list[OwnershipInfo] = []

        for fpath in tracked:
            if _SKIP_PATTERNS.search(fpath):
                continue

            blame = self._git_blame_stats(fpath)
            if not blame:
                continue

            # Aggregate into directory stats
            parts = fpath.split("/")
            dir_key = parts[0] if len(parts) > 1 else "."
            for author, count in blame.items():
                dir_stats[dir_key][author] += count

        # Build ownership info per directory
        results: list[OwnershipInfo] = []
        for dir_path in sorted(dir_stats.keys()):
            stats = dir_stats[dir_path]
            info = self._stats_to_ownership(dir_path, stats)
            results.append(info)

        logger.info("Analyzed %d directories", len(results))
        return results

    def generate_codeowners(self) -> str:
        """Generate CODEOWNERS file content from git blame analysis.

        Returns:
            String content suitable for a CODEOWNERS file.
        """
        logger.info("Generating CODEOWNERS content")
        ownership = self.analyze()

        lines = [
            "# CODEOWNERS — auto-generated from git blame analysis",
            "# Review and adjust before committing",
            "",
        ]

        for info in ownership:
            if info.primary_owner:
                path_pattern = f"/{info.path}/" if info.path != "." else "*"
                owner = self._format_owner(info.primary_owner)
                comment_parts = [f"bus_factor={info.bus_factor}"]
                if info.contributors:
                    comment_parts.append(f"contributors={len(info.contributors)}")
                comment = "  # " + ", ".join(comment_parts)
                lines.append(f"{path_pattern:<40} {owner}{comment}")

        content = "\n".join(lines) + "\n"
        logger.debug("Generated CODEOWNERS with %d entries", len(ownership))
        return content

    def _git_blame_stats(self, path: str) -> dict[str, int]:
        """Get author line counts from git blame for a file.

        Args:
            path: Relative file path within the repo.

        Returns:
            Dictionary mapping author name to line count.
        """
        try:
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", path],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            if result.returncode != 0:
                return {}
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("git blame failed for %s: %s", path, exc)
            return {}

        author_counts: Counter = Counter()
        for line in result.stdout.splitlines():
            if line.startswith("author "):
                author = line[7:].strip()
                if author and author != "Not Committed Yet":
                    author_counts[author] += 1

        return dict(author_counts)

    def _get_tracked_files(self) -> list[str]:
        """Get list of git-tracked files."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            return [f for f in result.stdout.strip().splitlines() if f]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("git ls-files failed: %s", exc)
            return []

    def _find_knowledge_silos(self) -> list[str]:
        """Find directories where bus_factor is 1 (knowledge silos).

        Returns:
            List of directory paths that are knowledge silos.
        """
        ownership = self.analyze()
        silos = [info.path for info in ownership if info.bus_factor == 1]
        if silos:
            logger.warning("Knowledge silos found: %s", silos)
        return silos

    @staticmethod
    def _stats_to_ownership(path: str, stats: Counter) -> OwnershipInfo:
        """Convert author statistics to OwnershipInfo.

        Args:
            path: The directory/file path.
            stats: Counter of author → line count.

        Returns:
            OwnershipInfo with primary owner, contributors, and bus factor.
        """
        if not stats:
            return OwnershipInfo(path=path, primary_owner="", contributors=[], bus_factor=0)

        total = sum(stats.values())
        sorted_authors = stats.most_common()
        primary = sorted_authors[0][0]

        # Contributors: anyone with >= 5% of lines
        contributors = [
            author for author, count in sorted_authors
            if count / total >= 0.05
        ]

        # Bus factor: number of people who collectively own >= 50% of the code
        bus_factor = 0
        cumulative = 0
        for _, count in sorted_authors:
            cumulative += count
            bus_factor += 1
            if cumulative / total >= 0.50:
                break

        return OwnershipInfo(
            path=path,
            primary_owner=primary,
            contributors=contributors,
            bus_factor=bus_factor,
        )

    @staticmethod
    def _format_owner(name: str) -> str:
        """Format an author name for CODEOWNERS.

        Converts 'First Last' to '@first-last' style.
        """
        formatted = name.lower().replace(" ", "-")
        formatted = re.sub(r"[^\w\-]", "", formatted)
        return f"@{formatted}" if formatted else "@unknown"
