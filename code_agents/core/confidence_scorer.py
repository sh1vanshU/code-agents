"""Agent Confidence Scorer — rates response confidence and suggests delegation.

Lightweight heuristic-based scoring (no API calls). Analyzes agent responses
for confidence indicators and suggests specialist delegation when score is low.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("code_agents.core.confidence_scorer")


@dataclass
class ConfidenceResult:
    """Result of confidence scoring."""

    score: int  # 1-5
    reasoning: str
    should_delegate: bool
    suggested_agent: str = ""


# ---------------------------------------------------------------------------
# Domain keywords — maps topics to the best-fit agent
# ---------------------------------------------------------------------------

AGENT_DOMAINS: dict[str, list[str]] = {
    "code-writer": [
        "implement", "create", "write code", "add feature", "refactor",
        "generate", "modify", "new file", "new class", "new function",
    ],
    "code-reviewer": [
        "review", "code quality", "best practice", "security issue",
        "vulnerability", "style", "lint", "smell",
    ],
    "code-tester": [
        "test", "unit test", "assert", "mock", "fixture", "pytest",
        "coverage", "tdd", "test case",
    ],
    "code-reasoning": [
        "explain", "how does", "architecture", "trace", "understand",
        "why does", "what is", "analyze code", "design pattern",
    ],
    "git-ops": [
        "git", "branch", "merge", "commit", "push", "pull", "checkout",
        "stash", "rebase", "diff", "log",
    ],
    "jenkins-cicd": [
        "build", "jenkins", "ci/cd", "pipeline", "deploy", "artifact",
        "job", "ci pipeline",
    ],
    "argocd-verify": [
        "argocd", "deployment", "pod", "rollback", "kubernetes", "k8s",
        "sync", "deploy status",
    ],
    "redash-query": [
        "sql", "query", "database", "redash", "schema", "table",
        "select", "join",
    ],
    "jira-ops": [
        "jira", "ticket", "issue", "sprint", "confluence", "story",
        "epic", "backlog",
    ],
    "test-coverage": [
        "coverage report", "coverage gap", "uncovered", "test suite",
        "coverage percent",
    ],
    "qa-regression": [
        "regression", "qa", "smoke test", "end-to-end", "e2e",
        "integration test",
    ],
    "pipeline-orchestrator": [
        "full pipeline", "sdlc", "release", "end to end pipeline",
        "orchestrate",
    ],
    "auto-pilot": [
        "autonomous", "auto", "do everything", "full workflow",
    ],
}


# ---------------------------------------------------------------------------
# Low-confidence phrases (case-insensitive)
# ---------------------------------------------------------------------------

_LOW_CONFIDENCE_PHRASES = [
    "i'm not sure",
    "i am not sure",
    "i think",
    "might be",
    "possibly",
    "i don't have access",
    "i cannot",
    "i can't",
    "i don't know",
    "i'm unable",
    "i am unable",
    "not certain",
    "beyond my",
    "outside my",
    "not my area",
    "you should ask",
    "you might want to try",
    "i don't have enough",
    "i'm not the best",
    "another agent",
    "not equipped",
]

# ---------------------------------------------------------------------------
# High-confidence indicators (regex patterns)
# ---------------------------------------------------------------------------

_HIGH_CONFIDENCE_PATTERNS = [
    r"```",                        # code blocks
    r"(?:^|\s)/[\w./-]+\.\w+",    # file paths like /src/foo.py
    r"\$ .+",                      # command examples
    r"^\s*def |^\s*class |^\s*function ",  # code definitions
]


class ConfidenceScorer:
    """Score agent response confidence using lightweight heuristics."""

    def score_response(
        self,
        agent_name: str,
        user_query: str,
        response: str,
    ) -> ConfidenceResult:
        """Score agent response confidence (1-5) based on heuristics.

        Returns a ConfidenceResult with score, reasoning, delegation flag,
        and suggested agent name.
        """
        if not response or not response.strip():
            return ConfidenceResult(
                score=1,
                reasoning="Empty response",
                should_delegate=False,
            )

        score = 3  # neutral baseline
        reasons: list[str] = []

        # --- Low-confidence signals ---
        response_lower = response.lower()

        low_phrase_count = sum(
            1 for phrase in _LOW_CONFIDENCE_PHRASES if phrase in response_lower
        )
        if low_phrase_count >= 3:
            score -= 2
            reasons.append("multiple uncertainty phrases")
        elif low_phrase_count >= 1:
            score -= 1
            reasons.append("uncertainty phrases detected")

        # Very short response for a substantive query
        query_words = len(user_query.split())
        if len(response.strip()) < 50 and query_words > 5:
            score -= 1
            reasons.append("very short response")

        # --- High-confidence signals ---
        for pattern in _HIGH_CONFIDENCE_PATTERNS:
            if re.search(pattern, response, re.MULTILINE):
                score += 1
                break  # only +1 total for having concrete artifacts

        # Long, detailed response
        if len(response.strip()) > 500:
            score += 1
            reasons.append("detailed response")

        # Tool/execution failure detection
        failure_patterns = ["error:", "failed:", "traceback", "exception", "timed out", "connection refused"]
        if any(pat in response_lower for pat in failure_patterns):
            score -= 1
            reasons.append("execution failure pattern detected")
            logger.debug("Confidence -1: execution failure pattern detected")

        # Incomplete response detection (ends mid-sentence)
        stripped = response.strip()
        if stripped and not stripped.endswith(('```', '.', '!', '?', ':', ')', ']')) and len(stripped) > 100:
            score -= 1
            reasons.append("response appears incomplete")
            logger.debug("Confidence -1: response appears incomplete")

        # --- Domain mismatch ---
        best_agent = self._best_agent_for_query(user_query, agent_name)
        if best_agent and best_agent != agent_name:
            score -= 1
            reasons.append(f"query better suited for {best_agent}")

        # Clamp to 1-5
        score = max(1, min(5, score))

        should_delegate = score <= 2 and bool(best_agent) and best_agent != agent_name
        suggested = best_agent if should_delegate else ""

        reasoning = "; ".join(reasons) if reasons else "standard confidence"

        result = ConfidenceResult(
            score=score,
            reasoning=reasoning,
            should_delegate=should_delegate,
            suggested_agent=suggested,
        )
        logger.debug(
            "Confidence score for %s: %d/5 (%s)", agent_name, score, reasoning,
        )
        return result

    def _best_agent_for_query(
        self, user_query: str, current_agent: str,
    ) -> str:
        """Find the best-fit agent for a query based on domain keywords.

        Returns the agent name with highest keyword overlap, or empty string
        if current agent is already the best fit or no clear winner.
        """
        query_lower = user_query.lower()
        scores: dict[str, int] = {}

        for agent, keywords in AGENT_DOMAINS.items():
            hit_count = sum(1 for kw in keywords if kw in query_lower)
            if hit_count > 0:
                scores[agent] = hit_count

        if not scores:
            return ""

        best = max(scores, key=lambda a: scores[a])

        # Only suggest if the best agent clearly wins (>= 1 hit)
        # and is different from the current agent
        if best == current_agent:
            return ""

        # If current agent also has hits, only suggest if best is significantly better
        current_hits = scores.get(current_agent, 0)
        if scores[best] <= current_hits:
            return ""

        return best


# Module-level singleton (lazy-loaded via get_scorer)
_scorer: ConfidenceScorer | None = None


def get_scorer() -> ConfidenceScorer:
    """Get or create the singleton ConfidenceScorer."""
    global _scorer
    if _scorer is None:
        _scorer = ConfidenceScorer()
    return _scorer
