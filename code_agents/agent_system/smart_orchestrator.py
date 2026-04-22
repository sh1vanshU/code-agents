"""
SmartOrchestrator — the brain of the lean auto-pilot.

Analyzes each user message and picks 1 agent + 1-3 skills + 1-2 tools,
producing a minimal context injection (~200 tokens) instead of the full
~5000 token fat prompt. Lazy-loaded: only imported when auto-pilot is active.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Agent capabilities: agent → (keywords, one-line description) ────────────
# Loaded dynamically from agent YAML `routing:` sections.
# Fallback dict used when agents haven't been loaded yet or lack `routing:`.

_FALLBACK_CAPABILITIES: dict[str, dict[str, Any]] = {
    "code-reasoning": {
        "keywords": ["explain code", "how does", "trace", "architecture", "flow", "analyze code", "understand code", "read code", "design pattern"],
        "description": "Read-only code analysis, architecture explanation, flow tracing",
    },
    "code-writer": {
        "keywords": ["write", "create", "implement", "add", "refactor", "modify", "generate", "new file", "feature", "update code", "fix code"],
        "description": "Generate and modify code, implement features, refactor",
    },
    "code-reviewer": {
        "keywords": ["review", "pr", "pull request", "security", "vulnerability", "style", "lint", "code quality", "bug", "smell"],
        "description": "Code review for bugs, security, style violations",
    },
    "code-tester": {
        "keywords": ["write test", "test this", "test", "debug", "unit test", "integration test", "mock", "assert", "tdd", "fixture", "pytest", "junit", "spec", "write tests", "run tests", "test repository", "test the code", "lets test"],
        "description": "Write tests, run tests, debug failures, test strategy",
    },
    "git-ops": {
        "keywords": ["git", "branch", "merge", "checkout", "push", "pull", "commit", "rebase", "stash", "diff", "log", "cherry-pick"],
        "description": "Git operations: branches, diffs, logs, merge, push",
    },
    "jenkins-cicd": {
        "keywords": ["build", "jenkins", "ci", "cd", "deploy", "job", "pipeline", "artifact", "trigger build"],
        "description": "Jenkins CI/CD: trigger builds, poll status, extract versions",
    },
    "argocd-verify": {
        "keywords": ["argocd", "argo", "sync", "pod", "kubernetes", "k8s", "rollback", "deployment status", "container"],
        "description": "ArgoCD deployment verification, pod logs, rollback",
    },
    "redash-query": {
        "keywords": ["sql", "query", "database", "redash", "schema", "table", "select", "join", "aggregate"],
        "description": "SQL queries via Redash, database exploration",
    },
    "qa-regression": {
        "keywords": ["regression", "regression test", "qa", "end to end test", "e2e", "test suite", "smoke test", "full test suite"],
        "description": "Regression suites, full test runs, eliminate manual QA",
    },
    "test-coverage": {
        "keywords": ["test coverage", "code coverage", "coverage", "coverage report", "uncovered", "coverage gap", "branch coverage", "line coverage", "coverage percent", "80%", "90%", "100%", "covered", "percent covered", "check coverage"],
        "description": "Run test suites, generate coverage reports, find gaps, improve coverage percentage",
    },
    "jira-ops": {
        "keywords": ["jira", "ticket", "issue", "confluence", "sprint", "story", "epic", "transition", "assign"],
        "description": "Jira ticket management, Confluence pages, status transitions",
    },
    "auto-pilot": {
        "keywords": ["autonomous", "full workflow", "do everything", "end to end"],
        "description": "Autonomous orchestrator — delegates to sub-agents",
    },
}


def _load_capabilities_from_agents() -> dict[str, dict[str, Any]]:
    """Build AGENT_CAPABILITIES from agent YAML routing sections.

    Falls back to _FALLBACK_CAPABILITIES for agents without routing config.
    """
    caps: dict[str, dict[str, Any]] = {}
    try:
        from code_agents.core.config import agent_loader
        agents = agent_loader.list_agents()
        for agent in agents:
            if agent.routing_keywords:
                caps[agent.name] = {
                    "keywords": agent.routing_keywords,
                    "description": agent.routing_description or agent.display_name,
                }
    except Exception:
        pass

    # Merge fallback for agents not yet in YAMLs
    for name, fallback in _FALLBACK_CAPABILITIES.items():
        if name not in caps:
            caps[name] = fallback

    return caps if caps else dict(_FALLBACK_CAPABILITIES)


# Lazy-loaded: built on first access
AGENT_CAPABILITIES: dict[str, dict[str, Any]] = {}


def _ensure_capabilities() -> None:
    """Populate AGENT_CAPABILITIES if empty."""
    if not AGENT_CAPABILITIES:
        AGENT_CAPABILITIES.update(_load_capabilities_from_agents())


# ── Conversational patterns — NEVER trigger routing ──────────────────────────

_CONVERSATIONAL_PATTERNS = frozenset({
    "yes", "no", "y", "n", "ok", "okay", "sure", "proceed", "go ahead",
    "go for it", "do it", "confirm", "cancel", "skip", "continue",
    "retry", "next", "done", "stop", "quit", "exit",
    "1", "2", "3", "4", "5", "option a", "option b", "option c",
})

# ── Skill keyword index (auto-pilot skills) ────────────────────────────────

_SKILL_KEYWORDS: dict[str, list[str]] = {
    "cicd-pipeline": ["pipeline", "ci/cd", "cicd", "stages", "pipeline status"],
    "investigate": ["investigate", "debug", "root cause", "error", "failure", "incident", "log"],
    "review-fix": ["review", "fix", "pull request", "code review", "bug fix"],
    "full-sdlc": ["sdlc", "full lifecycle", "end to end", "requirement to deploy", "complete workflow"],
    "incident-manager": ["incident", "outage", "downtime", "alert", "on-call", "sev1", "sev2"],
    "workflow-planner": ["plan", "workflow", "steps", "strategy", "approach", "task breakdown"],
    "release": ["release", "tag", "version bump", "changelog", "cut release"],
}

# ── Cross-agent skill keywords for delegation ──────────────────────────────

_CROSS_AGENT_SKILLS: dict[str, dict[str, list[str]]] = {
    "jenkins-cicd": {
        "build": ["build", "jenkins build", "trigger build", "build job"],
        "deploy": ["deploy", "jenkins deploy", "deployment"],
    },
    "git-ops": {
        "safe-checkout": ["checkout", "switch branch", "safe checkout"],
        "branching": ["branch", "create branch", "feature branch"],
    },
    "code-reviewer": {
        "security-review": ["security", "vulnerability", "owasp"],
    },
    "code-tester": {
        "test-strategy": ["test plan", "test strategy", "what to test"],
    },
}


# ── Centralized delegation map: agent → [(target, trigger description)] ───
# Each agent knows which specialists to delegate to and when.
# This is injected on-demand (not baked into every system prompt).

AGENT_DELEGATION_MAP: dict[str, list[tuple[str, str]]] = {
    "code-writer": [
        ("code-tester", "write/run tests for new code"),
        ("code-reviewer", "review changes"),
        ("test-coverage", "check coverage for changes"),
        ("jenkins-cicd", "trigger build"),
        ("git-ops", "git operations"),
    ],
    "code-tester": [
        ("code-writer", "implement features/fixes"),
        ("code-reviewer", "security review"),
        ("test-coverage", "coverage reports and gap analysis"),
        ("jenkins-cicd", "trigger CI build"),
    ],
    "code-reviewer": [
        ("code-tester", "write tests for findings"),
        ("code-writer", "fix bugs found"),
        ("test-coverage", "check coverage for reviewed code"),
        ("jenkins-cicd", "verify build"),
    ],
    "code-reasoning": [
        ("code-writer", "implement changes"),
        ("code-tester", "write tests"),
        ("test-coverage", "coverage analysis"),
        ("git-ops", "git operations"),
        ("redash-query", "SQL queries"),
    ],
    "test-coverage": [
        ("code-tester", "write complex tests"),
        ("code-writer", "fix code to pass tests"),
        ("qa-regression", "full regression suite"),
        ("jenkins-cicd", "trigger build after test changes"),
        ("git-ops", "branch/commit operations"),
    ],
    "qa-regression": [
        ("code-tester", "write individual tests"),
        ("code-writer", "implement fixes"),
        ("test-coverage", "coverage reports"),
        ("jenkins-cicd", "trigger build/deploy"),
    ],
    "git-ops": [
        ("code-writer", "implement code changes"),
        ("code-tester", "run tests after merge"),
        ("code-reviewer", "review before merge"),
        ("test-coverage", "check coverage for changes"),
        ("jenkins-cicd", "trigger build after push"),
    ],
    "jenkins-cicd": [
        ("argocd-verify", "verify deployment"),
        ("code-writer", "fix build failures"),
        ("code-tester", "run tests before build"),
        ("test-coverage", "check coverage before build"),
        ("git-ops", "git operations"),
        ("jira-ops", "update ticket with build status"),
    ],
    "argocd-verify": [
        ("jenkins-cicd", "trigger build/deploy"),
        ("code-writer", "fix failing pods"),
        ("code-tester", "debug test failures"),
        ("git-ops", "git operations"),
        ("jira-ops", "update ticket with deploy status"),
    ],
    "jira-ops": [
        ("code-writer", "implement ticket requirements"),
        ("code-tester", "write tests for ticket"),
        ("code-reviewer", "review code for ticket"),
        ("jenkins-cicd", "trigger build/deploy"),
        ("git-ops", "create branch for ticket"),
    ],
    "redash-query": [
        ("code-reasoning", "analyze code/schema"),
        ("code-writer", "fix data issues"),
        ("jira-ops", "create ticket for findings"),
    ],
}


def _keyword_matches(keyword: str, text: str) -> bool:
    """Check if keyword matches in text using word boundaries.

    Short keywords (<=3 chars like 'pr', 'ci', 'cd', 'qa', 'sql') require
    whole-word match to prevent false positives ('pr' in 'proceed',
    'ci' in 'acquiring', 'cd' in 'abcdef').

    Multi-word keywords ('pull request', 'trigger build') use substring
    match since they're specific enough.
    """
    if len(keyword) <= 3:
        # Whole-word match for short keywords
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
    elif ' ' in keyword:
        # Multi-word: substring match is fine (already specific)
        return keyword in text
    else:
        # Single word >3 chars: word boundary match
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))


class SmartOrchestrator:
    """Analyzes user messages and produces targeted context for auto-pilot."""

    def analyze_request(self, user_message: str) -> dict[str, Any]:
        """Analyze a user message and return routing + context info.

        Returns:
            dict with keys:
                intent: str - short description of what the user wants
                best_agent: str - recommended specialist agent name
                relevant_skills: list[str] - 1-3 skill names to load
                relevant_tools: list[str] - 1-2 tool names
                should_delegate: bool - whether auto-pilot should delegate
                context_injection: str - ~200 token context block to inject
        """
        msg_lower = user_message.lower().strip()

        # Skip routing for conversational follow-ups (yes, proceed, 2, etc.)
        if msg_lower in _CONVERSATIONAL_PATTERNS:
            return {
                "intent": "conversational follow-up",
                "best_agent": "auto-pilot",
                "score": 0.0,
                "relevant_skills": [],
                "should_delegate": False,
                "context_injection": "",
            }

        best_agent, best_score = self._find_best_agent(msg_lower)
        relevant_skills = self._find_relevant_skills(msg_lower, best_agent)
        intent = self._infer_intent(msg_lower, best_agent)
        should_delegate = best_agent != "auto-pilot"

        context_injection = self._build_minimal_context(
            best_agent, relevant_skills,
        )

        return {
            "intent": intent,
            "best_agent": best_agent,
            "score": best_score,
            "relevant_skills": relevant_skills,
            "should_delegate": should_delegate,
            "context_injection": context_injection,
        }

    @staticmethod
    def get_delegation_hints(current_agent: str) -> str:
        """Return a compact delegation block for the given agent (~80-120 tokens).

        Delegation is round-trip: the delegate executes as a tool and its result
        returns to you for synthesis. You keep control — delegates don't hand off.

        Injected into system prompt on-demand by stream.py, NOT baked into YAML.
        Returns empty string if no delegation map exists for the agent.
        """
        targets = AGENT_DELEGATION_MAP.get(current_agent)
        if not targets:
            return ""
        lines = [
            "[DELEGATION] Use [DELEGATE:agent-name] prompt to invoke a specialist.",
            "The delegate runs as a tool — its result returns to you. You synthesize and respond.",
            "Available delegates:",
        ]
        for agent, trigger in targets:
            lines.append(f"  - {trigger} → [DELEGATE:{agent}]")
        return "\n".join(lines)

    def _find_best_agent(self, msg_lower: str) -> tuple[str, float]:
        """Score each agent by keyword matches and return (best_agent, score).

        Uses word-boundary matching to prevent false positives like
        "pr" matching inside "proceed" or "ci" inside "acquiring".
        """
        _ensure_capabilities()
        scores: dict[str, float] = {}
        for agent_name, caps in AGENT_CAPABILITIES.items():
            if agent_name == "auto-pilot":
                continue  # Don't self-delegate
            score = 0.0
            for kw in caps["keywords"]:
                if _keyword_matches(kw, msg_lower):
                    # Longer keywords are more specific, give them more weight
                    score += len(kw.split())
            scores[agent_name] = score

        if not scores:
            return "auto-pilot", 0.0

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "auto-pilot", 0.0
        return best, scores[best]

    # Class-level cache for discovered skills (built once, reused)
    _all_skills_cache: dict[str, list[str]] | None = None

    def _find_relevant_skills(self, msg_lower: str, agent: str) -> list[str]:
        """Find up to 3 relevant skills from ALL agents + global _shared skills.

        Discovery order:
        1. Auto-pilot's own curated skill keywords
        2. Cross-agent hardcoded skill keywords (fast path)
        3. Dynamic filesystem scan of ALL agent skills (cached after first call)
        """
        scored: list[tuple[str, float]] = []

        # 1. Auto-pilot curated skills (fastest — hardcoded keywords)
        for skill_name, keywords in _SKILL_KEYWORDS.items():
            score = sum(1 for kw in keywords if _keyword_matches(kw, msg_lower))
            if score > 0:
                scored.append((skill_name, score))

        # 2. Cross-agent hardcoded skills (fast path for known combos)
        if agent in _CROSS_AGENT_SKILLS:
            for skill_name, keywords in _CROSS_AGENT_SKILLS[agent].items():
                score = sum(1 for kw in keywords if _keyword_matches(kw, msg_lower))
                if score > 0:
                    scored.append((f"{agent}:{skill_name}", score))

        # 3. Dynamic discovery: scan ALL agent skills from filesystem (cached)
        all_skills = self._discover_all_skills()
        msg_words = set(msg_lower.split())
        for full_key, skill_words in all_skills.items():
            # Skip if already found via curated/cross-agent
            if any(full_key.endswith(s[0].split(":")[-1]) for s in scored):
                continue
            score = 0
            for sw in skill_words:
                if sw in msg_words:
                    score += 1
                elif sw in msg_lower:
                    score += 0.5
            if score > 0:
                scored.append((full_key, score))

        # Sort by score descending, take top 3
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored[:3]]

    @classmethod
    def _discover_all_skills(cls) -> dict[str, list[str]]:
        """Discover ALL skills from ALL agents + _shared. Cached after first call.

        Returns: {"agent:skill-name": ["keyword", "words", ...], ...}
        """
        if cls._all_skills_cache is not None:
            return cls._all_skills_cache

        import os
        from pathlib import Path

        agents_dir = Path(__file__).parent.parent / "agents"
        cls._all_skills_cache = {}

        if not agents_dir.exists():
            return cls._all_skills_cache

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            skills_dir = agent_dir / "skills"
            if not skills_dir.exists():
                continue

            agent_name = agent_dir.name.replace("_", "-")
            # _shared skills are global (no agent prefix)
            is_shared = agent_name == "-shared" or agent_dir.name == "_shared"

            for skill_file in skills_dir.glob("*.md"):
                skill_name = skill_file.stem
                # Extract keywords from skill name + first line description
                keywords = skill_name.replace("-", " ").replace("_", " ").split()
                try:
                    with open(skill_file) as f:
                        # Read frontmatter for trigger keywords
                        first_lines = f.read(500)
                    # Parse trigger: line from YAML frontmatter
                    import re
                    trigger_match = re.search(r'trigger:\s*(.+)', first_lines)
                    if trigger_match:
                        triggers = [t.strip() for t in trigger_match.group(1).split(",")]
                        keywords.extend(triggers)
                    # Parse description
                    desc_match = re.search(r'description:\s*(.+)', first_lines)
                    if desc_match:
                        keywords.extend(desc_match.group(1).lower().split()[:5])
                except Exception:
                    pass

                # Filter short/common words
                keywords = [k.lower() for k in keywords if len(k) > 2]

                if is_shared:
                    full_key = skill_name  # global skill, no prefix
                else:
                    full_key = f"{agent_name}:{skill_name}"

                cls._all_skills_cache[full_key] = keywords

        logger.info("Discovered %d skills across all agents", len(cls._all_skills_cache))
        return cls._all_skills_cache

    def _infer_intent(self, msg_lower: str, best_agent: str) -> str:
        """Generate a short intent description."""
        if best_agent == "auto-pilot":
            return "general request"
        caps = AGENT_CAPABILITIES.get(best_agent, {})
        return caps.get("description", f"{best_agent} task")

    def _build_minimal_context(
        self,
        agent: str,
        skills: list[str],
    ) -> str:
        """Build a ~100 token context injection block."""
        parts: list[str] = []

        parts.append(f"[SMART CONTEXT] Recommended: {agent}")
        if agent != "auto-pilot":
            caps = AGENT_CAPABILITIES.get(agent, {})
            parts.append(f"  {agent}: {caps.get('description', '')}")
            parts.append(f"  -> Use [DELEGATE:{agent}] for best results")

        if skills:
            skill_str = ", ".join(f"[SKILL:{s}]" for s in skills)
            parts.append(f"  Relevant skills: {skill_str}")

        return "\n".join(parts)