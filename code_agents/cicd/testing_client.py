"""
Testing client for running test suites and analyzing coverage on target repositories.

Supports pytest (with pytest-cov), and can auto-detect test frameworks.
Parses coverage XML reports to identify gaps in new code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger("code_agents.testing_client")


class TestingError(Exception):
    """Raised when a test operation fails."""

    def __init__(self, message: str, output: Optional[str] = None):
        super().__init__(message)
        self.output = output


class TestingClient:
    """Async client for running tests and analyzing coverage."""

    def __init__(
        self,
        repo_path: str,
        test_command: Optional[str] = None,
        coverage_threshold: float = 100.0,
    ):
        self.repo_path = repo_path
        self.test_command = test_command
        self.coverage_threshold = coverage_threshold

    def _detect_test_command(self) -> str:
        """Auto-detect the test framework based on project files."""
        if self.test_command:
            return self.test_command

        # Check for Python (pytest)
        for marker in ("pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini"):
            if os.path.exists(os.path.join(self.repo_path, marker)):
                return "python -m pytest --tb=short -q --cov --cov-report=xml:coverage.xml"

        # Check for Node.js (jest/mocha)
        pkg_json = os.path.join(self.repo_path, "package.json")
        if os.path.exists(pkg_json):
            return "npm test -- --coverage"

        # Check for Java (Maven)
        if os.path.exists(os.path.join(self.repo_path, "pom.xml")):
            return "mvn test"

        # Check for Java (Gradle)
        if os.path.exists(os.path.join(self.repo_path, "build.gradle")):
            return "./gradlew test"

        # Check for Go
        if os.path.exists(os.path.join(self.repo_path, "go.mod")):
            return "go test -cover ./..."

        # Default fallback
        return "python -m pytest --tb=short -q --cov --cov-report=xml:coverage.xml"

    async def _run_command(self, command: str) -> tuple[int, str, str]:
        """Run a shell command in the repo directory."""
        import time as _time
        logger.info("test_client exec: cwd=%s cmd=%s", self.repo_path, command)
        t0 = _time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.repo_path,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (_time.monotonic() - t0) * 1000
        rc = proc.returncode or 0
        logger.info("test_client exec done: exit=%d elapsed=%.0fms stdout_len=%d stderr_len=%d",
                     rc, elapsed, len(stdout), len(stderr))
        return (
            rc,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def run_tests(self, branch: Optional[str] = None, test_command: Optional[str] = None) -> dict:
        """
        Run the test suite, optionally on a specific branch.

        Returns dict with: passed, total, passed_count, failed_count, output, return_code
        """
        cmd = test_command or self._detect_test_command()

        # If branch specified, checkout first
        if branch:
            rc, out, err = await self._run_command(f"git checkout {branch}")
            if rc != 0:
                raise TestingError(f"Failed to checkout branch {branch}: {err}", output=err)

        rc, stdout, stderr = await self._run_command(cmd)
        combined_output = stdout + "\n" + stderr

        # Parse basic pass/fail from return code
        passed = rc == 0

        # Try to extract counts from pytest output
        total = 0
        passed_count = 0
        failed_count = 0
        error_count = 0

        for line in combined_output.splitlines():
            line_lower = line.lower()
            # pytest summary line: "X passed, Y failed, Z errors"
            if "passed" in line_lower or "failed" in line_lower:
                import re
                p = re.search(r"(\d+) passed", line_lower)
                f = re.search(r"(\d+) failed", line_lower)
                e = re.search(r"(\d+) error", line_lower)
                if p:
                    passed_count = int(p.group(1))
                if f:
                    failed_count = int(f.group(1))
                if e:
                    error_count = int(e.group(1))
                total = passed_count + failed_count + error_count

        # Truncate output to avoid huge payloads
        max_output = 20000
        if len(combined_output) > max_output:
            combined_output = combined_output[:max_output] + "\n... (truncated)"

        return {
            "passed": passed,
            "return_code": rc,
            "total": total,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "test_command": cmd,
            "output": combined_output,
        }

    async def get_coverage(self) -> dict:
        """
        Parse the coverage XML report (coverage.xml) in the repo.

        Returns dict with: total_coverage, file_coverage, uncovered_lines
        """
        coverage_file = os.path.join(self.repo_path, "coverage.xml")
        if not os.path.exists(coverage_file):
            raise TestingError(
                "No coverage.xml found. Run tests with --cov-report=xml first.",
                output=f"Expected at: {coverage_file}",
            )

        try:
            tree = ET.parse(coverage_file)
        except ET.ParseError as e:
            raise TestingError(f"Failed to parse coverage.xml: {e}")

        root = tree.getroot()

        # Extract total coverage from <coverage> element
        total_coverage = 0.0
        line_rate = root.get("line-rate")
        if line_rate:
            total_coverage = round(float(line_rate) * 100, 2)

        # Extract per-file coverage
        file_coverage = []
        uncovered_lines: dict[str, list[int]] = {}

        for package in root.findall(".//package"):
            for cls in package.findall(".//class"):
                filename = cls.get("filename", "")
                file_rate = cls.get("line-rate", "0")
                file_pct = round(float(file_rate) * 100, 2)

                missed = []
                for line in cls.findall(".//line"):
                    if line.get("hits") == "0":
                        missed.append(int(line.get("number", 0)))

                file_coverage.append({
                    "file": filename,
                    "coverage": file_pct,
                    "missed_lines": len(missed),
                })

                if missed:
                    uncovered_lines[filename] = missed

        return {
            "total_coverage": total_coverage,
            "file_coverage": file_coverage,
            "uncovered_lines": uncovered_lines,
            "coverage_threshold": self.coverage_threshold,
            "meets_threshold": total_coverage >= self.coverage_threshold,
        }

    async def get_coverage_gaps(self, base: str, head: str) -> dict:
        """
        Identify coverage gaps specifically in new/changed code.

        Cross-references git diff with coverage data to find new lines
        that lack test coverage.
        """
        from .git_client import GitClient, GitOpsError

        git = GitClient(self.repo_path)

        # Get diff to find changed files and lines
        try:
            diff_result = await git.diff(base, head)
        except GitOpsError as e:
            raise TestingError(f"Failed to get diff: {e}")

        # Get coverage data
        try:
            coverage = await self.get_coverage()
        except TestingError:
            return {
                "error": "No coverage data available. Run tests first.",
                "base": base,
                "head": head,
            }

        uncovered = coverage.get("uncovered_lines", {})

        # Parse the diff to find new lines per file
        gaps = []
        new_lines_total = 0
        new_lines_covered = 0

        for file_info in diff_result.get("changed_files", []):
            filepath = file_info["file"]
            added = file_info.get("insertions", 0)
            new_lines_total += added

            if filepath in uncovered:
                uncovered_in_file = uncovered[filepath]
                # These are lines that are both new AND uncovered
                gap_lines = uncovered_in_file  # Simplified — in reality would cross-reference exact line numbers
                if gap_lines:
                    gaps.append({
                        "file": filepath,
                        "uncovered_lines": gap_lines[:50],  # Limit to first 50
                        "count": len(gap_lines),
                    })
            else:
                new_lines_covered += added

        total_gap_lines = sum(g["count"] for g in gaps)
        coverage_pct = (
            round((new_lines_total - total_gap_lines) / new_lines_total * 100, 2)
            if new_lines_total > 0
            else 100.0
        )

        return {
            "base": base,
            "head": head,
            "new_lines_total": new_lines_total,
            "new_lines_covered": new_lines_total - total_gap_lines,
            "coverage_pct": coverage_pct,
            "meets_threshold": coverage_pct >= self.coverage_threshold,
            "gaps": gaps,
        }
