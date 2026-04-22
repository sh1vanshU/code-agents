"""Codebase Navigator — semantic search for code concepts.

Answer questions like "where does authentication happen?" or "how are
errors handled?" by scanning code structure, function names, docstrings,
and import patterns.

Usage:
    from code_agents.knowledge.codebase_nav import CodebaseNavigator
    nav = CodebaseNavigator("/path/to/repo")
    result = nav.search("authentication")
    print(format_nav_results(result))
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.codebase_nav")

# Concept keywords mapping for semantic search
CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "authentication": ["auth", "login", "logout", "token", "jwt", "session", "password", "credential", "oauth", "sso"],
    "authorization": ["rbac", "permission", "role", "access", "acl", "policy", "authorize", "forbidden"],
    "database": ["db", "sql", "query", "migration", "schema", "model", "orm", "cursor", "connection", "pool"],
    "caching": ["cache", "redis", "memcache", "ttl", "invalidat", "expire", "lru"],
    "logging": ["logger", "log_", "logging", "log.", "sentry", "trace"],
    "testing": ["test_", "assert", "mock", "fixture", "pytest", "unittest"],
    "error_handling": ["except", "error", "raise", "catch", "try", "finally", "fault", "fallback"],
    "api": ["route", "endpoint", "handler", "request", "response", "middleware", "cors"],
    "security": ["encrypt", "decrypt", "hash", "salt", "secret", "sanitiz", "escape", "xss", "csrf", "injection"],
    "deployment": ["deploy", "docker", "k8s", "kubernetes", "helm", "terraform", "ci", "cd", "pipeline"],
    "messaging": ["queue", "kafka", "rabbit", "pubsub", "event", "publish", "subscribe", "consumer"],
    "payment": ["payment", "transaction", "refund", "charge", "settle", "merchant", "acquirer"],
    "configuration": ["config", "setting", "env", "environ", "dotenv", "yaml", "toml"],
    "validation": ["valid", "schema", "pydantic", "serialize", "deserialize", "parse"],
    "monitoring": ["metric", "monitor", "alert", "health", "check", "prometheus", "grafana", "dashboard"],
}


@dataclass
class NavConfig:
    """Configuration for codebase navigation."""
    cwd: str = "."
    max_results: int = 30
    include_tests: bool = False
    language: str = "python"


@dataclass
class NavResult:
    """A single navigation result."""
    file: str
    line: int
    name: str  # function/class name
    type: str  # "function", "class", "module", "config"
    relevance: float = 0.0  # 0-1 score
    snippet: str = ""
    docstring: str = ""


@dataclass
class NavSearchResult:
    """Result of a navigation search."""
    query: str
    results: list[NavResult] = field(default_factory=list)
    concepts_matched: list[str] = field(default_factory=list)
    total_files_scanned: int = 0


class CodebaseNavigator:
    """Semantic codebase navigation."""

    def __init__(self, config: NavConfig):
        self.config = config

    def search(self, query: str) -> NavSearchResult:
        """Search for a concept in the codebase."""
        logger.info("Navigating codebase for: %s", query)

        # Expand query into keywords
        keywords = self._expand_query(query)
        concepts = self._match_concepts(query)

        # Search using pattern matchers
        from code_agents.tools._pattern_matchers import grep_codebase, CODE_EXTS

        all_matches: list[NavResult] = []
        files_scanned = set()

        for keyword in keywords:
            matches = grep_codebase(
                self.config.cwd, keyword,
                max_results=50,
                case_sensitive=False,
            )
            for match in matches:
                if not self.config.include_tests and "/test" in match.file:
                    continue
                files_scanned.add(match.file)
                relevance = self._score_relevance(match.content, keywords, match.file)
                all_matches.append(NavResult(
                    file=match.file,
                    line=match.line,
                    name=self._extract_name(match.content),
                    type=self._classify_result(match.content, match.file),
                    relevance=relevance,
                    snippet=match.content.strip()[:120],
                ))

        # Deduplicate and sort by relevance
        seen = set()
        unique: list[NavResult] = []
        for m in all_matches:
            key = (m.file, m.line)
            if key not in seen:
                seen.add(key)
                unique.append(m)

        unique.sort(key=lambda x: x.relevance, reverse=True)

        return NavSearchResult(
            query=query,
            results=unique[:self.config.max_results],
            concepts_matched=concepts,
            total_files_scanned=len(files_scanned),
        )

    def _expand_query(self, query: str) -> list[str]:
        """Expand a natural language query into search keywords."""
        words = re.split(r"\s+", query.lower().strip())
        keywords = list(words)

        # Add concept keywords
        for word in words:
            for concept, kws in CONCEPT_KEYWORDS.items():
                if word in concept or concept.startswith(word):
                    keywords.extend(kws[:5])

        # Deduplicate preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen and len(kw) >= 3:
                seen.add(kw)
                unique.append(kw)
        return unique[:15]

    def _match_concepts(self, query: str) -> list[str]:
        """Find which high-level concepts match the query."""
        query_lower = query.lower()
        matched = []
        for concept in CONCEPT_KEYWORDS:
            if concept in query_lower or any(kw in query_lower for kw in CONCEPT_KEYWORDS[concept][:3]):
                matched.append(concept)
        return matched

    def _score_relevance(self, content: str, keywords: list[str], file_path: str) -> float:
        """Score how relevant a match is."""
        score = 0.0
        content_lower = content.lower()
        for kw in keywords:
            if kw in content_lower:
                score += 0.2
            # Higher score for definition matches
            if re.search(rf"(def|class|function|const)\s+\w*{re.escape(kw)}", content_lower):
                score += 0.4

        # Bonus for non-test files
        if "/test" not in file_path:
            score += 0.1

        # Bonus for source files (not configs)
        if file_path.endswith(".py") or file_path.endswith(".ts") or file_path.endswith(".go"):
            score += 0.1

        return min(score, 1.0)

    def _extract_name(self, content: str) -> str:
        """Extract function/class name from a line."""
        match = re.search(r"(def|class|function|const|let|var|func)\s+(\w+)", content)
        if match:
            return match.group(2)
        return content.strip()[:40]

    def _classify_result(self, content: str, file_path: str) -> str:
        """Classify what kind of result this is."""
        stripped = content.strip()
        if re.match(r"(def|async def)\s+", stripped):
            return "function"
        if stripped.startswith("class "):
            return "class"
        if any(stripped.startswith(kw) for kw in ("from ", "import ")):
            return "import"
        if file_path.endswith((".yaml", ".yml", ".json", ".toml", ".env")):
            return "config"
        if "/router" in file_path or "route" in stripped.lower():
            return "endpoint"
        return "reference"


def format_nav_results(result: NavSearchResult) -> str:
    """Format navigation results for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Codebase search: \"{result.query}\"")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Found {len(result.results)} results in {result.total_files_scanned} files")
    if result.concepts_matched:
        lines.append(f"  Concepts: {', '.join(result.concepts_matched)}")
    lines.append("")

    for i, r in enumerate(result.results, 1):
        rel_score = f"{'*' * int(r.relevance * 5)}"
        lines.append(f"  {i:2d}. [{r.type:10s}] {r.file}:{r.line}  {rel_score}")
        lines.append(f"      {r.snippet}")

    lines.append("")
    return "\n".join(lines)
