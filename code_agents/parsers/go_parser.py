"""Regex-based Go parser for the knowledge graph."""

from __future__ import annotations

import logging
import re

from code_agents.parsers import ModuleInfo, SymbolInfo

logger = logging.getLogger("code_agents.parsers.go")

MAX_LINES = 10000

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_PACKAGE = re.compile(r"^\s*package\s+(\w+)", re.MULTILINE)

# Single-line import: import "fmt"
_RE_IMPORT_SINGLE = re.compile(
    r"""^\s*import\s+(?:\w+\s+)?["']([^"']+)["']""", re.MULTILINE
)

# Multi-line import block: import ( ... )
_RE_IMPORT_BLOCK = re.compile(
    r"^\s*import\s*\((.*?)\)", re.MULTILINE | re.DOTALL
)
_RE_IMPORT_LINE = re.compile(r"""["']([^"']+)["']""")

# Functions: func name( and func (receiver) name(
_RE_FUNC = re.compile(
    r"^\s*func\s+(\w+)\s*\(", re.MULTILINE
)
_RE_METHOD = re.compile(
    r"^\s*func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+(\w+)\s*\(", re.MULTILINE
)

# type Name struct {
_RE_STRUCT = re.compile(
    r"^\s*type\s+(\w+)\s+struct\s*\{", re.MULTILINE
)

# type Name interface {
_RE_INTERFACE = re.compile(
    r"^\s*type\s+(\w+)\s+interface\s*\{", re.MULTILINE
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

def parse_go(file_path: str) -> ModuleInfo:
    """Parse a Go file and extract symbols."""
    info = ModuleInfo(file_path=file_path, language="go")

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
    if package_name:
        info.exports.append(package_name)

    # --- Imports ---
    for m in _RE_IMPORT_SINGLE.finditer(source):
        info.imports.append(m.group(1))

    for m in _RE_IMPORT_BLOCK.finditer(source):
        block = m.group(1)
        for line_m in _RE_IMPORT_LINE.finditer(block):
            info.imports.append(line_m.group(1))

    # --- Methods (receiver functions) — parse before plain functions so we
    #     can skip receiver funcs when matching plain func pattern ---
    method_positions: set[int] = set()
    for m in _RE_METHOD.finditer(source):
        receiver_type = m.group(1)
        method_name = m.group(2)
        line = _line_number(source, m.start())
        method_positions.add(line)
        info.symbols.append(SymbolInfo(
            name=f"{receiver_type}.{method_name}",
            kind="method",
            file_path=file_path,
            line_number=line,
            signature=m.group(0).strip(),
        ))

    # --- Functions ---
    for m in _RE_FUNC.finditer(source):
        func_name = m.group(1)
        line = _line_number(source, m.start())
        # Skip if this line was already captured as a method
        if line in method_positions:
            continue
        info.symbols.append(SymbolInfo(
            name=func_name,
            kind="function",
            file_path=file_path,
            line_number=line,
            signature=m.group(0).strip(),
        ))

    # --- Structs ---
    for m in _RE_STRUCT.finditer(source):
        struct_name = m.group(1)
        info.symbols.append(SymbolInfo(
            name=struct_name,
            kind="class",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=f"type {struct_name} struct",
        ))

    # --- Interfaces ---
    for m in _RE_INTERFACE.finditer(source):
        iface_name = m.group(1)
        info.symbols.append(SymbolInfo(
            name=iface_name,
            kind="class",
            file_path=file_path,
            line_number=_line_number(source, m.start()),
            signature=f"type {iface_name} interface",
        ))

    return info
