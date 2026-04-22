"""Comment Generator — add code comments only where logic is non-obvious.

Analyzes code to identify complex, non-obvious, or tricky sections and
generates comments explaining WHY, not WHAT the code does.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.comment_generator")

# ---------------------------------------------------------------------------
# Complexity indicators
# ---------------------------------------------------------------------------
_COMPLEX_PATTERNS = {
    "nested_condition": re.compile(r"(?:if|elif|while)\s.*(?:and|or)\s.*(?:and|or)"),
    "bitwise_ops": re.compile(r"[&|^~]\s*\d|<<|>>"),
    "regex_literal": re.compile(r"re\.(compile|match|search|findall|sub)\("),
    "magic_number": re.compile(r"(?<!\w)(?:0x[0-9a-fA-F]+|\d{3,})\b"),
    "lambda_complex": re.compile(r"lambda\s+\w+(?:,\s*\w+)+\s*:"),
    "list_comp_nested": re.compile(r"\[.*\bfor\b.*\bfor\b.*\]"),
    "exception_catch_broad": re.compile(r"except\s*(?:Exception|BaseException|\s*:)"),
    "type_cast_chain": re.compile(r"(?:int|float|str|bool)\(.*(?:int|float|str|bool)\("),
}

# Comment style per language
_COMMENT_STYLES = {
    ".py": "#",
    ".js": "//",
    ".ts": "//",
    ".java": "//",
    ".go": "//",
    ".rs": "//",
    ".rb": "#",
    ".sh": "#",
    ".c": "//",
    ".cpp": "//",
    ".cs": "//",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommentSuggestion:
    """A suggested comment for a specific code location."""

    file_path: str
    line_number: int
    comment: str
    reason: str  # why this line needs a comment
    complexity_type: str  # which pattern triggered it
    confidence: float = 0.0  # 0-1


@dataclass
class CommentResult:
    """Result of comment analysis."""

    suggestions: list[CommentSuggestion] = field(default_factory=list)
    files_analyzed: int = 0
    lines_analyzed: int = 0

    @property
    def summary(self) -> str:
        return f"{len(self.suggestions)} suggestions across {self.files_analyzed} files"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class CommentGenerator:
    """Analyze code and suggest comments for non-obvious logic."""

    def __init__(self, cwd: Optional[str] = None, min_confidence: float = 0.5):
        self.cwd = cwd or os.getcwd()
        self.min_confidence = min_confidence

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self, file_paths: Optional[list[str]] = None) -> CommentResult:
        """Analyze files and generate comment suggestions."""
        result = CommentResult()

        if file_paths is None:
            file_paths = self._find_source_files()

        for fpath in file_paths:
            suggestions = self._analyze_file(fpath)
            result.suggestions.extend(suggestions)
            result.files_analyzed += 1

        # Filter by confidence
        result.suggestions = [
            s for s in result.suggestions if s.confidence >= self.min_confidence
        ]
        result.suggestions.sort(key=lambda s: (-s.confidence, s.file_path, s.line_number))

        logger.info("Comment analysis: %s", result.summary)
        return result

    def analyze_file(self, file_path: str) -> list[CommentSuggestion]:
        """Analyze a single file."""
        return self._analyze_file(file_path)

    # ── File analysis ─────────────────────────────────────────────────────

    def _analyze_file(self, file_path: str) -> list[CommentSuggestion]:
        """Analyze a single file for non-obvious code."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        lines = content.splitlines()
        suggestions: list[CommentSuggestion] = []
        ext = os.path.splitext(file_path)[1]
        comment_prefix = _COMMENT_STYLES.get(ext, "#")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines, existing comments, docstrings
            if not stripped or stripped.startswith(comment_prefix) or stripped.startswith(('"""', "'''", "/*", "*")):
                continue

            # Check already has inline comment
            if self._has_inline_comment(stripped, comment_prefix):
                continue

            # Check each complexity pattern
            for pattern_name, pattern in _COMPLEX_PATTERNS.items():
                if pattern.search(stripped):
                    suggestion = self._generate_comment(
                        file_path, i + 1, stripped, pattern_name, lines, i,
                    )
                    if suggestion:
                        suggestions.append(suggestion)
                    break  # one suggestion per line

            # Check function complexity (nesting depth)
            nesting = self._calculate_nesting(lines, i)
            if nesting >= 4 and not any(s.line_number == i + 1 for s in suggestions):
                suggestions.append(CommentSuggestion(
                    file_path=file_path,
                    line_number=i + 1,
                    comment="Deeply nested logic — consider extracting to a helper function",
                    reason="High nesting depth indicates complex control flow",
                    complexity_type="deep_nesting",
                    confidence=0.7,
                ))

        return suggestions

    def _generate_comment(self, file_path: str, line_num: int, line: str,
                          pattern_name: str, all_lines: list[str], idx: int) -> Optional[CommentSuggestion]:
        """Generate a comment for a detected pattern."""
        generators = {
            "nested_condition": self._comment_nested_condition,
            "bitwise_ops": self._comment_bitwise,
            "regex_literal": self._comment_regex,
            "magic_number": self._comment_magic_number,
            "lambda_complex": self._comment_lambda,
            "list_comp_nested": self._comment_nested_comprehension,
            "exception_catch_broad": self._comment_broad_except,
            "type_cast_chain": self._comment_type_chain,
        }

        gen_fn = generators.get(pattern_name)
        if gen_fn:
            comment, confidence = gen_fn(line, all_lines, idx)
            if comment:
                return CommentSuggestion(
                    file_path=file_path,
                    line_number=line_num,
                    comment=comment,
                    reason=f"Pattern: {pattern_name}",
                    complexity_type=pattern_name,
                    confidence=confidence,
                )
        return None

    # ── Pattern-specific comment generators ───────────────────────────────

    def _comment_nested_condition(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for nested conditions."""
        return ("Complex conditional — document which business rule this encodes", 0.8)

    def _comment_bitwise(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for bitwise operations."""
        return ("Bitwise operation — explain the flag/mask semantics", 0.9)

    def _comment_regex(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for regex patterns."""
        # Extract the regex pattern
        m = re.search(r're\.\w+\(\s*r?["\'](.+?)["\']', line)
        if m:
            pattern = m.group(1)
            return (f"Regex matches: describe what '{pattern[:40]}' captures and why", 0.85)
        return ("Regex — document what pattern this matches and why", 0.7)

    def _comment_magic_number(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for magic numbers."""
        # Ignore common non-magic numbers in certain contexts
        if re.search(r"(range|sleep|timeout|port|status_code|HTTP_|\.get\(|index)", line):
            return ("", 0.0)
        return ("Magic number — extract to a named constant with explanation", 0.6)

    def _comment_lambda(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for complex lambdas."""
        return ("Complex lambda — consider a named function for clarity", 0.7)

    def _comment_nested_comprehension(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for nested list comprehensions."""
        return ("Nested comprehension — document the transformation being applied", 0.8)

    def _comment_broad_except(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for broad exception catches."""
        return ("Broad except — document why specific exceptions cannot be caught here", 0.75)

    def _comment_type_chain(self, line: str, lines: list[str], idx: int) -> tuple[str, float]:
        """Generate comment for chained type casts."""
        return ("Chained type cast — document the expected input format and conversion path", 0.65)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _has_inline_comment(line: str, prefix: str) -> bool:
        """Check if line already has an inline comment."""
        # Simple heuristic: look for comment prefix not inside a string
        in_string = False
        quote_char = ""
        for i, ch in enumerate(line):
            if ch in ('"', "'") and (i == 0 or line[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    quote_char = ch
                elif ch == quote_char:
                    in_string = False
            if not in_string and line[i:].startswith(prefix) and i > 0:
                return True
        return False

    @staticmethod
    def _calculate_nesting(lines: list[str], idx: int) -> int:
        """Calculate the nesting depth at a given line."""
        line = lines[idx] if idx < len(lines) else ""
        if not line.strip():
            return 0
        indent = len(line) - len(line.lstrip())
        # Approximate nesting by indent level (4 spaces per level)
        return indent // 4

    def _find_source_files(self) -> list[str]:
        """Find source files in cwd."""
        extensions = set(_COMMENT_STYLES.keys())
        files = []
        for root, dirs, filenames in os.walk(self.cwd):
            # Skip hidden/vendor dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ("node_modules", "vendor", "venv", ".venv", "__pycache__", "dist", "build")]
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if ext in extensions:
                    files.append(os.path.join(root, fname))
                    if len(files) >= 100:
                        return files
        return files
