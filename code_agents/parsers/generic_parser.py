"""Regex-based fallback parser for unsupported languages.

Provides best-effort symbol extraction using simple patterns that cover
common function, class, and import declaration syntax across many languages.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from code_agents.parsers import ModuleInfo, SymbolInfo

logger = logging.getLogger("code_agents.parsers.generic")

# ---------------------------------------------------------------------------
# Max lines to read (guard against very large files)
# ---------------------------------------------------------------------------

_MAX_LINES = 10_000

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Function-like definitions.
# Matches: def, func, function, fn, void, int, string, public, private, protected
# followed by an identifier and opening parenthesis.
_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?"
    r"(?:def|func|function|fn|void|int|string|float|double|bool|char|long"
    r"|public|private|protected|static|override|virtual|abstract|final"
    r"|pub(?:\s*\(.*?\))?)\s+"
    r"(?:static\s+|final\s+|override\s+|async\s+)*"
    r"([A-Za-z_]\w*)"
    r"\s*\(",
)

# Class-like definitions.
# Matches: class, struct, interface, enum followed by identifier.
_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+|public\s+|private\s+|protected\s+|final\s+)*"
    r"(class|struct|interface|enum)\s+"
    r"([A-Za-z_]\w*)",
)

# Import statements.
# Matches: import, from ... import, require(...), use, #include, using
_IMPORT_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    # Python / Java / Go / Kotlin / Scala: import foo.bar
    (re.compile(r"^\s*import\s+([^\s;]+)"), 1),
    # Python: from foo import bar
    (re.compile(r"^\s*from\s+([^\s]+)\s+import\b"), 1),
    # JS/TS: require("foo") or require('foo')
    (re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""), 1),
    # JS/TS: import ... from "foo"
    (re.compile(r"""^\s*import\s+.*?from\s+['"]([^'"]+)['"]"""), 1),
    # Rust: use foo::bar
    (re.compile(r"^\s*use\s+([^\s;{]+)"), 1),
    # C/C++: #include <foo> or #include "foo"
    (re.compile(r"""^\s*#\s*include\s+[<"]([^>"]+)[>"]"""), 1),
    # C#: using Foo.Bar;
    (re.compile(r"^\s*using\s+(?!namespace\b)([^\s;=]+)\s*;"), 1),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_generic(file_path: str, language: str = "unknown") -> ModuleInfo:
    """Parse a source file using regex patterns and return symbols and imports.

    This is a best-effort fallback for languages without a dedicated AST
    parser.  It reads at most 10 000 lines to stay safe on large files.

    Parameters
    ----------
    file_path:
        Absolute or relative path to a source file.
    language:
        Language hint (used in the returned ``ModuleInfo``).

    Returns
    -------
    ModuleInfo
        Parsed module information with symbols and imports.
    """
    file_path = str(Path(file_path).resolve())
    info = ModuleInfo(file_path=file_path, language=language)

    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError) as exc:
        logger.debug("Cannot read %s: %s", file_path, exc)
        return info

    lines = raw.splitlines()[:_MAX_LINES]

    for line_no, line in enumerate(lines, start=1):
        # --- Functions ---------------------------------------------------
        m = _FUNCTION_RE.match(line)
        if m:
            name = m.group(1)
            info.symbols.append(SymbolInfo(
                name=name,
                kind="function",
                file_path=file_path,
                line_number=line_no,
                signature=line.strip(),
            ))
            continue

        # --- Classes / structs / interfaces / enums ----------------------
        m = _CLASS_RE.match(line)
        if m:
            kind_word = m.group(1)  # class, struct, etc.
            name = m.group(2)
            info.symbols.append(SymbolInfo(
                name=name,
                kind="class",
                file_path=file_path,
                line_number=line_no,
                signature=line.strip(),
            ))
            continue

        # --- Imports -----------------------------------------------------
        for pattern, group in _IMPORT_PATTERNS:
            m = pattern.search(line)
            if m:
                info.imports.append(m.group(group))
                break

    return info
