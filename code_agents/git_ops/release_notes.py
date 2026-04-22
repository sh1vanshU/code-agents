"""Release Notes AI — generate release notes from git history."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("code_agents.git_ops.release_notes")

# ── Conventional commit prefixes → categories ────────────────────────────────
_PREFIX_MAP = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Testing",
    "chore": "Maintenance",
    "ci": "CI/CD",
    "build": "Build",
    "style": "Style",
    "revert": "Reverts",
}


@dataclass
class ReleaseNote:
    """A single release note entry."""

    category: str
    description: str
    pr_number: int = 0


class ReleaseNotesGenerator:
    """Generate release notes from git commit history."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    # ── Public API ───────────────────────────────────────────────────────

    def generate(self, from_ref: str, to_ref: str = "HEAD") -> list[ReleaseNote]:
        """Generate release notes between two git refs."""
        changes = self._get_changes(from_ref, to_ref)
        if not changes:
            logger.info("No commits found between %s and %s", from_ref, to_ref)
            return []

        notes: list[ReleaseNote] = []
        for commit in changes:
            msg = commit.get("message", "")
            pr = commit.get("pr_number", 0)
            category = self._categorize(msg)
            description = self._humanize(msg)
            if description:
                notes.append(ReleaseNote(category=category, description=description, pr_number=pr))

        logger.info("Generated %d release notes from %d commits", len(notes), len(changes))
        return notes

    def format_markdown(self, notes: list[ReleaseNote]) -> str:
        """Format release notes as Markdown."""
        if not notes:
            return "# Release Notes\n\nNo changes in this release.\n"

        lines: list[str] = [f"# Release Notes", f"", f"*Generated on {datetime.now().strftime('%Y-%m-%d')}*", ""]

        by_category: dict[str, list[ReleaseNote]] = {}
        for n in notes:
            by_category.setdefault(n.category, []).append(n)

        # Order: Features first, Bug Fixes second, then alphabetical
        priority = ["Features", "Bug Fixes", "Performance"]
        ordered = [c for c in priority if c in by_category]
        ordered.extend(sorted(c for c in by_category if c not in priority))

        for cat in ordered:
            lines.append(f"## {cat}")
            lines.append("")
            for n in by_category[cat]:
                pr_ref = f" (#{n.pr_number})" if n.pr_number else ""
                lines.append(f"- {n.description}{pr_ref}")
            lines.append("")

        return "\n".join(lines)

    def format_slack(self, notes: list[ReleaseNote]) -> str:
        """Format release notes as a Slack-friendly announcement."""
        if not notes:
            return ":package: *Release Notes*\n\nNo changes in this release."

        lines: list[str] = [":package: *Release Notes*", ""]

        by_category: dict[str, list[ReleaseNote]] = {}
        for n in notes:
            by_category.setdefault(n.category, []).append(n)

        emoji_map = {
            "Features": ":sparkles:",
            "Bug Fixes": ":bug:",
            "Performance": ":zap:",
            "Refactoring": ":recycle:",
            "Documentation": ":books:",
            "Testing": ":white_check_mark:",
            "Maintenance": ":wrench:",
            "CI/CD": ":gear:",
        }

        priority = ["Features", "Bug Fixes", "Performance"]
        ordered = [c for c in priority if c in by_category]
        ordered.extend(sorted(c for c in by_category if c not in priority))

        for cat in ordered:
            emoji = emoji_map.get(cat, ":pushpin:")
            lines.append(f"{emoji} *{cat}*")
            for n in by_category[cat]:
                pr_ref = f" (<#{n.pr_number}>)" if n.pr_number else ""
                lines.append(f"  - {n.description}{pr_ref}")
            lines.append("")

        lines.append(f"_Generated on {datetime.now().strftime('%Y-%m-%d')}_")
        return "\n".join(lines)

    # ── Git helpers ──────────────────────────────────────────────────────

    def _get_changes(self, from_ref: str, to_ref: str) -> list[dict]:
        """Get commit log between two refs."""
        try:
            result = subprocess.run(
                [
                    "git", "log", f"{from_ref}..{to_ref}",
                    "--pretty=format:%H|%s|%an|%ai",
                    "--no-merges",
                ],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git log failed: %s", result.stderr.strip())
                return []

            commits: list[dict] = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) < 2:
                    continue
                sha = parts[0]
                message = parts[1]
                author = parts[2] if len(parts) > 2 else ""
                date = parts[3] if len(parts) > 3 else ""

                # Extract PR number from message like "(#123)"
                pr_match = re.search(r"\(#(\d+)\)", message)
                pr_number = int(pr_match.group(1)) if pr_match else 0

                commits.append({
                    "sha": sha,
                    "message": message,
                    "author": author,
                    "date": date,
                    "pr_number": pr_number,
                })
            return commits
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get git changes: %s", exc)
            return []

    # ── Text processing ──────────────────────────────────────────────────

    def _categorize(self, commit_msg: str) -> str:
        """Categorize a commit message based on conventional commit prefix."""
        msg_lower = commit_msg.lower().strip()
        for prefix, category in _PREFIX_MAP.items():
            if msg_lower.startswith(prefix + ":") or msg_lower.startswith(prefix + "("):
                return category
        # Heuristic fallback
        if "fix" in msg_lower or "bug" in msg_lower:
            return "Bug Fixes"
        if "add" in msg_lower or "new" in msg_lower or "implement" in msg_lower:
            return "Features"
        if "update" in msg_lower or "upgrade" in msg_lower:
            return "Maintenance"
        return "Other"

    def _humanize(self, commit_msg: str) -> str:
        """Convert conventional commit message to human-readable description.

        "feat: add X" → "Added X"
        "fix(auth): resolve token expiry" → "Resolved token expiry"
        """
        msg = commit_msg.strip()

        # Strip conventional commit prefix: "type(scope): message" or "type: message"
        match = re.match(r"^[a-z]+(?:\([^)]*\))?\s*:\s*(.+)", msg, re.IGNORECASE)
        if match:
            msg = match.group(1).strip()

        # Strip trailing PR ref like "(#123)"
        msg = re.sub(r"\s*\(#\d+\)\s*$", "", msg)

        if not msg:
            return ""

        # Capitalize first letter and apply light past-tense transformation
        msg = msg[0].upper() + msg[1:]

        # Simple present -> past tense for common verbs at start
        _past_map = {
            "Add ": "Added ", "Fix ": "Fixed ", "Update ": "Updated ",
            "Remove ": "Removed ", "Implement ": "Implemented ",
            "Refactor ": "Refactored ", "Improve ": "Improved ",
            "Enable ": "Enabled ", "Disable ": "Disabled ",
            "Migrate ": "Migrated ", "Upgrade ": "Upgraded ",
            "Resolve ": "Resolved ", "Move ": "Moved ", "Rename ": "Renamed ",
            "Create ": "Created ", "Delete ": "Deleted ",
        }
        for present, past in _past_map.items():
            if msg.startswith(present):
                msg = past + msg[len(present):]
                break

        return msg
