"""Python source parser using the ``ast`` standard library module.

Extracts functions, classes, methods, imports, docstrings, and line numbers
from ``.py`` files and returns a :class:`ModuleInfo`.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from code_agents.parsers import ModuleInfo, SymbolInfo

logger = logging.getLogger("code_agents.parsers.python")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_arg(arg: ast.arg) -> str:
    """Format a single function argument with optional annotation."""
    name = arg.arg
    if arg.annotation:
        try:
            name += f": {ast.unparse(arg.annotation)}"
        except Exception:
            pass
    return name


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a human-readable signature string for a function/method."""
    args_parts: list[str] = []

    # Positional-only args
    for a in node.args.posonlyargs:
        args_parts.append(_format_arg(a))
    if node.args.posonlyargs:
        args_parts.append("/")

    # Regular positional args
    for a in node.args.args:
        args_parts.append(_format_arg(a))

    # *args
    if node.args.vararg:
        args_parts.append(f"*{_format_arg(node.args.vararg)}")

    # Keyword-only args
    for a in node.args.kwonlyargs:
        args_parts.append(_format_arg(a))

    # **kwargs
    if node.args.kwarg:
        args_parts.append(f"**{_format_arg(node.args.kwarg)}")

    sig = f"def {node.name}({', '.join(args_parts)})"

    if node.returns:
        try:
            sig += f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    return sig


def _format_class_signature(node: ast.ClassDef) -> str:
    """Build a human-readable signature for a class definition."""
    bases: list[str] = []
    for base in node.bases:
        try:
            bases.append(ast.unparse(base))
        except Exception:
            bases.append("?")
    if bases:
        return f"class {node.name}({', '.join(bases)})"
    return f"class {node.name}"


def _first_line_docstring(node: ast.AST) -> str:
    """Extract the first line of a docstring from a node, if present."""
    doc = ast.get_docstring(node)
    if doc:
        return doc.split("\n")[0].strip()
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_python(file_path: str) -> ModuleInfo:
    """Parse a Python source file and return its symbols and imports.

    Parameters
    ----------
    file_path:
        Absolute or relative path to a ``.py`` file.

    Returns
    -------
    ModuleInfo
        Parsed module information with symbols and imports.
    """
    file_path = str(Path(file_path).resolve())
    info = ModuleInfo(file_path=file_path, language="python")

    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError) as exc:
        logger.debug("Cannot read %s: %s", file_path, exc)
        return info

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        logger.debug("Syntax error in %s: %s", file_path, exc)
        return info

    # --- Walk top-level nodes ------------------------------------------------
    for node in ast.iter_child_nodes(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            info.imports.append(module)

        # Top-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.symbols.append(SymbolInfo(
                name=node.name,
                kind="function",
                file_path=file_path,
                line_number=node.lineno,
                signature=_format_signature(node),
                docstring=_first_line_docstring(node),
            ))

        # Classes (and their methods)
        elif isinstance(node, ast.ClassDef):
            info.symbols.append(SymbolInfo(
                name=node.name,
                kind="class",
                file_path=file_path,
                line_number=node.lineno,
                signature=_format_class_signature(node),
                docstring=_first_line_docstring(node),
            ))

            # Methods inside the class
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    info.symbols.append(SymbolInfo(
                        name=f"{node.name}.{child.name}",
                        kind="method",
                        file_path=file_path,
                        line_number=child.lineno,
                        signature=_format_signature(child),
                        docstring=_first_line_docstring(child),
                    ))

    return info
