"""Test gap finder — cross-reference source modules against test files.

Discovers which source modules lack corresponding test files and
which functions/classes within tested files are not covered by test cases.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.testing.test_gap_finder")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "migrations", "alembic",
}

# Files not expected to have dedicated tests
SKIP_FILES = {
    "__init__.py", "conftest.py", "__main__.py", "setup.py",
    "__version__.py", "wsgi.py", "asgi.py",
}


@dataclass
class GapInfo:
    """A single testing gap."""

    source_file: str = ""
    test_file: str | None = None  # None if no test file exists
    missing_functions: list[str] = field(default_factory=list)
    missing_classes: list[str] = field(default_factory=list)
    gap_type: str = ""  # no_test_file | partial_coverage | no_public_api
    priority: str = "medium"  # low | medium | high | critical


@dataclass
class GapInfoResult:
    """Result of test gap analysis."""

    source_files: int = 0
    test_files: int = 0
    files_with_tests: int = 0
    files_without_tests: int = 0
    gaps: list[GapInfo] = field(default_factory=list)
    coverage_ratio: float = 0.0
    summary: dict[str, int] = field(default_factory=dict)


class TestGapFinder:
    """Find untested code by cross-referencing source and test files."""

    __test__ = False  # Not a pytest class

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("TestGapFinder initialized for %s", cwd)

    def find_gaps(
        self,
        source_dirs: list[str] | None = None,
        test_dirs: list[str] | None = None,
        test_prefix: str = "test_",
    ) -> GapInfoResult:
        """Find testing gaps in the codebase.

        Args:
            source_dirs: Source directories to scan. Auto-detected if None.
            test_dirs: Test directories. Auto-detected if None.
            test_prefix: Test file prefix (default: test_).

        Returns:
            GapInfoResult with gaps and coverage stats.
        """
        result = GapInfoResult()

        src_dirs = source_dirs or self._detect_source_dirs()
        tst_dirs = test_dirs or self._detect_test_dirs()
        logger.info("Source dirs: %s, Test dirs: %s", src_dirs, tst_dirs)

        # Collect files
        source_files = self._collect_source_files(src_dirs)
        test_files = self._collect_test_files(tst_dirs, test_prefix)
        result.source_files = len(source_files)
        result.test_files = len(test_files)

        # Build test file mapping: module_name -> test_file_path
        test_map = self._build_test_map(test_files, test_prefix)

        # Check each source file
        for src_path in source_files:
            rel = os.path.relpath(src_path, self.cwd)
            module_name = Path(src_path).stem

            if module_name.startswith("_") and module_name != "__init__":
                continue

            test_file = test_map.get(module_name)

            if test_file is None:
                # No test file at all
                public_api = self._extract_public_api(src_path)
                if not public_api["functions"] and not public_api["classes"]:
                    continue  # No public API to test

                priority = "critical" if len(public_api["functions"]) > 5 else "high"
                result.gaps.append(GapInfo(
                    source_file=rel,
                    gap_type="no_test_file",
                    missing_functions=public_api["functions"],
                    missing_classes=public_api["classes"],
                    priority=priority,
                ))
                result.files_without_tests += 1
            else:
                # Test file exists — check partial coverage
                result.files_with_tests += 1
                public_api = self._extract_public_api(src_path)
                tested_names = self._extract_tested_names(test_file)
                missing_funcs = [
                    f for f in public_api["functions"]
                    if not self._is_likely_tested(f, tested_names)
                ]
                missing_classes = [
                    c for c in public_api["classes"]
                    if not self._is_likely_tested(c, tested_names)
                ]
                if missing_funcs or missing_classes:
                    result.gaps.append(GapInfo(
                        source_file=rel,
                        test_file=os.path.relpath(test_file, self.cwd),
                        gap_type="partial_coverage",
                        missing_functions=missing_funcs,
                        missing_classes=missing_classes,
                        priority="medium",
                    ))

        total = result.files_with_tests + result.files_without_tests
        result.coverage_ratio = (
            result.files_with_tests / total if total > 0 else 0.0
        )

        result.summary = {
            "source_files": result.source_files,
            "test_files": result.test_files,
            "files_with_tests": result.files_with_tests,
            "files_without_tests": result.files_without_tests,
            "total_gaps": len(result.gaps),
            "critical_gaps": sum(1 for g in result.gaps if g.priority == "critical"),
            "coverage_ratio": round(result.coverage_ratio * 100, 1),
        }
        logger.info(
            "Gap analysis complete: %d gaps, %.1f%% file coverage",
            len(result.gaps), result.coverage_ratio * 100,
        )
        return result

    def _detect_source_dirs(self) -> list[str]:
        """Auto-detect source directories."""
        candidates = ["src", "lib", "code_agents", "app"]
        dirs = []
        for c in candidates:
            path = os.path.join(self.cwd, c)
            if os.path.isdir(path):
                dirs.append(path)
        if not dirs:
            dirs = [self.cwd]
        return dirs

    def _detect_test_dirs(self) -> list[str]:
        """Auto-detect test directories."""
        candidates = ["tests", "test", "spec"]
        dirs = []
        for c in candidates:
            path = os.path.join(self.cwd, c)
            if os.path.isdir(path):
                dirs.append(path)
        return dirs

    def _collect_source_files(self, dirs: list[str]) -> list[str]:
        """Collect source Python files."""
        files: list[str] = []
        for d in dirs:
            for root, subdirs, fnames in os.walk(d):
                subdirs[:] = [s for s in subdirs if s not in SKIP_DIRS]
                for fname in fnames:
                    if fname.endswith(".py") and fname not in SKIP_FILES:
                        if not fname.startswith("test_"):
                            files.append(os.path.join(root, fname))
        return files

    def _collect_test_files(self, dirs: list[str], prefix: str) -> list[str]:
        """Collect test files."""
        files: list[str] = []
        for d in dirs:
            for root, subdirs, fnames in os.walk(d):
                subdirs[:] = [s for s in subdirs if s not in SKIP_DIRS]
                for fname in fnames:
                    if fname.startswith(prefix) and fname.endswith(".py"):
                        files.append(os.path.join(root, fname))
        return files

    def _build_test_map(self, test_files: list[str], prefix: str) -> dict[str, str]:
        """Build mapping from module name to test file path."""
        mapping: dict[str, str] = {}
        for tf in test_files:
            name = Path(tf).stem
            if name.startswith(prefix):
                module_name = name[len(prefix):]
                mapping[module_name] = tf
        return mapping

    def _extract_public_api(self, filepath: str) -> dict[str, list[str]]:
        """Extract public functions and classes from a Python file."""
        try:
            content = Path(filepath).read_text(errors="replace")
            tree = ast.parse(content)
        except (SyntaxError, OSError):
            return {"functions": [], "classes": []}

        functions: list[str] = []
        classes: list[str] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    classes.append(node.name)

        return {"functions": functions, "classes": classes}

    def _extract_tested_names(self, test_file: str) -> set[str]:
        """Extract names referenced in a test file."""
        try:
            content = Path(test_file).read_text(errors="replace")
        except OSError:
            return set()

        # Collect all identifiers from the test file
        names: set[str] = set()
        # Import names
        for match in re.finditer(r"import\s+.*?(\w+)", content):
            names.add(match.group(1))
        for match in re.finditer(r"from\s+\S+\s+import\s+(.+)", content):
            for name in match.group(1).split(","):
                names.add(name.strip().split(" as ")[0].strip())
        # Called names
        for match in re.finditer(r"\b(\w+)\s*\(", content):
            names.add(match.group(1))

        return names

    def _is_likely_tested(self, name: str, tested_names: set[str]) -> bool:
        """Check if a name is likely tested based on test file content."""
        if name in tested_names:
            return True
        # Check snake_case → CamelCase variants
        camel = "".join(w.capitalize() for w in name.split("_"))
        return camel in tested_names


def find_test_gaps(
    cwd: str,
    source_dirs: list[str] | None = None,
    test_dirs: list[str] | None = None,
) -> dict:
    """Convenience function to find test gaps.

    Returns:
        Dict with gaps, coverage ratio, and summary.
    """
    finder = TestGapFinder(cwd)
    result = finder.find_gaps(source_dirs=source_dirs, test_dirs=test_dirs)
    return {
        "gaps": [
            {
                "source_file": g.source_file, "test_file": g.test_file,
                "gap_type": g.gap_type, "priority": g.priority,
                "missing_functions": g.missing_functions,
                "missing_classes": g.missing_classes,
            }
            for g in result.gaps
        ],
        "coverage_ratio": result.coverage_ratio,
        "summary": result.summary,
    }
