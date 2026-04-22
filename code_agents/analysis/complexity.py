"""Code Complexity Report — per-function cyclomatic complexity and nesting depth."""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.complexity")

_SKIP_DIRS = frozenset({
    '.git', '__pycache__', 'venv', '.venv', 'node_modules',
    '.tox', 'dist', 'build', '.eggs', 'target', '.gradle', '.mvn', '.next',
})

# Java control-flow keywords for regex-based analysis
_JAVA_KEYWORDS = re.compile(
    r'\b(if|else\s+if|else|for|while|catch|case|&&|\|\|)\b'
)


@dataclass
class FunctionComplexity:
    """Complexity metrics for a single function/method."""

    file: str
    name: str
    line: int
    cyclomatic: int
    nesting_depth: int

    @property
    def rating(self) -> str:
        """A-F rating based on cyclomatic complexity."""
        if self.cyclomatic <= 5:
            return "A"
        elif self.cyclomatic <= 10:
            return "B"
        elif self.cyclomatic <= 20:
            return "C"
        elif self.cyclomatic <= 30:
            return "D"
        elif self.cyclomatic <= 50:
            return "E"
        else:
            return "F"


@dataclass
class FileComplexity:
    """Aggregate complexity for a file."""

    file: str
    functions: list[FunctionComplexity] = field(default_factory=list)

    @property
    def total_complexity(self) -> int:
        return sum(f.cyclomatic for f in self.functions)

    @property
    def avg_complexity(self) -> float:
        if not self.functions:
            return 0.0
        return self.total_complexity / len(self.functions)

    @property
    def most_complex(self) -> Optional[FunctionComplexity]:
        if not self.functions:
            return None
        return max(self.functions, key=lambda f: f.cyclomatic)


@dataclass
class ComplexityReport:
    """Full repo complexity report."""

    repo_path: str
    language: str
    files: list[FileComplexity] = field(default_factory=list)

    @property
    def total_functions(self) -> int:
        return sum(len(f.functions) for f in self.files)

    @property
    def total_complexity(self) -> int:
        return sum(f.total_complexity for f in self.files)

    @property
    def avg_complexity(self) -> float:
        total = self.total_functions
        if total == 0:
            return 0.0
        return self.total_complexity / total


class ComplexityAnalyzer:
    """Measures cyclomatic complexity and nesting depth per function."""

    def __init__(self, cwd: str, language: Optional[str] = None):
        self.cwd = cwd
        self.language = language or self._detect_language()
        self.report = ComplexityReport(repo_path=cwd, language=self.language)
        logger.info("ComplexityAnalyzer initialized — repo=%s lang=%s", cwd, self.language)

    def _detect_language(self) -> str:
        markers = {
            "python":     ("pyproject.toml", "setup.py", "requirements.txt"),
            "java":       ("pom.xml", "build.gradle", "build.gradle.kts"),
        }
        for lang, files in markers.items():
            for f in files:
                if os.path.exists(os.path.join(self.cwd, f)):
                    return lang
        return "unknown"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> ComplexityReport:
        """Analyze all source files and return the complexity report."""
        logger.info("Starting complexity analysis for %s (%s)", self.cwd, self.language)

        if self.language == "python":
            self._analyze_python()
        elif self.language == "java":
            self._analyze_java()

        return self.report

    # ------------------------------------------------------------------
    # Python — AST-based
    # ------------------------------------------------------------------

    def _analyze_python(self):
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    source = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                    tree = ast.parse(source, filename=rel)
                    file_cx = self._analyze_python_file(rel, tree)
                    if file_cx.functions:
                        self.report.files.append(file_cx)
                except (SyntaxError, UnicodeDecodeError):
                    logger.debug("Skipping unparseable file: %s", rel)

    def _analyze_python_file(self, rel_path: str, tree: ast.Module) -> FileComplexity:
        file_cx = FileComplexity(file=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = self._python_cyclomatic(node)
                depth = self._python_nesting_depth(node)
                file_cx.functions.append(FunctionComplexity(
                    file=rel_path,
                    name=node.name,
                    line=node.lineno,
                    cyclomatic=cc,
                    nesting_depth=depth,
                ))
        return file_cx

    def _python_cyclomatic(self, node: ast.AST) -> int:
        """Count cyclomatic complexity: 1 + decision points."""
        cc = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                # and/or add len(values) - 1 decision points
                cc += len(child.values) - 1
        return cc

    def _python_nesting_depth(self, node: ast.AST, depth: int = 0) -> int:
        """Find maximum nesting depth in a function."""
        max_depth = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                  ast.Try, ast.ExceptHandler)):
                child_depth = self._python_nesting_depth(child, depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self._python_nesting_depth(child, depth)
                max_depth = max(max_depth, child_depth)
        return max_depth

    # ------------------------------------------------------------------
    # Java — regex-based
    # ------------------------------------------------------------------

    def _analyze_java(self):
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)
                try:
                    source = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                    file_cx = self._analyze_java_file(rel, source)
                    if file_cx.functions:
                        self.report.files.append(file_cx)
                except UnicodeDecodeError:
                    logger.debug("Skipping unreadable file: %s", rel)

    def _analyze_java_file(self, rel_path: str, source: str) -> FileComplexity:
        file_cx = FileComplexity(file=rel_path)
        # Find methods: access-modifier return-type name(...)
        method_pattern = re.compile(
            r'(?:public|private|protected|static|\s)+\s+\w+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{',
        )
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            m = method_pattern.search(line)
            if m:
                method_name = m.group(1)
                body = self._extract_java_method_body(lines, i - 1)
                cc = 1 + len(_JAVA_KEYWORDS.findall(body))
                depth = self._java_nesting_depth(body)
                file_cx.functions.append(FunctionComplexity(
                    file=rel_path,
                    name=method_name,
                    line=i,
                    cyclomatic=cc,
                    nesting_depth=depth,
                ))
        return file_cx

    def _extract_java_method_body(self, lines: list[str], start_idx: int) -> str:
        """Extract method body by brace counting."""
        depth = 0
        body_lines = []
        started = False
        for line in lines[start_idx:]:
            for ch in line:
                if ch == '{':
                    depth += 1
                    started = True
                elif ch == '}':
                    depth -= 1
            body_lines.append(line)
            if started and depth <= 0:
                break
        return '\n'.join(body_lines)

    def _java_nesting_depth(self, body: str) -> int:
        """Estimate nesting by counting max brace depth."""
        max_d = 0
        d = 0
        for ch in body:
            if ch == '{':
                d += 1
                max_d = max(max_d, d)
            elif ch == '}':
                d -= 1
        # Subtract 1 for the method body itself
        return max(0, max_d - 1)


def format_complexity_report(report: ComplexityReport) -> str:
    """Format complexity report as a table."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"  Complexity Report — {report.language}")
    lines.append("  " + "=" * 70)
    lines.append("")

    if not report.files:
        lines.append("  No functions found to analyze.")
        return "\n".join(lines)

    # Header
    lines.append(f"  {'File':<35} {'Function':<25} {'CC':>4} {'Depth':>6} {'Rating':>7}")
    lines.append("  " + "-" * 80)

    all_funcs = []
    for fc in report.files:
        for fn in fc.functions:
            all_funcs.append(fn)

    # Sort by complexity descending
    all_funcs.sort(key=lambda f: f.cyclomatic, reverse=True)

    for fn in all_funcs[:50]:  # top 50
        fname = fn.file if len(fn.file) <= 34 else "..." + fn.file[-31:]
        funcname = fn.name if len(fn.name) <= 24 else fn.name[:21] + "..."
        lines.append(f"  {fname:<35} {funcname:<25} {fn.cyclomatic:>4} {fn.nesting_depth:>6} {fn.rating:>7}")

    lines.append("")
    lines.append(f"  Total functions: {report.total_functions}")
    lines.append(f"  Average complexity: {report.avg_complexity:.1f}")
    lines.append(f"  Total complexity: {report.total_complexity}")

    # Rating distribution
    dist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
    for fn in all_funcs:
        dist[fn.rating] += 1
    lines.append(f"  Rating distribution: " + ", ".join(f"{k}={v}" for k, v in dist.items() if v))

    return "\n".join(lines)
