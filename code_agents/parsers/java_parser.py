"""Regex-based Java parser for the knowledge graph."""

from __future__ import annotations

import logging
import re

from code_agents.parsers import ModuleInfo, SymbolInfo

logger = logging.getLogger("code_agents.parsers.java")

MAX_LINES = 10000

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

_RE_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)

_RE_CLASS = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?"
    r"(?:abstract\s+|final\s+|static\s+)*"
    r"class\s+(\w+)"
    r"(?:\s+extends\s+(\w+))?"
    r"(?:\s+implements\s+([\w,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_INTERFACE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?"
    r"(?:abstract\s+|static\s+)*"
    r"interface\s+(\w+)"
    r"(?:\s+extends\s+([\w,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_ENUM = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?"
    r"(?:static\s+)*"
    r"enum\s+(\w+)"
    r"(?:\s+implements\s+([\w,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_METHOD = re.compile(
    r"^\s+(?:public|private|protected)\s+"
    r"(?:static\s+|final\s+|abstract\s+|synchronized\s+|native\s+)*"
    r"(?:<[\w,\s?]+>\s+)?"        # generic return type
    r"([\w<>\[\]?,\s]+?)\s+"      # return type
    r"(\w+)\s*\(",                # method name
    re.MULTILINE,
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

def parse_java(file_path: str) -> ModuleInfo:
    """Parse a Java file and extract symbols."""
    info = ModuleInfo(file_path=file_path, language="java")

    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines(MAX_LINES * 200)
            if len(lines) > MAX_LINES:
                lines = lines[:MAX_LINES]
            source = "".join(lines)
    except OSError:
        logger.debug("Cannot read %s", file_path)
        return info

    # --- Package ---
    pkg_match = _RE_PACKAGE.search(source)
    package_name = pkg_match.group(1) if pkg_match else ""

    # --- Imports ---
    for m in _RE_IMPORT.finditer(source):
        info.imports.append(m.group(1))

    # --- Classes ---
    for m in _RE_CLASS.finditer(source):
        class_name = m.group(1)
        extends = m.group(2) or ""
        implements = m.group(3).strip() if m.group(3) else ""
        sig = f"class {class_name}"
        if extends:
            sig += f" extends {extends}"
        if implements:
            sig += f" implements {implements}"
        info.symbols.append(SymbolInfo(
            name=f"{package_name}.{class_name}" if package_name else class_name,
            kind="class",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=sig,
        ))

    # --- Interfaces ---
    for m in _RE_INTERFACE.finditer(source):
        iface_name = m.group(1)
        extends = m.group(2).strip() if m.group(2) else ""
        sig = f"interface {iface_name}"
        if extends:
            sig += f" extends {extends}"
        info.symbols.append(SymbolInfo(
            name=f"{package_name}.{iface_name}" if package_name else iface_name,
            kind="class",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=sig,
        ))

    # --- Enums ---
    for m in _RE_ENUM.finditer(source):
        enum_name = m.group(1)
        sig = f"enum {enum_name}"
        implements = m.group(2).strip() if m.group(2) else ""
        if implements:
            sig += f" implements {implements}"
        info.symbols.append(SymbolInfo(
            name=f"{package_name}.{enum_name}" if package_name else enum_name,
            kind="class",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=sig,
        ))

    # --- Methods ---
    for m in _RE_METHOD.finditer(source):
        return_type = m.group(1).strip()
        method_name = m.group(2)
        # Skip constructors matched by class regex and common false positives
        if method_name in ("if", "for", "while", "switch", "catch", "return", "new", "throw"):
            continue
        info.symbols.append(SymbolInfo(
            name=method_name,
            kind="method",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=f"{return_type} {method_name}(",
        ))

    # Store package as an export for cross-referencing
    if package_name:
        info.exports.append(package_name)

    return info
