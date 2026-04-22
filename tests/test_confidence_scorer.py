"""Tests for confidence_scorer.py — agent confidence scoring and delegation suggestions."""

from __future__ import annotations

import pytest

from code_agents.core.confidence_scorer import (
    AGENT_DOMAINS,
    ConfidenceResult,
    ConfidenceScorer,
    get_scorer,
    _LOW_CONFIDENCE_PHRASES,
)


@pytest.fixture
def scorer():
    return ConfidenceScorer()


class TestConfidenceResult:
    """ConfidenceResult dataclass basics."""

    def test_defaults(self):
        r = ConfidenceResult(score=3, reasoning="ok", should_delegate=False)
        assert r.suggested_agent == ""

    def test_with_suggested_agent(self):
        r = ConfidenceResult(score=1, reasoning="bad", should_delegate=True, suggested_agent="code-tester")
        assert r.suggested_agent == "code-tester"
        assert r.should_delegate is True

    def test_score_range(self):
        r = ConfidenceResult(score=5, reasoning="great", should_delegate=False)
        assert 1 <= r.score <= 5


class TestScoreResponse:
    """Core scoring logic."""

    def test_empty_response_scores_1(self, scorer):
        result = scorer.score_response("code-writer", "write a function", "")
        assert result.score == 1

    def test_whitespace_response_scores_1(self, scorer):
        result = scorer.score_response("code-writer", "write a function", "   \n  ")
        assert result.score == 1

    def test_confident_response_with_code(self, scorer):
        response = """Here's the implementation:

```python
def add(a, b):
    return a + b
```

This function takes two arguments and returns their sum. You can find it at /src/utils.py.
It handles both integers and floats correctly."""
        result = scorer.score_response("code-writer", "write an add function", response)
        assert result.score >= 3

    def test_uncertain_response_low_score(self, scorer):
        response = "I'm not sure about this. I think it might be related to the database, but I don't have access to check. You might want to try asking someone else."
        result = scorer.score_response("code-writer", "why is the query slow?", response)
        assert result.score <= 2

    def test_short_response_penalty(self, scorer):
        result = scorer.score_response("code-reasoning", "explain the full architecture of this system", "It's a web app.")
        # Short response to a detailed question should be penalized
        assert result.score <= 3

    def test_long_detailed_response_bonus(self, scorer):
        response = "x " * 300  # 600 chars, long response
        result = scorer.score_response("code-reasoning", "hi", response)
        assert result.score >= 3

    def test_score_clamped_to_1(self, scorer):
        """Even with many negative signals, score stays >= 1."""
        response = "I'm not sure. I think possibly. I cannot. I don't know. I don't have access."
        result = scorer.score_response("code-reasoning", "how do I deploy this to kubernetes with argocd?", response)
        assert result.score >= 1

    def test_score_clamped_to_5(self, scorer):
        """Even with many positive signals, score stays <= 5."""
        response = """Here's exactly what you need:

```python
def solve():
    pass
```

Check /src/solver.py for the implementation. Run it with:

$ python solve.py

""" + "Detail " * 200
        result = scorer.score_response("code-writer", "write a function", response)
        assert result.score <= 5


class TestDomainMismatch:
    """Domain mismatch detection and delegation suggestions."""

    def test_deploy_question_to_code_writer(self, scorer):
        result = scorer.score_response(
            "code-writer",
            "how do I deploy this with argocd and check pod status?",
            "I'm not sure about ArgoCD deployment. I think you need to sync.",
        )
        assert result.should_delegate is True
        assert result.suggested_agent == "argocd-verify"

    def test_test_question_to_code_writer(self, scorer):
        result = scorer.score_response(
            "code-writer",
            "write a unit test with pytest and mock the database",
            "I think you need some tests.",
        )
        assert result.should_delegate is True
        assert result.suggested_agent == "code-tester"

    def test_git_question_to_code_reasoning(self, scorer):
        result = scorer.score_response(
            "code-reasoning",
            "how do I merge this branch and push to remote?",
            "I think you should merge it.",
        )
        assert result.should_delegate is True
        assert result.suggested_agent == "git-ops"

    def test_sql_question_to_code_writer(self, scorer):
        result = scorer.score_response(
            "code-writer",
            "write a SQL query to join the users and orders table",
            "I'm not sure about the schema.",
        )
        assert result.should_delegate is True
        assert result.suggested_agent == "redash-query"

    def test_no_delegation_when_agent_matches_domain(self, scorer):
        result = scorer.score_response(
            "code-tester",
            "write a pytest unit test for the login function",
            "I'm not sure how to test this.",
        )
        # Even with low confidence, should not delegate to itself
        assert result.suggested_agent != "code-tester"

    def test_no_delegation_on_high_confidence(self, scorer):
        response = """Here's the deployment config:

```yaml
apiVersion: apps/v1
kind: Deployment
```

Check /deploy/app.yaml for the full config. Run with:

$ kubectl apply -f deploy/app.yaml

This sets up the ArgoCD sync and pod health checks correctly."""
        result = scorer.score_response(
            "code-writer",
            "how do I deploy with argocd?",
            response,
        )
        # High confidence = no delegation even with domain mismatch
        assert result.should_delegate is False

    def test_jira_question_delegates(self, scorer):
        result = scorer.score_response(
            "code-reasoning",
            "create a jira ticket for the login bug",
            "I don't have access to Jira.",
        )
        assert result.should_delegate is True
        assert result.suggested_agent == "jira-ops"


class TestBestAgentForQuery:
    """_best_agent_for_query helper."""

    def test_returns_empty_for_generic_query(self, scorer):
        result = scorer._best_agent_for_query("hello world", "code-reasoning")
        assert result == ""

    def test_returns_best_match(self, scorer):
        result = scorer._best_agent_for_query(
            "write a pytest unit test with mock fixtures", "code-writer"
        )
        assert result == "code-tester"

    def test_returns_empty_when_current_is_best(self, scorer):
        result = scorer._best_agent_for_query(
            "explain the architecture", "code-reasoning"
        )
        assert result == ""

    def test_git_keywords(self, scorer):
        result = scorer._best_agent_for_query(
            "merge the feature branch and push", "code-writer"
        )
        assert result == "git-ops"


class TestGetScorer:
    """Singleton accessor."""

    def test_returns_scorer(self):
        s = get_scorer()
        assert isinstance(s, ConfidenceScorer)

    def test_returns_same_instance(self):
        s1 = get_scorer()
        s2 = get_scorer()
        assert s1 is s2


class TestAgentDomains:
    """AGENT_DOMAINS data integrity."""

    def test_all_agents_have_domains(self):
        expected = [
            "code-writer", "code-reviewer", "code-tester", "code-reasoning",
            "git-ops", "jenkins-cicd", "argocd-verify", "redash-query",
            "jira-ops", "test-coverage", "qa-regression",
            "pipeline-orchestrator", "auto-pilot",
        ]
        for agent in expected:
            assert agent in AGENT_DOMAINS, f"Missing domain for {agent}"
            assert len(AGENT_DOMAINS[agent]) >= 2, f"Too few keywords for {agent}"

    def test_keywords_are_lowercase(self):
        for agent, keywords in AGENT_DOMAINS.items():
            for kw in keywords:
                assert kw == kw.lower(), f"Keyword '{kw}' in {agent} should be lowercase"


class TestLowConfidencePhrases:
    """Phrase list sanity."""

    def test_phrases_are_lowercase(self):
        for phrase in _LOW_CONFIDENCE_PHRASES:
            assert phrase == phrase.lower(), f"Phrase should be lowercase: {phrase}"

    def test_minimum_phrases(self):
        assert len(_LOW_CONFIDENCE_PHRASES) >= 10
