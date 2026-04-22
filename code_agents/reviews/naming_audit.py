"""Naming convention enforcer — audit naming consistency across a codebase.

Detects mixed naming styles, abbreviations, single-character variables,
and other naming anti-patterns.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("code_agents.reviews.naming_audit")

# Common abbreviations that hurt readability
ABBREVIATIONS = {
    "mgr": "manager",
    "cfg": "config",
    "impl": "implementation",
    "ctx": "context",
    "req": "request",
    "res": "response",
    "resp": "response",
    "msg": "message",
    "btn": "button",
    "dlg": "dialog",
    "env": "environment",
    "fmt": "format",
    "fn": "function",
    "func": "function",
    "idx": "index",
    "lbl": "label",
    "lib": "library",
    "num": "number",
    "obj": "object",
    "pkg": "package",
    "ptr": "pointer",
    "ref": "reference",
    "srv": "server",
    "str": "string",
    "tmp": "temporary",
    "val": "value",
    "var": "variable",
    "wgt": "widget",
    "cnt": "count",
    "buf": "buffer",
    "len": "length",
    "err": "error",
    "tbl": "table",
    "col": "column",
    "desc": "description",
    "src": "source",
    "dst": "destination",
    "prev": "previous",
    "curr": "current",
}

# File extensions to scan
PYTHON_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".ts", ".jsx", ".tsx"}
ALL_EXTENSIONS = PYTHON_EXTENSIONS | JS_EXTENSIONS

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", "target", ".next", ".nuxt", "migrations",
}

# Loop variable names that are acceptable as single-char
LOOP_VARS = {"i", "j", "k", "n", "x", "y", "z"}

# Built-in / common names to ignore
IGNORE_NAMES = {
    "self", "cls", "args", "kwargs", "os", "sys", "re", "io",
    "f", "e", "ex", "_", "__", "id", "pk", "db", "ui", "ip",
}


@dataclass
class NamingFinding:
    """A naming convention issue found during audit."""

    file: str
    line: int
    name: str
    issue: str
    suggestion: str
    severity: str  # "error" | "warning" | "info"


class NamingAuditor:
    """Audit naming conventions across a codebase."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("NamingAuditor initialized for %s", cwd)

    def audit(self, target: str = "") -> list[NamingFinding]:
        """Audit naming conventions in the target path.

        Args:
            target: Specific file or directory to audit. If empty, audits
                    the entire cwd.

        Returns:
            List of NamingFinding instances.
        """
        findings: list[NamingFinding] = []

        if target:
            full_path = os.path.join(self.cwd, target) if not os.path.isabs(target) else target
            if os.path.isfile(full_path):
                findings.extend(self._audit_file(full_path))
            elif os.path.isdir(full_path):
                findings.extend(self._audit_directory(full_path))
            else:
                logger.warning("Target not found: %s", full_path)
        else:
            findings.extend(self._audit_directory(self.cwd))

        logger.info("Found %d naming issues", len(findings))
        return findings

    def _detect_style(self) -> str:
        """Detect the dominant naming style in the project.

        Returns:
            "snake_case" or "camelCase" based on the majority of names.
        """
        snake_count = 0
        camel_count = 0

        files = self._collect_files(self.cwd)
        # Sample up to 20 files for speed
        for fpath in files[:20]:
            try:
                with open(fpath) as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            # Count naming patterns
            names = re.findall(r"\b([a-z][a-z0-9_]*[a-z0-9])\b", content)
            for name in names:
                if "_" in name:
                    snake_count += 1

            camel_names = re.findall(r"\b([a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*)\b", content)
            camel_count += len(camel_names)

        dominant = "snake_case" if snake_count >= camel_count else "camelCase"
        logger.debug(
            "Detected dominant style: %s (snake=%d, camel=%d)",
            dominant, snake_count, camel_count,
        )
        return dominant

    def _audit_directory(self, directory: str) -> list[NamingFinding]:
        """Audit all supported files in a directory."""
        findings: list[NamingFinding] = []
        files = self._collect_files(directory)

        for fpath in files:
            findings.extend(self._audit_file(fpath))

        return findings

    def _audit_file(self, path: str) -> list[NamingFinding]:
        """Audit a single file for naming issues."""
        findings: list[NamingFinding] = []

        ext = os.path.splitext(path)[1].lower()
        if ext not in ALL_EXTENSIONS:
            return findings

        findings.extend(self._check_consistency(path))
        findings.extend(self._check_abbreviations(path))
        findings.extend(self._check_single_char(path))

        return findings

    def _check_consistency(self, path: str) -> list[NamingFinding]:
        """Check for mixed naming styles within the same file."""
        findings: list[NamingFinding] = []
        rel_path = os.path.relpath(path, self.cwd)

        ext = os.path.splitext(path)[1].lower()
        is_python = ext in PYTHON_EXTENSIONS

        if is_python:
            findings.extend(self._check_python_consistency(path, rel_path))
        else:
            findings.extend(self._check_generic_consistency(path, rel_path))

        return findings

    def _check_python_consistency(
        self, path: str, rel_path: str
    ) -> list[NamingFinding]:
        """Check Python-specific naming conventions using AST."""
        findings: list[NamingFinding] = []

        try:
            with open(path) as f:
                source = f.read()
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            return findings

        for node in ast.walk(tree):
            # Function names should be snake_case
            if isinstance(node, ast.FunctionDef):
                name = node.name
                if name.startswith("_"):
                    name = name.lstrip("_")
                if name and not name.startswith("__") and self._is_camel_case(name):
                    findings.append(NamingFinding(
                        file=rel_path,
                        line=node.lineno,
                        name=node.name,
                        issue="Function uses camelCase instead of snake_case",
                        suggestion=self._to_snake_case(node.name),
                        severity="warning",
                    ))

            # Class names should be PascalCase
            elif isinstance(node, ast.ClassDef):
                name = node.name
                if "_" in name and not name.startswith("_"):
                    findings.append(NamingFinding(
                        file=rel_path,
                        line=node.lineno,
                        name=name,
                        issue="Class uses snake_case instead of PascalCase",
                        suggestion=self._to_pascal_case(name),
                        severity="warning",
                    ))

            # Variable / argument names
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
                if name in IGNORE_NAMES or name.startswith("_"):
                    continue
                if self._is_camel_case(name) and not name[0].isupper():
                    findings.append(NamingFinding(
                        file=rel_path,
                        line=node.lineno,
                        name=name,
                        issue="Variable uses camelCase instead of snake_case",
                        suggestion=self._to_snake_case(name),
                        severity="info",
                    ))

        return findings

    def _check_generic_consistency(
        self, path: str, rel_path: str
    ) -> list[NamingFinding]:
        """Check naming consistency using regex for non-Python files."""
        findings: list[NamingFinding] = []

        try:
            with open(path) as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            return findings

        snake_names: list[tuple[int, str]] = []
        camel_names: list[tuple[int, str]] = []

        for lineno, line in enumerate(lines, 1):
            # Find function/method declarations
            func_match = re.search(
                r"(?:function|const|let|var)\s+([a-zA-Z_]\w*)", line
            )
            if func_match:
                name = func_match.group(1)
                if "_" in name and not name.startswith("_"):
                    snake_names.append((lineno, name))
                elif self._is_camel_case(name):
                    camel_names.append((lineno, name))

        # If both styles exist, flag the minority
        if snake_names and camel_names:
            minority = snake_names if len(snake_names) < len(camel_names) else camel_names
            dominant = "camelCase" if len(camel_names) >= len(snake_names) else "snake_case"
            for lineno, name in minority:
                findings.append(NamingFinding(
                    file=rel_path,
                    line=lineno,
                    name=name,
                    issue=f"Mixed naming style (dominant is {dominant})",
                    suggestion=(
                        self._to_camel_case(name) if dominant == "camelCase"
                        else self._to_snake_case(name)
                    ),
                    severity="warning",
                ))

        return findings

    def _check_abbreviations(self, path: str) -> list[NamingFinding]:
        """Check for common abbreviations that hurt readability."""
        findings: list[NamingFinding] = []
        rel_path = os.path.relpath(path, self.cwd)

        try:
            with open(path) as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            return findings

        for lineno, line in enumerate(lines, 1):
            # Skip comments and strings (simplified)
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            names = re.findall(r"\b([a-zA-Z_]\w*)\b", line)
            for name in names:
                lower = name.lower()
                # Check if the whole name IS an abbreviation
                if lower in ABBREVIATIONS and lower not in IGNORE_NAMES:
                    # Only flag if it's used as a standalone variable
                    if re.search(rf"\b{re.escape(name)}\s*[=:]", line):
                        findings.append(NamingFinding(
                            file=rel_path,
                            line=lineno,
                            name=name,
                            issue=f"Abbreviation '{name}' — consider a descriptive name",
                            suggestion=ABBREVIATIONS[lower],
                            severity="info",
                        ))

        return findings

    def _check_single_char(self, path: str) -> list[NamingFinding]:
        """Check for single-character variable names outside loops."""
        findings: list[NamingFinding] = []
        rel_path = os.path.relpath(path, self.cwd)

        try:
            with open(path) as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            return findings

        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Find single-char assignments
            matches = re.findall(r"\b([a-zA-Z])\s*=\s*", line)
            for name in matches:
                if name in IGNORE_NAMES or name == "_":
                    continue

                # Check if it's in a loop context (for x in ...)
                is_loop = bool(re.match(r"\s*for\s+", line))
                # Check if it's a comprehension
                is_comp = " for " in line and " in " in line

                if not is_loop and not is_comp and name.lower() in LOOP_VARS:
                    findings.append(NamingFinding(
                        file=rel_path,
                        line=lineno,
                        name=name,
                        issue=f"Single-character variable '{name}' outside loop",
                        suggestion=f"Use a descriptive name instead of '{name}'",
                        severity="warning",
                    ))

        return findings

    def _collect_files(self, directory: str) -> list[str]:
        """Collect all source files in a directory."""
        files: list[str] = []
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in ALL_EXTENSIONS:
                    files.append(os.path.join(root, fname))
        return files

    # --- Name style helpers ---

    @staticmethod
    def _is_camel_case(name: str) -> bool:
        """Check if a name uses camelCase."""
        return bool(re.match(r"^[a-z]+[a-zA-Z0-9]*$", name) and re.search(r"[A-Z]", name))

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert camelCase or PascalCase to snake_case."""
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    @staticmethod
    def _to_camel_case(name: str) -> str:
        """Convert snake_case to camelCase."""
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    @staticmethod
    def _to_pascal_case(name: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(p.capitalize() for p in name.split("_"))


def format_naming_report(findings: list[NamingFinding]) -> str:
    """Format naming audit results as a terminal-friendly report."""
    if not findings:
        return "\n  No naming issues found.\n"

    # Group by severity
    by_severity: dict[str, list[NamingFinding]] = {
        "error": [], "warning": [], "info": [],
    }
    for f in findings:
        by_severity.get(f.severity, by_severity["info"]).append(f)

    lines = [
        "",
        f"  Found {len(findings)} naming issue(s):",
        "",
    ]

    severity_icons = {"error": "E", "warning": "W", "info": "I"}

    for finding in findings[:50]:  # Cap output
        icon = severity_icons.get(finding.severity, "?")
        lines.append(
            f"  [{icon}] {finding.file}:{finding.line} "
            f"'{finding.name}' — {finding.issue}"
        )
        if finding.suggestion:
            lines.append(f"       Suggestion: {finding.suggestion}")

    if len(findings) > 50:
        lines.append(f"\n  ... and {len(findings) - 50} more issues")

    # Summary
    lines.append("")
    lines.append(
        f"  Summary: {len(by_severity['error'])} errors, "
        f"{len(by_severity['warning'])} warnings, "
        f"{len(by_severity['info'])} info"
    )
    lines.append("")

    return "\n".join(lines)
