"""Test Impact Analyzer — changed code → impacted tests only."""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.test_impact")


@dataclass
class ImpactedTest:
    test_file: str
    test_functions: list[str] = field(default_factory=list)
    reason: str = ""  # "direct import", "transitive", "same module", "naming convention"
    confidence: float = 0.8


@dataclass
class ImpactReport:
    changed_files: list[str] = field(default_factory=list)
    changed_functions: list[str] = field(default_factory=list)
    impacted_tests: list[ImpactedTest] = field(default_factory=list)
    total_test_files: int = 0
    impacted_test_files: int = 0
    reduction_pct: float = 0.0
    run_result: Optional[dict] = None
    test_framework: str = "pytest"

    @property
    def skipped_tests(self) -> int:
        return self.total_test_files - self.impacted_test_files


_TEST_FILE_PATTERNS = re.compile(r"(?:test_\w+|_test|\w+\.test|\w+\.spec|tests)\.\w+$")
_TEST_DIR_NAMES = {"tests", "test", "spec", "__tests__", "specs"}


class ImpactAnalyzer:
    """Analyzes code changes to determine which tests are impacted."""

    def __init__(self, cwd: str = ".", base: str = "main"):
        self.cwd = os.path.abspath(cwd)
        self.base = base
        self._import_graph: Optional[dict] = None

    def analyze(self) -> ImpactReport:
        """Analyze impact without running tests."""
        changed_files = self._get_changed_files()
        changed_functions = self._get_changed_functions(changed_files)
        all_test_files = self._find_all_test_files()
        impacted = self._map_to_tests(changed_files, changed_functions, all_test_files)

        total = len(all_test_files)
        impacted_count = len(impacted)
        reduction = round((1 - impacted_count / max(total, 1)) * 100, 1) if total else 0

        return ImpactReport(
            changed_files=changed_files,
            changed_functions=changed_functions,
            impacted_tests=impacted,
            total_test_files=total,
            impacted_test_files=impacted_count,
            reduction_pct=reduction,
            test_framework=self._detect_test_framework(),
        )

    def analyze_and_run(self) -> ImpactReport:
        """Analyze and run only impacted tests."""
        report = self.analyze()
        if report.impacted_tests:
            report.run_result = self._run_impacted_tests(report.impacted_tests)
        else:
            report.run_result = {"status": "skip", "message": "No impacted tests found"}
        return report

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _get_changed_files(self) -> list[str]:
        """Get files changed relative to base branch."""
        # Try branch diff first
        output = self._run_git("diff", "--name-only", f"{self.base}...HEAD")
        if not output:
            # Fallback to staged + unstaged
            output = self._run_git("diff", "--name-only", "HEAD")
        if not output:
            output = self._run_git("diff", "--name-only")
        return [f for f in output.split("\n") if f.strip()] if output else []

    def _get_changed_functions(self, files: list[str]) -> list[str]:
        """Extract changed function names from diffs using AST."""
        functions = []
        for f in files:
            if not f.endswith(".py"):
                continue
            full_path = os.path.join(self.cwd, f)
            if not os.path.exists(full_path):
                continue

            # Get diff for this file to find changed line ranges
            diff = self._run_git("diff", f"{self.base}...HEAD", "--", f)
            if not diff:
                diff = self._run_git("diff", "HEAD", "--", f)
            changed_lines = self._parse_diff_lines(diff)

            # Parse AST to find functions at those lines
            try:
                source = Path(full_path).read_text(errors="replace")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not changed_lines or node.lineno in changed_lines:
                            functions.append(f"{f}::{node.name}")
                    elif isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if not changed_lines or item.lineno in changed_lines:
                                    functions.append(f"{f}::{node.name}.{item.name}")
            except (SyntaxError, OSError):
                continue

        return functions

    def _parse_diff_lines(self, diff: str) -> set[int]:
        """Parse diff to find changed line numbers in the new file."""
        changed = set()
        if not diff:
            return changed
        for line in diff.split("\n"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                changed.update(range(start, start + count))
        return changed

    def _find_all_test_files(self) -> list[str]:
        """Find all test files in the repository."""
        test_files = []
        for root, dirs, files in os.walk(self.cwd):
            # Skip hidden dirs and common non-test dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv")]
            rel_root = os.path.relpath(root, self.cwd)
            for f in files:
                if _TEST_FILE_PATTERNS.search(f):
                    rel_path = os.path.join(rel_root, f) if rel_root != "." else f
                    test_files.append(rel_path)
        return test_files

    def _build_import_graph(self) -> dict[str, set[str]]:
        """Build a mapping of module -> set of files that import it."""
        if self._import_graph is not None:
            return self._import_graph

        graph: dict[str, set[str]] = defaultdict(set)
        for root, dirs, files in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.cwd)
                try:
                    source = Path(full_path).read_text(errors="replace")
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                module = alias.name.replace(".", "/")
                                graph[module].add(rel_path)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                module = node.module.replace(".", "/")
                                graph[module].add(rel_path)
                except (SyntaxError, OSError):
                    continue

        self._import_graph = graph
        return graph

    def _map_to_tests(self, changed_files: list[str], changed_functions: list[str],
                      all_test_files: list[str]) -> list[ImpactedTest]:
        """Map changed files/functions to impacted tests."""
        impacted: dict[str, ImpactedTest] = {}

        # 1. Naming convention: test_<module>.py for <module>.py
        for cf in changed_files:
            stem = Path(cf).stem
            for tf in all_test_files:
                tf_stem = Path(tf).stem
                if tf_stem == f"test_{stem}" or tf_stem == f"{stem}_test":
                    if tf not in impacted:
                        impacted[tf] = ImpactedTest(
                            test_file=tf, reason="naming convention", confidence=0.95,
                        )

        # 2. Direct import: test files that import changed modules
        import_graph = self._build_import_graph()
        for cf in changed_files:
            if not cf.endswith(".py"):
                continue
            module = cf.replace("/", ".").replace("\\", ".").removesuffix(".py")
            module_path = cf.removesuffix(".py")
            # Check which test files import this module
            importers = import_graph.get(module_path, set()) | import_graph.get(module, set())
            for importer in importers:
                if _TEST_FILE_PATTERNS.search(importer):
                    if importer not in impacted:
                        impacted[importer] = ImpactedTest(
                            test_file=importer, reason="direct import", confidence=0.9,
                        )

        # 3. Same directory tests
        for cf in changed_files:
            cf_dir = str(Path(cf).parent)
            for tf in all_test_files:
                tf_dir = str(Path(tf).parent)
                if cf_dir == tf_dir and tf not in impacted:
                    impacted[tf] = ImpactedTest(
                        test_file=tf, reason="same directory", confidence=0.5,
                    )

        # 4. If changed file is itself a test file
        for cf in changed_files:
            if _TEST_FILE_PATTERNS.search(cf) and cf not in impacted:
                impacted[cf] = ImpactedTest(
                    test_file=cf, reason="directly changed", confidence=1.0,
                )

        # Map functions to test functions
        for func_ref in changed_functions:
            file_part, func_name = func_ref.split("::", 1) if "::" in func_ref else (func_ref, "")
            if "." in func_name:
                _, method = func_name.rsplit(".", 1)
            else:
                method = func_name
            if method:
                for tf, impact in impacted.items():
                    test_func = f"test_{method}"
                    impact.test_functions.append(test_func)

        return sorted(impacted.values(), key=lambda x: -x.confidence)

    def _detect_test_framework(self) -> str:
        """Detect the test framework."""
        if os.path.exists(os.path.join(self.cwd, "pytest.ini")) or \
           os.path.exists(os.path.join(self.cwd, "conftest.py")):
            return "pytest"
        pyproject = os.path.join(self.cwd, "pyproject.toml")
        if os.path.exists(pyproject):
            content = Path(pyproject).read_text()
            if "pytest" in content:
                return "pytest"
        pkg = os.path.join(self.cwd, "package.json")
        if os.path.exists(pkg):
            content = Path(pkg).read_text()
            if "jest" in content:
                return "jest"
            if "mocha" in content:
                return "mocha"
        return "pytest"

    def _run_impacted_tests(self, tests: list[ImpactedTest]) -> dict:
        """Run only the impacted tests."""
        test_files = [t.test_file for t in tests]
        framework = self._detect_test_framework()

        try:
            if framework == "pytest":
                cmd = ["poetry", "run", "pytest"] + test_files + ["--tb=short", "-q"]
            elif framework == "jest":
                cmd = ["npx", "jest"] + test_files + ["--no-coverage"]
            else:
                cmd = ["pytest"] + test_files + ["--tb=short", "-q"]

            result = subprocess.run(
                cmd, cwd=self.cwd, capture_output=True, text=True, timeout=300,
            )
            return {
                "status": "pass" if result.returncode == 0 else "fail",
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-500:],
                "tests_run": len(test_files),
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "tests_run": len(test_files)}
        except FileNotFoundError as e:
            return {"status": "error", "error": str(e)}


def format_test_impact(report: ImpactReport) -> str:
    """Format test impact report for display."""
    lines = [
        "## Test Impact Analysis",
        "",
        f"**Framework:** {report.test_framework}",
        f"**Changed Files:** {len(report.changed_files)}",
        f"**Changed Functions:** {len(report.changed_functions)}",
        f"**Total Test Files:** {report.total_test_files}",
        f"**Impacted Tests:** {report.impacted_test_files}",
        f"**Reduction:** {report.reduction_pct}% (skipping {report.skipped_tests} test files)",
        "",
    ]

    if report.changed_files:
        lines.extend(["### Changed Files", ""])
        for f in report.changed_files[:20]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report.changed_functions:
        lines.extend(["### Changed Functions", ""])
        for f in report.changed_functions[:20]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report.impacted_tests:
        lines.extend(["### Impacted Tests", ""])
        for t in report.impacted_tests:
            conf = f"{t.confidence:.0%}"
            lines.append(f"- `{t.test_file}` ({t.reason}, {conf} confidence)")
            if t.test_functions:
                for func in t.test_functions[:5]:
                    lines.append(f"  - `{func}`")
        lines.append("")

    if report.run_result:
        r = report.run_result
        status_icon = {"pass": "✅", "fail": "❌", "timeout": "⏰", "error": "💥"}.get(
            r.get("status", ""), "❓")
        lines.extend([
            "### Test Run Results", "",
            f"{status_icon} **Status:** {r.get('status', 'unknown')}",
            f"**Tests Run:** {r.get('tests_run', 0)}",
        ])
        if r.get("stdout"):
            lines.extend(["", "```", r["stdout"][-1000:], "```"])
        lines.append("")

    return "\n".join(lines)
