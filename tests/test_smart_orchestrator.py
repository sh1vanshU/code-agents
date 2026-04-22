"""Tests for SmartOrchestrator — lean auto-pilot brain."""

import pytest

from code_agents.agent_system.smart_orchestrator import (
    AGENT_CAPABILITIES,
    _FALLBACK_CAPABILITIES,
    SmartOrchestrator,
    _SKILL_KEYWORDS,
    _CROSS_AGENT_SKILLS,
    _ensure_capabilities,
)


@pytest.fixture
def orch():
    _ensure_capabilities()
    return SmartOrchestrator()


# ── AGENT_CAPABILITIES coverage ────────────────────────────────────────────

class TestAgentCapabilities:
    def test_at_least_11_agents(self):
        _ensure_capabilities()
        assert len(AGENT_CAPABILITIES) >= 11

    def test_fallback_has_core_agents(self):
        assert len(_FALLBACK_CAPABILITIES) >= 11

    def test_each_agent_has_keywords_and_description(self):
        _ensure_capabilities()
        for name, caps in AGENT_CAPABILITIES.items():
            assert "keywords" in caps, f"{name} missing keywords"
            assert "description" in caps, f"{name} missing description"
            assert len(caps["keywords"]) >= 2, f"{name} has too few keywords"
            assert len(caps["description"]) >= 10, f"{name} description too short"

    def test_known_agents_present(self):
        _ensure_capabilities()
        # After consolidation: pipeline-orchestrator, explore, agent-router merged
        expected = {
            "code-reasoning", "code-writer", "code-reviewer", "code-tester",
            "git-ops", "jenkins-cicd", "argocd-verify",
            "redash-query", "qa-regression", "test-coverage", "jira-ops",
            "auto-pilot",
        }
        assert expected.issubset(set(AGENT_CAPABILITIES.keys()))


# ── Dynamic loading from YAML ──────────────────────────────────────────────

class TestDynamicLoading:
    def test_capabilities_loaded_from_yaml(self):
        _ensure_capabilities()
        # Should have at least 11 agents (fallback + YAML routing)
        assert len(AGENT_CAPABILITIES) >= 11

    def test_yaml_keywords_override_fallback(self):
        _ensure_capabilities()
        # jenkins-cicd YAML has "argocd" and "verify deployment" keywords
        # that aren't in the fallback
        jk = AGENT_CAPABILITIES.get("jenkins-cicd", {})
        assert "build" in jk.get("keywords", [])


# ── analyze_request ────────────────────────────────────────────────────────

class TestAnalyzeRequest:
    def test_returns_all_expected_keys(self, orch):
        result = orch.analyze_request("explain how the auth flow works")
        assert set(result.keys()) == {
            "intent", "best_agent", "relevant_skills", "score",
            "should_delegate", "context_injection",
        }

    def test_git_request_routes_to_git_ops(self, orch):
        result = orch.analyze_request("show me the git diff between main and release")
        assert result["best_agent"] == "git-ops"
        assert result["should_delegate"] is True

    def test_code_review_routes_to_reviewer(self, orch):
        result = orch.analyze_request("review this pull request for security issues")
        assert result["best_agent"] == "code-reviewer"
        assert result["should_delegate"] is True

    def test_build_deploy_routes_to_jenkins(self, orch):
        result = orch.analyze_request("trigger a jenkins build and deploy to staging")
        assert result["best_agent"] == "jenkins-cicd"

    def test_test_request_routes_to_tester(self, orch):
        result = orch.analyze_request("write unit tests for the payment service")
        assert result["best_agent"] == "code-tester"

    def test_sql_routes_to_redash(self, orch):
        result = orch.analyze_request("write a SQL query to find active users")
        assert result["best_agent"] == "redash-query"

    def test_jira_routes_to_jira_ops(self, orch):
        result = orch.analyze_request("update the jira ticket status to done")
        assert result["best_agent"] == "jira-ops"

    def test_ambiguous_request_falls_back_to_auto_pilot(self, orch):
        result = orch.analyze_request("hello, how are you today?")
        assert result["best_agent"] == "auto-pilot"
        assert result["should_delegate"] is False

    def test_context_injection_is_nonempty_for_delegation(self, orch):
        result = orch.analyze_request("create a new branch for the feature")
        assert result["context_injection"]
        assert "[DELEGATE:" in result["context_injection"]

    def test_argocd_request_routes_correctly(self, orch):
        result = orch.analyze_request("check the argocd sync status and pod health")
        assert result["best_agent"] == "argocd-verify"

    def test_explain_request_routes_to_reasoning(self, orch):
        result = orch.analyze_request("explain the architecture of this service")
        assert result["best_agent"] == "code-reasoning"

    def test_write_code_routes_to_writer(self, orch):
        result = orch.analyze_request("implement a retry mechanism for failed API calls")
        assert result["best_agent"] == "code-writer"

    def test_coverage_request_routes_to_test_coverage(self, orch):
        result = orch.analyze_request("lets build the test coverage for this repo and reach to 80% code coverage gradually")
        assert result["best_agent"] == "test-coverage"
        assert result["should_delegate"] is True

    def test_coverage_report_routes_to_test_coverage(self, orch):
        result = orch.analyze_request("generate a coverage report and find uncovered lines")
        assert result["best_agent"] == "test-coverage"


# ── _find_relevant_skills ──────────────────────────────────────────────────

class TestFindRelevantSkills:
    def test_build_deploy_skill_found(self, orch):
        skills = orch._find_relevant_skills("build and deploy the service", "jenkins-cicd")
        assert any("build" in s or "deploy" in s for s in skills)

    def test_incident_skill_found(self, orch):
        skills = orch._find_relevant_skills("investigate this production incident", "auto-pilot")
        assert any("incident" in s or "investigate" in s for s in skills)

    def test_max_3_skills_returned(self, orch):
        # A message that matches many keywords
        msg = "build deploy release pipeline incident investigate debug review fix"
        skills = orch._find_relevant_skills(msg, "auto-pilot")
        assert len(skills) <= 3

    def test_cross_agent_skills_included(self, orch):
        skills = orch._find_relevant_skills("trigger a jenkins build", "jenkins-cicd")
        assert any("jenkins-cicd:" in s for s in skills)

    def test_no_skills_for_generic_message(self, orch):
        skills = orch._find_relevant_skills("hello world", "auto-pilot")
        assert skills == []


# ── _find_relevant_tools (removed — tools inferred from agent) ────────────


# ── get_lean_system_prompt (removed — prompt built dynamically) ───────────


# ── _build_minimal_context ─────────────────────────────────────────────────

class TestBuildMinimalContext:
    def test_context_includes_agent(self, orch):
        ctx = orch._build_minimal_context("git-ops", ["safe-checkout"])
        assert "git-ops" in ctx
        assert "[DELEGATE:git-ops]" in ctx

    def test_context_includes_skills(self, orch):
        ctx = orch._build_minimal_context("jenkins-cicd", ["build-deploy", "cicd-pipeline"])
        assert "[SKILL:build-deploy]" in ctx
        assert "[SKILL:cicd-pipeline]" in ctx

    def test_auto_pilot_context_no_delegate(self, orch):
        ctx = orch._build_minimal_context("auto-pilot", [])
        assert "[DELEGATE:" not in ctx

    def test_context_is_compact(self, orch):
        ctx = orch._build_minimal_context(
            "git-ops", ["safe-checkout", "branching"]
        )
        # Should be under ~200 tokens (~800 chars)
        assert len(ctx) < 1000, f"Context too long: {len(ctx)} chars"


# ── _infer_intent ──────────────────────────────────────────────────────────

class TestInferIntent:
    def test_auto_pilot_intent(self, orch):
        assert orch._infer_intent("random stuff", "auto-pilot") == "general request"

    def test_agent_intent_uses_description(self, orch):
        intent = orch._infer_intent("git branch list", "git-ops")
        assert "git" in intent.lower() or "Git" in intent


# ── get_delegation_hints (centralized delegation) ────────────────────────

class TestGetDelegationHints:
    def test_returns_hints_for_known_agent(self):
        hints = SmartOrchestrator.get_delegation_hints("code-writer")
        assert "[DELEGATE:" in hints
        assert "code-tester" in hints

    def test_returns_empty_for_unknown_agent(self):
        hints = SmartOrchestrator.get_delegation_hints("nonexistent-agent")
        assert hints == ""

    def test_all_mapped_agents_have_hints(self):
        from code_agents.agent_system.smart_orchestrator import AGENT_DELEGATION_MAP
        for agent_name in AGENT_DELEGATION_MAP:
            hints = SmartOrchestrator.get_delegation_hints(agent_name)
            assert hints, f"No hints for {agent_name}"
            assert "[DELEGATE:" in hints

    def test_hints_are_compact(self):
        """Delegation hints should be under ~100 tokens (~400 chars)."""
        from code_agents.agent_system.smart_orchestrator import AGENT_DELEGATION_MAP
        for agent_name in AGENT_DELEGATION_MAP:
            hints = SmartOrchestrator.get_delegation_hints(agent_name)
            assert len(hints) < 600, f"Hints too long for {agent_name}: {len(hints)} chars"

    def test_no_self_delegation(self):
        """Agent should not delegate to itself."""
        from code_agents.agent_system.smart_orchestrator import AGENT_DELEGATION_MAP
        for agent_name, targets in AGENT_DELEGATION_MAP.items():
            target_names = [t[0] for t in targets]
            assert agent_name not in target_names, f"{agent_name} delegates to itself"

    def test_code_writer_delegates_to_tester_after_writing(self):
        hints = SmartOrchestrator.get_delegation_hints("code-writer")
        assert "code-tester" in hints
        assert "test" in hints.lower()

    def test_test_coverage_delegates_to_code_tester(self):
        hints = SmartOrchestrator.get_delegation_hints("test-coverage")
        assert "code-tester" in hints