"""Tests for mutation_tester.py — mutation testing to verify test quality."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from code_agents.testing.mutation_tester import (
    Mutation,
    MutationReport,
    MutationTester,
    MUTATIONS,
    format_mutation_report,
)


# ---------------------------------------------------------------------------
# Mutation dataclass
# ---------------------------------------------------------------------------

class TestMutationDataclass:
    def test_defaults(self):
        m = Mutation(file="a.py", line=1, original="x == y", mutated="x != y", mutation_type="operator")
        assert m.killed is False

    def test_with_killed(self):
        m = Mutation(file="a.py", line=1, original="x", mutated="y", mutation_type="operator", killed=True)
        assert m.killed is True


# ---------------------------------------------------------------------------
# MutationReport dataclass
# ---------------------------------------------------------------------------

class TestMutationReport:
    def test_defaults(self):
        r = MutationReport(source_file="test.py")
        assert r.total == 0
        assert r.score == 0.0

    def test_with_data(self):
        r = MutationReport(source_file="a.py", total=10, killed=8, survived=2, score=80.0)
        assert r.score == 80.0
        assert r.killed == 8


# ---------------------------------------------------------------------------
# MUTATIONS dict — verify all regexes are valid
# ---------------------------------------------------------------------------

class TestMutationsDict:
    def test_all_categories_present(self):
        assert "operator" in MUTATIONS
        assert "boundary" in MUTATIONS
        assert "return_value" in MUTATIONS
        assert "null_check" in MUTATIONS

    def test_all_patterns_are_valid_regex(self):
        for category, patterns in MUTATIONS.items():
            for pattern, replacement in patterns:
                try:
                    re.compile(pattern)
                except re.error as e:
                    pytest.fail(f"Invalid regex in {category}: {pattern!r} — {e}")

    def test_each_category_has_patterns(self):
        for category, patterns in MUTATIONS.items():
            assert len(patterns) > 0, f"Category {category} has no patterns"


# ---------------------------------------------------------------------------
# MutationTester.generate_mutations
# ---------------------------------------------------------------------------

class TestGenerateMutations:
    def test_generates_operator_mutations(self, tmp_path):
        src = tmp_path / "calc.py"
        src.write_text("def check(a, b):\n    return a == b\n")
        tester = MutationTester(repo_path=str(tmp_path))
        mutations = tester.generate_mutations(str(src))
        assert len(mutations) > 0
        types = {m.mutation_type for m in mutations}
        assert "operator" in types

    def test_generates_return_value_mutations(self, tmp_path):
        src = tmp_path / "util.py"
        src.write_text("def flag():\n    return True\n")
        tester = MutationTester(repo_path=str(tmp_path))
        mutations = tester.generate_mutations(str(src))
        assert any(m.mutation_type == "return_value" for m in mutations)
        assert any("False" in m.mutated for m in mutations)

    def test_generates_null_check_mutations(self, tmp_path):
        src = tmp_path / "guard.py"
        src.write_text("def safe(x):\n    if x is None:\n        return 0\n    return x\n")
        tester = MutationTester(repo_path=str(tmp_path))
        mutations = tester.generate_mutations(str(src))
        assert any(m.mutation_type == "null_check" for m in mutations)

    def test_skips_comments(self, tmp_path):
        src = tmp_path / "commented.py"
        src.write_text("# return True\ndef f():\n    return 1\n")
        tester = MutationTester(repo_path=str(tmp_path))
        mutations = tester.generate_mutations(str(src))
        # Should not mutate the comment line
        for m in mutations:
            assert m.line != 1

    def test_missing_file_returns_empty(self, tmp_path):
        tester = MutationTester(repo_path=str(tmp_path))
        mutations = tester.generate_mutations("/nonexistent/file.py")
        assert mutations == []


# ---------------------------------------------------------------------------
# format_mutation_report
# ---------------------------------------------------------------------------

class TestFormatMutationReport:
    def test_high_score_shows_good(self):
        report = MutationReport(source_file="a.py", total=10, killed=9, survived=1, score=90.0)
        output = format_mutation_report(report)
        assert "MUTATION TESTING" in output
        assert "GOOD" in output

    def test_low_score_shows_low(self):
        report = MutationReport(
            source_file="a.py", total=10, killed=2, survived=8, score=20.0,
            mutations=[
                Mutation(file="a.py", line=5, original="x == y", mutated="x != y",
                         mutation_type="operator", killed=False),
            ],
        )
        output = format_mutation_report(report)
        assert "LOW" in output
        assert "Survived" in output

    def test_moderate_score(self):
        report = MutationReport(source_file="a.py", total=10, killed=6, survived=4, score=60.0)
        output = format_mutation_report(report)
        assert "MODERATE" in output
