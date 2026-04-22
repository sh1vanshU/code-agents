"""Explain Code — takes a function/class/module path and generates plain-English explanation.

Analyzes the code structure, dependencies, edge cases, and how it fits
in the overall system. Works with Python, JS/TS, Java, Go.

Usage:
    from code_agents.knowledge.explain_code import CodeExplainer
    explainer = CodeExplainer("/path/to/repo")
    result = explainer.explain("code_agents/stream.py:build_prompt")
    print(format_explanation(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.explain_code")


@dataclass
class ExplainConfig:
    """Configuration for code explanation."""
    cwd: str = "."
    include_edge_cases: bool = True
    include_dependencies: bool = True
    include_callers: bool = True
    max_depth: int = 2


@dataclass
class CodeExplanation:
    """Result of explaining a piece of code."""
    target: str  # what was explained (file:function)
    target_type: str  # "function", "class", "module", "method"
    summary: str  # one-line summary
    detailed: str  # multi-paragraph explanation
    signature: str  # function signature or class definition
    docstring: str  # existing docstring
    source_lines: int = 0  # line count
    complexity: int = 1  # cyclomatic complexity
    edge_cases: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # what it imports/uses
    callers: list[str] = field(default_factory=list)  # what calls it
    side_effects: list[str] = field(default_factory=list)  # I/O, mutations, etc.
    related_files: list[str] = field(default_factory=list)


class CodeExplainer:
    """Explain code constructs in plain English."""

    def __init__(self, config: ExplainConfig):
        self.config = config
        self.cwd = config.cwd

    def explain(self, target: str) -> CodeExplanation:
        """Explain a code target (file:function, file:class, or file)."""
        logger.info("Explaining: %s", target)

        file_path, symbol = self._parse_target(target)
        if not file_path:
            return CodeExplanation(
                target=target, target_type="unknown",
                summary=f"Could not resolve target: {target}",
                detailed="Target not found. Use format: file.py:function_name or file.py:ClassName",
                signature="", docstring="",
            )

        full_path = os.path.join(self.cwd, file_path) if not os.path.isabs(file_path) else file_path

        if not os.path.exists(full_path):
            return CodeExplanation(
                target=target, target_type="unknown",
                summary=f"File not found: {file_path}",
                detailed=f"The file {file_path} does not exist in {self.cwd}",
                signature="", docstring="",
            )

        if full_path.endswith(".py"):
            return self._explain_python(full_path, file_path, symbol)
        else:
            return self._explain_generic(full_path, file_path, symbol)

    def _parse_target(self, target: str) -> tuple[str, str]:
        """Parse 'file.py:function' or 'file.py' into (file, symbol)."""
        if ":" in target:
            parts = target.rsplit(":", 1)
            return parts[0], parts[1]
        return target, ""

    def _explain_python(self, full_path: str, rel_path: str, symbol: str) -> CodeExplanation:
        """Explain Python code using AST analysis."""
        from code_agents.analysis._ast_helpers import (
            parse_python_file, find_functions, find_classes,
            find_imports, find_calls,
        )

        tree = parse_python_file(full_path)
        if tree is None:
            return CodeExplanation(
                target=f"{rel_path}:{symbol}" if symbol else rel_path,
                target_type="unknown",
                summary=f"Failed to parse {rel_path}",
                detailed="Could not parse the Python file — syntax error or encoding issue.",
                signature="", docstring="",
            )

        functions = find_functions(tree, rel_path)
        classes = find_classes(tree, rel_path)
        imports = find_imports(tree, rel_path)
        calls = find_calls(tree, rel_path)

        # If no symbol specified, explain the module
        if not symbol:
            return self._explain_module(rel_path, full_path, functions, classes, imports)

        # Find matching function
        for func in functions:
            if func.name == symbol:
                return self._explain_function(rel_path, func, imports, calls, full_path)

        # Find matching class
        for cls in classes:
            if cls.name == symbol:
                return self._explain_class(rel_path, cls, functions, imports, full_path)

        return CodeExplanation(
            target=f"{rel_path}:{symbol}",
            target_type="unknown",
            summary=f"Symbol '{symbol}' not found in {rel_path}",
            detailed=f"Available: functions={[f.name for f in functions]}, classes={[c.name for c in classes]}",
            signature="", docstring="",
        )

    def _explain_module(self, rel_path, full_path, functions, classes, imports):
        """Explain a Python module."""
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            source = ""

        # Module docstring
        import ast
        try:
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree) or ""
        except SyntaxError:
            docstring = ""

        line_count = source.count("\n") + 1
        func_names = [f.name for f in functions if not f.name.startswith("_")]
        class_names = [c.name for c in classes]
        import_modules = [i.module for i in imports]

        summary = f"Module with {len(functions)} functions, {len(classes)} classes ({line_count} lines)"
        detailed_parts = []
        if docstring:
            detailed_parts.append(f"Purpose: {docstring.split(chr(10))[0]}")
        if class_names:
            detailed_parts.append(f"Classes: {', '.join(class_names)}")
        if func_names:
            detailed_parts.append(f"Public functions: {', '.join(func_names[:15])}")
        if import_modules:
            detailed_parts.append(f"Dependencies: {', '.join(sorted(set(import_modules))[:10])}")

        return CodeExplanation(
            target=rel_path,
            target_type="module",
            summary=summary,
            detailed="\n".join(detailed_parts),
            signature="",
            docstring=docstring,
            source_lines=line_count,
            dependencies=list(set(import_modules)),
            related_files=[],
        )

    def _explain_function(self, rel_path, func, imports, calls, full_path):
        """Explain a Python function."""
        # Build signature
        args_str = ", ".join(func.args)
        ret = f" -> {func.return_annotation}" if func.return_annotation else ""
        prefix = "async def" if func.is_async else "def"
        signature = f"{prefix} {func.name}({args_str}){ret}"

        # Find what this function calls
        func_calls = [c.callee for c in calls if c.caller == func.name]

        # Detect edge cases
        edge_cases = self._detect_edge_cases(full_path, func.line, func.end_line)

        # Detect side effects
        side_effects = self._detect_side_effects(full_path, func.line, func.end_line)

        # Build detailed explanation
        parts = []
        if func.docstring:
            parts.append(func.docstring)
        parts.append(f"Defined at {rel_path}:{func.line} ({func.end_line - func.line + 1} lines)")
        if func.is_method:
            parts.append(f"Method of class {func.class_name}")
        if func.decorators:
            parts.append(f"Decorators: {', '.join(func.decorators)}")
        parts.append(f"Cyclomatic complexity: {func.complexity}")
        if func_calls:
            parts.append(f"Calls: {', '.join(set(func_calls)[:10])}")
        if side_effects:
            parts.append(f"Side effects: {', '.join(side_effects)}")
        if edge_cases:
            parts.append(f"Edge cases to consider: {', '.join(edge_cases)}")

        summary = func.docstring.split("\n")[0] if func.docstring else f"{'Async f' if func.is_async else 'F'}unction with {func.complexity} branches"

        # Find callers
        callers = []
        if self.config.include_callers:
            callers = [c.caller for c in calls if c.callee == func.name]

        return CodeExplanation(
            target=f"{rel_path}:{func.name}",
            target_type="method" if func.is_method else "function",
            summary=summary,
            detailed="\n".join(parts),
            signature=signature,
            docstring=func.docstring,
            source_lines=func.end_line - func.line + 1,
            complexity=func.complexity,
            edge_cases=edge_cases,
            dependencies=func_calls,
            callers=callers,
            side_effects=side_effects,
        )

    def _explain_class(self, rel_path, cls, functions, imports, full_path):
        """Explain a Python class."""
        methods = [f for f in functions if f.class_name == cls.name]
        public_methods = [m.name for m in methods if not m.name.startswith("_")]
        private_methods = [m.name for m in methods if m.name.startswith("_") and m.name != "__init__"]

        signature = f"class {cls.name}"
        if cls.bases:
            signature += f"({', '.join(cls.bases)})"

        parts = []
        if cls.docstring:
            parts.append(cls.docstring)
        parts.append(f"Defined at {rel_path}:{cls.line} ({cls.end_line - cls.line + 1} lines)")
        if cls.bases:
            parts.append(f"Inherits from: {', '.join(cls.bases)}")
        if public_methods:
            parts.append(f"Public methods: {', '.join(public_methods)}")
        if private_methods:
            parts.append(f"Private methods: {', '.join(private_methods)}")
        if cls.decorators:
            parts.append(f"Decorators: {', '.join(cls.decorators)}")

        summary = cls.docstring.split("\n")[0] if cls.docstring else f"Class with {len(methods)} methods"

        return CodeExplanation(
            target=f"{rel_path}:{cls.name}",
            target_type="class",
            summary=summary,
            detailed="\n".join(parts),
            signature=signature,
            docstring=cls.docstring,
            source_lines=cls.end_line - cls.line + 1,
            dependencies=[],
            related_files=[],
        )

    def _explain_generic(self, full_path, rel_path, symbol):
        """Explain non-Python files with basic analysis."""
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            source = ""

        line_count = source.count("\n") + 1
        ext = Path(full_path).suffix

        return CodeExplanation(
            target=rel_path,
            target_type="module",
            summary=f"{ext} file with {line_count} lines",
            detailed=f"File: {rel_path}\nType: {ext}\nLines: {line_count}",
            signature="",
            docstring="",
            source_lines=line_count,
        )

    def _detect_edge_cases(self, file_path: str, start: int, end: int) -> list[str]:
        """Detect potential edge cases in a code range."""
        edges: list[str] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[start - 1:end]
        except (OSError, IndexError):
            return edges

        source = "".join(lines)
        if "None" in source or "null" in source:
            edges.append("None/null input handling")
        if "[]" in source or "list()" in source:
            edges.append("Empty collection handling")
        if "try" in source and "except" in source:
            edges.append("Exception paths")
        if "timeout" in source.lower():
            edges.append("Timeout scenarios")
        if "len(" in source:
            edges.append("Empty/large input sizes")
        if re.search(r"[\[/]0\]?", source):
            edges.append("Division by zero / index zero")
        if "async" in source:
            edges.append("Concurrent execution ordering")
        return edges

    def _detect_side_effects(self, file_path: str, start: int, end: int) -> list[str]:
        """Detect side effects in a code range."""
        effects: list[str] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[start - 1:end]
        except (OSError, IndexError):
            return effects

        source = "".join(lines)
        if re.search(r"\.(write|save|insert|update|delete|remove|create)\(", source):
            effects.append("writes data")
        if re.search(r"(subprocess|os\.system|os\.popen)", source):
            effects.append("executes shell commands")
        if re.search(r"(open|Path.*write|shutil)", source):
            effects.append("file I/O")
        if re.search(r"(requests\.|httpx\.|urllib|aiohttp)", source):
            effects.append("HTTP requests")
        if "logger." in source or "logging." in source:
            effects.append("logging")
        if re.search(r"(print|sys\.stdout)", source):
            effects.append("console output")
        return effects


def format_explanation(result: CodeExplanation) -> str:
    """Format explanation for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.target}  ({result.target_type})")
    lines.append(f"{'=' * 60}")

    if result.signature:
        lines.append(f"\n  Signature: {result.signature}")
    lines.append(f"\n  Summary: {result.summary}")
    lines.append(f"  Lines: {result.source_lines}  |  Complexity: {result.complexity}")

    if result.detailed:
        lines.append(f"\n  Details:")
        for detail_line in result.detailed.split("\n"):
            lines.append(f"    {detail_line}")

    if result.edge_cases:
        lines.append(f"\n  Edge Cases:")
        for ec in result.edge_cases:
            lines.append(f"    • {ec}")

    if result.side_effects:
        lines.append(f"\n  Side Effects:")
        for se in result.side_effects:
            lines.append(f"    ⚡ {se}")

    if result.dependencies:
        lines.append(f"\n  Dependencies: {', '.join(result.dependencies[:10])}")

    if result.callers:
        lines.append(f"  Called by: {', '.join(result.callers[:10])}")

    lines.append("")
    return "\n".join(lines)
