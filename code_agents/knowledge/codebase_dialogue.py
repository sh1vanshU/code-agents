"""Codebase dialogue — persistent Q&A over entire codebase with context memory.

Maintains a conversation context about the codebase, building up understanding
across multiple questions. Indexes files and remembers previous answers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.knowledge.codebase_dialogue")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".rs", ".c", ".cpp", ".h", ".yaml", ".yml",
    ".json", ".toml", ".cfg", ".ini", ".md",
}


@dataclass
class DialogueTurn:
    """A single Q&A turn in the dialogue."""

    question: str = ""
    answer: str = ""
    relevant_files: list[str] = field(default_factory=list)
    context_used: list[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class FileContext:
    """Indexed context about a file."""

    path: str = ""
    summary: str = ""
    symbols: list[str] = field(default_factory=list)  # functions, classes
    imports: list[str] = field(default_factory=list)
    size_lines: int = 0
    content_hash: str = ""


@dataclass
class DialogueResult:
    """Result of a dialogue query."""

    answer: str = ""
    relevant_files: list[str] = field(default_factory=list)
    code_snippets: list[dict] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    confidence: float = 0.0


class CodebaseDialogue:
    """Persistent Q&A dialogue over a codebase."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._file_index: dict[str, FileContext] = {}
        self._history: list[DialogueTurn] = []
        self._indexed = False
        logger.debug("CodebaseDialogue initialized for %s", cwd)

    def index(self) -> int:
        """Build file index for the codebase.

        Returns:
            Number of files indexed.
        """
        self._file_index = {}
        count = 0
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                ext = os.path.splitext(fname)[1]
                if ext not in CODE_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)
                ctx = self._index_file(fpath, rel)
                if ctx:
                    self._file_index[rel] = ctx
                    count += 1

        self._indexed = True
        logger.info("Indexed %d files", count)
        return count

    def ask(self, question: str) -> DialogueResult:
        """Ask a question about the codebase.

        Args:
            question: Natural language question.

        Returns:
            DialogueResult with answer and relevant context.
        """
        if not self._indexed:
            self.index()

        result = DialogueResult()
        logger.info("Question: %s", question[:80])

        # Find relevant files
        relevant = self._find_relevant_files(question)
        result.relevant_files = [f for f, _ in relevant[:10]]

        # Build answer from file contexts
        answer_parts: list[str] = []
        snippets: list[dict] = []

        for fpath, score in relevant[:5]:
            ctx = self._file_index.get(fpath)
            if not ctx:
                continue

            answer_parts.append(f"- **{fpath}**: {ctx.summary}")
            if ctx.symbols:
                answer_parts.append(f"  Symbols: {', '.join(ctx.symbols[:10])}")

            # Extract relevant snippets
            snippet = self._extract_snippet(fpath, question)
            if snippet:
                snippets.append(snippet)

        if answer_parts:
            result.answer = (
                f"Based on analysis of {len(relevant)} relevant files:\n\n"
                + "\n".join(answer_parts)
            )
            result.confidence = min(0.9, 0.3 + 0.1 * len(relevant))
        else:
            result.answer = "No relevant files found for this question."
            result.confidence = 0.1

        result.code_snippets = snippets

        # Use previous context to enhance answer
        prev_context = self._get_relevant_history(question)
        if prev_context:
            result.answer += "\n\n(Previous context also considered)"
            result.confidence = min(1.0, result.confidence + 0.1)

        # Suggest follow-ups
        result.follow_up_questions = self._suggest_follow_ups(question, result.relevant_files)

        # Record turn
        self._history.append(DialogueTurn(
            question=question,
            answer=result.answer,
            relevant_files=result.relevant_files,
        ))

        return result

    def get_history(self) -> list[dict]:
        """Get dialogue history."""
        return [
            {"question": t.question, "answer": t.answer,
             "files": t.relevant_files}
            for t in self._history
        ]

    def _index_file(self, fpath: str, rel: str) -> FileContext | None:
        """Index a single file."""
        try:
            content = Path(fpath).read_text(errors="replace")
        except OSError:
            return None

        lines = content.splitlines()
        ctx = FileContext(
            path=rel,
            size_lines=len(lines),
            content_hash=hashlib.md5(content.encode()).hexdigest()[:12],
        )

        # Extract summary (first docstring or comment block)
        for line in lines[:10]:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                ctx.summary = stripped.strip("\"' ")
                break
            elif stripped.startswith("#") and not stripped.startswith("#!"):
                ctx.summary = stripped.lstrip("# ")
                break

        if not ctx.summary:
            ctx.summary = f"{rel} ({len(lines)} lines)"

        # Extract symbols (functions, classes)
        if fpath.endswith(".py"):
            ctx.symbols = self._extract_python_symbols(content)
            ctx.imports = self._extract_python_imports(content)

        return ctx

    def _extract_python_symbols(self, content: str) -> list[str]:
        """Extract function and class names from Python source."""
        symbols: list[str] = []
        for match in re.finditer(r"^(?:class|def|async\s+def)\s+(\w+)", content, re.MULTILINE):
            symbols.append(match.group(1))
        return symbols

    def _extract_python_imports(self, content: str) -> list[str]:
        """Extract import names from Python source."""
        imports: list[str] = []
        for match in re.finditer(r"^(?:from|import)\s+(\S+)", content, re.MULTILINE):
            imports.append(match.group(1))
        return imports

    def _find_relevant_files(self, question: str) -> list[tuple[str, float]]:
        """Find files relevant to a question using keyword matching."""
        q_words = set(re.findall(r"\b\w{3,}\b", question.lower()))
        scored: list[tuple[str, float]] = []

        for rel, ctx in self._file_index.items():
            score = 0.0
            # Match against file path
            path_words = set(re.findall(r"\w{3,}", rel.lower()))
            score += len(q_words & path_words) * 2.0

            # Match against summary
            if ctx.summary:
                summary_words = set(re.findall(r"\b\w{3,}\b", ctx.summary.lower()))
                score += len(q_words & summary_words) * 1.5

            # Match against symbols
            for sym in ctx.symbols:
                sym_words = set(re.findall(r"[a-z]{3,}", sym.lower()))
                score += len(q_words & sym_words) * 1.0

            # Match against imports
            for imp in ctx.imports:
                if any(w in imp.lower() for w in q_words):
                    score += 0.5

            if score > 0:
                scored.append((rel, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _extract_snippet(self, rel_path: str, question: str) -> dict | None:
        """Extract a relevant code snippet from a file."""
        fpath = os.path.join(self.cwd, rel_path)
        try:
            content = Path(fpath).read_text(errors="replace")
        except OSError:
            return None

        q_words = set(re.findall(r"\b\w{3,}\b", question.lower()))
        lines = content.splitlines()
        best_start = 0
        best_score = 0

        for i, line in enumerate(lines):
            line_words = set(re.findall(r"\b\w{3,}\b", line.lower()))
            score = len(q_words & line_words)
            if score > best_score:
                best_score = score
                best_start = i

        if best_score > 0:
            start = max(0, best_start - 2)
            end = min(len(lines), best_start + 10)
            return {
                "file": rel_path,
                "start_line": start + 1,
                "content": "\n".join(lines[start:end]),
            }
        return None

    def _get_relevant_history(self, question: str) -> list[DialogueTurn]:
        """Find previous dialogue turns relevant to current question."""
        if not self._history:
            return []

        q_words = set(re.findall(r"\b\w{3,}\b", question.lower()))
        relevant: list[DialogueTurn] = []

        for turn in self._history[-10:]:  # Last 10 turns
            turn_words = set(re.findall(r"\b\w{3,}\b", turn.question.lower()))
            if len(q_words & turn_words) >= 2:
                relevant.append(turn)

        return relevant

    def _suggest_follow_ups(self, question: str, files: list[str]) -> list[str]:
        """Suggest follow-up questions."""
        suggestions: list[str] = []
        if files:
            suggestions.append(f"How does {files[0]} interact with other modules?")
        if "how" in question.lower():
            suggestions.append("What are the edge cases to consider?")
        if "what" in question.lower():
            suggestions.append("How is this feature tested?")
        suggestions.append("What would break if this code changed?")
        return suggestions[:3]


def ask_codebase(cwd: str, question: str) -> dict:
    """Convenience function to ask the codebase a question.

    Returns:
        Dict with answer, relevant files, snippets, and follow-ups.
    """
    dialogue = CodebaseDialogue(cwd)
    result = dialogue.ask(question)
    return {
        "answer": result.answer,
        "relevant_files": result.relevant_files,
        "code_snippets": result.code_snippets,
        "follow_up_questions": result.follow_up_questions,
        "confidence": result.confidence,
    }
