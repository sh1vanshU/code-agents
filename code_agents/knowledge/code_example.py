"""Code Example Finder — find usage patterns for any concept in the codebase.

Answer questions like "how is Redis used here?" or "show me error handling
patterns" by finding, grouping, and ranking real code examples.

Usage:
    from code_agents.knowledge.code_example import ExampleFinder
    finder = ExampleFinder("/path/to/repo")
    result = finder.find("Redis")
    print(format_examples(result))
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.code_example")


@dataclass
class ExampleConfig:
    """Configuration for example finding."""
    cwd: str = "."
    max_examples: int = 20
    context_lines: int = 5
    include_tests: bool = True
    group_by: str = "pattern"  # "pattern", "file", "type"


@dataclass
class CodeExample:
    """A single code example."""
    file: str
    start_line: int
    end_line: int
    code: str
    pattern: str  # what pattern this exemplifies
    relevance: float = 0.0
    language: str = "python"
    is_test: bool = False
    enclosing_function: str = ""


@dataclass
class ExampleSearchResult:
    """Result of searching for code examples."""
    query: str
    examples: list[CodeExample] = field(default_factory=list)
    patterns_found: list[str] = field(default_factory=list)
    total_matches: int = 0
    files_searched: int = 0
    examples_by_pattern: dict[str, list[CodeExample]] = field(default_factory=lambda: defaultdict(list))


class ExampleFinder:
    """Find and rank code examples."""

    def __init__(self, config: ExampleConfig):
        self.config = config

    def find(self, query: str) -> ExampleSearchResult:
        """Find code examples matching a query."""
        logger.info("Finding examples for: %s", query)

        from code_agents.tools._pattern_matchers import grep_codebase

        # Search for the query
        matches = grep_codebase(
            self.config.cwd, re.escape(query),
            max_results=200,
            context_lines=self.config.context_lines,
            case_sensitive=False,
        )

        result = ExampleSearchResult(query=query, total_matches=len(matches))
        seen_files = set()
        examples: list[CodeExample] = []

        for match in matches:
            seen_files.add(match.file)
            is_test = "/test" in match.file or match.file.startswith("test")

            if not self.config.include_tests and is_test:
                continue

            # Get surrounding code for context
            code_block = self._extract_code_block(match.file, match.line)
            if not code_block:
                continue

            pattern = self._classify_pattern(code_block, query)
            relevance = self._score_example(code_block, query, is_test)

            example = CodeExample(
                file=match.file,
                start_line=max(1, match.line - self.config.context_lines),
                end_line=match.line + self.config.context_lines,
                code=code_block,
                pattern=pattern,
                relevance=relevance,
                language=self._detect_language(match.file),
                is_test=is_test,
            )
            examples.append(example)
            result.examples_by_pattern[pattern].append(example)

        # Sort by relevance and deduplicate
        examples.sort(key=lambda x: x.relevance, reverse=True)
        result.examples = examples[:self.config.max_examples]
        result.patterns_found = sorted(result.examples_by_pattern.keys())
        result.files_searched = len(seen_files)

        logger.info("Found %d examples across %d patterns", len(result.examples), len(result.patterns_found))
        return result

    def _extract_code_block(self, file_path: str, line: int) -> str:
        """Extract a meaningful code block around a line."""
        full_path = os.path.join(self.config.cwd, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return ""

        start = max(0, line - 1 - self.config.context_lines)
        end = min(len(lines), line + self.config.context_lines)
        return "".join(lines[start:end])

    def _classify_pattern(self, code: str, query: str) -> str:
        """Classify what pattern a code block represents."""
        code_lower = code.lower()
        query_lower = query.lower()

        if re.search(r"(from|import)\s+.*" + re.escape(query_lower), code_lower):
            return "import"
        if re.search(r"(def|class)\s+.*" + re.escape(query_lower), code_lower):
            return "definition"
        if re.search(r"with\s+.*" + re.escape(query_lower), code_lower):
            return "context_manager"
        if re.search(r"try.*" + re.escape(query_lower), code_lower, re.DOTALL):
            return "error_handling"
        if re.search(rf"{re.escape(query_lower)}\s*\(", code_lower):
            return "function_call"
        if re.search(rf"{re.escape(query_lower)}\s*=", code_lower):
            return "initialization"
        if "@" in code and query_lower in code_lower:
            return "decorator"
        return "usage"

    def _score_example(self, code: str, query: str, is_test: bool) -> float:
        """Score how good an example is."""
        score = 0.5

        # Prefer non-test examples slightly
        if not is_test:
            score += 0.1

        # Prefer examples with comments
        if "#" in code or '"""' in code:
            score += 0.1

        # Prefer examples with the query in a definition
        if re.search(rf"(def|class|function)\s+\w*{re.escape(query)}", code, re.IGNORECASE):
            score += 0.3

        # Prefer shorter, more focused examples
        line_count = code.count("\n")
        if line_count < 10:
            score += 0.1
        elif line_count > 30:
            score -= 0.1

        return min(max(score, 0.0), 1.0)

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".java": "java", ".go": "go", ".rs": "rust",
            ".yaml": "yaml", ".json": "json", ".sql": "sql",
        }
        ext = Path(file_path).suffix
        return ext_map.get(ext, "text")


def format_examples(result: ExampleSearchResult) -> str:
    """Format examples for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Code Examples: \"{result.query}\"")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Found {len(result.examples)} examples ({result.total_matches} total matches)")
    lines.append(f"  Patterns: {', '.join(result.patterns_found)}")
    lines.append("")

    for i, ex in enumerate(result.examples, 1):
        test_marker = " [TEST]" if ex.is_test else ""
        lines.append(f"  --- Example {i} [{ex.pattern}]{test_marker} ---")
        lines.append(f"  File: {ex.file}:{ex.start_line}-{ex.end_line}")
        lines.append("")
        for code_line in ex.code.splitlines()[:12]:
            lines.append(f"    {code_line}")
        if ex.code.count("\n") > 12:
            lines.append(f"    ... ({ex.code.count(chr(10)) - 12} more lines)")
        lines.append("")

    return "\n".join(lines)
