"""Dead Code Eliminator — cross-file static analysis + safe removal of unused code."""

from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.dead_code_eliminator")

_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "venv", ".venv", "node_modules",
    ".tox", "dist", "build", ".eggs", "target", ".gradle",
    ".mvn", ".next", ".mypy_cache", ".pytest_cache", "egg-info",
})

_PROTECTED_FILES = frozenset({
    "__init__.py", "__main__.py", "conftest.py", "setup.py",
    "manage.py", "wsgi.py", "asgi.py",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DeadCodeFinding:
    """A single piece of dead code detected by the eliminator."""

    file: str
    line: int
    name: str
    kind: str  # "function", "class", "file", "variable"
    proof: str  # why it's dead: "no imports found", "0 callers", "orphan file"


@dataclass
class DeadCodeReport:
    """Aggregated results from a dead-code elimination scan."""

    findings: list[DeadCodeFinding] = field(default_factory=list)
    total_dead_lines: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    safe_to_remove: list[DeadCodeFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Eliminator
# ---------------------------------------------------------------------------

class DeadCodeEliminator:
    """Cross-file dead code detector with optional safe removal."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._py_files: list[str] = []
        self._all_source: str = ""
        self._file_contents: dict[str, str] = {}
        self._files_scanned: int = 0
        logger.info("DeadCodeEliminator initialized — cwd=%s", cwd)

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_python_files(self) -> list[str]:
        """Gather all .py files excluding skipped dirs."""
        if self._py_files:
            return self._py_files
        files: list[str] = []
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if f.endswith(".py"):
                    files.append(os.path.join(root, f))
        self._py_files = files
        self._files_scanned = len(files)
        return files

    def _load_file(self, fpath: str) -> str:
        """Read file content with caching."""
        if fpath not in self._file_contents:
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    self._file_contents[fpath] = f.read()
            except OSError as exc:
                logger.debug("Cannot read %s: %s", fpath, exc)
                self._file_contents[fpath] = ""
        return self._file_contents[fpath]

    def _get_all_source(self) -> str:
        """Concatenate all Python source for cross-file grep."""
        if self._all_source:
            return self._all_source
        parts: list[str] = []
        for fpath in self._collect_python_files():
            parts.append(self._load_file(fpath))
        self._all_source = "\n".join(parts)
        return self._all_source

    def _rel(self, fpath: str) -> str:
        return os.path.relpath(fpath, self.cwd)

    def _is_test_file(self, fpath: str) -> bool:
        rel = self._rel(fpath)
        base = os.path.basename(fpath)
        return (
            base.startswith("test_")
            or base.endswith("_test.py")
            or "/tests/" in rel
            or "/test/" in rel
            or rel.startswith("tests/")
            or rel.startswith("test/")
        )

    def _is_protected(self, fpath: str) -> bool:
        base = os.path.basename(fpath)
        return base in _PROTECTED_FILES or self._is_test_file(fpath)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, target: str = "") -> DeadCodeReport:
        """Run all dead-code checks and return a report.

        Args:
            target: Optional subdirectory or file to limit the scan to.
        """
        logger.info("Starting dead-code elimination scan — cwd=%s target=%s", self.cwd, target or "(all)")
        self._collect_python_files()
        self._get_all_source()

        findings: list[DeadCodeFinding] = []
        findings.extend(self._find_unused_functions(target))
        findings.extend(self._find_unused_classes(target))
        findings.extend(self._find_orphan_files(target))
        findings.extend(self._find_unused_variables(target))

        # Build by_kind summary
        by_kind: dict[str, int] = {}
        for f in findings:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1

        # Estimate dead lines
        total_dead = self._estimate_dead_lines(findings)

        # Mark safe to remove (non-public, non-test, non-protected)
        safe = [f for f in findings if self._is_safe_to_remove(f)]

        report = DeadCodeReport(
            findings=findings,
            total_dead_lines=total_dead,
            by_kind=by_kind,
            safe_to_remove=safe,
        )
        logger.info(
            "Scan complete — %d findings, %d safe to remove, ~%d dead lines",
            len(findings), len(safe), total_dead,
        )
        return report

    def apply(self, findings: list[DeadCodeFinding] | None = None) -> int:
        """Remove dead code from source files with backup.

        Returns the number of items removed.
        """
        if findings is None:
            report = self.scan()
            findings = report.safe_to_remove

        if not findings:
            logger.info("Nothing to remove.")
            return 0

        removed = 0
        # Group by file for efficient processing
        by_file: dict[str, list[DeadCodeFinding]] = {}
        for f in findings:
            by_file.setdefault(f.file, []).append(f)

        for rel_file, file_findings in by_file.items():
            fpath = os.path.join(self.cwd, rel_file)
            if not os.path.isfile(fpath):
                continue

            # Backup
            backup_path = fpath + ".deadcode.bak"
            shutil.copy2(fpath, backup_path)
            logger.info("Backed up %s -> %s", fpath, backup_path)

            try:
                if any(f.kind == "file" for f in file_findings):
                    # Entire file is dead — remove it
                    os.remove(fpath)
                    removed += 1
                    logger.info("Removed orphan file: %s", rel_file)
                    continue

                source = self._load_file(fpath)
                new_source = self._remove_definitions(source, file_findings)

                # Atomic write
                dir_name = os.path.dirname(fpath)
                with tempfile.NamedTemporaryFile(
                    mode="w", dir=dir_name, suffix=".py",
                    delete=False, encoding="utf-8",
                ) as tmp:
                    tmp.write(new_source)
                    tmp_path = tmp.name
                os.replace(tmp_path, fpath)
                removed += len(file_findings)
                logger.info("Removed %d items from %s", len(file_findings), rel_file)

                # Invalidate cache
                self._file_contents.pop(fpath, None)
            except Exception as exc:
                logger.error("Failed to apply removal to %s: %s", rel_file, exc)
                # Restore from backup
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, fpath)

        return removed

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _find_unused_functions(self, target: str = "") -> list[DeadCodeFinding]:
        """Find functions defined but never called across the codebase."""
        findings: list[DeadCodeFinding] = []
        all_source = self._get_all_source()

        for fpath in self._collect_python_files():
            if self._is_test_file(fpath) or self._is_protected(fpath):
                continue
            if target and not self._rel(fpath).startswith(target):
                continue

            source = self._load_file(fpath)
            if not source:
                continue

            try:
                tree = ast.parse(source, filename=fpath)
            except SyntaxError:
                continue

            rel = self._rel(fpath)
            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = node.name
                # Skip dunder methods, public API in __init__, decorators like @property
                if name.startswith("__") and name.endswith("__"):
                    continue
                # Skip decorated functions (likely hooks/routes/tests)
                if node.decorator_list:
                    continue

                # Cross-file search: count occurrences across ALL source
                pattern = re.compile(r"\b" + re.escape(name) + r"\b")
                matches = pattern.findall(all_source)
                # Subtract the definition itself (def name) — at least 1
                call_count = len(matches) - 1
                if call_count <= 0:
                    proof = self._build_proof(name, "function")
                    findings.append(DeadCodeFinding(
                        file=rel, line=node.lineno, name=name,
                        kind="function", proof=proof,
                    ))

        return findings

    def _find_unused_classes(self, target: str = "") -> list[DeadCodeFinding]:
        """Find classes never instantiated or inherited across the codebase."""
        findings: list[DeadCodeFinding] = []
        all_source = self._get_all_source()

        for fpath in self._collect_python_files():
            if self._is_test_file(fpath) or self._is_protected(fpath):
                continue
            if target and not self._rel(fpath).startswith(target):
                continue

            source = self._load_file(fpath)
            if not source:
                continue

            try:
                tree = ast.parse(source, filename=fpath)
            except SyntaxError:
                continue

            rel = self._rel(fpath)
            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                name = node.name
                # Skip decorated classes (e.g. @dataclass, @app.route)
                if node.decorator_list:
                    continue

                pattern = re.compile(r"\b" + re.escape(name) + r"\b")
                matches = pattern.findall(all_source)
                # Subtract the class definition line itself
                usage_count = len(matches) - 1
                if usage_count <= 0:
                    proof = self._build_proof(name, "class")
                    findings.append(DeadCodeFinding(
                        file=rel, line=node.lineno, name=name,
                        kind="class", proof=proof,
                    ))

        return findings

    def _find_orphan_files(self, target: str = "") -> list[DeadCodeFinding]:
        """Find Python source files never imported by any other file."""
        findings: list[DeadCodeFinding] = []
        all_source = self._get_all_source()

        for fpath in self._collect_python_files():
            if self._is_protected(fpath):
                continue
            rel = self._rel(fpath)
            if target and not rel.startswith(target):
                continue

            base = os.path.basename(fpath)
            stem = Path(fpath).stem  # filename without .py

            # Build possible import names
            # e.g. "code_agents/foo.py" -> "code_agents.foo" or just "foo"
            module_path = rel.replace(os.sep, ".").replace("/", ".")
            if module_path.endswith(".py"):
                module_path = module_path[:-3]

            # Check if this module is imported anywhere
            import_patterns = [
                re.compile(r"\bimport\s+" + re.escape(module_path) + r"\b"),
                re.compile(r"\bfrom\s+" + re.escape(module_path) + r"\s+import\b"),
                re.compile(r"\bimport\s+" + re.escape(stem) + r"\b"),
                re.compile(r"\bfrom\s+\S*" + re.escape(stem) + r"\s+import\b"),
            ]

            imported = False
            for pat in import_patterns:
                if pat.search(all_source):
                    imported = True
                    break

            if not imported:
                proof = self._build_proof(stem, "file")
                findings.append(DeadCodeFinding(
                    file=rel, line=1, name=stem,
                    kind="file", proof=proof,
                ))

        return findings

    def _find_unused_variables(self, target: str = "") -> list[DeadCodeFinding]:
        """Find module-level variables never referenced outside their file."""
        findings: list[DeadCodeFinding] = []
        all_source = self._get_all_source()

        for fpath in self._collect_python_files():
            if self._is_test_file(fpath) or self._is_protected(fpath):
                continue
            if target and not self._rel(fpath).startswith(target):
                continue

            source = self._load_file(fpath)
            if not source:
                continue

            try:
                tree = ast.parse(source, filename=fpath)
            except SyntaxError:
                continue

            rel = self._rel(fpath)
            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for t in node.targets:
                    if not isinstance(t, ast.Name):
                        continue
                    name = t.id
                    # Skip dunder, UPPER_CASE constants, single-char, private convention
                    if name.startswith("__") and name.endswith("__"):
                        continue
                    if name.isupper():
                        continue
                    if len(name) <= 1:
                        continue
                    # Skip if starts with underscore (private but may be intentional)
                    if name.startswith("_"):
                        continue

                    pattern = re.compile(r"\b" + re.escape(name) + r"\b")
                    matches = pattern.findall(all_source)
                    # Subtract the assignment itself
                    if len(matches) - 1 <= 0:
                        proof = self._build_proof(name, "variable")
                        findings.append(DeadCodeFinding(
                            file=rel, line=node.lineno, name=name,
                            kind="variable", proof=proof,
                        ))

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_proof(self, name: str, kind: str) -> str:
        """Generate a human-readable proof string."""
        if kind == "file":
            return f"no imports found in {self._files_scanned} files scanned"
        elif kind == "function":
            return f"0 callers found in {self._files_scanned} files scanned"
        elif kind == "class":
            return f"0 instantiations/subclasses in {self._files_scanned} files scanned"
        elif kind == "variable":
            return f"0 references found in {self._files_scanned} files scanned"
        return f"unused {kind} in {self._files_scanned} files scanned"

    def _is_safe_to_remove(self, finding: DeadCodeFinding) -> bool:
        """Determine if a finding is safe to auto-remove."""
        fpath = os.path.join(self.cwd, finding.file)
        if self._is_protected(fpath):
            return False
        # Don't auto-remove public functions (no underscore prefix)
        if finding.kind == "function" and not finding.name.startswith("_"):
            return False
        # Don't auto-remove classes that look like public API
        if finding.kind == "class" and not finding.name.startswith("_"):
            return False
        return True

    def _estimate_dead_lines(self, findings: list[DeadCodeFinding]) -> int:
        """Estimate total dead lines by looking at AST node spans."""
        total = 0
        for finding in findings:
            if finding.kind == "file":
                fpath = os.path.join(self.cwd, finding.file)
                source = self._load_file(fpath)
                total += source.count("\n") + 1
                continue

            fpath = os.path.join(self.cwd, finding.file)
            source = self._load_file(fpath)
            if not source:
                total += 1
                continue

            try:
                tree = ast.parse(source, filename=fpath)
            except SyntaxError:
                total += 1
                continue

            found = False
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and getattr(node, "name", None) == finding.name
                    and node.lineno == finding.line
                ):
                    end = getattr(node, "end_lineno", node.lineno)
                    total += end - node.lineno + 1
                    found = True
                    break
            if not found:
                total += 1

        return total

    def _remove_definitions(
        self, source: str, findings: list[DeadCodeFinding],
    ) -> str:
        """Remove function/class/variable definitions from source by line range."""
        lines = source.split("\n")
        # Collect line ranges to remove
        remove_ranges: list[tuple[int, int]] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        for finding in findings:
            if finding.kind in ("function", "class"):
                for node in ast.walk(tree):
                    if (
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        and getattr(node, "name", None) == finding.name
                        and node.lineno == finding.line
                    ):
                        end = getattr(node, "end_lineno", node.lineno)
                        remove_ranges.append((node.lineno, end))
                        break
            elif finding.kind == "variable":
                # Remove just the assignment line
                remove_ranges.append((finding.line, finding.line))

        # Sort ranges and remove from bottom to top to preserve line numbers
        remove_ranges.sort(reverse=True)
        for start, end in remove_ranges:
            # Remove blank line after definition too if present
            if end < len(lines) and not lines[end].strip():
                end += 1
            del lines[start - 1: end]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_dead_code_report(report: DeadCodeReport) -> str:
    """Format a DeadCodeReport for terminal display."""
    lines: list[str] = []
    lines.append("  \u2554\u2550\u2550 DEAD CODE ELIMINATOR \u2550\u2550\u2557")
    lines.append(f"  \u2551 Findings: {len(report.findings)}")
    lines.append(f"  \u2551 Dead lines (est.): ~{report.total_dead_lines}")
    lines.append(f"  \u2551 Safe to remove: {len(report.safe_to_remove)}")

    if report.by_kind:
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(report.by_kind.items()))
        lines.append(f"  \u2551 By kind: {breakdown}")
    lines.append("  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")

    for kind in ("function", "class", "file", "variable"):
        items = [f for f in report.findings if f.kind == kind]
        if not items:
            continue
        label = kind.capitalize() + ("s" if kind != "class" else "es")
        lines.append(f"\n  Unused {label} ({len(items)}):")
        for item in items[:20]:
            safe_marker = " [safe]" if item in report.safe_to_remove else ""
            lines.append(
                f"    \u2717 {item.file}:{item.line} \u2014 {item.name}{safe_marker}"
            )
            lines.append(f"      {item.proof}")
        if len(items) > 20:
            lines.append(f"    ... and {len(items) - 20} more")

    if not report.findings:
        lines.append("\n  \u2713 No dead code detected!")

    return "\n".join(lines)
