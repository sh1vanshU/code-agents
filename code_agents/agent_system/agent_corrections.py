"""Agent corrections — learn from user corrections to improve future responses.

Stores correction->expected pairs when user rejects/edits agent output.
Before generating, checks similar past corrections and injects into prompt.

Storage:
- Global: ~/.code-agents/corrections/<agent>.jsonl
- Per-project: .code-agents/corrections/<agent>.jsonl
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.agent_corrections")

GLOBAL_CORRECTIONS_DIR = Path.home() / ".code-agents" / "corrections"
PROJECT_CORRECTIONS_DIR_NAME = ".code-agents/corrections"

DEFAULT_SIMILARITY_THRESHOLD = 0.3
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_CHARS = 2000


@dataclass
class CorrectionEntry:
    """A single correction record: what the agent produced vs what user expected."""

    agent: str
    timestamp: float
    original: str  # what agent produced
    expected: str  # what user corrected to
    context: str  # surrounding context (file, task)
    similarity_key: str  # normalized text for matching
    project: str = ""


class CorrectionStore:
    """Manages correction entries for an agent, with global + per-project storage."""

    def __init__(
        self,
        agent_name: str,
        project_path: Optional[str] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ):
        self.agent_name = agent_name
        self.project_path = project_path
        self.similarity_threshold = similarity_threshold

        # Global storage
        self._global_dir = GLOBAL_CORRECTIONS_DIR
        self._global_file = self._global_dir / f"{agent_name}.jsonl"

        # Per-project storage
        self._project_file: Optional[Path] = None
        if project_path:
            proj = Path(project_path) / PROJECT_CORRECTIONS_DIR_NAME
            self._project_file = proj / f"{agent_name}.jsonl"

    def record(
        self, original: str, expected: str, context: str = ""
    ) -> CorrectionEntry:
        """Record a correction. Writes to both global and project stores."""
        entry = CorrectionEntry(
            agent=self.agent_name,
            timestamp=time.time(),
            original=original,
            expected=expected,
            context=context,
            similarity_key=self._normalize(original + " " + context),
            project=self.project_path or "",
        )
        self._append(entry)
        logger.info(
            "Recorded correction for agent=%s context=%s",
            self.agent_name,
            context[:80] if context else "(none)",
        )
        return entry

    def find_similar(
        self,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> list[CorrectionEntry]:
        """Find corrections similar to query using Jaccard similarity on tokens."""
        query_norm = self._normalize(query)
        query_tokens = set(query_norm.split())
        if not query_tokens:
            return []

        entries = self.list_all()
        scored: list[tuple[float, CorrectionEntry]] = []

        for entry in entries:
            entry_tokens = set(entry.similarity_key.split())
            if not entry_tokens:
                continue
            intersection = query_tokens & entry_tokens
            union = query_tokens | entry_tokens
            similarity = len(intersection) / len(union) if union else 0.0
            if similarity >= self.similarity_threshold:
                scored.append((similarity, entry))

        # Sort by similarity descending, then by timestamp descending (newer first)
        scored.sort(key=lambda x: (-x[0], -x[1].timestamp))
        return [entry for _, entry in scored[:max_results]]

    def format_for_prompt(
        self, query: str, max_chars: int = DEFAULT_MAX_CHARS
    ) -> str:
        """Format similar corrections as a prompt injection block."""
        similar = self.find_similar(query)
        if not similar:
            return ""

        lines = ["--- Past Corrections ---"]
        total_len = len(lines[0])

        for i, entry in enumerate(similar, 1):
            block_lines = [
                f"Correction {i}:",
                f"  Context: {entry.context}" if entry.context else "",
                f"  Original: {entry.original[:200]}",
                f"  Expected: {entry.expected[:200]}",
                "",
            ]
            block = "\n".join(line for line in block_lines if line)
            if total_len + len(block) + 1 > max_chars:
                break
            lines.append(block)
            total_len += len(block) + 1

        lines.append("--- End Corrections ---")
        return "\n".join(lines)

    def list_all(self) -> list[CorrectionEntry]:
        """Load all corrections from both global and project stores."""
        entries: list[CorrectionEntry] = []
        for path in self._storage_paths():
            entries.extend(self._load_file(path))
        return entries

    def clear(self) -> int:
        """Clear all corrections for this agent. Returns count of entries removed."""
        count = 0
        for path in self._storage_paths():
            if path.is_file():
                try:
                    count += sum(1 for _ in path.open(encoding="utf-8"))
                    path.unlink()
                    logger.info("Cleared corrections file: %s", path)
                except OSError as exc:
                    logger.warning("Failed to clear %s: %s", path, exc)
        return count

    def _normalize(self, text: str) -> str:
        """Normalize text: lowercase, strip, collapse whitespace, remove punctuation."""
        text = text.lower().strip()
        # Collapse multi-line to single line
        text = " ".join(text.splitlines())
        # Remove punctuation (keep alphanumeric and whitespace)
        text = re.sub(r"[^\w\s]", "", text)
        # Collapse multiple whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _storage_paths(self) -> list[Path]:
        """Return list of storage file paths (global + project if set)."""
        paths = [self._global_file]
        if self._project_file:
            paths.append(self._project_file)
        return paths

    def _append(self, entry: CorrectionEntry) -> None:
        """Append entry to storage files (thread-safe append mode)."""
        line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
        for path in self._storage_paths():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as exc:
                logger.warning("Failed to write correction to %s: %s", path, exc)

    def _load_file(self, path: Path) -> list[CorrectionEntry]:
        """Load entries from a JSONL file."""
        if not path.is_file():
            return []
        entries: list[CorrectionEntry] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(CorrectionEntry(**data))
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.warning(
                            "Skipping invalid line %d in %s: %s",
                            line_num,
                            path,
                            exc,
                        )
        except OSError as exc:
            logger.warning("Failed to read %s: %s", path, exc)
        return entries


def inject_corrections(
    agent_name: str,
    user_message: str,
    project_path: Optional[str] = None,
) -> str:
    """Build a corrections context block for prompt injection.

    Returns formatted string of past corrections relevant to the user message,
    or empty string if no relevant corrections found.
    """
    try:
        store = CorrectionStore(agent_name, project_path=project_path)
        return store.format_for_prompt(user_message)
    except Exception as exc:
        logger.warning("Failed to inject corrections: %s", exc)
        return ""
