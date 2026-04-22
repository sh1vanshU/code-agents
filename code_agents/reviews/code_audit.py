"""Code audit — SDLC quality checks for error handling, logging, type hints, imports.

Scans Python source files for consistency in error handling patterns,
logging usage, type hint coverage, and import organization.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.reviews.code_audit")

PYTHON_EXTENSIONS = {".py"}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Bare except is discouraged
BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:", re.MULTILINE)

# Logging call patterns
LOGGING_CALL_RE = re.compile(
    r"\blogger\.(debug|info|warning|error|critical|exception)\b",
)

# print() usage (often should be logger)
PRINT_CALL_RE = re.compile(r"\bprint\s*\(")

# Import sorting: stdlib vs third-party vs local
FROM_IMPORT_RE = re.compile(r"^(?:from|import)\s+(\S+)", re.MULTILINE)


@dataclass
class AuditFinding:
    """A single audit finding."""

    file: str = ""
    line: int = 0
    category: str = ""  # error_handling | logging | type_hints | imports
    severity: str = "warning"  # info | warning | error
    message: str = ""
    suggestion: str = ""


@dataclass
class AuditResult:
    """Aggregated result of a code audit."""

    files_scanned: int = 0
    findings: list[AuditFinding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    # Per-category scores 0-100


class CodeAuditor:
    """Perform SDLC quality audits on a codebase."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CodeAuditor initialized for %s", cwd)

    def audit(
        self,
        categories: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> AuditResult:
        """Run code audit across the codebase.

        Args:
            categories: Which checks to run. Default: all.
                Options: error_handling, logging, type_hints, imports
            exclude_patterns: File path patterns to skip.

        Returns:
            AuditResult with findings and scores.
        """
        if categories is None:
            categories = ["error_handling", "logging", "type_hints", "imports"]

        exclude = exclude_patterns or []
        result = AuditResult()
        files = self._collect_files(exclude)
        result.files_scanned = len(files)
        logger.info("Auditing %d files in %s", len(files), self.cwd)

        category_counts: dict[str, int] = {c: 0 for c in categories}
        category_totals: dict[str, int] = {c: 0 for c in categories}

        for fpath in files:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", fpath, exc)
                continue

            rel = os.path.relpath(fpath, self.cwd)

            if "error_handling" in categories:
                findings = self._check_error_handling(content, rel)
                result.findings.extend(findings)
                category_counts["error_handling"] += len(findings)
                category_totals["error_handling"] += max(1, content.count("except"))

            if "logging" in categories:
                findings = self._check_logging(content, rel)
                result.findings.extend(findings)
                category_counts["logging"] += len(findings)
                category_totals["logging"] += max(1, content.count("def "))

            if "type_hints" in categories:
                findings = self._check_type_hints(content, rel)
                result.findings.extend(findings)
                category_counts["type_hints"] += len(findings)
                category_totals["type_hints"] += max(1, content.count("def "))

            if "imports" in categories:
                findings = self._check_imports(content, rel)
                result.findings.extend(findings)
                category_counts["imports"] += len(findings)
                category_totals["imports"] += 1

        # Calculate scores (100 = perfect, fewer findings = higher score)
        for cat in categories:
            total = category_totals.get(cat, 1) or 1
            issues = category_counts.get(cat, 0)
            score = max(0.0, 100.0 * (1 - issues / (total * len(files) + 1)))
            result.scores[cat] = round(score, 1)

        result.summary = {
            "total_findings": len(result.findings),
            "errors": sum(1 for f in result.findings if f.severity == "error"),
            "warnings": sum(1 for f in result.findings if f.severity == "warning"),
            "info": sum(1 for f in result.findings if f.severity == "info"),
        }
        logger.info("Audit complete: %d findings", len(result.findings))
        return result

    def _collect_files(self, exclude: list[str]) -> list[str]:
        """Collect Python files to audit."""
        files: list[str] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not any(fname.endswith(ext) for ext in PYTHON_EXTENSIONS):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.cwd)
                if any(pat in rel for pat in exclude):
                    continue
                files.append(fpath)
        return files

    def _check_error_handling(self, content: str, rel_path: str) -> list[AuditFinding]:
        """Check error handling patterns."""
        findings: list[AuditFinding] = []

        # Bare except
        for i, line in enumerate(content.splitlines(), 1):
            if BARE_EXCEPT_RE.match(line):
                findings.append(AuditFinding(
                    file=rel_path, line=i, category="error_handling",
                    severity="error",
                    message="Bare except clause — catches all exceptions including SystemExit",
                    suggestion="Use 'except Exception:' or a specific exception type",
                ))

        # except pass (swallowed exceptions)
        lines = content.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("except") and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped == "pass":
                    findings.append(AuditFinding(
                        file=rel_path, line=i + 1, category="error_handling",
                        severity="warning",
                        message="Exception silently swallowed with 'pass'",
                        suggestion="Log the exception or re-raise",
                    ))

        return findings

    def _check_logging(self, content: str, rel_path: str) -> list[AuditFinding]:
        """Check logging patterns."""
        findings: list[AuditFinding] = []
        has_logger = "logger" in content or "logging" in content
        print_calls = PRINT_CALL_RE.findall(content)

        if print_calls and has_logger:
            for i, line in enumerate(content.splitlines(), 1):
                if PRINT_CALL_RE.search(line) and "# noqa" not in line:
                    findings.append(AuditFinding(
                        file=rel_path, line=i, category="logging",
                        severity="warning",
                        message="print() used alongside logger — prefer logger calls",
                        suggestion="Replace print() with logger.info() or logger.debug()",
                    ))

        # Check for f-string in logger calls (lazy formatting preferred)
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r'logger\.\w+\(f["\']', line):
                findings.append(AuditFinding(
                    file=rel_path, line=i, category="logging",
                    severity="info",
                    message="f-string in logger call — lazy formatting preferred",
                    suggestion="Use logger.info('msg %s', var) instead of f-strings",
                ))

        return findings

    def _check_type_hints(self, content: str, rel_path: str) -> list[AuditFinding]:
        """Check type hint coverage on function definitions."""
        findings: list[AuditFinding] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check return annotation
                if node.returns is None and not node.name.startswith("_"):
                    findings.append(AuditFinding(
                        file=rel_path, line=node.lineno, category="type_hints",
                        severity="info",
                        message=f"Function '{node.name}' missing return type annotation",
                        suggestion="Add -> ReturnType annotation",
                    ))
                # Check argument annotations
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg not in ("self", "cls"):
                        findings.append(AuditFinding(
                            file=rel_path, line=node.lineno, category="type_hints",
                            severity="info",
                            message=f"Parameter '{arg.arg}' in '{node.name}' missing type annotation",
                            suggestion=f"Add type annotation to '{arg.arg}'",
                        ))
                        break  # One finding per function

        return findings

    def _check_imports(self, content: str, rel_path: str) -> list[AuditFinding]:
        """Check import organization."""
        findings: list[AuditFinding] = []
        lines = content.splitlines()
        import_lines: list[tuple[int, str]] = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                import_lines.append((i, stripped))

        # Check for wildcard imports
        for lineno, imp in import_lines:
            if "import *" in imp:
                findings.append(AuditFinding(
                    file=rel_path, line=lineno, category="imports",
                    severity="warning",
                    message=f"Wildcard import: {imp}",
                    suggestion="Import specific names instead of using *",
                ))

        # Check for duplicate imports
        seen: set[str] = set()
        for lineno, imp in import_lines:
            if imp in seen:
                findings.append(AuditFinding(
                    file=rel_path, line=lineno, category="imports",
                    severity="warning",
                    message=f"Duplicate import: {imp}",
                    suggestion="Remove the duplicate import statement",
                ))
            seen.add(imp)

        return findings


def run_code_audit(
    cwd: str,
    categories: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict:
    """Convenience function to run a code audit.

    Returns:
        Dict with findings, summary, and scores.
    """
    auditor = CodeAuditor(cwd)
    result = auditor.audit(categories=categories, exclude_patterns=exclude_patterns)
    return {
        "files_scanned": result.files_scanned,
        "findings": [
            {
                "file": f.file, "line": f.line, "category": f.category,
                "severity": f.severity, "message": f.message, "suggestion": f.suggestion,
            }
            for f in result.findings
        ],
        "summary": result.summary,
        "scores": result.scores,
    }
