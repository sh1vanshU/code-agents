"""Regex-based JavaScript/TypeScript parser for the knowledge graph."""

from __future__ import annotations

import logging
import re

from code_agents.parsers import ModuleInfo, SymbolInfo

logger = logging.getLogger("code_agents.parsers.javascript")

MAX_LINES = 10000

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Functions
_RE_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE
)
_RE_ARROW_CONST = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(", re.MULTILINE
)

# Classes
_RE_CLASS = re.compile(
    r"^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{", re.MULTILINE
)

# Methods (inside class bodies — indented, no function keyword typically)
_RE_METHOD = re.compile(
    r"^\s+(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?(\w+)\s*\(", re.MULTILINE
)

# Imports
_RE_IMPORT_FROM = re.compile(
    r"""^\s*import\s+.+?\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE
)
_RE_REQUIRE = re.compile(
    r"""^\s*(?:const|let|var)\s+\w+\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Exports
_RE_EXPORT_DEFAULT = re.compile(r"^\s*export\s+default\s+", re.MULTILINE)
_RE_EXPORT_NAMED = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)", re.MULTILINE
)
_RE_MODULE_EXPORTS = re.compile(r"^\s*module\.exports\s*=", re.MULTILINE)

# TypeScript extras
_RE_INTERFACE = re.compile(
    r"^\s*(?:export\s+)?interface\s+(\w+)", re.MULTILINE
)
_RE_TYPE_ALIAS = re.compile(
    r"^\s*(?:export\s+)?type\s+(\w+)\s*=", re.MULTILINE
)
_RE_ENUM = re.compile(
    r"^\s*(?:export\s+)?(?:const\s+)?enum\s+(\w+)", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_number(source: str, pos: int) -> int:
    """Return the 1-based line number for a character offset."""
    return source.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_javascript(file_path: str, language: str = "javascript") -> ModuleInfo:
    """Parse a JavaScript or TypeScript file and extract symbols."""
    info = ModuleInfo(file_path=file_path, language=language)

    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines(MAX_LINES * 200)  # rough byte cap
            if len(lines) > MAX_LINES:
                lines = lines[:MAX_LINES]
            source = "".join(lines)
    except OSError:
        logger.debug("Cannot read %s", file_path)
        return info

    # --- Functions ---
    for m in _RE_FUNCTION.finditer(source):
        info.symbols.append(SymbolInfo(
            name=m.group(1),
            kind="function",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=m.group(0).strip(),
        ))

    for m in _RE_ARROW_CONST.finditer(source):
        info.symbols.append(SymbolInfo(
            name=m.group(1),
            kind="function",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=m.group(0).strip(),
        ))

    # --- Classes + methods ---
    for m in _RE_CLASS.finditer(source):
        class_name = m.group(1)
        class_line = _line_number(source, m.start())
        extends = m.group(2) or ""
        sig = f"class {class_name}"
        if extends:
            sig += f" extends {extends}"
        info.symbols.append(SymbolInfo(
            name=class_name,
            kind="class",
            file_path=file_path,
            line_number=class_line,
            signature=sig,
        ))

        # Find methods inside the class body (scan until matching closing brace)
        brace_start = m.end() - 1  # position of opening '{'
        depth = 1
        pos = brace_start + 1
        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1
        class_body = source[brace_start:pos]

        for mm in _RE_METHOD.finditer(class_body):
            method_name = mm.group(1)
            # Skip common false positives
            if method_name in ("if", "for", "while", "switch", "catch", "return", "new", "await", "yield"):
                continue
            info.symbols.append(SymbolInfo(
                name=f"{class_name}.{method_name}",
                kind="method",
                file_path=file_path,
                line_number=_line_number(source, brace_start + mm.start()),
                signature=mm.group(0).strip(),
            ))

    # --- Imports ---
    for m in _RE_IMPORT_FROM.finditer(source):
        info.imports.append(m.group(1))

    for m in _RE_REQUIRE.finditer(source):
        info.imports.append(m.group(1))

    # --- Exports ---
    for m in _RE_EXPORT_DEFAULT.finditer(source):
        info.exports.append("default")

    for m in _RE_EXPORT_NAMED.finditer(source):
        info.exports.append(m.group(1))

    for m in _RE_MODULE_EXPORTS.finditer(source):
        info.exports.append("module.exports")

    # --- TypeScript extras ---
    if language == "typescript":
        for m in _RE_INTERFACE.finditer(source):
            info.symbols.append(SymbolInfo(
                name=m.group(1),
                kind="class",
                file_path=file_path,
                line_number=_line_number(source, m.start()),
                signature=f"interface {m.group(1)}",
            ))

        for m in _RE_TYPE_ALIAS.finditer(source):
            info.symbols.append(SymbolInfo(
                name=m.group(1),
                kind="variable",
                file_path=file_path,
                line_number=_line_number(source, m.start()),
                signature=f"type {m.group(1)}",
            ))

        for m in _RE_ENUM.finditer(source):
            info.symbols.append(SymbolInfo(
                name=m.group(1),
                kind="class",
                file_path=file_path,
                line_number=_line_number(source, m.start()),
                signature=f"enum {m.group(1)}",
            ))

    return info
