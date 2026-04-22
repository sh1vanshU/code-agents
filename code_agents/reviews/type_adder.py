"""Type Annotation Adder — scan for untyped functions and infer type hints.

Scans Python source files for functions missing type annotations and uses
heuristic analysis of return statements and parameter usage to infer types.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.type_adder")

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    ".pytest_cache", "htmlcov", "site-packages",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class UntypedFunction:
    """A function missing type annotations."""
    file: str
    line: int
    name: str
    params: list[str] = field(default_factory=list)
    has_return_annotation: bool = False
    has_param_annotations: bool = False
    inferred_return: str = ""
    inferred_params: dict = field(default_factory=dict)


@dataclass
class TypeAddResult:
    """Result of adding type annotations."""
    file: str
    line: int
    name: str
    annotations_added: int = 0
    return_type: str = ""
    param_types: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Return type inference patterns
# ---------------------------------------------------------------------------

_RETURN_PATTERNS = {
    "bool": [
        re.compile(r"\breturn\s+True\b"),
        re.compile(r"\breturn\s+False\b"),
        re.compile(r"\breturn\s+not\s+"),
        re.compile(r"\breturn\s+\w+\s+(?:==|!=|<|>|<=|>=|in\b|not\s+in\b|is\b|is\s+not\b)\s+"),
    ],
    "str": [
        re.compile(r'\breturn\s+["\']'),
        re.compile(r"\breturn\s+f[\"']"),
        re.compile(r"\breturn\s+\w+\.format\("),
        re.compile(r"\breturn\s+\w+\.strip\("),
        re.compile(r"\breturn\s+\w+\.join\("),
        re.compile(r"\breturn\s+str\("),
    ],
    "int": [
        re.compile(r"\breturn\s+\d+\s*$", re.MULTILINE),
        re.compile(r"\breturn\s+len\("),
        re.compile(r"\breturn\s+int\("),
        re.compile(r"\breturn\s+\w+\s*[\+\-\*//%%]\s*\w+"),
    ],
    "float": [
        re.compile(r"\breturn\s+\d+\.\d+"),
        re.compile(r"\breturn\s+float\("),
    ],
    "list": [
        re.compile(r"\breturn\s+\["),
        re.compile(r"\breturn\s+list\("),
        re.compile(r"\breturn\s+sorted\("),
    ],
    "dict": [
        re.compile(r"\breturn\s+\{"),
        re.compile(r"\breturn\s+dict\("),
    ],
    "set": [
        re.compile(r"\breturn\s+set\("),
    ],
    "tuple": [
        re.compile(r"\breturn\s+tuple\("),
        re.compile(r"\breturn\s+\(.*,"),
    ],
    "None": [
        re.compile(r"\breturn\s*$", re.MULTILINE),
        re.compile(r"\breturn\s+None\b"),
    ],
    "Optional": [],  # mixed None + other
}

# Param name heuristic patterns
_PARAM_NAME_HINTS = {
    "name": "str", "path": "str", "url": "str", "text": "str",
    "message": "str", "msg": "str", "key": "str", "value": "str",
    "label": "str", "title": "str", "description": "str", "content": "str",
    "pattern": "str", "prefix": "str", "suffix": "str", "fmt": "str",
    "format": "str", "encoding": "str", "filename": "str", "filepath": "str",
    "count": "int", "index": "int", "idx": "int", "num": "int",
    "size": "int", "limit": "int", "offset": "int", "port": "int",
    "timeout": "int", "max_retries": "int", "retries": "int", "depth": "int",
    "width": "int", "height": "int", "length": "int", "age": "int",
    "enabled": "bool", "verbose": "bool", "debug": "bool", "force": "bool",
    "recursive": "bool", "dry_run": "bool", "quiet": "bool", "strict": "bool",
    "is_valid": "bool", "is_active": "bool", "as_json": "bool",
    "items": "list", "results": "list", "values": "list", "args": "list",
    "names": "list", "files": "list", "paths": "list", "lines": "list",
    "data": "dict", "config": "dict", "options": "dict", "kwargs": "dict",
    "headers": "dict", "params": "dict", "metadata": "dict", "context": "dict",
    "settings": "dict", "mapping": "dict", "env": "dict",
}


class TypeAdder:
    """Scan for untyped functions and add inferred type annotations."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("TypeAdder initialized for %s", cwd)

    def scan(self, path: str = "") -> list[UntypedFunction]:
        """Find all functions missing type hints in the given path."""
        target = Path(self.cwd) / path if path else Path(self.cwd)
        results: list[UntypedFunction] = []

        py_files = self._collect_py_files(target)
        logger.info("Scanning %d Python files for untyped functions", len(py_files))

        for fpath in py_files:
            try:
                source = fpath.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=str(fpath))
            except (SyntaxError, UnicodeDecodeError) as exc:
                logger.debug("Skipping %s: %s", fpath, exc)
                continue

            rel = str(fpath.relative_to(self.cwd))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    untyped = self._check_function(node, rel, source)
                    if untyped:
                        results.append(untyped)

        logger.info("Found %d untyped functions", len(results))
        return results

    def add_types(self, path: str = "", dry_run: bool = False) -> int:
        """Infer and add type annotations to untyped functions. Return count."""
        untyped = self.scan(path)
        if not untyped:
            logger.info("No untyped functions found")
            return 0

        # Group by file
        by_file: dict[str, list[UntypedFunction]] = {}
        for func in untyped:
            by_file.setdefault(func.file, []).append(func)

        count = 0
        for rel_path, funcs in by_file.items():
            fpath = Path(self.cwd) / rel_path
            try:
                source = fpath.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            lines = source.split("\n")
            # Process from bottom to top so line numbers stay valid
            funcs.sort(key=lambda f: f.line, reverse=True)

            for func in funcs:
                ret_type = func.inferred_return or self._infer_return_type(
                    self._get_func_body(lines, func.line - 1)
                )
                param_types = func.inferred_params or self._infer_param_types(
                    func.name, self._get_func_body(lines, func.line - 1)
                )

                if not ret_type and not param_types:
                    continue

                line_idx = func.line - 1
                if line_idx < len(lines):
                    original = lines[line_idx]
                    modified = self._annotate_line(
                        original, func.params, param_types, ret_type,
                        func.has_return_annotation,
                    )
                    if modified != original:
                        lines[line_idx] = modified
                        count += 1

            if not dry_run and count > 0:
                fpath.write_text("\n".join(lines), encoding="utf-8")

        logger.info("Added types to %d functions (dry_run=%s)", count, dry_run)
        return count

    def _infer_return_type(self, func_body: str) -> str:
        """Infer return type from return statements in the function body."""
        if not func_body.strip():
            return ""

        found_types: set[str] = set()
        has_bare_return = False

        for type_name, patterns in _RETURN_PATTERNS.items():
            if type_name == "Optional":
                continue
            for pat in patterns:
                if pat.search(func_body):
                    if type_name == "None":
                        has_bare_return = True
                    else:
                        found_types.add(type_name)
                    break

        if not found_types and has_bare_return:
            return "None"
        if not found_types:
            return ""
        if len(found_types) == 1:
            result = found_types.pop()
            if has_bare_return:
                return f"Optional[{result}]"
            return result
        # Multiple types — too ambiguous
        return ""

    def _infer_param_types(self, func_name: str, func_body: str) -> dict:
        """Infer parameter types from usage patterns and naming conventions."""
        result: dict[str, str] = {}

        # Extract param names from the def line
        match = re.search(r"def\s+\w+\s*\((.*?)\)", func_body, re.DOTALL)
        if not match:
            return result

        params_str = match.group(1)
        params = []
        depth = 0
        current = ""
        for ch in params_str:
            if ch in "([{":
                depth += 1
                current += ch
            elif ch in ")]}":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                params.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            params.append(current.strip())

        for param in params:
            # Skip self, cls, *args, **kwargs, already-annotated
            pname = param.split("=")[0].split(":")[0].strip()
            if pname in ("self", "cls", "") or pname.startswith("*") or ":" in param:
                continue

            # Check naming heuristics
            lower = pname.lower().rstrip("_s")
            for hint_name, hint_type in _PARAM_NAME_HINTS.items():
                if lower == hint_name or lower.endswith(f"_{hint_name}"):
                    result[pname] = hint_type
                    break

            # Check usage patterns in body if not already inferred
            if pname not in result:
                inferred = self._infer_from_usage(pname, func_body)
                if inferred:
                    result[pname] = inferred

        return result

    def _infer_from_usage(self, param: str, body: str) -> str:
        """Infer type from how a parameter is used in the function body."""
        # String methods
        if re.search(rf"\b{re.escape(param)}\.(?:strip|split|replace|upper|lower|startswith|endswith|format|encode|decode)\b", body):
            return "str"
        # List methods
        if re.search(rf"\b{re.escape(param)}\.(?:append|extend|pop|sort|reverse)\b", body):
            return "list"
        # Dict methods
        if re.search(rf"\b{re.escape(param)}\.(?:keys|values|items|get|setdefault|update)\b", body):
            return "dict"
        # Set methods
        if re.search(rf"\b{re.escape(param)}\.(?:add|discard|intersection|union|difference)\b", body):
            return "set"
        # Integer arithmetic
        if re.search(rf"\b{re.escape(param)}\s*[\+\-\*/%]=", body):
            return "int"
        # Boolean checks
        if re.search(rf"\bif\s+{re.escape(param)}\s*:", body) or re.search(rf"\bif\s+not\s+{re.escape(param)}\s*:", body):
            # Could be any truthy type — skip
            pass
        # len() call
        if re.search(rf"\blen\({re.escape(param)}\)", body):
            # Has length — could be str/list/dict
            pass
        # Path-like usage
        if re.search(rf"\bPath\({re.escape(param)}\)", body) or re.search(rf"\bos\.path\.\w+\({re.escape(param)}", body):
            return "str"

        return ""

    # ----- helpers -----

    def _collect_py_files(self, target: Path) -> list[Path]:
        """Collect Python files, skipping excluded directories."""
        if target.is_file() and target.suffix == ".py":
            return [target]
        if not target.is_dir():
            return []

        files: list[Path] = []
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in fnames:
                if fn.endswith(".py"):
                    files.append(Path(root) / fn)
        return sorted(files)

    def _check_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str, source: str,
    ) -> Optional[UntypedFunction]:
        """Check if a function is missing type annotations."""
        # Check return annotation
        has_return = node.returns is not None
        # Check param annotations
        has_all_params = True
        param_names: list[str] = []
        for arg in node.args.args:
            param_names.append(arg.arg)
            if arg.arg not in ("self", "cls") and arg.annotation is None:
                has_all_params = False

        if has_return and has_all_params:
            return None

        lines = source.split("\n")
        body = self._get_func_body(lines, node.lineno - 1)

        untyped = UntypedFunction(
            file=rel_path,
            line=node.lineno,
            name=node.name,
            params=param_names,
            has_return_annotation=has_return,
            has_param_annotations=has_all_params,
        )

        # Pre-infer
        if not has_return:
            untyped.inferred_return = self._infer_return_type(body)
        if not has_all_params:
            untyped.inferred_params = self._infer_param_types(node.name, body)

        return untyped

    def _get_func_body(self, lines: list[str], start: int) -> str:
        """Extract function body from lines starting at the def line."""
        if start >= len(lines):
            return ""

        # Find the end of the function (next def/class at same or less indent, or EOF)
        def_line = lines[start]
        indent = len(def_line) - len(def_line.lstrip())

        end = start + 1
        while end < len(lines):
            line = lines[end]
            stripped = line.lstrip()
            if stripped and not stripped.startswith("#"):
                line_indent = len(line) - len(stripped)
                if line_indent <= indent and (
                    stripped.startswith("def ")
                    or stripped.startswith("class ")
                    or stripped.startswith("@")
                ):
                    break
            end += 1

        return "\n".join(lines[start : min(end, start + 80)])

    def _annotate_line(
        self,
        line: str,
        params: list[str],
        param_types: dict[str, str],
        return_type: str,
        has_return: bool,
    ) -> str:
        """Add type annotations to a function definition line."""
        if not return_type and not param_types:
            return line

        modified = line

        # Add param types
        for pname, ptype in param_types.items():
            # Replace 'param' with 'param: type' but not if already annotated
            pattern = rf"(\b{re.escape(pname)}\b)(?!\s*:)(\s*[,=)])"
            replacement = rf"\1: {ptype}\2"
            modified = re.sub(pattern, replacement, modified, count=1)

        # Add return type
        if return_type and not has_return:
            modified = re.sub(
                r"\)\s*:",
                f") -> {return_type}:",
                modified,
                count=1,
            )

        return modified


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_type_report(untyped: list[UntypedFunction]) -> str:
    """Format a human-readable report of untyped functions."""
    if not untyped:
        return "  All functions have type annotations!"

    parts = [f"  Found {len(untyped)} functions missing type annotations:\n"]

    by_file: dict[str, list[UntypedFunction]] = {}
    for func in untyped:
        by_file.setdefault(func.file, []).append(func)

    for fpath, funcs in sorted(by_file.items()):
        parts.append(f"  {fpath}")
        for f in sorted(funcs, key=lambda x: x.line):
            hints = []
            if f.inferred_return:
                hints.append(f"-> {f.inferred_return}")
            if f.inferred_params:
                hint_strs = [f"{k}: {v}" for k, v in f.inferred_params.items()]
                hints.append(", ".join(hint_strs))
            hint_text = f"  (inferred: {'; '.join(hints)})" if hints else ""
            parts.append(f"    L{f.line}: {f.name}(){hint_text}")
        parts.append("")

    return "\n".join(parts)
