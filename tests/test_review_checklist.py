"""Tests for review_checklist.py — per-repo configurable review checklist with pattern-based scoring."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.reviews.review_checklist import (
    ChecklistItem,
    ChecklistResult,
    ReviewChecklist,
    DEFAULT_CHECKLIST,
    format_checklist,
)


# ---------------------------------------------------------------------------
# ChecklistItem dataclass
# ---------------------------------------------------------------------------

class TestChecklistItem:
    def test_defaults(self):
        item = ChecklistItem(name="test", description="desc", category="quality")
        assert item.passed is True
        assert item.weight == 1.0
        assert item.pattern == ""

    def test_custom_weight(self):
        item = ChecklistItem(name="sec", description="d", category="security", weight=3.0)
        assert item.weight == 3.0

    def test_with_pattern(self):
        item = ChecklistItem(name="x", description="d", category="c", pattern=r"eval\(")
        assert item.pattern == r"eval\("


# ---------------------------------------------------------------------------
# ChecklistResult dataclass
# ---------------------------------------------------------------------------

class TestChecklistResult:
    def test_defaults(self):
        r = ChecklistResult()
        assert r.score == 100.0
        assert r.passed_count == 0
        assert r.failed_count == 0

    def test_total(self):
        r = ChecklistResult(passed_count=3, failed_count=2)
        assert r.total == 5


# ---------------------------------------------------------------------------
# ReviewChecklist.evaluate — default rules
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_clean_diff_passes_all(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        result = cl.evaluate("+ added a clean line", changed_files=["test_foo.py"])
        assert result.score == 100.0
        assert result.failed_count == 0

    def test_hardcoded_secret_fails(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        diff = '+ api_key = "sk-1234567890abcdef"'
        result = cl.evaluate(diff)
        failed = [i for i in result.items if not i.passed and i.name == "no_hardcoded_secrets"]
        assert len(failed) == 1

    def test_eval_detected(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        diff = "+ result = eval(user_input)"
        result = cl.evaluate(diff)
        failed_names = [i.name for i in result.items if not i.passed]
        assert "no_eval" in failed_names

    def test_sql_injection_detected(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        diff = '+ cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        result = cl.evaluate(diff)
        failed_names = [i.name for i in result.items if not i.passed]
        assert "no_sql_injection" in failed_names

    def test_print_debug_detected(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        diff = "+ print(response.json())"
        result = cl.evaluate(diff)
        failed_names = [i.name for i in result.items if not i.passed]
        assert "no_print_debug" in failed_names

    def test_tests_included_passes_with_test_file(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        result = cl.evaluate("+ clean line", changed_files=["src/app.py", "tests/test_app.py"])
        test_item = [i for i in result.items if i.name == "tests_included"]
        assert len(test_item) == 1
        assert test_item[0].passed is True

    def test_tests_not_included_fails(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        result = cl.evaluate("+ clean line", changed_files=["src/app.py"])
        test_item = [i for i in result.items if i.name == "tests_included"]
        assert len(test_item) == 1
        assert test_item[0].passed is False

    def test_score_decreases_with_failures(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        clean = cl.evaluate("+ clean", changed_files=["test_x.py"])
        dirty = cl.evaluate('+ api_key = "secretkey12345678"', changed_files=[])
        assert dirty.score < clean.score

    def test_weighted_scoring(self):
        """Security items have higher weight, so score drops more."""
        cl = ReviewChecklist(repo_path="/nonexistent")
        result = cl.evaluate('+ password = "hunter2longpassword"', changed_files=["test_x.py"])
        # Security failure should reduce score significantly due to weight=3.0
        assert result.score < 80


# ---------------------------------------------------------------------------
# Custom checklist loading
# ---------------------------------------------------------------------------

class TestCustomChecklist:
    def test_custom_yaml_loaded(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        yaml_file = config_dir / "review-checklist.yaml"
        yaml_file.write_text(
            "checklist:\n"
            "  - name: no_todo\n"
            "    description: No TODO comments\n"
            "    category: quality\n"
            "    weight: 1.0\n"
            "    pattern: 'TODO'\n"
        )
        cl = ReviewChecklist(repo_path=str(tmp_path))
        # Should only have the custom item
        assert len(cl._items) == 1
        result = cl.evaluate("+ # TODO fix later")
        assert result.failed_count == 1

    def test_missing_yaml_uses_defaults(self):
        cl = ReviewChecklist(repo_path="/nonexistent")
        assert len(cl._items) == len(DEFAULT_CHECKLIST)


# ---------------------------------------------------------------------------
# format_checklist
# ---------------------------------------------------------------------------

class TestFormatChecklist:
    def test_format_contains_score(self):
        result = ChecklistResult(
            items=[ChecklistItem(name="test", description="desc", category="quality", passed=True)],
            score=100.0,
            passed_count=1,
            failed_count=0,
        )
        output = format_checklist(result)
        assert "100/100" in output
        assert "REVIEW CHECKLIST" in output

    def test_format_shows_fail(self):
        result = ChecklistResult(
            items=[ChecklistItem(name="bad", description="found issue", category="security", passed=False)],
            score=0.0,
            passed_count=0,
            failed_count=1,
        )
        output = format_checklist(result)
        assert "FAIL" in output
        assert "SECURITY" in output
