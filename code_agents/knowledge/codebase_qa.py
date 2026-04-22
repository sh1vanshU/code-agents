"""Codebase Q&A — natural language questions → code answers with sources."""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.codebase_qa")


@dataclass
class QASource:
    file: str
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
    relevance: float = 0.0


@dataclass
class QAContext:
    relevant_files: list[str] = field(default_factory=list)
    relevant_symbols: list[dict] = field(default_factory=list)
    architecture_notes: list[str] = field(default_factory=list)
    related_docs: list[str] = field(default_factory=list)


@dataclass
class QAAnswer:
    question: str
    answer: str = ""
    context: QAContext = field(default_factory=QAContext)
    confidence: float = 0.0
    sources: list[QASource] = field(default_factory=list)


# Keywords that map to architectural concepts
_CONCEPT_MAP = {
    "auth": ["auth", "login", "session", "token", "jwt", "oauth", "password", "credential"],
    "api": ["api", "endpoint", "route", "router", "handler", "controller", "rest"],
    "database": ["database", "db", "model", "schema", "migration", "query", "sql", "orm"],
    "testing": ["test", "spec", "fixture", "mock", "assert", "pytest", "jest"],
    "config": ["config", "setting", "env", "environment", "variable"],
    "deploy": ["deploy", "ci", "cd", "pipeline", "docker", "kubernetes", "k8s"],
    "logging": ["log", "logger", "logging", "trace", "debug", "monitor"],
    "error": ["error", "exception", "catch", "try", "raise", "throw", "handle"],
    "security": ["security", "encrypt", "hash", "sanitize", "cors", "csrf", "xss"],
    "cache": ["cache", "redis", "memcache", "ttl", "invalidate"],
}

_CODE_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rb", ".rs", ".jsx", ".tsx"}
_DOC_EXTENSIONS = {".md", ".rst", ".txt"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}


class CodebaseQA:
    """Answers questions about the codebase using local analysis."""

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)

    def ask(self, question: str) -> QAAnswer:
        """Answer a question about the codebase."""
        parsed = self._parse_question(question)
        context = self._gather_context(parsed)
        answer = self._compose_answer(question, parsed, context)
        sources = self._extract_sources(context)
        confidence = self._estimate_confidence(context)

        return QAAnswer(
            question=question,
            answer=answer,
            context=context,
            confidence=confidence,
            sources=sources,
        )

    def _parse_question(self, question: str) -> dict:
        """Parse question to extract intent and search terms."""
        q = question.lower().strip().rstrip("?")
        terms = set(re.findall(r'\b\w{3,}\b', q))

        # Remove common stop words
        stop_words = {"how", "does", "what", "where", "which", "the", "this", "that",
                      "are", "is", "was", "were", "can", "could", "should", "would",
                      "will", "has", "have", "had", "been", "being", "for", "with",
                      "from", "about", "into", "through", "and", "but", "not"}
        terms -= stop_words

        # Detect concepts
        concepts = []
        for concept, keywords in _CONCEPT_MAP.items():
            if terms & set(keywords):
                concepts.append(concept)

        # Detect specific symbols (CamelCase, snake_case patterns)
        symbols = []
        for word in re.findall(r'\b(?:[A-Z][a-z]+){2,}\b', question):  # CamelCase
            symbols.append(word)
        for word in re.findall(r'\b[a-z]+_[a-z_]+\b', question):  # snake_case
            if word not in stop_words:
                symbols.append(word)

        # Detect file references
        files = re.findall(r'[\w/.-]+\.\w{1,4}', question)

        intent = "explain"  # default
        if any(w in q for w in ("where", "find", "locate", "which file")):
            intent = "locate"
        elif any(w in q for w in ("how", "work", "flow", "process")):
            intent = "explain"
        elif any(w in q for w in ("why", "reason", "purpose")):
            intent = "rationale"
        elif any(w in q for w in ("list", "all", "show", "what are")):
            intent = "enumerate"

        return {
            "terms": list(terms),
            "concepts": concepts,
            "symbols": symbols,
            "files": files,
            "intent": intent,
        }

    def _gather_context(self, parsed: dict) -> QAContext:
        """Gather relevant code context."""
        context = QAContext()

        # Search for referenced files
        for f in parsed.get("files", []):
            full = os.path.join(self.cwd, f)
            if os.path.exists(full):
                context.relevant_files.append(f)

        # Search for symbols
        for sym in parsed.get("symbols", []):
            results = self._grep_code(sym)
            for r in results[:5]:
                context.relevant_symbols.append(r)
                if r["file"] not in context.relevant_files:
                    context.relevant_files.append(r["file"])

        # Search for concepts
        for term in parsed.get("terms", [])[:5]:
            if len(term) >= 4:  # Skip short terms
                results = self._grep_code(term)
                for r in results[:3]:
                    if r["file"] not in context.relevant_files:
                        context.relevant_files.append(r["file"])

        # Search documentation
        context.related_docs = self._search_docs(parsed.get("terms", []))

        # Architecture notes from project structure
        context.architecture_notes = self._analyze_architecture(
            context.relevant_files, parsed.get("concepts", [])
        )

        return context

    def _grep_code(self, pattern: str) -> list[dict]:
        """Search codebase for a pattern using git grep."""
        try:
            result = subprocess.run(
                ["git", "grep", "-n", "-i", "--max-count=10", pattern],
                cwd=self.cwd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        results = []
        for line in result.stdout.strip().split("\n")[:10]:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                results.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "match": parts[2].strip()[:200],
                })
        return results

    def _search_docs(self, terms: list[str]) -> list[str]:
        """Search documentation files."""
        docs = []
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                if Path(f).suffix in _DOC_EXTENSIONS:
                    full = os.path.join(root, f)
                    try:
                        content = Path(full).read_text(errors="replace").lower()
                        if any(t in content for t in terms[:3]):
                            rel = os.path.relpath(full, self.cwd)
                            docs.append(rel)
                    except OSError:
                        continue
        return docs[:10]

    def _analyze_architecture(self, files: list[str],
                               concepts: list[str]) -> list[str]:
        """Generate architecture notes from file patterns."""
        notes = []

        # Analyze directory structure
        dirs = set(str(Path(f).parent) for f in files)
        if dirs:
            notes.append(f"Relevant directories: {', '.join(sorted(dirs)[:5])}")

        # Detect patterns
        has_tests = any("test" in f.lower() for f in files)
        has_routers = any("router" in f.lower() or "route" in f.lower() for f in files)
        has_models = any("model" in f.lower() for f in files)

        if has_routers:
            notes.append("Uses router pattern for API endpoints")
        if has_models:
            notes.append("Has model layer for data representation")
        if has_tests:
            notes.append("Has test coverage for related modules")

        # Check for specific files
        for config_file in ["CLAUDE.md", "README.md", "ARCHITECTURE.md"]:
            if os.path.exists(os.path.join(self.cwd, config_file)):
                notes.append(f"See {config_file} for project documentation")

        return notes

    def _compose_answer(self, question: str, parsed: dict, context: QAContext) -> str:
        """Compose an answer from gathered context."""
        parts = []

        intent = parsed.get("intent", "explain")

        if intent == "locate" and context.relevant_files:
            parts.append(f"Found in the following files:")
            for f in context.relevant_files[:10]:
                parts.append(f"  - `{f}`")
        elif intent == "enumerate" and context.relevant_symbols:
            parts.append("Found the following:")
            seen = set()
            for sym in context.relevant_symbols:
                key = f"{sym['file']}:{sym['line']}"
                if key not in seen:
                    parts.append(f"  - `{sym['file']}:{sym['line']}` — {sym['match']}")
                    seen.add(key)
        elif context.relevant_files or context.relevant_symbols:
            if context.architecture_notes:
                parts.append("Architecture context:")
                for note in context.architecture_notes:
                    parts.append(f"  - {note}")
                parts.append("")

            if context.relevant_files:
                parts.append("Key files:")
                for f in context.relevant_files[:10]:
                    parts.append(f"  - `{f}`")
                parts.append("")

            if context.relevant_symbols:
                parts.append("Relevant code:")
                seen = set()
                for sym in context.relevant_symbols[:10]:
                    key = f"{sym['file']}:{sym['line']}"
                    if key not in seen:
                        parts.append(f"  - `{sym['file']}:{sym['line']}` — {sym['match']}")
                        seen.add(key)

        if context.related_docs:
            parts.append("")
            parts.append("Related documentation:")
            for doc in context.related_docs[:5]:
                parts.append(f"  - `{doc}`")

        if not parts:
            parts.append(
                "Could not find specific information. Try being more specific "
                "or reference a file/function name directly."
            )

        return "\n".join(parts)

    def _extract_sources(self, context: QAContext) -> list[QASource]:
        """Extract source references from context."""
        sources = []
        for sym in context.relevant_symbols[:10]:
            sources.append(QASource(
                file=sym["file"],
                line_start=sym.get("line", 0),
                snippet=sym.get("match", ""),
                relevance=0.8,
            ))
        for f in context.relevant_files:
            if not any(s.file == f for s in sources):
                sources.append(QASource(file=f, relevance=0.5))
        return sources

    def _estimate_confidence(self, context: QAContext) -> float:
        """Estimate answer confidence."""
        score = 0.0
        if context.relevant_files:
            score += min(len(context.relevant_files) * 0.1, 0.3)
        if context.relevant_symbols:
            score += min(len(context.relevant_symbols) * 0.1, 0.3)
        if context.related_docs:
            score += 0.2
        if context.architecture_notes:
            score += 0.1
        return min(round(score, 2), 1.0)


def format_qa_answer(answer: QAAnswer) -> str:
    """Format Q&A answer for display."""
    conf_pct = f"{answer.confidence:.0%}"
    lines = [
        "## Codebase Q&A",
        "",
        f"**Q:** {answer.question}",
        f"**Confidence:** {conf_pct}",
        "",
        answer.answer,
        "",
    ]

    if answer.sources:
        lines.extend(["### Sources", ""])
        for s in answer.sources[:10]:
            loc = f"{s.file}:{s.line_start}" if s.line_start else s.file
            lines.append(f"- `{loc}`")
        lines.append("")

    return "\n".join(lines)
