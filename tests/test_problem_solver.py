"""Tests for problem_solver.py — intelligent problem-to-solution mapping."""

from __future__ import annotations

import pytest

from code_agents.knowledge.problem_solver import (
    ProblemAnalysis,
    ProblemSolver,
    Solution,
    PROBLEM_MAP,
    format_problem_analysis,
)


@pytest.fixture
def solver():
    return ProblemSolver()


# ---------------------------------------------------------------------------
# Solution dataclass
# ---------------------------------------------------------------------------

class TestSolution:
    def test_defaults(self):
        s = Solution(title="T", description="D", action_type="agent", action="code-writer")
        assert s.confidence == 0.0
        assert s.follow_up == []

    def test_with_follow_up(self):
        s = Solution(title="T", description="D", action_type="slash", action="/test",
                     confidence=0.9, follow_up=["step 2"])
        assert s.follow_up == ["step 2"]


# ---------------------------------------------------------------------------
# ProblemAnalysis dataclass
# ---------------------------------------------------------------------------

class TestProblemAnalysis:
    def test_defaults(self):
        a = ProblemAnalysis(original_query="test")
        assert a.intent == ""
        assert a.domain == ""
        assert a.urgency == "normal"
        assert a.solutions == []
        assert a.recommended is None


# ---------------------------------------------------------------------------
# Analyze — code queries
# ---------------------------------------------------------------------------

class TestAnalyzeCode:
    def test_code_query_suggests_code_writer(self, solver):
        analysis = solver.analyze("write a new payment service class")
        assert analysis.domain == "code"
        assert analysis.recommended is not None
        agent_actions = [s.action for s in analysis.solutions if s.action_type == "agent"]
        assert "code-writer" in agent_actions

    def test_refactor_query(self, solver):
        analysis = solver.analyze("refactor the user module to reduce complexity")
        assert analysis.domain == "code"
        assert any("refactor" in s.action.lower() for s in analysis.solutions)


# ---------------------------------------------------------------------------
# Analyze — test queries
# ---------------------------------------------------------------------------

class TestAnalyzeTest:
    def test_test_query_suggests_coverage_boost(self, solver):
        analysis = solver.analyze("improve test coverage for the payment module")
        assert analysis.domain == "test"
        slash_actions = [s.action for s in analysis.solutions if s.action_type == "slash"]
        assert any("coverage" in a.lower() for a in slash_actions)


# ---------------------------------------------------------------------------
# Analyze — deploy queries
# ---------------------------------------------------------------------------

class TestAnalyzeDeploy:
    def test_deploy_query_suggests_release(self, solver):
        analysis = solver.analyze("deploy the service to staging")
        assert analysis.domain == "deploy"
        assert analysis.recommended is not None
        assert len(analysis.solutions) > 0


# ---------------------------------------------------------------------------
# Analyze — incident/debug queries
# ---------------------------------------------------------------------------

class TestAnalyzeIncident:
    def test_incident_query_suggests_runbook(self, solver):
        analysis = solver.analyze("production incident — payment service is down")
        assert analysis.domain == "debug"
        actions = [s.action for s in analysis.solutions]
        assert any("incident" in a.lower() for a in actions)

    def test_error_query(self, solver):
        analysis = solver.analyze("NullPointerException in user service")
        assert analysis.domain == "debug"
        assert analysis.recommended is not None


# ---------------------------------------------------------------------------
# Analyze — git queries
# ---------------------------------------------------------------------------

class TestAnalyzeGit:
    def test_git_commit_query_suggests_smart_commit(self, solver):
        analysis = solver.analyze("commit my changes with a good message")
        assert analysis.domain == "git"
        actions = [s.action for s in analysis.solutions]
        assert any("commit" in a.lower() for a in actions)

    def test_branch_query(self, solver):
        analysis = solver.analyze("create a new branch and push it")
        assert analysis.domain == "git"


# ---------------------------------------------------------------------------
# Urgency detection
# ---------------------------------------------------------------------------

class TestUrgency:
    def test_p1_is_critical(self, solver):
        analysis = solver.analyze("P1 outage in production payment service")
        assert analysis.urgency == "critical"

    def test_outage_is_critical(self, solver):
        analysis = solver.analyze("the service is down, outage reported")
        assert analysis.urgency == "critical"

    def test_normal_query_is_normal(self, solver):
        analysis = solver.analyze("write a helper function for string formatting")
        assert analysis.urgency == "normal"

    def test_blocking_is_high(self, solver):
        analysis = solver.analyze("this bug is blocking the release")
        assert analysis.urgency == "high"


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_query(self, solver):
        analysis = solver.analyze("")
        assert analysis.solutions == []
        assert analysis.recommended is None

    def test_unrelated_query(self, solver):
        analysis = solver.analyze("the weather is nice today")
        # May or may not match — should not crash
        assert isinstance(analysis, ProblemAnalysis)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_solutions_sorted_by_confidence(self, solver):
        analysis = solver.analyze("deploy the service and run tests")
        if len(analysis.solutions) > 1:
            for i in range(len(analysis.solutions) - 1):
                assert analysis.solutions[i].confidence >= analysis.solutions[i + 1].confidence

    def test_recommended_is_highest_confidence(self, solver):
        analysis = solver.analyze("write unit tests for payment service")
        if analysis.recommended and len(analysis.solutions) > 1:
            assert analysis.recommended.confidence >= analysis.solutions[1].confidence


# ---------------------------------------------------------------------------
# format_problem_analysis
# ---------------------------------------------------------------------------

class TestFormatOutput:
    def test_format_with_solutions(self, solver):
        analysis = solver.analyze("deploy to production")
        output = format_problem_analysis(analysis)
        assert "PROBLEM SOLVER" in output
        assert "Intent:" in output
        assert "Domain:" in output

    def test_format_critical_shows_urgency(self, solver):
        analysis = solver.analyze("P1 production outage")
        output = format_problem_analysis(analysis)
        assert "CRITICAL" in output

    def test_format_empty_analysis(self):
        analysis = ProblemAnalysis(original_query="nothing")
        output = format_problem_analysis(analysis)
        assert "PROBLEM SOLVER" in output
