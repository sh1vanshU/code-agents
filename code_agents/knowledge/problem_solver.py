"""Intelligent Problem Solver — maps user problems to agents, commands, skills, and workflows."""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.problem_solver")


@dataclass
class Solution:
    """A recommended solution for a user problem."""
    title: str
    description: str
    action_type: str  # "agent", "command", "slash", "skill", "workflow"
    action: str  # the actual command/agent/skill to use
    confidence: float = 0.0  # 0-1
    follow_up: list[str] = field(default_factory=list)  # next steps after this


@dataclass
class ProblemAnalysis:
    """Analysis of the user's problem."""
    original_query: str
    intent: str = ""  # what the user wants to achieve
    domain: str = ""  # code, test, deploy, debug, review, git, infra, data, docs
    urgency: str = "normal"  # critical, high, normal, low
    solutions: list[Solution] = field(default_factory=list)
    recommended: Optional[Solution] = None  # top recommendation


# ──────────────────────────────────────────────────────────────────────
# Knowledge base: maps keywords/patterns to solutions
# ──────────────────────────────────────────────────────────────────────

PROBLEM_MAP = [
    # ── Code Writing & Modification ──
    {
        "keywords": ["write", "create", "implement", "add feature", "build", "develop", "new file", "scaffold"],
        "domain": "code",
        "intent": "Write or create code",
        "solutions": [
            Solution("Code Writer Agent", "Specialist for writing, modifying, and refactoring code",
                     "agent", "code-writer", 0.9),
            Solution("Auto-Pilot Agent", "Full autonomy — delegates to specialists automatically",
                     "agent", "auto-pilot", 0.7),
        ],
    },
    {
        "keywords": ["refactor", "clean up", "restructure", "code smell", "improve code", "technical debt"],
        "domain": "code",
        "intent": "Refactor or improve existing code",
        "solutions": [
            Solution("Refactor Planner", "Analyze code smells, get step-by-step refactoring plan",
                     "slash", "/refactor <file>", 0.9,
                     follow_up=["Code Writer will implement the changes"]),
            Solution("Dead Code Finder", "Find unused imports, functions, endpoints",
                     "command", "code-agents deadcode", 0.7),
            Solution("Code Writer Agent", "Implement the refactoring",
                     "agent", "code-writer", 0.6),
        ],
    },
    {
        "keywords": ["explain", "understand", "how does", "what does", "trace", "flow", "architecture", "read code"],
        "domain": "code",
        "intent": "Understand existing code",
        "solutions": [
            Solution("Code Reasoning Agent", "Read-only analysis — explains architecture, traces flows",
                     "agent", "code-reasoning", 0.9),
            Solution("Dependency Graph", "See who calls what, dependency tree",
                     "slash", "/deps <class>", 0.7),
            Solution("Blame Investigator", "Full story of a line: who, when, why, what PR",
                     "slash", "/blame <file> <line>", 0.6),
        ],
    },

    # ── Testing ──
    {
        "keywords": ["test", "write test", "unit test", "integration test", "test case", "coverage"],
        "domain": "test",
        "intent": "Write or improve tests",
        "solutions": [
            Solution("Auto-Coverage Boost", "One-button: scan, gaps, prioritize, write tests, verify",
                     "slash", "/coverage-boost", 0.9,
                     follow_up=["Creates branch, commits tests automatically"]),
            Solution("Test Generator", "AI-generate tests for a specific file",
                     "slash", "/generate-tests <file>", 0.85),
            Solution("Code Tester Agent", "Specialist for writing tests and debugging",
                     "agent", "code-tester", 0.8),
            Solution("QA Suite Generator", "Generate full test framework from scratch",
                     "slash", "/qa-suite", 0.7),
        ],
    },
    {
        "keywords": ["coverage", "coverage report", "uncovered", "coverage gap", "improve coverage"],
        "domain": "test",
        "intent": "Improve test coverage",
        "solutions": [
            Solution("Auto-Coverage Boost", "Automated: scan, baseline, gaps, write tests, verify",
                     "slash", "/coverage-boost", 0.95),
            Solution("Test Coverage Agent", "Coverage analysis and gap identification",
                     "agent", "test-coverage", 0.8),
        ],
    },
    {
        "keywords": ["qa", "regression", "automation suite", "test suite", "full test", "e2e test"],
        "domain": "test",
        "intent": "Build or run regression suite",
        "solutions": [
            Solution("QA Suite Generator", "Auto-generate full test framework for the repo",
                     "slash", "/qa-suite", 0.9),
            Solution("QA Regression Agent", "Full regression testing specialist",
                     "agent", "qa-regression", 0.85),
            Solution("Run Tests", "Execute existing test suite",
                     "command", "code-agents test", 0.6),
        ],
    },

    # ── Code Review ──
    {
        "keywords": ["review", "code review", "pr review", "check code", "find bugs", "security review"],
        "domain": "review",
        "intent": "Review code for issues",
        "solutions": [
            Solution("Code Reviewer Agent", "Review for bugs, security, style violations",
                     "agent", "code-reviewer", 0.9),
            Solution("AI Code Review", "Review diff between branches",
                     "command", "code-agents review", 0.85),
            Solution("Security Scanner", "OWASP top 10 vulnerability scan",
                     "command", "code-agents security", 0.7),
            Solution("PR Preview", "Preview PR: diff stats, risk score, affected tests",
                     "command", "code-agents pr-preview", 0.6),
        ],
    },
    {
        "keywords": ["pr comment", "review comment", "reply to review", "address feedback"],
        "domain": "review",
        "intent": "Respond to PR review comments",
        "solutions": [
            Solution("Review Responder", "Generate replies and code fixes for PR comments",
                     "slash", "/review-reply", 0.95),
        ],
    },

    # ── Git Operations ──
    {
        "keywords": ["commit", "git commit", "stage", "git add"],
        "domain": "git",
        "intent": "Commit changes",
        "solutions": [
            Solution("Smart Commit", "Auto-generate conventional commit message from diff",
                     "command", "code-agents commit", 0.95),
            Solution("Git-Ops Agent", "Full git operations specialist",
                     "agent", "git-ops", 0.7),
        ],
    },
    {
        "keywords": ["branch", "checkout", "merge", "git operations", "push", "pull", "stash"],
        "domain": "git",
        "intent": "Git branch operations",
        "solutions": [
            Solution("Git-Ops Agent", "Branch management, merge, stash, push",
                     "agent", "git-ops", 0.9),
            Solution("Branches", "List all branches",
                     "command", "code-agents branches", 0.6),
        ],
    },
    {
        "keywords": ["diff", "what changed", "compare branches", "changes"],
        "domain": "git",
        "intent": "See code changes",
        "solutions": [
            Solution("Diff", "Compare branches with file stats",
                     "command", "code-agents diff", 0.9),
            Solution("PR Preview", "Full PR preview with risk score",
                     "command", "code-agents pr-preview", 0.8),
        ],
    },

    # ── CI/CD & Deploy ──
    {
        "keywords": ["build", "jenkins", "ci", "compile", "package"],
        "domain": "deploy",
        "intent": "Build the project",
        "solutions": [
            Solution("Jenkins CI/CD Agent", "Build and deploy via Jenkins",
                     "agent", "jenkins-cicd", 0.9),
            Solution("Pipeline", "Start CI/CD pipeline",
                     "command", "code-agents pipeline start", 0.8),
        ],
    },
    {
        "keywords": ["deploy", "release", "staging", "production", "rollout"],
        "domain": "deploy",
        "intent": "Deploy or release",
        "solutions": [
            Solution("Release Automation", "End-to-end: branch, test, changelog, build, deploy, Jira",
                     "command", "code-agents release <version>", 0.9),
            Solution("Jenkins CI/CD Agent", "Build and deploy via Jenkins",
                     "agent", "jenkins-cicd", 0.85),
            Solution("ArgoCD Verify Agent", "Check deploy status, pods, rollback",
                     "agent", "argocd-verify", 0.7),
        ],
    },
    {
        "keywords": ["rollback", "revert deploy", "undo deploy", "pod crash", "deployment issue"],
        "domain": "deploy",
        "intent": "Rollback a deployment",
        "solutions": [
            Solution("ArgoCD Verify Agent", "Check pods, rollback deployments",
                     "agent", "argocd-verify", 0.95),
            Solution("Pipeline Rollback", "Rollback via pipeline",
                     "command", "code-agents pipeline rollback <id>", 0.8),
        ],
    },

    # ── Debugging & Incidents ──
    {
        "keywords": ["error", "bug", "exception", "crash", "not working", "broken", "fail", "issue"],
        "domain": "debug",
        "intent": "Debug an error or bug",
        "solutions": [
            Solution("Log Investigator", "Search Kibana logs, correlate with deploys, find root cause",
                     "slash", "/investigate <error>", 0.9),
            Solution("Incident Runbook", "Full incident investigation: pods, logs, deploys, RCA",
                     "command", "code-agents incident <service>", 0.85),
            Solution("Blame Investigator", "Find who changed the code and why",
                     "slash", "/blame <file> <line>", 0.7),
            Solution("Code Reasoning Agent", "Analyze code to understand the bug",
                     "agent", "code-reasoning", 0.6),
        ],
    },
    {
        "keywords": ["incident", "outage", "down", "p1", "p2", "production issue", "on-call"],
        "domain": "debug",
        "intent": "Handle a production incident",
        "solutions": [
            Solution("Incident Runbook", "Auto: check pods, logs, deploys, health, suggest fix, generate RCA",
                     "command", "code-agents incident <service>", 0.95),
            Solution("Log Investigator", "Deep log search and correlation",
                     "slash", "/investigate <error>", 0.8),
            Solution("On-Call Report", "Weekly handoff summary",
                     "command", "code-agents oncall-report", 0.5),
        ],
    },
    {
        "keywords": ["log", "kibana", "search log", "error log", "tail log", "monitor"],
        "domain": "debug",
        "intent": "Search or monitor logs",
        "solutions": [
            Solution("Log Investigator", "Search Kibana, correlate with deploys",
                     "slash", "/investigate <error>", 0.9),
            Solution("Kibana Logs Agent", "Log search, filtering, tail",
                     "agent", "kibana-logs", 0.85),
        ],
    },

    # ── Database & Data ──
    {
        "keywords": ["sql", "query", "database", "db", "redash", "table", "schema"],
        "domain": "data",
        "intent": "Query or explore database",
        "solutions": [
            Solution("Redash Query Agent", "SQL queries, explore schemas",
                     "agent", "redash-query", 0.95),
        ],
    },
    {
        "keywords": ["migration", "flyway", "liquibase", "alter table", "schema change"],
        "domain": "data",
        "intent": "Database migration",
        "solutions": [
            Solution("Code Writer Agent", "Write migration scripts",
                     "agent", "code-writer", 0.8),
            Solution("API Compatibility Check", "Detect breaking changes",
                     "command", "code-agents api-check", 0.6),
        ],
    },

    # ── Jira & Project ──
    {
        "keywords": ["jira", "ticket", "issue", "sprint", "story", "task", "kanban"],
        "domain": "project",
        "intent": "Manage Jira issues",
        "solutions": [
            Solution("Jira-Ops Agent", "Issue management, transitions, Confluence",
                     "agent", "jira-ops", 0.95),
            Solution("Sprint Report", "Sprint summary from Jira + git",
                     "command", "code-agents sprint-report", 0.7),
            Solution("Sprint Velocity", "Velocity tracking across sprints",
                     "command", "code-agents sprint-velocity", 0.6),
        ],
    },
    {
        "keywords": ["standup", "daily", "what did i do", "yesterday", "today"],
        "domain": "project",
        "intent": "Generate standup report",
        "solutions": [
            Solution("AI Standup", "Git log + Jira + build status, standup format",
                     "command", "code-agents standup", 0.95),
        ],
    },

    # ── Documentation ──
    {
        "keywords": ["document", "api doc", "swagger", "openapi", "api documentation"],
        "domain": "docs",
        "intent": "Generate API documentation",
        "solutions": [
            Solution("API Doc Generator", "Scan endpoints, OpenAPI/markdown docs",
                     "command", "code-agents apidoc", 0.95),
        ],
    },
    {
        "keywords": ["onboard", "new developer", "getting started", "how to setup", "project structure"],
        "domain": "docs",
        "intent": "Onboard a new team member",
        "solutions": [
            Solution("Onboarding Guide", "Auto-generate: stack, structure, build/test/run, team",
                     "command", "code-agents onboard --save", 0.95),
            Solution("Knowledge Base", "Search team knowledge",
                     "slash", "/kb <topic>", 0.7),
        ],
    },

    # ── Security & Quality ──
    {
        "keywords": ["security", "vulnerability", "owasp", "injection", "xss", "secret", "credential"],
        "domain": "security",
        "intent": "Security analysis",
        "solutions": [
            Solution("Security Scanner", "OWASP top 10: SQL injection, XSS, secrets, insecure deps",
                     "command", "code-agents security", 0.95),
            Solution("Dependency Audit", "CVE check, license issues, outdated versions",
                     "command", "code-agents audit", 0.8),
        ],
    },
    {
        "keywords": ["dead code", "unused", "cleanup", "remove unused"],
        "domain": "code",
        "intent": "Find and remove dead code",
        "solutions": [
            Solution("Dead Code Finder", "Unused imports, functions, endpoints",
                     "command", "code-agents deadcode", 0.95),
        ],
    },
    {
        "keywords": ["feature flag", "toggle", "flag", "feature toggle"],
        "domain": "code",
        "intent": "Manage feature flags",
        "solutions": [
            Solution("Feature Flag Manager", "Find flags, env matrix, stale detection",
                     "command", "code-agents flags", 0.95),
        ],
    },
    {
        "keywords": ["config", "configuration", "environment", "staging vs prod", "config drift"],
        "domain": "infra",
        "intent": "Compare or manage configs",
        "solutions": [
            Solution("Config Drift Detector", "Compare configs across environments",
                     "slash", "/config-diff staging prod", 0.95),
            Solution("Doctor", "Full health check including config validation",
                     "command", "code-agents doctor", 0.6),
        ],
    },

    # ── Performance ──
    {
        "keywords": ["slow", "performance", "latency", "speed", "optimize", "profil"],
        "domain": "performance",
        "intent": "Analyze or improve performance",
        "solutions": [
            Solution("Performance Profiler", "Hit endpoints, measure p50/p95/p99 latency",
                     "slash", "/profile <url>", 0.9),
            Solution("Performance Baseline", "Record baseline, detect regressions",
                     "command", "code-agents perf-baseline", 0.85),
        ],
    },

    # ── Setup & Config ──
    {
        "keywords": ["setup", "install", "configure", "init", "get started"],
        "domain": "setup",
        "intent": "Setup code-agents",
        "solutions": [
            Solution("Smart Init", "Configure code-agents (detects existing config, modify sections)",
                     "command", "code-agents init", 0.95),
            Solution("Doctor", "Diagnose setup issues",
                     "command", "code-agents doctor", 0.8),
        ],
    },
    {
        "keywords": ["switch model", "change model", "use claude", "use cursor", "backend"],
        "domain": "setup",
        "intent": "Change AI model or backend",
        "solutions": [
            Solution("Switch Backend", "Change backend mid-conversation",
                     "slash", "/backend <cursor|claude|claude-cli>", 0.95),
            Solution("Switch Model", "Change model mid-conversation",
                     "slash", "/model <opus|sonnet|haiku>", 0.9),
            Solution("Init Backend", "Reconfigure backend",
                     "command", "code-agents init --backend", 0.7),
        ],
    },
]


class ProblemSolver:
    """Analyzes a user's problem and recommends solutions."""

    def analyze(self, query: str) -> ProblemAnalysis:
        """Analyze a problem description and return solutions."""
        analysis = ProblemAnalysis(original_query=query)
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_entries = []
        for entry in PROBLEM_MAP:
            score = 0
            for kw in entry["keywords"]:
                kw_lower = kw.lower()
                if " " in kw_lower:
                    # Multi-word keyword — check as phrase
                    if kw_lower in query_lower:
                        score += 3
                else:
                    # Single word
                    if kw_lower in query_words:
                        score += 2
                    elif kw_lower in query_lower:
                        score += 1
            if score > 0:
                scored_entries.append((score, entry))

        # Sort by score descending
        scored_entries.sort(key=lambda x: -x[0])

        # Take top matches
        seen_actions = set()
        for score, entry in scored_entries[:5]:
            if not analysis.domain:
                analysis.domain = entry.get("domain", "")
            if not analysis.intent:
                analysis.intent = entry.get("intent", "")
            for sol in entry["solutions"]:
                key = f"{sol.action_type}:{sol.action}"
                if key not in seen_actions:
                    # Adjust confidence by match score
                    adjusted = Solution(
                        title=sol.title,
                        description=sol.description,
                        action_type=sol.action_type,
                        action=sol.action,
                        confidence=min(sol.confidence * (score / 6), 1.0),
                        follow_up=list(sol.follow_up),
                    )
                    analysis.solutions.append(adjusted)
                    seen_actions.add(key)

        # Sort by confidence
        analysis.solutions.sort(key=lambda s: -s.confidence)

        # Set recommended
        if analysis.solutions:
            analysis.recommended = analysis.solutions[0]

        # Detect urgency
        urgent_words = {"urgent", "critical", "p1", "down", "outage", "crash", "asap", "production issue", "incident"}
        if any(w in query_lower for w in urgent_words):
            analysis.urgency = "critical"
        elif any(w in query_lower for w in {"important", "p2", "blocking", "blocker"}):
            analysis.urgency = "high"

        return analysis


def format_problem_analysis(analysis: ProblemAnalysis) -> str:
    """Format analysis for terminal display."""
    lines = []
    lines.append("  ╔══ PROBLEM SOLVER ══╗")
    lines.append(f"  ║ Intent: {analysis.intent}")
    lines.append(f"  ║ Domain: {analysis.domain}")
    if analysis.urgency != "normal":
        lines.append(f"  ║ Urgency: {analysis.urgency.upper()}")
    lines.append("  ╚═════════════════════╝")

    if analysis.recommended:
        r = analysis.recommended
        lines.append(f"\n  ★ Recommended: {r.title}")
        lines.append(f"    {r.description}")

        type_prefix = {
            "agent": "Start chat with:",
            "command": "Run:",
            "slash": "In chat, type:",
            "skill": "Use skill:",
            "workflow": "Workflow:",
        }
        prefix = type_prefix.get(r.action_type, "Action:")
        lines.append(f"    → {prefix} {r.action}")

        if r.follow_up:
            for fu in r.follow_up:
                lines.append(f"      Then: {fu}")

    if len(analysis.solutions) > 1:
        lines.append(f"\n  Other options:")
        for i, sol in enumerate(analysis.solutions[1:6], 2):
            conf_bar = "█" * int(sol.confidence * 5) + "░" * (5 - int(sol.confidence * 5))
            lines.append(f"    {i}. [{conf_bar}] {sol.title}")
            lines.append(f"       {sol.action_type}: {sol.action}")

    return "\n".join(lines)
