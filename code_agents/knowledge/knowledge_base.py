"""Knowledge Base — searchable team knowledge from chat history, code, and docs."""

import logging
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("code_agents.knowledge.knowledge_base")

KB_INDEX_PATH = Path.home() / ".code-agents" / "kb_index.json"


@dataclass
class KBEntry:
    title: str
    source: str  # "chat", "code-comment", "doc", "agent-memory", "manual"
    file: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: str = ""
    relevance: float = 0.0


class KnowledgeBase:
    def __init__(self, cwd: str):
        self.cwd = cwd
        self.entries: list[KBEntry] = []
        self._load_index()

    def _load_index(self):
        """Load cached index if exists."""
        if KB_INDEX_PATH.exists():
            try:
                with open(KB_INDEX_PATH) as f:
                    data = json.load(f)
                self.entries = [KBEntry(**e) for e in data.get("entries", [])]
                logger.info("KB loaded: %d entries", len(self.entries))
            except Exception as e:
                logger.debug("KB operation failed: %s", e)
                self.entries = []

    def _save_index(self):
        """Save index to cache."""
        KB_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [vars(e) for e in self.entries],
            "updated": datetime.now().isoformat(),
        }
        with open(KB_INDEX_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def rebuild_index(self):
        """Rebuild the KB index from all sources."""
        self.entries = []
        self._index_chat_history()
        self._index_code_comments()
        self._index_docs()
        self._index_agent_memory()
        self._save_index()
        return len(self.entries)

    def _index_chat_history(self):
        """Index chat sessions for knowledge."""
        history_dir = Path.home() / ".code-agents" / "chat_history"
        if not history_dir.exists():
            return
        for f in history_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    session = json.load(fp)
                messages = session.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if len(content) > 100:  # meaningful response
                            title = content.split("\n")[0][:100]
                            self.entries.append(KBEntry(
                                title=title,
                                source="chat",
                                file=str(f.name),
                                content=content[:500],
                                tags=self._extract_tags(content),
                                timestamp=session.get("updated", ""),
                            ))
            except Exception as e:
                logger.debug("KB operation failed: %s", e)

    def _index_code_comments(self):
        """Index meaningful code comments (TODO, FIXME, NOTE, HACK, etc.)."""
        skip = {".git", "node_modules", "__pycache__", "venv", ".venv", "target", "build"}
        patterns = [
            (r'#\s*(TODO|FIXME|NOTE|HACK|BUG|XXX|REVIEW)[\s:]+(.+)', "python"),
            (r'//\s*(TODO|FIXME|NOTE|HACK|BUG|XXX|REVIEW)[\s:]+(.+)', "java/js"),
            (r'/\*\*?\s*(TODO|FIXME|NOTE|HACK|BUG|XXX|REVIEW)[\s:]+(.+)', "block"),
        ]
        exts = (".py", ".java", ".js", ".ts", ".go", ".kt", ".scala", ".rb")

        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                if not f.endswith(exts):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath, errors="replace") as fp:
                        for i, line in enumerate(fp, 1):
                            for pattern, _ in patterns:
                                match = re.search(pattern, line)
                                if match:
                                    tag = match.group(1)
                                    text = match.group(2).strip()
                                    self.entries.append(KBEntry(
                                        title=f"[{tag}] {text}",
                                        source="code-comment",
                                        file=f"{rel}:{i}",
                                        content=text,
                                        tags=[tag.lower(), os.path.splitext(f)[1].lstrip(".")],
                                    ))
                except Exception as e:
                    logger.debug("KB operation failed: %s", e)

    def _index_docs(self):
        """Index markdown docs in the repo."""
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules"}]
            for f in files:
                if not f.endswith((".md", ".rst", ".txt")):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    with open(fpath, errors="replace") as fp:
                        content = fp.read()
                    for match in re.finditer(r'^#+\s+(.+)$', content, re.MULTILINE):
                        title = match.group(1)
                        start = match.end()
                        snippet = content[start:start + 500].strip()
                        self.entries.append(KBEntry(
                            title=title,
                            source="doc",
                            file=rel,
                            content=snippet[:300],
                            tags=["doc", os.path.splitext(f)[0].lower()],
                        ))
                except Exception as e:
                    logger.debug("KB operation failed: %s", e)

    def _index_agent_memory(self):
        """Index agent memory files."""
        mem_dir = Path.home() / ".code-agents" / "memory"
        if not mem_dir.exists():
            return
        for f in mem_dir.glob("*.md"):
            try:
                content = f.read_text()
                self.entries.append(KBEntry(
                    title=f"Agent Memory: {f.stem}",
                    source="agent-memory",
                    file=str(f.name),
                    content=content[:500],
                    tags=["memory", f.stem.split("_")[0] if "_" in f.stem else "general"],
                ))
            except Exception as e:
                logger.debug("KB operation failed: %s", e)

    def _extract_tags(self, text: str) -> list[str]:
        """Extract meaningful tags from text."""
        tags = []
        keywords = [
            "api", "database", "auth", "deploy", "test", "bug", "feature",
            "jenkins", "jira", "kafka", "redis", "spring", "payment",
        ]
        text_lower = text.lower()
        for kw in keywords:
            if kw in text_lower:
                tags.append(kw)
        return tags[:5]

    def search(self, query: str, limit: int = 10) -> list[KBEntry]:
        """Search KB entries by keyword matching."""
        if not self.entries:
            self.rebuild_index()

        query_lower = query.lower()
        query_words = query_lower.split()

        results = []
        for entry in self.entries:
            searchable = f"{entry.title} {entry.content} {' '.join(entry.tags)}".lower()
            score = 0
            for word in query_words:
                if word in searchable:
                    score += 1
                    if word in entry.title.lower():
                        score += 2  # title match bonus
                    if word in entry.tags:
                        score += 1  # tag match bonus

            if score > 0:
                entry.relevance = score
                results.append(entry)

        results.sort(key=lambda e: -e.relevance)
        return results[:limit]

    def add_entry(self, title: str, content: str, source: str = "manual", tags: list[str] = None):
        """Manually add a KB entry."""
        self.entries.append(KBEntry(
            title=title, source=source, content=content,
            tags=tags or [], timestamp=datetime.now().isoformat(),
        ))
        self._save_index()


def format_kb_results(results: list[KBEntry], query: str) -> str:
    """Format search results for terminal."""
    lines = []
    lines.append(f"  KB Search: \"{query}\" ({len(results)} results)")
    lines.append(f"  {'─' * 50}")

    source_icons = {
        "chat": "💬",
        "code-comment": "📝",
        "doc": "📄",
        "agent-memory": "🧠",
        "manual": "✏️",
    }

    for i, entry in enumerate(results, 1):
        icon = source_icons.get(entry.source, "·")
        lines.append(f"\n  {icon} {i}. {entry.title}")
        if entry.file:
            lines.append(f"     Source: {entry.source} — {entry.file}")
        if entry.content:
            lines.append(f"     {entry.content[:150]}...")
        if entry.tags:
            lines.append(f"     Tags: {', '.join(entry.tags)}")

    if not results:
        lines.append("\n  No results found. Try different keywords.")
        lines.append("  Run /kb --rebuild to re-index the knowledge base.")

    return "\n".join(lines)
