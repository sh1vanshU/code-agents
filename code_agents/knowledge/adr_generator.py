"""ADR (Architecture Decision Record) generator.

Generates, lists, and saves ADRs in a standardized markdown format.
Supports docs/adr/ and docs/decisions/ directory conventions.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.adr_generator")

# Valid ADR statuses
VALID_STATUSES = ("proposed", "accepted", "deprecated")

# Default ADR directory
DEFAULT_ADR_DIR = "docs/decisions"


@dataclass
class ADR:
    """An Architecture Decision Record."""

    id: int
    title: str
    date: str
    status: str  # "proposed" | "accepted" | "deprecated"
    context: str
    decision: str
    alternatives: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid ADR status '{self.status}'. "
                f"Must be one of: {', '.join(VALID_STATUSES)}"
            )


class ADRGenerator:
    """Generate, list, and manage Architecture Decision Records."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._adr_dir: str | None = None
        logger.debug("ADRGenerator initialized for %s", cwd)

    @property
    def adr_dir(self) -> str:
        """Return the ADR directory path, detecting existing or using default."""
        if self._adr_dir is not None:
            return self._adr_dir

        # Check for existing ADR directories
        candidates = [
            os.path.join(self.cwd, "docs", "adr"),
            os.path.join(self.cwd, "docs", "decisions"),
            os.path.join(self.cwd, "doc", "adr"),
            os.path.join(self.cwd, "doc", "decisions"),
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                self._adr_dir = candidate
                logger.debug("Found existing ADR directory: %s", candidate)
                return self._adr_dir

        # Default
        self._adr_dir = os.path.join(self.cwd, DEFAULT_ADR_DIR)
        logger.debug("Using default ADR directory: %s", self._adr_dir)
        return self._adr_dir

    def generate(
        self,
        decision: str,
        context: str = "",
        alternatives: str = "",
        status: str = "proposed",
    ) -> ADR:
        """Generate a new ADR from the given parameters.

        Args:
            decision: The decision being recorded.
            context: Background context for the decision.
            alternatives: Comma-separated alternative options considered.
            status: ADR status (proposed, accepted, deprecated).

        Returns:
            A new ADR instance.
        """
        next_id = self._next_id()
        title = self._title_from_decision(decision)
        date = datetime.now().strftime("%Y-%m-%d")

        alt_list = [
            a.strip() for a in alternatives.split(",") if a.strip()
        ] if alternatives else []

        consequences = self._infer_consequences(decision, alt_list)

        adr = ADR(
            id=next_id,
            title=title,
            date=date,
            status=status,
            context=context or f"A decision is needed regarding: {decision}",
            decision=decision,
            alternatives=alt_list,
            consequences=consequences,
        )

        logger.info("Generated ADR-%04d: %s", adr.id, adr.title)
        return adr

    def list_adrs(self) -> list[dict]:
        """List all existing ADRs found in the ADR directory.

        Returns:
            List of dicts with id, title, status, date, and file path.
        """
        results: list[dict] = []
        adr_dir = self.adr_dir

        if not os.path.isdir(adr_dir):
            logger.debug("ADR directory does not exist: %s", adr_dir)
            return results

        for fname in sorted(os.listdir(adr_dir)):
            if not fname.endswith(".md"):
                continue

            fpath = os.path.join(adr_dir, fname)
            entry = self._parse_adr_file(fpath, fname)
            if entry:
                results.append(entry)

        logger.info("Found %d ADRs in %s", len(results), adr_dir)
        return results

    def _parse_adr_file(self, fpath: str, fname: str) -> dict | None:
        """Parse an ADR markdown file to extract metadata."""
        try:
            with open(fpath) as f:
                content = f.read()
        except OSError:
            logger.warning("Could not read ADR file: %s", fpath)
            return None

        # Extract ID from filename first, then from content
        id_match = re.search(r"(\d+)", fname)
        adr_id = int(id_match.group(1)) if id_match else 0

        if adr_id == 0:
            # Try to extract from content (e.g. "ADR-0001" in heading)
            content_id_match = re.search(r"ADR[-\s]*(\d+)", content)
            if content_id_match:
                adr_id = int(content_id_match.group(1))

        # Extract title from first heading
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else fname

        # Clean ADR prefix from title
        title = re.sub(r"^ADR[-\s]*\d+[:\s]*", "", title).strip() or title

        # Extract status
        status_match = re.search(
            r"\*\*Status\*\*:\s*(\w+)", content, re.IGNORECASE
        )
        if not status_match:
            status_match = re.search(
                r"Status:\s*(\w+)", content, re.IGNORECASE
            )
        status = status_match.group(1).lower() if status_match else "unknown"

        # Extract date
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", content)
        date = date_match.group(0) if date_match else ""

        return {
            "id": adr_id,
            "title": title,
            "status": status,
            "date": date,
            "file": fpath,
        }

    def _next_id(self) -> int:
        """Determine the next ADR ID by scanning existing files."""
        existing = self.list_adrs()
        if not existing:
            return 1

        max_id = max(entry["id"] for entry in existing)
        return max_id + 1

    def _title_from_decision(self, decision: str) -> str:
        """Generate a short title from a decision string."""
        # Take first sentence or first 80 chars
        title = decision.split(".")[0].strip()
        if len(title) > 80:
            title = title[:77] + "..."
        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]
        return title

    def _infer_consequences(
        self, decision: str, alternatives: list[str]
    ) -> list[str]:
        """Infer basic consequences from the decision."""
        consequences = [
            f"Team adopts: {decision.split('.')[0].strip().lower()}",
        ]
        if alternatives:
            consequences.append(
                f"Alternatives ({', '.join(alternatives)}) are not pursued"
            )
        consequences.append("This decision should be revisited if context changes")
        return consequences

    def _template(self, adr: ADR) -> str:
        """Render an ADR as a markdown document."""
        lines = [
            f"# ADR-{adr.id:04d}: {adr.title}",
            "",
            f"**Date**: {adr.date}",
            f"**Status**: {adr.status}",
            "",
            "## Context",
            "",
            adr.context,
            "",
            "## Decision",
            "",
            adr.decision,
            "",
        ]

        if adr.alternatives:
            lines.extend([
                "## Alternatives Considered",
                "",
            ])
            for alt in adr.alternatives:
                lines.append(f"- {alt}")
            lines.append("")

        lines.extend([
            "## Consequences",
            "",
        ])
        for con in adr.consequences:
            lines.append(f"- {con}")
        lines.append("")

        return "\n".join(lines)

    def save(self, adr: ADR) -> str:
        """Save an ADR to the decisions directory.

        Args:
            adr: The ADR to save.

        Returns:
            The file path of the saved ADR.
        """
        adr_dir = self.adr_dir
        os.makedirs(adr_dir, exist_ok=True)

        # Sanitize title for filename
        safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", adr.title).strip("_").lower()
        if len(safe_title) > 60:
            safe_title = safe_title[:60].rstrip("_")

        filename = f"DECISION_{safe_title}.md"
        filepath = os.path.join(adr_dir, filename)

        content = self._template(adr)
        with open(filepath, "w") as f:
            f.write(content)

        logger.info("Saved ADR to %s", filepath)
        return filepath


def format_adr_table(adrs: list[dict]) -> str:
    """Format a list of ADRs as a terminal-friendly table."""
    if not adrs:
        return "  No ADRs found."

    lines = [
        "",
        f"  {'ID':<6} {'Status':<12} {'Date':<12} {'Title'}",
        f"  {'─' * 6} {'─' * 12} {'─' * 12} {'─' * 40}",
    ]
    for entry in adrs:
        lines.append(
            f"  {entry['id']:<6} {entry['status']:<12} "
            f"{entry.get('date', ''):<12} {entry['title']}"
        )
    lines.append("")
    return "\n".join(lines)
