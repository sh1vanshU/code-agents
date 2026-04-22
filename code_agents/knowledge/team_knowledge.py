"""Team Knowledge Base — shared, git-tracked knowledge store.

Provides a simple topic-based knowledge base stored in ``.code-agents/team-kb/``
as individual Markdown files. Designed to be git-tracked so the whole team
shares the same knowledge.

Usage::

    from code_agents.knowledge.team_knowledge import TeamKnowledgeBase

    kb = TeamKnowledgeBase("/path/to/repo")
    kb.add("deployment", "Always deploy to dev first", author="alice")
    results = kb.search("deploy")
    topics = kb.list_topics()
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.knowledge.team_knowledge")


class TeamKnowledgeBase:
    """Topic-based knowledge base stored as Markdown files in .code-agents/team-kb/."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self.kb_dir = os.path.join(cwd, ".code-agents", "team-kb")
        os.makedirs(self.kb_dir, exist_ok=True)
        logger.debug("TeamKnowledgeBase initialized: %s", self.kb_dir)

    def add(self, topic: str, content: str, author: str = "") -> dict[str, Any]:
        """Add or update a knowledge base entry.

        Args:
            topic: Topic name (used as filename slug).
            content: The knowledge content (Markdown).
            author: Optional author name.

        Returns:
            Dict with topic metadata.
        """
        slug = self._slugify(topic)
        if not slug:
            logger.warning("Invalid topic name: %s", topic)
            return {"error": "Invalid topic name"}

        filepath = os.path.join(self.kb_dir, f"{slug}.md")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        # Build frontmatter + content
        lines = [
            "---",
            f"topic: {topic}",
            f"author: {author or 'unknown'}",
            f"updated: {now}",
            "---",
            "",
            content.strip(),
            "",
        ]
        text = "\n".join(lines)

        is_update = os.path.isfile(filepath)
        Path(filepath).write_text(text, encoding="utf-8")

        action = "Updated" if is_update else "Added"
        logger.info("%s knowledge entry: %s", action, topic)

        return {
            "topic": topic,
            "slug": slug,
            "author": author,
            "updated": now,
            "path": filepath,
            "action": action.lower(),
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search knowledge base entries by keyword.

        Args:
            query: Search query (case-insensitive substring match).

        Returns:
            List of matching entries with topic, content preview, and score.
        """
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        for entry in self._read_all():
            score = 0
            topic_lower = entry["topic"].lower()
            content_lower = entry["content"].lower()

            # Topic match is highest score
            if query_lower in topic_lower:
                score += 10
            if query_lower == topic_lower:
                score += 5

            # Content match
            content_count = content_lower.count(query_lower)
            if content_count > 0:
                score += min(content_count, 5)

            if score > 0:
                entry["score"] = score
                # Add content preview
                entry["preview"] = entry["content"][:200]
                results.append(entry)

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        logger.info("Search '%s': %d results", query, len(results))
        return results

    def list_topics(self) -> list[str]:
        """List all topics in the knowledge base.

        Returns:
            Sorted list of topic names.
        """
        topics: list[str] = []
        for entry in self._read_all():
            topics.append(entry["topic"])
        return sorted(topics)

    def get(self, topic: str) -> dict[str, Any] | None:
        """Get a specific knowledge base entry by topic.

        Args:
            topic: Topic name or slug.

        Returns:
            Entry dict with topic, content, author, updated, path — or None.
        """
        slug = self._slugify(topic)
        filepath = os.path.join(self.kb_dir, f"{slug}.md")

        if not os.path.isfile(filepath):
            # Try fuzzy match
            for entry in self._read_all():
                if entry["topic"].lower() == topic.lower():
                    return entry
            logger.debug("Topic not found: %s", topic)
            return None

        return self._parse_entry(filepath)

    def delete(self, topic: str) -> bool:
        """Delete a knowledge base entry by topic.

        Args:
            topic: Topic name or slug.

        Returns:
            True if deleted, False if not found.
        """
        slug = self._slugify(topic)
        filepath = os.path.join(self.kb_dir, f"{slug}.md")

        if os.path.isfile(filepath):
            os.remove(filepath)
            logger.info("Deleted knowledge entry: %s", topic)
            return True

        # Try fuzzy match
        for entry in self._read_all():
            if entry["topic"].lower() == topic.lower():
                os.remove(entry["path"])
                logger.info("Deleted knowledge entry: %s", topic)
                return True

        logger.debug("Topic not found for deletion: %s", topic)
        return False

    # --- Internal helpers ---

    def _read_all(self) -> list[dict[str, Any]]:
        """Read all knowledge base entries."""
        entries: list[dict[str, Any]] = []
        if not os.path.isdir(self.kb_dir):
            return entries

        for f in sorted(os.listdir(self.kb_dir)):
            if not f.endswith(".md"):
                continue
            filepath = os.path.join(self.kb_dir, f)
            entry = self._parse_entry(filepath)
            if entry:
                entries.append(entry)
        return entries

    def _parse_entry(self, filepath: str) -> dict[str, Any] | None:
        """Parse a knowledge base Markdown file with YAML frontmatter."""
        try:
            text = Path(filepath).read_text(encoding="utf-8")
        except OSError:
            return None

        topic = Path(filepath).stem
        author = ""
        updated = ""
        content = text

        # Parse frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            content = text[fm_match.end():]
            for line in fm.splitlines():
                if line.startswith("topic:"):
                    topic = line.split(":", 1)[1].strip()
                elif line.startswith("author:"):
                    author = line.split(":", 1)[1].strip()
                elif line.startswith("updated:"):
                    updated = line.split(":", 1)[1].strip()

        return {
            "topic": topic,
            "author": author,
            "updated": updated,
            "content": content.strip(),
            "path": filepath,
        }

    def _slugify(self, topic: str) -> str:
        """Convert topic name to a filesystem-safe slug."""
        slug = topic.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug[:80]
