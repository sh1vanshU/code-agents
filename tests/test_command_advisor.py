"""Tests for the command advisor — smart /commands with agent routing."""

from __future__ import annotations

import pytest

from code_agents.ui.command_advisor import (
    INTENT_MAP,
    CommandAdvisor,
    CommandSuggestion,
    format_all_commands,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def advisor():
    return CommandAdvisor()


# ---------------------------------------------------------------------------
# TestSuggest — exact keyword matches
# ---------------------------------------------------------------------------

class TestSuggest:
    """Exact keyword queries return the correct agent."""

    def test_build_returns_jenkins(self, advisor):
        results = advisor.suggest("build")
        assert len(results) >= 1
        top = results[0]
        assert top.agent == "jenkins-cicd"
        assert top.intent == "build"
        assert top.score == 1.0

    def test_security_returns_security_agent(self, advisor):
        results = advisor.suggest("security")
        assert len(results) >= 1
        top = results[0]
        assert top.agent == "security"
        assert top.intent == "security"

    def test_deploy_returns_jenkins(self, advisor):
        results = advisor.suggest("deploy")
        top = results[0]
        assert top.agent == "jenkins-cicd"

    def test_terraform_returns_terraform_ops(self, advisor):
        results = advisor.suggest("terraform")
        top = results[0]
        assert top.agent == "terraform-ops"

    def test_git_returns_git_ops(self, advisor):
        results = advisor.suggest("git")
        top = results[0]
        assert top.agent == "git-ops"

    def test_database_returns_db_ops(self, advisor):
        results = advisor.suggest("database")
        top = results[0]
        assert top.agent == "db-ops"

    def test_empty_query_returns_empty(self, advisor):
        assert advisor.suggest("") == []
        assert advisor.suggest("   ") == []

    def test_no_match_returns_empty(self, advisor):
        results = advisor.suggest("xyznonexistent")
        assert results == []

    def test_suggestion_has_commands(self, advisor):
        results = advisor.suggest("build")
        top = results[0]
        assert len(top.commands) > 0
        assert isinstance(top.commands, list)

    def test_suggestion_has_description(self, advisor):
        results = advisor.suggest("review")
        top = results[0]
        assert top.description
        assert isinstance(top.description, str)


# ---------------------------------------------------------------------------
# TestFuzzyMatch — partial / prefix matches
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    """Partial queries still find the right intent."""

    def test_sec_matches_security(self, advisor):
        results = advisor.suggest("sec")
        intents = [r.intent for r in results]
        assert "security" in intents

    def test_dep_matches_deploy(self, advisor):
        results = advisor.suggest("dep")
        intents = [r.intent for r in results]
        assert "deploy" in intents

    def test_build_prefix_bui(self, advisor):
        results = advisor.suggest("bui")
        intents = [r.intent for r in results]
        assert "build" in intents

    def test_ter_matches_terraform(self, advisor):
        results = advisor.suggest("ter")
        intents = [r.intent for r in results]
        assert "terraform" in intents

    def test_log_matches_logs(self, advisor):
        results = advisor.suggest("log")
        intents = [r.intent for r in results]
        assert "logs" in intents

    def test_prefix_match_scores_higher_than_substring(self, advisor):
        results = advisor.suggest("dep")
        # "deploy" starts with "dep" -> 0.8 prefix score
        deploy = next(r for r in results if r.intent == "deploy")
        assert deploy.score == 0.8

    def test_description_match(self, advisor):
        # "Jenkins" appears in description of "build"
        results = advisor.suggest("jenkins")
        assert len(results) >= 1
        # Should find via description or agent name
        agents = [r.agent for r in results]
        assert "jenkins-cicd" in agents

    def test_agent_name_match(self, advisor):
        results = advisor.suggest("grafana")
        assert len(results) >= 1
        top = results[0]
        assert top.agent == "grafana-ops"

    def test_case_insensitive(self, advisor):
        results_lower = advisor.suggest("build")
        results_upper = advisor.suggest("BUILD")
        assert len(results_lower) == len(results_upper)
        assert results_lower[0].intent == results_upper[0].intent


# ---------------------------------------------------------------------------
# TestListAll — grouped listing
# ---------------------------------------------------------------------------

class TestListAll:
    """list_all() returns all intents grouped by category."""

    def test_returns_dict(self, advisor):
        grouped = advisor.list_all()
        assert isinstance(grouped, dict)

    def test_all_intents_present(self, advisor):
        grouped = advisor.list_all()
        all_intents = []
        for items in grouped.values():
            all_intents.extend(item["intent"] for item in items)
        assert len(all_intents) == len(INTENT_MAP)

    def test_categories_not_empty(self, advisor):
        grouped = advisor.list_all()
        for category, items in grouped.items():
            assert len(items) > 0, f"Category '{category}' is empty"

    def test_expected_categories(self, advisor):
        grouped = advisor.list_all()
        expected = {"CI/CD", "Code Quality", "Analysis", "Database", "Payment",
                    "Monitoring", "Documentation", "Git/PR", "Infrastructure"}
        assert expected == set(grouped.keys())

    def test_each_item_has_required_keys(self, advisor):
        grouped = advisor.list_all()
        for items in grouped.values():
            for item in items:
                assert "intent" in item
                assert "agent" in item
                assert "commands" in item
                assert "description" in item


# ---------------------------------------------------------------------------
# TestFormat — output formatting
# ---------------------------------------------------------------------------

class TestFormat:
    """Verify formatted output contains agent names and ANSI codes."""

    def test_format_suggestions_with_results(self, advisor):
        suggestions = advisor.suggest("build")
        output = advisor.format_suggestions(suggestions)
        assert "jenkins-cicd" in output
        assert "build" in output

    def test_format_suggestions_empty(self, advisor):
        output = advisor.format_suggestions([])
        assert "No matching commands found" in output

    def test_format_suggestions_contains_ansi(self, advisor):
        suggestions = advisor.suggest("deploy")
        output = advisor.format_suggestions(suggestions)
        assert "\033[" in output  # ANSI escape codes present

    def test_format_suggestions_shows_commands(self, advisor):
        suggestions = advisor.suggest("security")
        output = advisor.format_suggestions(suggestions)
        assert "/pci-scan" in output or "/owasp-scan" in output

    def test_format_all_commands(self):
        output = format_all_commands()
        assert "Smart Command Reference" in output
        assert "CI/CD" in output
        assert "Code Quality" in output
        assert "jenkins-cicd" in output

    def test_format_all_contains_all_categories(self):
        output = format_all_commands()
        for category in ["CI/CD", "Analysis", "Database", "Payment",
                         "Monitoring", "Documentation", "Git/PR", "Infrastructure"]:
            assert category in output, f"Missing category: {category}"


# ---------------------------------------------------------------------------
# TestCommandSuggestion dataclass
# ---------------------------------------------------------------------------

class TestCommandSuggestion:
    """CommandSuggestion dataclass basics."""

    def test_creation(self):
        s = CommandSuggestion(
            intent="build",
            agent="jenkins-cicd",
            commands=["/jenkins-cicd build"],
            description="Build project",
            score=1.0,
        )
        assert s.intent == "build"
        assert s.agent == "jenkins-cicd"
        assert s.score == 1.0

    def test_sorting(self):
        a = CommandSuggestion("a", "x", [], "", 0.5)
        b = CommandSuggestion("b", "y", [], "", 1.0)
        c = CommandSuggestion("c", "z", [], "", 0.3)
        results = sorted([a, b, c], key=lambda s: s.score, reverse=True)
        assert results[0].intent == "b"
        assert results[-1].intent == "c"
