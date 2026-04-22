"""Test Fixer — analyze failing tests, diagnose root cause, suggest fix.

Reads test error output, maps to code changes, determines if the test
or the code is wrong, and suggests corrections.

Usage:
    from code_agents.testing.test_fixer import TestFixer
    fixer = TestFixer(TestFixerConfig(cwd="/path/to/repo"))
    result = fixer.diagnose(error_output)
    print(format_test_fix(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.testing.test_fixer")


@dataclass
class TestFixerConfig:
    cwd: str = "."


@dataclass
class TestFailure:
    """A parsed test failure."""
    test_file: str
    test_name: str = ""
    test_class: str = ""
    error_type: str = ""
    error_message: str = ""
    failing_line: int = 0
    failing_code: str = ""
    expected: str = ""
    actual: str = ""


@dataclass
class TestFixSuggestion:
    """A suggested fix for a failing test."""
    fix_type: str  # "update_assertion", "update_mock", "fix_import", "fix_code", "add_setup"
    description: str
    file: str
    line: int = 0
    old_code: str = ""
    new_code: str = ""
    confidence: float = 0.0  # 0-1


@dataclass
class TestFixResult:
    """Result of diagnosing test failures."""
    failures: list[TestFailure] = field(default_factory=list)
    suggestions: list[TestFixSuggestion] = field(default_factory=list)
    diagnosis: str = ""  # "test_wrong", "code_wrong", "both", "environment"
    summary: str = ""


class TestFixer:
    """Diagnose and fix failing tests."""

    def __init__(self, config: TestFixerConfig):
        self.config = config

    def diagnose(self, error_output: str) -> TestFixResult:
        """Diagnose test failures from pytest output."""
        logger.info("Diagnosing test failures (%d chars)", len(error_output))
        result = TestFixResult()

        # Parse failures
        result.failures = self._parse_failures(error_output)

        # For each failure, suggest fixes
        for failure in result.failures:
            suggestions = self._suggest_fixes(failure)
            result.suggestions.extend(suggestions)

        # Overall diagnosis
        result.diagnosis = self._diagnose_root_cause(result)
        result.summary = f"{len(result.failures)} failure(s), {len(result.suggestions)} suggestion(s): {result.diagnosis}"

        return result

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """Parse pytest failure output."""
        failures: list[TestFailure] = []
        lines = output.splitlines()

        # Pattern: FAILED tests/test_xxx.py::TestClass::test_name
        failed_pattern = re.compile(r"FAILED\s+([\w/.-]+)::(\w+)::(\w+)")
        # Simpler: FAILED tests/test_xxx.py::test_name
        failed_simple = re.compile(r"FAILED\s+([\w/.-]+)::(\w+)")

        for line in lines:
            match = failed_pattern.search(line) or failed_simple.search(line)
            if match:
                groups = match.groups()
                failure = TestFailure(test_file=groups[0])
                if len(groups) == 3:
                    failure.test_class = groups[1]
                    failure.test_name = groups[2]
                else:
                    failure.test_name = groups[1]
                failures.append(failure)

        # Extract error details
        for failure in failures:
            self._extract_error_details(failure, output)

        return failures

    def _extract_error_details(self, failure: TestFailure, output: str):
        """Extract error type, message, and assertion details."""
        # Look for assertion errors
        assert_match = re.search(
            rf"(?:E\s+)?AssertionError:\s*(.*?)(?:\n|$)", output
        )
        if assert_match:
            failure.error_type = "AssertionError"
            failure.error_message = assert_match.group(1)

        # Look for expected vs actual
        expected_match = re.search(r"E\s+assert\s+(.+?)\s*==\s*(.+)", output)
        if expected_match:
            failure.actual = expected_match.group(1).strip()
            failure.expected = expected_match.group(2).strip()

        # Other error types
        for error_type in ("TypeError", "AttributeError", "ImportError", "KeyError", "ValueError", "NameError"):
            err_match = re.search(rf"E\s+{error_type}:\s*(.*)", output)
            if err_match:
                failure.error_type = error_type
                failure.error_message = err_match.group(1)
                break

    def _suggest_fixes(self, failure: TestFailure) -> list[TestFixSuggestion]:
        """Suggest fixes based on the failure type."""
        suggestions: list[TestFixSuggestion] = []

        if failure.error_type == "AssertionError":
            if failure.expected and failure.actual:
                suggestions.append(TestFixSuggestion(
                    fix_type="update_assertion",
                    description=f"Update assertion: expected {failure.expected} but got {failure.actual}",
                    file=failure.test_file,
                    confidence=0.7,
                ))

        elif failure.error_type == "AttributeError":
            suggestions.append(TestFixSuggestion(
                fix_type="update_mock",
                description=f"Mock missing attribute: {failure.error_message}",
                file=failure.test_file,
                confidence=0.6,
            ))

        elif failure.error_type == "ImportError":
            suggestions.append(TestFixSuggestion(
                fix_type="fix_import",
                description=f"Fix import: {failure.error_message}",
                file=failure.test_file,
                confidence=0.8,
            ))

        elif failure.error_type == "TypeError":
            suggestions.append(TestFixSuggestion(
                fix_type="fix_code",
                description=f"Type mismatch: {failure.error_message}. Check function signature changes.",
                file=failure.test_file,
                confidence=0.5,
            ))

        elif failure.error_type == "KeyError":
            suggestions.append(TestFixSuggestion(
                fix_type="update_mock",
                description=f"Mock missing key: {failure.error_message}. Update mock data.",
                file=failure.test_file,
                confidence=0.7,
            ))

        return suggestions

    def _diagnose_root_cause(self, result: TestFixResult) -> str:
        """Determine if the test or the code is wrong."""
        if not result.failures:
            return "no_failures"

        # If most failures are assertion errors, likely the code changed
        assertion_count = sum(1 for f in result.failures if f.error_type == "AssertionError")
        import_count = sum(1 for f in result.failures if f.error_type == "ImportError")
        type_count = sum(1 for f in result.failures if f.error_type == "TypeError")

        if import_count > len(result.failures) // 2:
            return "code_refactored — imports changed"
        if assertion_count > len(result.failures) // 2:
            return "code_behavior_changed — assertions need updating"
        if type_count > len(result.failures) // 2:
            return "code_signature_changed — function signatures modified"

        return "mixed — review each failure individually"


def format_test_fix(result: TestFixResult) -> str:
    """Format test fix suggestions for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Test Fixer")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")

    if result.failures:
        lines.append(f"\n  Failures ({len(result.failures)}):")
        for f in result.failures:
            cls = f"{f.test_class}::" if f.test_class else ""
            lines.append(f"    X {f.test_file}::{cls}{f.test_name}")
            lines.append(f"      {f.error_type}: {f.error_message[:80]}")

    if result.suggestions:
        lines.append(f"\n  Suggestions ({len(result.suggestions)}):")
        for s in result.suggestions:
            conf = f" ({int(s.confidence*100)}% confidence)" if s.confidence else ""
            lines.append(f"    > [{s.fix_type}] {s.description}{conf}")

    lines.append("")
    return "\n".join(lines)
