"""Tests for chat_complexity.py — auto plan-mode detection for complex tasks."""

from __future__ import annotations

import pytest


class TestEstimateComplexity:
    """Test complexity scoring of user messages."""

    def test_simple_message_low_score(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("fix the typo in README.md")
        assert score < 4

    def test_refactor_detected(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("refactor the entire backend module")
        assert score >= 3
        assert any("refactor" in r.lower() for r in reasons)

    def test_migration_detected(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("migrate all endpoints from REST to gRPC")
        assert score >= 4

    def test_rewrite_from_scratch(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("rewrite the auth module from scratch")
        assert score >= 6

    def test_multiple_files_detected(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("update all files in the routers directory")
        assert score >= 2

    def test_multi_step_keywords(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity(
            "first update the config, then refactor the backend, and finally update the tests"
        )
        assert score >= 4  # refactor(3) + sequence words(1+)

    def test_long_message_bonus(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        short = "fix the bug"
        long_msg = "fix the bug " + "with details " * 30  # >300 chars
        score_short, _ = estimate_complexity(short)
        score_long, _ = estimate_complexity(long_msg)
        assert score_long > score_short

    def test_empty_message(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("")
        assert score == 0
        assert reasons == []

    def test_implement_all_detected(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("implement all the features listed in ROADMAP")
        assert score >= 3

    def test_across_all_modules(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("add logging across all modules")
        assert score >= 2

    def test_complete_rewrite_high_score(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("do a complete rewrite of the CLI")
        assert score >= 7


class TestShouldSuggestPlanMode:
    """Test the plan mode suggestion decision."""

    def test_simple_task_no_suggestion(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode("add a print statement")
        assert suggest is False

    def test_complex_task_suggests_plan(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode(
            "refactor all the routers to use a new middleware pattern across every endpoint"
        )
        assert suggest is True
        assert score >= 4

    def test_medium_complexity_edge(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        # Just "upgrade" alone = 2, should not trigger
        suggest, _, _ = should_suggest_plan_mode("upgrade the dependency")
        assert suggest is False

    def test_returns_reasons(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode(
            "rewrite the entire pipeline from scratch"
        )
        assert len(reasons) >= 2

    def test_threshold_is_4(self):
        from code_agents.chat.chat_complexity import COMPLEXITY_THRESHOLD
        assert COMPLEXITY_THRESHOLD == 4


class TestPlanReport:
    """Test plan report .md file creation in plan mode."""

    def test_init_plan_report_creates_file(self, tmp_path):
        from unittest.mock import patch
        from code_agents.chat.chat import _init_plan_report
        state = {"agent": "code-writer", "repo_path": "/tmp/myrepo"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "refactor all modules")
        assert "_plan_report" in state
        import os
        assert os.path.exists(state["_plan_report"])
        with open(state["_plan_report"]) as f:
            content = f.read()
        assert "Plan Report" in content
        assert "code-writer" in content
        assert "refactor all modules" in content

    def test_init_plan_report_no_double_init(self, tmp_path):
        from unittest.mock import patch
        from code_agents.chat.chat import _init_plan_report
        state = {"agent": "test", "repo_path": "/tmp", "_plan_report": "/fake/existing.md"}
        _init_plan_report(state, "something")
        # Should not overwrite existing
        assert state["_plan_report"] == "/fake/existing.md"

    def test_append_plan_report(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report
        report = tmp_path / "test-plan.md"
        report.write_text("# Plan\n\n")
        state = {"_plan_report": str(report)}
        _append_plan_report(state, "Execution", "Step 1 done\nStep 2 done")
        content = report.read_text()
        assert "## Execution" in content
        assert "Step 1 done" in content

    def test_append_plan_report_no_path(self):
        from code_agents.chat.chat import _append_plan_report
        # Should not raise
        _append_plan_report({}, "Test", "content")


class TestComplexityPatterns:
    """Test specific pattern matches."""

    def test_step_numbers_detected(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("step 1: create the model, step 2: add tests")
        assert any("step" in r.lower() for r in reasons)

    def test_end_to_end(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("build an end-to-end test suite")
        assert score >= 2

    def test_replace_with(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("replace SQLAlchemy with raw SQL across the codebase")
        assert score >= 4

    def test_20_files_mention(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score, reasons = estimate_complexity("this affects about 20 files")
        assert any("20 files" in r for r in reasons)

    def test_case_insensitive(self):
        from code_agents.chat.chat_complexity import estimate_complexity
        score1, _ = estimate_complexity("REFACTOR the module")
        score2, _ = estimate_complexity("refactor the module")
        assert score1 == score2

    def test_build_and_deploy(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode("build and deploy pg-acquiring-biz to dev2")
        assert suggest is True
        assert score >= 4

    def test_build_deploy_verify(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode(
            "build and deploy pg-acquiring-biz to dev2 and verify argocd"
        )
        assert suggest is True
        assert score >= 5

    def test_deploy_and_verify(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, score, reasons = should_suggest_plan_mode("deploy to qa4 and verify")
        assert suggest is True

    def test_just_build_no_suggestion(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, _, _ = should_suggest_plan_mode("build pg-acquiring-biz")
        assert suggest is False

    def test_just_deploy_no_suggestion(self):
        from code_agents.chat.chat_complexity import should_suggest_plan_mode
        suggest, _, _ = should_suggest_plan_mode("deploy 925-grv to dev2")
        assert suggest is False
