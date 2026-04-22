"""Tests for the test gap finder module."""

from __future__ import annotations

import os
import pytest

from code_agents.testing.test_gap_finder import (
    TestGapFinder, GapInfoResult, GapInfo, find_test_gaps,
)


class TestTestGapFinder:
    """Test TestGapFinder methods."""

    def test_init(self, tmp_path):
        finder = TestGapFinder(cwd=str(tmp_path))
        assert finder.cwd == str(tmp_path)

    def test_find_gaps_empty_project(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        finder = TestGapFinder(cwd=str(tmp_path))
        result = finder.find_gaps(
            source_dirs=[str(tmp_path / "src")],
            test_dirs=[str(tmp_path / "tests")],
        )
        assert isinstance(result, GapInfoResult)
        assert result.source_files == 0

    def test_find_gaps_missing_test(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()

        (src / "calculator.py").write_text(
            "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
        )
        # No test file for calculator

        finder = TestGapFinder(cwd=str(tmp_path))
        result = finder.find_gaps(
            source_dirs=[str(src)], test_dirs=[str(tests)],
        )
        assert result.files_without_tests >= 1
        gaps = [g for g in result.gaps if g.gap_type == "no_test_file"]
        assert len(gaps) >= 1
        assert "add" in gaps[0].missing_functions

    def test_find_gaps_partial_coverage(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()

        (src / "math_ops.py").write_text(
            "def multiply(a, b):\n    return a * b\n\n"
            "def divide(a, b):\n    return a / b\n"
        )
        (tests / "test_math_ops.py").write_text(
            "from src.math_ops import multiply\n\n"
            "def test_multiply():\n    assert multiply(2, 3) == 6\n"
        )

        finder = TestGapFinder(cwd=str(tmp_path))
        result = finder.find_gaps(
            source_dirs=[str(src)], test_dirs=[str(tests)],
        )
        partial = [g for g in result.gaps if g.gap_type == "partial_coverage"]
        assert len(partial) >= 1
        assert "divide" in partial[0].missing_functions

    def test_coverage_ratio(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()

        (src / "a.py").write_text("def func_a():\n    pass\n")
        (src / "b.py").write_text("def func_b():\n    pass\n")
        (tests / "test_a.py").write_text("from src.a import func_a\ndef test_a():\n    pass\n")

        finder = TestGapFinder(cwd=str(tmp_path))
        result = finder.find_gaps(
            source_dirs=[str(src)], test_dirs=[str(tests)],
        )
        assert 0 < result.coverage_ratio <= 1.0

    def test_convenience_function(self, tmp_path):
        (tmp_path / "tests").mkdir()
        result = find_test_gaps(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "coverage_ratio" in result
        assert "gaps" in result
