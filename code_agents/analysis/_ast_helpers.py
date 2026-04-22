"""AST helpers — shared utilities for Python AST parsing and analysis.

Used by: explain_code, usage_tracer, call_chain, code_example, import_fixer,
         leak_finder, deadlock_detector, code_audit, arch_reviewer, etc.
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis._ast_helpers")

# Directories to skip during scanning
SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "target", ".gradle", ".idea", ".vscode", ".eggs",
})

PYTHON_EXTS = frozenset({".py"})


@dataclass
class FunctionInfo:
    """Parsed function/method metadata."""
    name: str
    file: str
    line: int
    end_line: int
    args: list[str] = field(default_factory=list)
    return_annotation: str = ""
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    is_async: bool = False
    is_method: bool = False
    class_name: str = ""
    complexity: int = 1  # cyclomatic complexity estimate


@dataclass
class ClassInfo:
    """Parsed class metadata."""
    name: str
    file: str
    line: int
    end_line: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Parsed import statement."""
    module: str
    names: list[str] = field(default_factory=list)  # empty for `import x`
    alias: str = ""
    line: int = 0
    is_from: bool = False  # True for `from x import y`


@dataclass
class CallInfo:
    """A function call found in AST."""
    caller: str  # function that contains this call
    callee: str  # function being called
    line: int = 0
    file: str = ""


def parse_python_file(file_path: str) -> Optional[ast.Module]:
    """Parse a Python file into AST, returning None on failure."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        return ast.parse(source, filename=file_path)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        logger.debug("Failed to parse %s: %s", file_path, exc)
        return None


def find_functions(tree: ast.Module, file_path: str = "") -> list[FunctionInfo]:
    """Extract all function/method definitions from an AST."""
    results: list[FunctionInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Determine if it's a method
            class_name = ""
            is_method = False
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    for child in ast.iter_child_nodes(parent):
                        if child is node:
                            class_name = parent.name
                            is_method = True
                            break

            # Extract args
            args = []
            for arg in node.args.args:
                args.append(arg.arg)

            # Extract decorators
            decorators = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
                elif isinstance(dec, ast.Attribute):
                    decorators.append(ast.dump(dec))

            # Docstring
            docstring = ast.get_docstring(node) or ""

            # Return annotation
            ret_ann = ""
            if node.returns:
                try:
                    ret_ann = ast.unparse(node.returns)
                except Exception:
                    ret_ann = "..."

            # Complexity estimate (count branches)
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                      ast.With, ast.Assert, ast.BoolOp)):
                    complexity += 1

            results.append(FunctionInfo(
                name=node.name,
                file=file_path,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                args=args,
                return_annotation=ret_ann,
                decorators=decorators,
                docstring=docstring,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_method=is_method,
                class_name=class_name,
                complexity=complexity,
            ))
    return results


def find_classes(tree: ast.Module, file_path: str = "") -> list[ClassInfo]:
    """Extract all class definitions from an AST."""
    results: list[ClassInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    bases.append("...")

            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)

            decorators = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)

            results.append(ClassInfo(
                name=node.name,
                file=file_path,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                bases=bases,
                methods=methods,
                docstring=ast.get_docstring(node) or "",
                decorators=decorators,
            ))
    return results


def find_imports(tree: ast.Module, file_path: str = "") -> list[ImportInfo]:
    """Extract all import statements from an AST."""
    results: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append(ImportInfo(
                    module=alias.name,
                    alias=alias.asname or "",
                    line=node.lineno,
                    is_from=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            results.append(ImportInfo(
                module=module,
                names=names,
                line=node.lineno,
                is_from=True,
            ))
    return results


def find_calls(tree: ast.Module, file_path: str = "") -> list[CallInfo]:
    """Extract function calls with their calling context."""
    results: list[CallInfo] = []

    # First, find all function scopes
    function_nodes: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_nodes.append((node.name, node))

    # For each function, find calls within it
    for func_name, func_node in function_nodes:
        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                callee = _resolve_call_name(child)
                if callee:
                    results.append(CallInfo(
                        caller=func_name,
                        callee=callee,
                        line=child.lineno,
                        file=file_path,
                    ))
    return results


def _resolve_call_name(node: ast.Call) -> str:
    """Resolve a Call node to a readable name."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    elif isinstance(func, ast.Attribute):
        parts = []
        current = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def walk_call_graph(cwd: str, extensions: frozenset[str] = PYTHON_EXTS) -> dict[str, set[str]]:
    """Build a function → callees mapping across an entire codebase."""
    graph: dict[str, set[str]] = {}
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            if Path(fname).suffix not in extensions:
                continue
            tree = parse_python_file(fpath)
            if tree is None:
                continue
            for call in find_calls(tree, fpath):
                key = f"{call.file}:{call.caller}" if call.file else call.caller
                graph.setdefault(key, set()).add(call.callee)
    return graph


def scan_python_files(cwd: str) -> list[str]:
    """List all Python files under cwd, skipping standard excludes."""
    result: list[str] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if fname.endswith(".py"):
                result.append(os.path.join(root, fname))
    return result
