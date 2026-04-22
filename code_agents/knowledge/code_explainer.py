"""Code Explanation Engine — pure static analysis, no AI calls.

Reads a code block, parses symbols via ``parsers/``, traces call chains
via grep, identifies side effects, and produces a human-readable
``Explanation``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.knowledge.code_explainer")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Explanation:
    """Result of analysing a code block."""

    file: str
    start_line: int
    end_line: int
    code: str
    summary: str
    call_chain: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    complexity: str = "simple"  # "simple", "moderate", "complex"


# ---------------------------------------------------------------------------
# Side-effect patterns
# ---------------------------------------------------------------------------

_SIDE_EFFECT_PATTERNS: list[tuple[str, str]] = [
    # DB writes
    (r"\b(db|session|cursor|conn|connection)\.(execute|commit|add|merge|delete|flush|rollback)\b", "DB write"),
    (r"\b(insert|update|delete|create_all|drop_all)\b\(", "DB write"),
    # API calls
    (r"\b(requests|httpx|aiohttp|urllib)\.(get|post|put|patch|delete|head|options)\b", "API call"),
    (r"\bfetch\s*\(", "API call"),
    # File I/O
    (r"\bopen\s*\(", "File I/O"),
    (r"\b(os|shutil)\.(remove|unlink|rename|makedirs|mkdir|rmdir|rmtree|write|copy|move)\b", "File I/O"),
    (r"\bPath\([^)]*\)\.(write_text|write_bytes|unlink|rename|mkdir|rmdir|touch)\b", "File I/O"),
    # Subprocess / shell
    (r"\bsubprocess\.(run|call|check_call|check_output|Popen)\b", "Subprocess"),
    (r"\bos\.(system|popen|exec[a-z]*)\b", "Subprocess"),
    # Print / logging (informational)
    (r"\bprint\s*\(", "Console output"),
    (r"\blogger\.(info|warning|error|critical|debug|exception)\b", "Logging"),
    # Messaging / events
    (r"\b(send_email|send_message|publish_event|publish|emit|notify|dispatch)\s*\(", "Event/message"),
    # Network
    (r"\b(socket|smtplib|paramiko)\b", "Network I/O"),
    # Cache writes
    (r"\b(cache|redis|memcache)\.(set|delete|incr|decr|expire|hset|lpush|rpush)\b", "Cache write"),
]

# Compiled for performance
_SIDE_EFFECT_RES = [(re.compile(p, re.IGNORECASE), label) for p, label in _SIDE_EFFECT_PATTERNS]

# Complexity keywords
_COMPLEXITY_KEYWORDS = re.compile(
    r"\b(if|elif|else|for|while|except|and|or|not|assert|raise|try|with|match|case)\b"
)

# Function call pattern (simple heuristic)
_FUNCTION_CALL_RE = re.compile(r"\b([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*\(")

# Function/method definition
_FUNC_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)

# Class definition
_CLASS_DEF_RE = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(file_path: str, cwd: str) -> Path:
    """Resolve a file path relative to cwd, returning an absolute Path."""
    p = Path(file_path)
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _grep_callers(function_name: str, cwd: str, exclude_file: str = "") -> list[str]:
    """Grep across the codebase for call sites of *function_name*.

    Returns a list of ``"file:line: snippet"`` strings (max 20).
    """
    callers: list[str] = []
    pattern = rf"\b{re.escape(function_name)}\s*\("
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.js",
             "--include=*.ts", "--include=*.java", "--include=*.go",
             "-E", pattern, cwd],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines()[:30]:
            # Skip the definition itself
            if "def " + function_name in line:
                continue
            # Skip the excluded file (the file we're explaining)
            if exclude_file and line.startswith(exclude_file):
                continue
            callers.append(line.strip())
            if len(callers) >= 20:
                break
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("Grep for callers failed: %s", exc)
    return callers


# ---------------------------------------------------------------------------
# CodeExplainer
# ---------------------------------------------------------------------------


class CodeExplainer:
    """Static code explanation engine.

    No AI calls -- pure AST parsing, regex matching, and grep-based
    call-chain discovery.
    """

    def __init__(self, cwd: str):
        self.cwd = str(Path(cwd).resolve())

    # -- public API ---------------------------------------------------------

    def explain(
        self,
        file_path: str,
        start_line: int = 0,
        end_line: int = 0,
        function_name: str = "",
    ) -> Explanation:
        """Explain a code block or function.

        Parameters
        ----------
        file_path:
            Path to the source file (absolute or relative to *cwd*).
        start_line / end_line:
            1-based inclusive line range.  ``0`` means "whole file" or
            auto-detect from *function_name*.
        function_name:
            If provided, locate this function/method in the file and
            explain it.  Overrides *start_line* / *end_line*.
        """
        resolved = _resolve_path(file_path, self.cwd)
        if not resolved.is_file():
            logger.warning("File not found: %s", resolved)
            return Explanation(
                file=str(resolved), start_line=0, end_line=0,
                code="", summary=f"File not found: {resolved}",
                complexity="simple",
            )

        source = resolved.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()

        # If function_name given, find its range
        if function_name:
            start_line, end_line = self._find_function_range(
                lines, function_name,
            )
            if start_line == 0:
                return Explanation(
                    file=str(resolved), start_line=0, end_line=0,
                    code="", summary=f"Function '{function_name}' not found in {resolved.name}",
                    complexity="simple",
                )

        code = self._extract_code_block(lines, start_line, end_line)

        # Parse symbols via parsers/
        symbols = self._parse_symbols(str(resolved))

        # Detect the primary function name from the block
        primary_fn = function_name or self._detect_primary_function(code)

        call_chain = self._find_call_chain(str(resolved), primary_fn, code)
        side_effects = self._identify_side_effects(code)
        complexity = self._assess_complexity(code)
        summary = self._generate_summary(
            code, symbols, call_chain, side_effects, str(resolved), start_line, end_line,
        )

        return Explanation(
            file=str(resolved),
            start_line=start_line or 1,
            end_line=end_line or len(lines),
            code=code,
            summary=summary,
            call_chain=call_chain,
            side_effects=side_effects,
            complexity=complexity,
        )

    # -- private helpers ----------------------------------------------------

    def _extract_code_block(
        self, lines: list[str], start: int, end: int,
    ) -> str:
        """Return the code between *start* and *end* (1-based inclusive).

        If both are 0, return the whole file.
        """
        if start <= 0 and end <= 0:
            return "\n".join(lines)
        s = max(start - 1, 0)
        e = min(end, len(lines))
        return "\n".join(lines[s:e])

    def _find_function_range(
        self, lines: list[str], function_name: str,
    ) -> tuple[int, int]:
        """Find 1-based (start, end) line range for a function or method."""
        target_indent: int | None = None
        start = 0
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(("def ", "async def ")):
                # Extract function name
                m = re.match(r"(?:async\s+)?def\s+(\w+)", stripped)
                if m and m.group(1) == function_name:
                    start = i
                    target_indent = len(line) - len(stripped)
                    continue
            if start > 0 and target_indent is not None:
                # End when we find a line at same or lesser indent that isn't blank
                if stripped and not stripped.startswith("#"):
                    current_indent = len(line) - len(stripped)
                    if current_indent <= target_indent and not stripped.startswith(("@",)):
                        return start, i - 1
        if start > 0:
            return start, len(lines)
        return 0, 0

    def _parse_symbols(self, file_path: str) -> list:
        """Parse symbols from file using the parsers package."""
        try:
            from code_agents.parsers import parse_file
            info = parse_file(file_path)
            return info.symbols
        except Exception as exc:
            logger.debug("Symbol parsing failed for %s: %s", file_path, exc)
            return []

    def _detect_primary_function(self, code: str) -> str:
        """Detect the first function/method defined in the code block."""
        m = _FUNC_DEF_RE.search(code)
        if m:
            return m.group(1)
        # Maybe it's a class
        m = _CLASS_DEF_RE.search(code)
        if m:
            return m.group(1)
        return ""

    def _find_call_chain(
        self, file_path: str, function_name: str, code: str,
    ) -> list[str]:
        """Build a call chain: callers -> this function -> callees.

        Returns a flat list of strings like:
          ``["caller_a() -> this_func()", "this_func() -> callee_x()"]``
        """
        chain: list[str] = []

        if not function_name:
            return chain

        # 1. Find callers (who calls this function)
        callers = _grep_callers(function_name, self.cwd, exclude_file=file_path)
        for c in callers[:5]:
            # Extract file:line prefix
            parts = c.split(":", 2)
            if len(parts) >= 2:
                caller_file = Path(parts[0]).name
                chain.append(f"{caller_file} -> {function_name}()")

        # 2. Find callees (what this function calls)
        calls = _FUNCTION_CALL_RE.findall(code)
        # Deduplicate, skip builtins and the function itself
        _builtins = {
            "print", "len", "range", "str", "int", "float", "list", "dict",
            "set", "tuple", "type", "isinstance", "issubclass", "hasattr",
            "getattr", "setattr", "super", "enumerate", "zip", "map",
            "filter", "sorted", "reversed", "any", "all", "min", "max",
            "abs", "sum", "round", "open", "repr", "bool", "bytes",
            "format", "id", "input", "iter", "next", "hash", "hex", "oct",
            "ord", "chr", "vars", "dir",
        }
        seen: set[str] = set()
        for call in calls:
            if call in seen or call in _builtins or call == function_name:
                continue
            seen.add(call)
            chain.append(f"{function_name}() -> {call}()")

        return chain

    def _identify_side_effects(self, code: str) -> list[str]:
        """Identify side effects in the code block."""
        effects: list[str] = []
        seen_labels: set[str] = set()
        for pattern, label in _SIDE_EFFECT_RES:
            matches = pattern.findall(code)
            if matches:
                if label not in seen_labels:
                    # Grab a sample match for context
                    for line in code.splitlines():
                        if pattern.search(line):
                            snippet = line.strip()[:80]
                            effects.append(f"{label}: {snippet}")
                            seen_labels.add(label)
                            break
        return effects

    def _assess_complexity(self, code: str) -> str:
        """Assess code complexity by counting branching keywords.

        Returns ``"simple"`` (<5), ``"moderate"`` (5-15), or ``"complex"`` (>15).
        """
        matches = _COMPLEXITY_KEYWORDS.findall(code)
        count = len(matches)
        if count < 5:
            return "simple"
        elif count <= 15:
            return "moderate"
        else:
            return "complex"

    def _generate_summary(
        self,
        code: str,
        symbols: list,
        call_chain: list[str],
        side_effects: list[str],
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """Build a human-readable summary from analysis results."""
        parts: list[str] = []
        fname = Path(file_path).name

        # Count definitions
        func_defs = _FUNC_DEF_RE.findall(code)
        class_defs = _CLASS_DEF_RE.findall(code)

        if class_defs:
            parts.append(f"Defines class{'es' if len(class_defs) > 1 else ''}: {', '.join(class_defs)}.")
        if func_defs:
            parts.append(
                f"Contains {len(func_defs)} function{'s' if len(func_defs) != 1 else ''}: "
                f"{', '.join(func_defs[:8])}"
                f"{'...' if len(func_defs) > 8 else ''}."
            )

        # Line count
        line_count = len(code.splitlines())
        parts.append(f"{line_count} lines in {fname}")
        if start_line and end_line:
            parts.append(f"(lines {start_line}-{end_line}).")
        else:
            parts[-1] += "."

        # Side effects
        if side_effects:
            effect_labels = list({e.split(":")[0] for e in side_effects})
            parts.append(f"Side effects: {', '.join(effect_labels)}.")

        # Call chain summary
        callees = [
            c for c in call_chain
            if "() -> " in c and (
                not func_defs or not c.endswith(f"-> {func_defs[0]}()")
            )
        ]
        if callees:
            parts.append(f"Calls {len(callees)} other function{'s' if len(callees) != 1 else ''}.")

        return " ".join(parts) if parts else f"Code block in {fname}."


# ---------------------------------------------------------------------------
# Rich formatter
# ---------------------------------------------------------------------------


def format_explanation(exp: Explanation) -> str:
    """Format an Explanation into a rich terminal box."""
    fname = Path(exp.file).name
    header = f"Explanation: {fname}:{exp.start_line}-{exp.end_line}"

    lines: list[str] = []
    lines.append("")
    lines.append(f"  Summary: {exp.summary}")
    lines.append("")

    if exp.call_chain:
        lines.append("  Call chain:")
        for c in exp.call_chain[:10]:
            lines.append(f"    {c}")
        if len(exp.call_chain) > 10:
            lines.append(f"    ... and {len(exp.call_chain) - 10} more")
        lines.append("")

    if exp.side_effects:
        lines.append("  Side effects:")
        _icons = {
            "DB write": "DB",
            "API call": "API",
            "File I/O": "File",
            "Subprocess": "Shell",
            "Console output": "Print",
            "Logging": "Log",
            "Event/message": "Event",
            "Network I/O": "Net",
            "Cache write": "Cache",
        }
        for eff in exp.side_effects:
            label = eff.split(":")[0].strip()
            detail = eff.split(":", 1)[1].strip() if ":" in eff else ""
            icon = _icons.get(label, "?")
            lines.append(f"    [{icon}] {detail}")
        lines.append("")

    # Complexity with branch count
    branch_count = len(_COMPLEXITY_KEYWORDS.findall(exp.code))
    lines.append(f"  Complexity: {exp.complexity} ({branch_count} branches)")
    lines.append("")

    # Build box
    max_width = max((len(l) for l in lines), default=40) + 4
    max_width = max(max_width, len(header) + 6)

    box: list[str] = []
    top = f"+----- {header} " + "-" * max(0, max_width - len(header) - 8) + "+"
    bot = "+" + "-" * (len(top) - 2) + "+"
    box.append(top)
    for l in lines:
        padded = l + " " * max(0, len(top) - 2 - len(l) - 2)
        box.append(f"|{padded}|")
    box.append(bot)

    return "\n".join(box)
