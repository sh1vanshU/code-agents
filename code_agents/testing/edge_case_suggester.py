"""Edge Case Suggester — analyze a function and suggest untested edge cases.

Uses AST analysis + heuristics to find: null/None, empty collections,
boundary values, unicode, concurrency, type mismatches, overflow.

Usage:
    from code_agents.testing.edge_case_suggester import EdgeCaseSuggester
    suggester = EdgeCaseSuggester(EdgeCaseConfig(cwd="/path/to/repo"))
    result = suggester.suggest("code_agents/stream.py:build_prompt")
    print(format_edge_cases(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.testing.edge_case_suggester")


@dataclass
class EdgeCaseConfig:
    cwd: str = "."


@dataclass
class EdgeCase:
    """A suggested edge case to test."""
    category: str  # "null", "empty", "boundary", "type", "concurrency", "unicode", "error", "overflow"
    description: str
    test_input: str = ""  # suggested test input
    severity: str = "medium"  # "high", "medium", "low"
    rationale: str = ""  # why this edge case matters


@dataclass
class EdgeCaseResult:
    """Result of edge case analysis."""
    target: str
    function_name: str = ""
    args: list[str] = field(default_factory=list)
    edge_cases: list[EdgeCase] = field(default_factory=list)
    existing_checks: list[str] = field(default_factory=list)  # what the code already handles
    summary: str = ""


class EdgeCaseSuggester:
    """Suggest edge cases for a function."""

    def __init__(self, config: EdgeCaseConfig):
        self.config = config

    def suggest(self, target: str) -> EdgeCaseResult:
        """Suggest edge cases for a target function."""
        logger.info("Suggesting edge cases for: %s", target)

        result = EdgeCaseResult(target=target)

        # Parse target
        file_path, _, func_name = target.rpartition(":")
        if not file_path or not func_name:
            result.summary = "Use format: file.py:function_name"
            return result

        result.function_name = func_name
        full_path = os.path.join(self.config.cwd, file_path)

        # Parse function
        from code_agents.analysis._ast_helpers import parse_python_file, find_functions

        tree = parse_python_file(full_path)
        if tree is None:
            result.summary = f"Could not parse {file_path}"
            return result

        funcs = find_functions(tree, file_path)
        target_func = next((f for f in funcs if f.name == func_name), None)
        if not target_func:
            result.summary = f"Function '{func_name}' not found"
            return result

        result.args = target_func.args

        # Read function source
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            source = "".join(lines[target_func.line - 1:target_func.end_line])
        except OSError:
            source = ""

        # Analyze and suggest
        self._suggest_from_args(result, target_func.args, target_func.return_annotation)
        self._suggest_from_source(result, source)
        self._detect_existing_checks(result, source)

        result.summary = f"{len(result.edge_cases)} edge cases suggested for {func_name}({', '.join(result.args)})"
        return result

    def _suggest_from_args(self, result: EdgeCaseResult, args: list[str], return_annotation: str):
        """Suggest edge cases based on function arguments."""
        for arg in args:
            if arg in ("self", "cls"):
                continue

            # String args
            if any(hint in arg.lower() for hint in ("name", "path", "url", "text", "message", "query", "key", "id")):
                result.edge_cases.extend([
                    EdgeCase("null", f"Pass None for '{arg}'", f"{arg}=None", "high", "Null inputs are the #1 cause of runtime errors"),
                    EdgeCase("empty", f"Pass empty string for '{arg}'", f'{arg}=""', "high", "Empty strings often cause unexpected behavior"),
                    EdgeCase("unicode", f"Pass unicode/emoji for '{arg}'", f'{arg}="test\\u00e9\\U0001f600"', "medium", "Unicode can break encoding, length checks, regex"),
                    EdgeCase("boundary", f"Pass very long string for '{arg}'", f'{arg}="x" * 10000', "low", "Long inputs may cause performance issues or buffer overflows"),
                ])

            # Numeric args
            if any(hint in arg.lower() for hint in ("count", "size", "limit", "offset", "page", "timeout", "port", "num", "max", "min", "depth", "width", "height", "index")):
                result.edge_cases.extend([
                    EdgeCase("boundary", f"Pass 0 for '{arg}'", f"{arg}=0", "high", "Zero often causes division errors or empty results"),
                    EdgeCase("boundary", f"Pass negative for '{arg}'", f"{arg}=-1", "high", "Negative values often cause unexpected behavior"),
                    EdgeCase("overflow", f"Pass very large number for '{arg}'", f"{arg}=2**31", "medium", "Large numbers may cause overflow or memory issues"),
                ])

            # List/collection args
            if any(hint in arg.lower() for hint in ("list", "items", "data", "records", "entries", "batch", "files")):
                result.edge_cases.extend([
                    EdgeCase("empty", f"Pass empty list for '{arg}'", f"{arg}=[]", "high", "Empty collections are a common edge case"),
                    EdgeCase("null", f"Pass None for '{arg}'", f"{arg}=None", "high", "None instead of empty collection"),
                    EdgeCase("boundary", f"Pass single-item list for '{arg}'", f"{arg}=[item]", "medium", "Single-item lists may hit off-by-one bugs"),
                    EdgeCase("boundary", f"Pass very large list for '{arg}'", f"{arg}=[...] * 10000", "low", "Large inputs test memory and performance"),
                ])

    def _suggest_from_source(self, result: EdgeCaseResult, source: str):
        """Suggest edge cases based on source code patterns."""
        if re.search(r"\.split\(", source):
            result.edge_cases.append(EdgeCase("boundary", "Input with no delimiter for split()", "", "medium", "split() on empty or delimiter-free input"))

        if re.search(r"\[\d+\]|\[-\d+\]", source):
            result.edge_cases.append(EdgeCase("boundary", "Input shorter than indexed position", "", "high", "Fixed index access may cause IndexError"))

        if re.search(r"int\(|float\(", source):
            result.edge_cases.append(EdgeCase("type", "Non-numeric string passed to int()/float()", "", "high", "Type conversion from invalid string"))

        if re.search(r"json\.loads|json\.load", source):
            result.edge_cases.append(EdgeCase("error", "Malformed JSON input", '{"invalid"}', "high", "JSON parsing can fail with JSONDecodeError"))

        if re.search(r"\.get\(|\.pop\(", source):
            result.edge_cases.append(EdgeCase("null", "Dict with missing expected keys", "{}", "medium", "Missing keys return None which may propagate"))

        if re.search(r"open\(|Path\(", source):
            result.edge_cases.extend([
                EdgeCase("error", "File does not exist", "", "high", "FileNotFoundError"),
                EdgeCase("error", "File with no read permissions", "", "medium", "PermissionError"),
            ])

        if re.search(r"requests\.|httpx\.|urllib", source):
            result.edge_cases.extend([
                EdgeCase("error", "Network timeout", "", "high", "TimeoutError from remote service"),
                EdgeCase("error", "HTTP 500 response", "", "high", "Server error response handling"),
                EdgeCase("error", "Connection refused", "", "medium", "ConnectionError when service is down"),
            ])

        if re.search(r"async def|await ", source):
            result.edge_cases.append(EdgeCase("concurrency", "Concurrent calls to this function", "", "medium", "Race conditions with shared state"))

    def _detect_existing_checks(self, result: EdgeCaseResult, source: str):
        """Detect what the code already handles."""
        if "is None" in source or "is not None" in source:
            result.existing_checks.append("None/null checks")
        if "try" in source and "except" in source:
            result.existing_checks.append("Exception handling")
        if "len(" in source:
            result.existing_checks.append("Length/size checks")
        if "isinstance(" in source:
            result.existing_checks.append("Type checking")
        if "raise" in source:
            result.existing_checks.append("Error raising")


def format_edge_cases(result: EdgeCaseResult) -> str:
    """Format edge case suggestions for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Edge Case Suggester: {result.target}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")

    if result.existing_checks:
        lines.append(f"  Already handles: {', '.join(result.existing_checks)}")

    if not result.edge_cases:
        lines.append("\n  No additional edge cases suggested.")
        return "\n".join(lines)

    for category in ("null", "empty", "boundary", "type", "error", "concurrency", "unicode", "overflow"):
        cases = [c for c in result.edge_cases if c.category == category]
        if cases:
            lines.append(f"\n  [{category.upper()}]")
            for c in cases:
                sev_icon = {"high": "X", "medium": "!", "low": "~"}[c.severity]
                lines.append(f"    {sev_icon} {c.description}")
                if c.test_input:
                    lines.append(f"      Test: {c.test_input}")

    lines.append("")
    return "\n".join(lines)
