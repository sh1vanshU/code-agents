"""Code smell detector — pure AST/regex-based analysis for Python and other languages.

Detects: god classes, long methods, long param lists, deep nesting, feature envy,
primitive obsession, shotgun surgery (git history), and data clumps.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.code_smell")

# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class SmellFinding:
    file: str
    line: int
    smell_type: str
    severity: str  # "critical", "warning", "info"
    message: str
    metric: str = ""  # e.g., "523 lines", "8 params"


@dataclass
class SmellReport:
    findings: list[SmellFinding] = field(default_factory=list)
    score: int = 100  # 0-100 (100=clean)
    by_type: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)


# ── Constants ───────────────────────────────────────────────────────────────

_PYTHON_EXTS = {".py"}
_SUPPORTED_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go"}

_GOD_CLASS_WARN = 500
_GOD_CLASS_CRIT = 1000

_LONG_METHOD_WARN = 50
_LONG_METHOD_CRIT = 100

_LONG_PARAMS_WARN = 5
_LONG_PARAMS_CRIT = 8

_DEEP_NESTING_WARN = 4
_DEEP_NESTING_CRIT = 6

_PRIMITIVE_OBSESSION_THRESHOLD = 3
_DATA_CLUMP_THRESHOLD = 3
_SHOTGUN_FILE_THRESHOLD = 5

# Penalty per finding for score calculation
_PENALTY = {"critical": 10, "warning": 3, "info": 1}

# Regex for function definitions in non-Python languages
_FUNC_RE = {
    ".js":   re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ".ts":   re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ".jsx":  re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ".tsx":  re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ".java": re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
    ".go":   re.compile(r"^func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(([^)]*)\)", re.MULTILINE),
}

# Arrow / method patterns for JS/TS
_ARROW_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
    re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"^[ \t]*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _iter_python_files(root: str, target: str = "") -> list[str]:
    """Yield .py files under root (or a specific file)."""
    if target:
        full = os.path.join(root, target) if not os.path.isabs(target) else target
        if os.path.isfile(full) and full.endswith(".py"):
            return [full]
        if os.path.isdir(full):
            root = full
        else:
            return []
    result: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden dirs and common non-source dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build",
        )]
        for fn in filenames:
            if fn.endswith(".py"):
                result.append(os.path.join(dirpath, fn))
    return result


def _iter_source_files(root: str, target: str = "") -> list[str]:
    """Yield all supported source files under root (or a specific target)."""
    if target:
        full = os.path.join(root, target) if not os.path.isabs(target) else target
        if os.path.isfile(full):
            ext = os.path.splitext(full)[1]
            return [full] if ext in _SUPPORTED_EXTS else []
        if os.path.isdir(full):
            root = full
        else:
            return []
    result: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build",
        )]
        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            if ext in _SUPPORTED_EXTS:
                result.append(os.path.join(dirpath, fn))
    return result


def _read_lines(path: str) -> list[str]:
    """Read file lines, return empty list on error."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


def _relative(path: str, root: str) -> str:
    """Make path relative to root for display."""
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _indent_level(line: str) -> int:
    """Count indentation level (spaces/4 or tabs)."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return 0
    indent = len(line) - len(stripped)
    # Normalize: 4 spaces = 1 level, 2 spaces = 1 level (for JS), tab = 1 level
    tabs = line.count("\t", 0, indent)
    spaces = indent - tabs
    return tabs + (spaces // 4 if spaces >= 4 else spaces // 2 if spaces >= 2 else 0)


# ── Detector ────────────────────────────────────────────────────────────────

class CodeSmellDetector:
    """Pure code-scanning smell detector using AST for Python, regex for others."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CodeSmellDetector initialized for %s", cwd)

    def scan(self, target: str = "") -> SmellReport:
        """Run all smell checks, aggregate results into a SmellReport."""
        findings: list[SmellFinding] = []
        files = _iter_source_files(self.cwd, target)
        logger.info("Scanning %d files for code smells", len(files))

        for path in files:
            findings.extend(self._check_god_class(path))
            findings.extend(self._check_long_method(path))
            findings.extend(self._check_long_params(path))
            findings.extend(self._check_deep_nesting(path))
            if path.endswith(".py"):
                findings.extend(self._check_feature_envy(path))
                findings.extend(self._check_primitive_obsession(path))
                findings.extend(self._check_data_clumps(path))

        # Shotgun surgery uses git history, not per-file
        findings.extend(self._check_shotgun_surgery())

        # Aggregate
        by_type: dict[str, int] = Counter()
        by_severity: dict[str, int] = Counter()
        for f in findings:
            by_type[f.smell_type] += 1
            by_severity[f.severity] += 1

        # Score: start at 100, deduct penalties
        penalty = sum(_PENALTY.get(f.severity, 1) for f in findings)
        score = max(0, 100 - penalty)

        report = SmellReport(
            findings=findings,
            score=score,
            by_type=dict(by_type),
            by_severity=dict(by_severity),
        )
        logger.info("Scan complete: score=%d, findings=%d", score, len(findings))
        return report

    # ── Individual checks ───────────────────────────────────────────────

    def _check_god_class(self, path: str) -> list[SmellFinding]:
        """Files/classes > 500 lines -> warning, > 1000 -> critical."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        total = len(lines)
        rel = _relative(path, self.cwd)

        if total > _GOD_CLASS_CRIT:
            findings.append(SmellFinding(
                file=rel, line=1, smell_type="god-class", severity="critical",
                message=f"File has {total} lines (>{_GOD_CLASS_CRIT})",
                metric=f"{total} lines",
            ))
        elif total > _GOD_CLASS_WARN:
            findings.append(SmellFinding(
                file=rel, line=1, smell_type="god-class", severity="warning",
                message=f"File has {total} lines (>{_GOD_CLASS_WARN})",
                metric=f"{total} lines",
            ))

        # For Python, also check individual class bodies
        if path.endswith(".py"):
            try:
                tree = ast.parse("".join(lines), filename=path)
            except SyntaxError:
                return findings
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    cls_lines = (node.end_lineno or node.lineno) - node.lineno + 1
                    if cls_lines > _GOD_CLASS_CRIT:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="god-class",
                            severity="critical",
                            message=f"Class '{node.name}' has {cls_lines} lines (>{_GOD_CLASS_CRIT})",
                            metric=f"{cls_lines} lines",
                        ))
                    elif cls_lines > _GOD_CLASS_WARN:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="god-class",
                            severity="warning",
                            message=f"Class '{node.name}' has {cls_lines} lines (>{_GOD_CLASS_WARN})",
                            metric=f"{cls_lines} lines",
                        ))
        return findings

    def _check_long_method(self, path: str) -> list[SmellFinding]:
        """Functions > 50 lines -> warning, > 100 -> critical."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        rel = _relative(path, self.cwd)

        if path.endswith(".py"):
            try:
                tree = ast.parse("".join(lines), filename=path)
            except SyntaxError:
                return findings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_lines = (node.end_lineno or node.lineno) - node.lineno + 1
                    if func_lines > _LONG_METHOD_CRIT:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="long-method",
                            severity="critical",
                            message=f"Function '{node.name}' has {func_lines} lines (>{_LONG_METHOD_CRIT})",
                            metric=f"{func_lines} lines",
                        ))
                    elif func_lines > _LONG_METHOD_WARN:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="long-method",
                            severity="warning",
                            message=f"Function '{node.name}' has {func_lines} lines (>{_LONG_METHOD_WARN})",
                            metric=f"{func_lines} lines",
                        ))
        else:
            # Regex-based for other languages: find function starts, estimate length
            ext = os.path.splitext(path)[1]
            patterns = []
            if ext in _FUNC_RE:
                patterns.append(_FUNC_RE[ext])
            if ext in (".js", ".ts", ".jsx", ".tsx"):
                patterns.extend([_ARROW_RE, _METHOD_RE])

            content = "".join(lines)
            func_starts: list[tuple[str, int]] = []
            for pat in patterns:
                for m in pat.finditer(content):
                    lineno = content[:m.start()].count("\n") + 1
                    name = m.group(1)
                    func_starts.append((name, lineno))

            # Sort by line number, estimate function length by distance to next function
            func_starts.sort(key=lambda x: x[1])
            total_lines = len(lines)
            for i, (name, start) in enumerate(func_starts):
                end = func_starts[i + 1][1] - 1 if i + 1 < len(func_starts) else total_lines
                func_len = end - start + 1
                if func_len > _LONG_METHOD_CRIT:
                    findings.append(SmellFinding(
                        file=rel, line=start, smell_type="long-method",
                        severity="critical",
                        message=f"Function '{name}' ~{func_len} lines (>{_LONG_METHOD_CRIT})",
                        metric=f"{func_len} lines",
                    ))
                elif func_len > _LONG_METHOD_WARN:
                    findings.append(SmellFinding(
                        file=rel, line=start, smell_type="long-method",
                        severity="warning",
                        message=f"Function '{name}' ~{func_len} lines (>{_LONG_METHOD_WARN})",
                        metric=f"{func_len} lines",
                    ))
        return findings

    def _check_long_params(self, path: str) -> list[SmellFinding]:
        """Functions with > 5 parameters -> warning, > 8 -> critical."""
        findings: list[SmellFinding] = []
        rel = _relative(path, self.cwd)
        lines = _read_lines(path)

        if path.endswith(".py"):
            try:
                tree = ast.parse("".join(lines), filename=path)
            except SyntaxError:
                return findings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    count = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
                    # Exclude 'self' and 'cls'
                    if args.args and args.args[0].arg in ("self", "cls"):
                        count -= 1
                    if count > _LONG_PARAMS_CRIT:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="long-params",
                            severity="critical",
                            message=f"Function '{node.name}' has {count} parameters (>{_LONG_PARAMS_CRIT})",
                            metric=f"{count} params",
                        ))
                    elif count > _LONG_PARAMS_WARN:
                        findings.append(SmellFinding(
                            file=rel, line=node.lineno, smell_type="long-params",
                            severity="warning",
                            message=f"Function '{node.name}' has {count} parameters (>{_LONG_PARAMS_WARN})",
                            metric=f"{count} params",
                        ))
        else:
            ext = os.path.splitext(path)[1]
            if ext in _FUNC_RE:
                content = "".join(lines)
                for m in _FUNC_RE[ext].finditer(content):
                    name = m.group(1)
                    params_str = m.group(2).strip()
                    if not params_str:
                        continue
                    count = len([p.strip() for p in params_str.split(",") if p.strip()])
                    lineno = content[:m.start()].count("\n") + 1
                    if count > _LONG_PARAMS_CRIT:
                        findings.append(SmellFinding(
                            file=rel, line=lineno, smell_type="long-params",
                            severity="critical",
                            message=f"Function '{name}' has {count} parameters (>{_LONG_PARAMS_CRIT})",
                            metric=f"{count} params",
                        ))
                    elif count > _LONG_PARAMS_WARN:
                        findings.append(SmellFinding(
                            file=rel, line=lineno, smell_type="long-params",
                            severity="warning",
                            message=f"Function '{name}' has {count} parameters (>{_LONG_PARAMS_WARN})",
                            metric=f"{count} params",
                        ))
        return findings

    def _check_deep_nesting(self, path: str) -> list[SmellFinding]:
        """Indentation > 4 levels -> warning, > 6 -> critical."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        rel = _relative(path, self.cwd)

        max_depth = 0
        max_line = 0
        for i, line in enumerate(lines, 1):
            depth = _indent_level(line)
            if depth > max_depth:
                max_depth = depth
                max_line = i

        if max_depth > _DEEP_NESTING_CRIT:
            findings.append(SmellFinding(
                file=rel, line=max_line, smell_type="deep-nesting",
                severity="critical",
                message=f"Max nesting depth {max_depth} levels (>{_DEEP_NESTING_CRIT})",
                metric=f"{max_depth} levels",
            ))
        elif max_depth > _DEEP_NESTING_WARN:
            findings.append(SmellFinding(
                file=rel, line=max_line, smell_type="deep-nesting",
                severity="warning",
                message=f"Max nesting depth {max_depth} levels (>{_DEEP_NESTING_WARN})",
                metric=f"{max_depth} levels",
            ))
        return findings

    def _check_feature_envy(self, path: str) -> list[SmellFinding]:
        """Method accesses other object's attributes more than own (self.x < other.y)."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        rel = _relative(path, self.cwd)

        try:
            tree = ast.parse("".join(lines), filename=path)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Only check methods (first arg is self)
            if not node.args.args or node.args.args[0].arg != "self":
                continue

            self_count = 0
            other_count = 0
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    if child.value.id == "self":
                        self_count += 1
                    else:
                        other_count += 1

            if other_count > 0 and other_count > self_count * 2 and other_count >= 5:
                findings.append(SmellFinding(
                    file=rel, line=node.lineno, smell_type="feature-envy",
                    severity="warning",
                    message=f"Method '{node.name}' accesses external objects ({other_count}x) more than self ({self_count}x)",
                    metric=f"self={self_count} other={other_count}",
                ))
        return findings

    def _check_primitive_obsession(self, path: str) -> list[SmellFinding]:
        """Functions with > 3 str/int params that could be a value object."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        rel = _relative(path, self.cwd)

        try:
            tree = ast.parse("".join(lines), filename=path)
        except SyntaxError:
            return findings

        _PRIMITIVE_TYPES = {"str", "int", "float", "bool", "bytes"}

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            prim_count = 0
            for arg in node.args.args + node.args.kwonlyargs:
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    if arg.annotation.id in _PRIMITIVE_TYPES:
                        prim_count += 1
            if prim_count > _PRIMITIVE_OBSESSION_THRESHOLD:
                findings.append(SmellFinding(
                    file=rel, line=node.lineno, smell_type="primitive-obsession",
                    severity="info",
                    message=f"Function '{node.name}' has {prim_count} primitive-typed params — consider a value object",
                    metric=f"{prim_count} primitives",
                ))
        return findings

    def _check_shotgun_surgery(self) -> list[SmellFinding]:
        """Small changes require touching > 5 files (analyze recent git history)."""
        findings: list[SmellFinding] = []
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--name-only", "-20"],
                capture_output=True, text=True, cwd=self.cwd, timeout=10,
            )
            if result.returncode != 0:
                return findings
        except (OSError, subprocess.TimeoutExpired):
            return findings

        # Parse commits: group files per commit
        current_files: list[str] = []
        commits: list[list[str]] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                if current_files:
                    commits.append(current_files)
                    current_files = []
                continue
            # Lines starting with a hash are commit headers
            if re.match(r"^[0-9a-f]{7,}", line):
                if current_files:
                    commits.append(current_files)
                current_files = []
            else:
                current_files.append(line)
        if current_files:
            commits.append(current_files)

        for file_list in commits:
            if len(file_list) > _SHOTGUN_FILE_THRESHOLD:
                # Find common prefix to identify the "change set"
                findings.append(SmellFinding(
                    file="(git history)", line=0, smell_type="shotgun-surgery",
                    severity="info",
                    message=f"Commit touched {len(file_list)} files — possible shotgun surgery",
                    metric=f"{len(file_list)} files",
                ))
        return findings

    def _check_data_clumps(self, path: str) -> list[SmellFinding]:
        """Same group of parameters appears in > 3 functions."""
        findings: list[SmellFinding] = []
        lines = _read_lines(path)
        rel = _relative(path, self.cwd)

        try:
            tree = ast.parse("".join(lines), filename=path)
        except SyntaxError:
            return findings

        # Collect parameter name sets per function (min 2 params to count)
        param_groups: list[tuple[str, int, frozenset[str]]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = []
            for arg in node.args.args:
                if arg.arg not in ("self", "cls"):
                    params.append(arg.arg)
            if len(params) >= 2:
                param_groups.append((node.name, node.lineno, frozenset(params)))

        if len(param_groups) < _DATA_CLUMP_THRESHOLD:
            return findings

        # Find common param subsets (size >= 2) appearing in >= 3 functions
        from itertools import combinations
        pair_counts: Counter[frozenset[str]] = Counter()
        for _, _, params in param_groups:
            for pair in combinations(sorted(params), 2):
                pair_counts[frozenset(pair)] += 1

        reported: set[frozenset[str]] = set()
        for pair, count in pair_counts.items():
            if count >= _DATA_CLUMP_THRESHOLD and pair not in reported:
                reported.add(pair)
                names = ", ".join(sorted(pair))
                findings.append(SmellFinding(
                    file=rel, line=1, smell_type="data-clump",
                    severity="info",
                    message=f"Parameters ({names}) appear together in {count} functions — consider grouping",
                    metric=f"{count} occurrences",
                ))
        return findings


# ── Formatter ───────────────────────────────────────────────────────────────

def format_smell_report(report: SmellReport) -> str:
    """Format a SmellReport into a human-readable terminal string."""
    parts: list[str] = []

    # Header
    score = report.score
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    parts.append(f"Code Smell Report  |  Score: {score}/100 ({grade})")
    parts.append("=" * 60)

    if not report.findings:
        parts.append("No code smells detected. Clean codebase!")
        return "\n".join(parts)

    # Summary by severity
    parts.append("")
    parts.append("Summary:")
    for sev in ("critical", "warning", "info"):
        count = report.by_severity.get(sev, 0)
        if count:
            parts.append(f"  {sev.upper():<10} {count}")

    # Summary by type
    parts.append("")
    parts.append("By type:")
    for smell_type, count in sorted(report.by_type.items()):
        parts.append(f"  {smell_type:<25} {count}")

    # Findings grouped by severity
    parts.append("")
    parts.append("-" * 60)
    for sev in ("critical", "warning", "info"):
        group = [f for f in report.findings if f.severity == sev]
        if not group:
            continue
        parts.append(f"\n{sev.upper()} ({len(group)}):")
        for f in group:
            loc = f"{f.file}:{f.line}" if f.line > 0 else f.file
            metric_suffix = f" [{f.metric}]" if f.metric else ""
            parts.append(f"  {loc}  {f.smell_type}: {f.message}{metric_suffix}")

    parts.append("")
    return "\n".join(parts)
