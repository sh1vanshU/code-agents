"""Mutation testing engine — inject code mutations, verify tests catch them.

Auto-generates mutants (negated conditions, swapped operators, removed returns, etc.)
and runs the test suite against each one. Surviving mutations indicate weak test coverage.
"""

from __future__ import annotations

import ast
import copy
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.mutation_testing")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Mutation:
    """A single code mutation."""

    file: str
    line: int
    original: str
    mutated: str
    mutation_type: str  # "negate_condition", "remove_return", "swap_operator", "boundary", "null_return", "remove_call", "swap_boolean", "swap_constant"
    killed: bool = False
    surviving: bool = False
    test_that_caught: str = ""


@dataclass
class MutationReport:
    """Aggregated mutation testing results."""

    total_mutations: int = 0
    killed: int = 0
    survived: int = 0
    score: float = 0.0  # killed / total (0-1)
    timed_out: int = 0
    errors: int = 0
    survivors: list[Mutation] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Operator swap tables
# ---------------------------------------------------------------------------

_COMPARISON_SWAPS = {
    ">": "<=",
    "<": ">=",
    ">=": "<",
    "<=": ">",
    "==": "!=",
    "!=": "==",
}

_ARITHMETIC_SWAPS = {
    "+": "-",
    "-": "+",
    "*": "/",
    "/": "*",
    "//": "/",
    "%": "*",
}

_LOGICAL_SWAPS = {
    " and ": " or ",
    " or ": " and ",
}

_BOUNDARY_SHIFTS = {
    "> 0": "> 1",
    ">= 0": "> 0",
    "< 0": "<= 0",
    "<= 0": "< 0",
    "> 1": "> 0",
    ">= 1": "> 1",
}


# ---------------------------------------------------------------------------
# MutationTester
# ---------------------------------------------------------------------------

class MutationTester:
    """Generate and test code mutations to find weak spots in test suites."""

    def __init__(self, cwd: str, test_command: str = ""):
        self.cwd = os.path.abspath(cwd)
        self.test_command = test_command or self._detect_test_command()
        self._backup_dir = tempfile.mkdtemp(prefix="mutation_backup_")
        logger.info("MutationTester initialized: cwd=%s, test_command=%s", self.cwd, self.test_command)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, target: str = "", max_mutations: int = 50) -> MutationReport:
        """Run mutation testing on target file(s).

        Args:
            target: Specific file or directory to mutate (relative to cwd).
                    Empty string means auto-discover source files.
            max_mutations: Maximum number of mutations to test.

        Returns:
            MutationReport with score and surviving mutations.
        """
        start = time.time()
        report = MutationReport()

        # 1. Find target files
        source_files = self._find_source_files(target)
        if not source_files:
            logger.warning("No source files found for mutation testing")
            report.duration_seconds = time.time() - start
            return report

        logger.info("Found %d source files for mutation", len(source_files))

        # 2. Generate mutations across all files
        all_mutations: list[Mutation] = []
        for sf in source_files:
            mutations = self._generate_mutations(sf)
            all_mutations.extend(mutations)
            if len(all_mutations) >= max_mutations:
                break

        all_mutations = all_mutations[:max_mutations]
        report.total_mutations = len(all_mutations)
        logger.info("Generated %d mutations (capped at %d)", len(all_mutations), max_mutations)

        # 3. Test each mutation
        for idx, mutation in enumerate(all_mutations, 1):
            logger.debug("Testing mutation %d/%d: %s:%d (%s)",
                         idx, report.total_mutations, mutation.file, mutation.line, mutation.mutation_type)
            try:
                self._apply_mutation(mutation)
                result = self._run_tests(mutation, timeout=30)

                if result == "killed":
                    mutation.killed = True
                    report.killed += 1
                elif result == "survived":
                    mutation.surviving = True
                    report.survived += 1
                    report.survivors.append(mutation)
                elif result == "timeout":
                    report.timed_out += 1
                else:  # error
                    report.errors += 1
            except Exception as exc:
                logger.error("Error processing mutation %s:%d: %s", mutation.file, mutation.line, exc)
                report.errors += 1
            finally:
                self._restore_original(mutation)

        # 4. Compute score
        if report.total_mutations > 0:
            report.score = report.killed / report.total_mutations

        report.duration_seconds = time.time() - start
        logger.info("Mutation testing complete: score=%.1f%% (%d/%d killed) in %.1fs",
                     report.score * 100, report.killed, report.total_mutations, report.duration_seconds)
        return report

    # ------------------------------------------------------------------
    # Test command detection
    # ------------------------------------------------------------------

    def _detect_test_command(self) -> str:
        """Auto-detect the project's test command."""
        # Python: pytest / poetry run pytest
        if os.path.isfile(os.path.join(self.cwd, "pyproject.toml")):
            if shutil.which("poetry"):
                return "poetry run pytest -x -q --tb=no --no-header"
            return "pytest -x -q --tb=no --no-header"

        if os.path.isfile(os.path.join(self.cwd, "setup.py")) or os.path.isfile(os.path.join(self.cwd, "setup.cfg")):
            return "pytest -x -q --tb=no --no-header"

        # Node.js
        if os.path.isfile(os.path.join(self.cwd, "package.json")):
            return "npm test"

        # Go
        if os.path.isfile(os.path.join(self.cwd, "go.mod")):
            return "go test ./..."

        # Java / Maven
        if os.path.isfile(os.path.join(self.cwd, "pom.xml")):
            return "mvn test -q"

        # Java / Gradle
        if os.path.isfile(os.path.join(self.cwd, "build.gradle")) or os.path.isfile(os.path.join(self.cwd, "build.gradle.kts")):
            return "./gradlew test"

        # Fallback
        logger.warning("Could not auto-detect test command, defaulting to pytest")
        return "pytest -x -q --tb=no --no-header"

    # ------------------------------------------------------------------
    # Source file discovery
    # ------------------------------------------------------------------

    def _find_source_files(self, target: str = "") -> list[str]:
        """Find Python source files to mutate."""
        if target:
            abs_target = os.path.join(self.cwd, target) if not os.path.isabs(target) else target
            if os.path.isfile(abs_target):
                return [abs_target]
            if os.path.isdir(abs_target):
                return self._collect_python_files(abs_target)
            return []

        # Auto-discover: look for common source dirs
        candidates = ["src", "lib", "app", "code_agents"]
        for c in candidates:
            d = os.path.join(self.cwd, c)
            if os.path.isdir(d):
                return self._collect_python_files(d)

        # Fallback: .py files in cwd (non-test, non-config)
        return self._collect_python_files(self.cwd)

    def _collect_python_files(self, directory: str) -> list[str]:
        """Collect Python files suitable for mutation."""
        files = []
        skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".tox", ".eggs", "build", "dist"}
        skip_prefixes = ("test_", "conftest")
        skip_suffixes = ("_test.py",)

        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                if fn.startswith(skip_prefixes) or fn.endswith(skip_suffixes):
                    continue
                if fn in ("__init__.py", "setup.py", "conftest.py"):
                    continue
                files.append(os.path.join(root, fn))
        return sorted(files)

    # ------------------------------------------------------------------
    # Mutation generation
    # ------------------------------------------------------------------

    def _generate_mutations(self, file_path: str) -> list[Mutation]:
        """Generate mutations for a single file using AST analysis + regex."""
        mutations: list[Mutation] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return mutations

        # Try AST-based mutations for Python files
        if file_path.endswith(".py"):
            mutations.extend(self._generate_python_ast_mutations(file_path, lines))

        # Also apply regex-based mutations (works for any language)
        mutations.extend(self._generate_regex_mutations(file_path, lines))

        # Deduplicate by (file, line, mutation_type)
        seen: set[tuple[str, int, str]] = set()
        unique: list[Mutation] = []
        for m in mutations:
            key = (m.file, m.line, m.mutation_type)
            if key not in seen:
                seen.add(key)
                unique.append(m)

        return unique

    def _generate_python_ast_mutations(self, file_path: str, lines: list[str]) -> list[Mutation]:
        """Use Python AST to find precise mutation points."""
        mutations: list[Mutation] = []
        source = "".join(lines)
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            logger.debug("Cannot parse %s as Python AST", file_path)
            return mutations

        for node in ast.walk(tree):
            # Negate conditions in if/while/assert
            if isinstance(node, (ast.If, ast.While, ast.Assert)):
                test_node = node.test
                lineno = test_node.lineno
                if 1 <= lineno <= len(lines):
                    original = lines[lineno - 1]
                    # Wrap condition in `not (...)`
                    mutated = self._negate_condition_line(original)
                    if mutated and mutated != original:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=original, mutated=mutated,
                            mutation_type="negate_condition",
                        ))

            # Remove return value -> return None
            if isinstance(node, ast.Return) and node.value is not None:
                lineno = node.lineno
                if 1 <= lineno <= len(lines):
                    original = lines[lineno - 1]
                    indent = len(original) - len(original.lstrip())
                    mutated = " " * indent + "return None\n"
                    if mutated != original:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=original, mutated=mutated,
                            mutation_type="remove_return",
                        ))

            # Remove function calls (standalone Expr(Call))
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                lineno = node.lineno
                if 1 <= lineno <= len(lines):
                    original = lines[lineno - 1]
                    indent = len(original) - len(original.lstrip())
                    mutated = " " * indent + "pass\n"
                    if mutated != original:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=original, mutated=mutated,
                            mutation_type="remove_call",
                        ))

        return mutations

    def _generate_regex_mutations(self, file_path: str, lines: list[str]) -> list[Mutation]:
        """Apply regex-based mutations for broader language support."""
        mutations: list[Mutation] = []

        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and empty lines
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Swap comparison operators
            for old_op, new_op in _COMPARISON_SWAPS.items():
                # Match operator surrounded by spaces or adjacent to word chars
                pattern = re.compile(r'(?<=\S)\s*' + re.escape(old_op) + r'\s*(?=\S)')
                if pattern.search(line):
                    mutated = line.replace(old_op, new_op, 1)
                    if mutated != line:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=line, mutated=mutated,
                            mutation_type="swap_operator",
                        ))
                        break  # One operator swap per line

            # Swap arithmetic operators (only in expressions, not strings)
            for old_op, new_op in _ARITHMETIC_SWAPS.items():
                # Look for operator with spaces around it (avoids matching in strings/paths)
                spaced = f" {old_op} "
                if spaced in line and not stripped.startswith(("def ", "class ", "import ", "from ")):
                    mutated = line.replace(spaced, f" {new_op} ", 1)
                    if mutated != line:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=line, mutated=mutated,
                            mutation_type="swap_operator",
                        ))
                        break

            # Swap logical operators
            for old_op, new_op in _LOGICAL_SWAPS.items():
                if old_op in line:
                    mutated = line.replace(old_op, new_op, 1)
                    if mutated != line:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=line, mutated=mutated,
                            mutation_type="swap_operator",
                        ))
                        break

            # Boundary mutations
            for old_boundary, new_boundary in _BOUNDARY_SHIFTS.items():
                if old_boundary in line:
                    mutated = line.replace(old_boundary, new_boundary, 1)
                    if mutated != line:
                        mutations.append(Mutation(
                            file=file_path, line=lineno,
                            original=line, mutated=mutated,
                            mutation_type="boundary",
                        ))
                        break

            # Swap True/False
            if "True" in line and not stripped.startswith(("def ", "class ", "#")):
                mutated = line.replace("True", "False", 1)
                if mutated != line:
                    mutations.append(Mutation(
                        file=file_path, line=lineno,
                        original=line, mutated=mutated,
                        mutation_type="swap_boolean",
                    ))
            elif "False" in line and not stripped.startswith(("def ", "class ", "#")):
                mutated = line.replace("False", "True", 1)
                if mutated != line:
                    mutations.append(Mutation(
                        file=file_path, line=lineno,
                        original=line, mutated=mutated,
                        mutation_type="swap_boolean",
                    ))

            # Swap 0/1 constants (standalone, not part of larger number)
            if re.search(r'\b0\b', line) and not stripped.startswith(("#", "import", "from")):
                mutated = re.sub(r'\b0\b', '1', line, count=1)
                if mutated != line:
                    mutations.append(Mutation(
                        file=file_path, line=lineno,
                        original=line, mutated=mutated,
                        mutation_type="swap_constant",
                    ))

        return mutations

    # ------------------------------------------------------------------
    # Mutation application & restoration
    # ------------------------------------------------------------------

    def _apply_mutation(self, mutation: Mutation) -> None:
        """Apply a mutation to a file, backing up the original first."""
        file_path = mutation.file
        backup_path = self._backup_path(file_path)

        # Create backup (atomic copy)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(file_path, backup_path)
        logger.debug("Backed up %s -> %s", file_path, backup_path)

        # Read file and apply mutation
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if 1 <= mutation.line <= len(lines):
            lines[mutation.line - 1] = mutation.mutated

        # Write mutated file atomically
        tmp_path = file_path + ".mutation_tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(tmp_path, file_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        logger.debug("Applied mutation at %s:%d (%s)", file_path, mutation.line, mutation.mutation_type)

    def _restore_original(self, mutation: Mutation) -> None:
        """Restore the original file from backup."""
        file_path = mutation.file
        backup_path = self._backup_path(file_path)

        if os.path.isfile(backup_path):
            shutil.copy2(backup_path, file_path)
            os.unlink(backup_path)
            logger.debug("Restored %s from backup", file_path)
        else:
            logger.warning("No backup found for %s — cannot restore", file_path)

    def _backup_path(self, file_path: str) -> str:
        """Compute backup path for a source file."""
        # Use relative path from cwd as subdirectory in backup dir
        rel = os.path.relpath(file_path, self.cwd)
        return os.path.join(self._backup_dir, rel)

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def _run_tests(self, mutation: Mutation, timeout: int = 30) -> str:
        """Run the test suite against a mutated codebase.

        Returns:
            "killed"   — tests failed (mutation caught = good)
            "survived" — tests passed (mutation not caught = bad)
            "timeout"  — tests timed out
            "error"    — could not run tests
        """
        test_file = self._find_test_file(mutation.file)
        cmd = self.test_command
        if test_file:
            # Run only the relevant test file for speed
            if "pytest" in cmd:
                cmd = f"{cmd} {test_file}"
            elif "go test" in cmd:
                pass  # go test ./... already runs all
            # For other runners, keep the full suite

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                timeout=timeout,
                text=True,
            )
            if result.returncode != 0:
                # Tests failed — mutation was killed
                logger.debug("Mutation killed: %s:%d (exit=%d)", mutation.file, mutation.line, result.returncode)
                return "killed"
            else:
                # Tests passed — mutation survived
                logger.debug("Mutation survived: %s:%d", mutation.file, mutation.line)
                return "survived"
        except subprocess.TimeoutExpired:
            logger.debug("Mutation timed out: %s:%d", mutation.file, mutation.line)
            return "timeout"
        except OSError as exc:
            logger.error("Error running tests: %s", exc)
            return "error"

    def _find_test_file(self, source_file: str) -> str:
        """Map a source file to its corresponding test file."""
        base = os.path.basename(source_file)
        name, ext = os.path.splitext(base)

        # Common patterns
        candidates = [
            f"test_{name}{ext}",
            f"{name}_test{ext}",
            f"tests/test_{name}{ext}",
            f"test/test_{name}{ext}",
        ]

        # Try relative to cwd
        for candidate in candidates:
            full = os.path.join(self.cwd, candidate)
            if os.path.isfile(full):
                return full

        # Try relative to source file's directory
        src_dir = os.path.dirname(source_file)
        for candidate in candidates:
            full = os.path.join(src_dir, candidate)
            if os.path.isfile(full):
                return full

        # Try tests/ at project root
        test_dir = os.path.join(self.cwd, "tests")
        if os.path.isdir(test_dir):
            test_file = os.path.join(test_dir, f"test_{name}{ext}")
            if os.path.isfile(test_file):
                return test_file

        return ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _negate_condition_line(line: str) -> Optional[str]:
        """Negate a condition in a line (e.g., `if x > 0:` -> `if not (x > 0):`)."""
        # Match if/while/elif/assert followed by condition
        m = re.match(r'^(\s*)(if|elif|while|assert)\s+(.+?)(\s*:\s*)$', line)
        if m:
            indent, keyword, condition, colon = m.groups()
            # Already negated? Remove not
            if condition.startswith("not "):
                return f"{indent}{keyword} {condition[4:]}{colon}"
            return f"{indent}{keyword} not ({condition}){colon}"
        return None

    def cleanup(self) -> None:
        """Remove temporary backup directory."""
        if os.path.isdir(self._backup_dir):
            shutil.rmtree(self._backup_dir, ignore_errors=True)
            logger.debug("Cleaned up backup dir: %s", self._backup_dir)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_mutation_report(report: MutationReport) -> str:
    """Format a mutation testing report as a rich terminal box.

    Returns a string with the formatted report.
    """
    if report.total_mutations == 0:
        return (
            "\n"
            "  No mutations generated.\n"
            "  Check that target files exist and contain mutable code.\n"
        )

    pct = int(report.score * 100)
    bar_filled = int(10 * report.score)
    bar_empty = 10 - bar_filled
    bar = "\u2588" * bar_filled + "\u2591" * bar_empty

    width = 50
    lines: list[str] = []
    lines.append(f"\u256d\u2500 Mutation Testing {'─' * (width - 20)}\u256e")
    lines.append(f"\u2502 Score: {pct}% ({report.killed}/{report.total_mutations} mutations killed){' ' * max(0, width - 38 - len(str(pct)) - len(str(report.killed)) - len(str(report.total_mutations)))}\u2502")
    stats = f"{bar} {report.killed} killed, {report.survived} survived, {report.errors} errors"
    lines.append(f"\u2502 {stats}{' ' * max(0, width - len(stats) - 1)}\u2502")

    if report.timed_out:
        to_line = f"Timed out: {report.timed_out}"
        lines.append(f"\u2502 {to_line}{' ' * max(0, width - len(to_line) - 1)}\u2502")

    duration_line = f"Duration: {report.duration_seconds:.1f}s"
    lines.append(f"\u2502 {duration_line}{' ' * max(0, width - len(duration_line) - 1)}\u2502")

    if report.survivors:
        lines.append(f"\u251c{'─' * width}\u2524")
        header = "SURVIVORS (weak spots):"
        lines.append(f"\u2502 {header}{' ' * max(0, width - len(header) - 1)}\u2502")
        for s in report.survivors[:10]:  # Show top 10
            rel_file = os.path.basename(s.file)
            desc = f"{rel_file}:{s.line} \u2014 {s.mutation_type} NOT caught"
            if len(desc) > width - 2:
                desc = desc[:width - 5] + "..."
            lines.append(f"\u2502 {desc}{' ' * max(0, width - len(desc) - 1)}\u2502")
        if len(report.survivors) > 10:
            more = f"... and {len(report.survivors) - 10} more"
            lines.append(f"\u2502 {more}{' ' * max(0, width - len(more) - 1)}\u2502")

    lines.append(f"\u2570{'─' * width}\u256f")

    return "\n".join(lines) + "\n"


def format_mutation_report_json(report: MutationReport) -> dict:
    """Format report as a JSON-serializable dictionary."""
    return {
        "total_mutations": report.total_mutations,
        "killed": report.killed,
        "survived": report.survived,
        "score": round(report.score, 4),
        "score_percent": round(report.score * 100, 1),
        "timed_out": report.timed_out,
        "errors": report.errors,
        "duration_seconds": round(report.duration_seconds, 2),
        "survivors": [
            {
                "file": s.file,
                "line": s.line,
                "mutation_type": s.mutation_type,
                "original": s.original.rstrip(),
                "mutated": s.mutated.rstrip(),
            }
            for s in report.survivors
        ],
    }
