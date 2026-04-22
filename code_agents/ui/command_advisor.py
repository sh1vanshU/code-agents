"""Smart /commands with Agent Routing — maps user intents to the right agent + commands.

When user types `/commands build` it shows which agent handles builds and the relevant commands.
Provides fuzzy matching, categorized listing, and formatted output with agent routing info.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("code_agents.ui.command_advisor")

# ---------------------------------------------------------------------------
# Intent map: keyword -> {agent, commands, description}
# ---------------------------------------------------------------------------

INTENT_MAP: dict[str, dict] = {
    # CI/CD
    "build": {
        "agent": "jenkins-cicd",
        "commands": ["/jenkins-cicd build", "code-agents ci-heal"],
        "description": "Build project via Jenkins",
        "category": "CI/CD",
    },
    "deploy": {
        "agent": "jenkins-cicd",
        "commands": ["/jenkins-cicd deploy", "/argocd-verify"],
        "description": "Deploy to environment",
        "category": "CI/CD",
    },
    "pipeline": {
        "agent": "jenkins-cicd",
        "commands": ["/ci-heal", "code-agents ci-run"],
        "description": "CI/CD pipeline management",
        "category": "CI/CD",
    },

    # Code Quality
    "review": {
        "agent": "code-reviewer",
        "commands": ["/review", "code-agents review --fix"],
        "description": "AI code review with inline diff",
        "category": "Code Quality",
    },
    "test": {
        "agent": "code-tester",
        "commands": ["/mutate-test", "/gen-tests", "code-agents profiler"],
        "description": "Testing and quality",
        "category": "Code Quality",
    },
    "security": {
        "agent": "security",
        "commands": ["/pci-scan", "/owasp-scan", "/security"],
        "description": "Security scanning",
        "category": "Code Quality",
    },
    "debug": {
        "agent": "debug-agent",
        "commands": ["/explain-code", "/txn-flow"],
        "description": "Debug and trace issues",
        "category": "Code Quality",
    },

    # Analysis
    "analyze": {
        "agent": "code-reasoning",
        "commands": ["/smell", "/tech-debt", "/complexity", "/dead-code"],
        "description": "Code analysis",
        "category": "Analysis",
    },
    "audit": {
        "agent": "auto-pilot",
        "commands": ["/audit", "/pci-scan", "/owasp-scan"],
        "description": "Full codebase audit",
        "category": "Analysis",
    },
    "mindmap": {
        "agent": "auto-pilot",
        "commands": ["/mindmap", "/dashboard"],
        "description": "Visualize codebase",
        "category": "Analysis",
    },

    # Database
    "database": {
        "agent": "db-ops",
        "commands": ["/schema", "code-agents schema --sql-file"],
        "description": "Database operations",
        "category": "Database",
    },
    "query": {
        "agent": "db-ops",
        "commands": ["/db-ops", "code-agents recon"],
        "description": "Query and reconciliation",
        "category": "Database",
    },

    # Payment
    "payment": {
        "agent": "jenkins-cicd",
        "commands": ["/txn-flow", "/idempotency", "/validate-states"],
        "description": "Payment flow management",
        "category": "Payment",
    },
    "reconciliation": {
        "agent": "auto-pilot",
        "commands": ["/recon", "/settlement"],
        "description": "Settlement reconciliation",
        "category": "Payment",
    },
    "acquirer": {
        "agent": "auto-pilot",
        "commands": ["/acquirer-health", "/retry-audit"],
        "description": "Acquirer monitoring",
        "category": "Payment",
    },

    # Monitoring
    "monitor": {
        "agent": "grafana-ops",
        "commands": ["/tail", "/acquirer-health", "/dashboard"],
        "description": "Monitoring and alerts",
        "category": "Monitoring",
    },
    "logs": {
        "agent": "auto-pilot",
        "commands": ["/tail", "/explain-code"],
        "description": "Log analysis",
        "category": "Monitoring",
    },
    "incident": {
        "agent": "auto-pilot",
        "commands": ["/incident", "/postmortem-gen"],
        "description": "Incident response",
        "category": "Monitoring",
    },

    # Documentation
    "docs": {
        "agent": "auto-pilot",
        "commands": ["/api-docs", "/changelog", "/release-notes"],
        "description": "Documentation generation",
        "category": "Documentation",
    },
    "translate": {
        "agent": "auto-pilot",
        "commands": ["/translate", "/explain-code"],
        "description": "Code translation",
        "category": "Documentation",
    },

    # Git/PR
    "pr": {
        "agent": "auto-pilot",
        "commands": ["/pr-respond", "/pr-describe", "/review"],
        "description": "PR management",
        "category": "Git/PR",
    },
    "git": {
        "agent": "git-ops",
        "commands": ["/blame", "/ownership"],
        "description": "Git operations",
        "category": "Git/PR",
    },

    # Infrastructure
    "terraform": {
        "agent": "terraform-ops",
        "commands": ["/terraform-ops plan", "code-agents validate-states"],
        "description": "Infrastructure management",
        "category": "Infrastructure",
    },
    "k8s": {
        "agent": "argocd-verify",
        "commands": ["/argocd-verify", "/acquirer-health"],
        "description": "Kubernetes operations",
        "category": "Infrastructure",
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommandSuggestion:
    """A single command suggestion with routing info."""

    intent: str
    agent: str
    commands: list[str]
    description: str
    score: float


# ---------------------------------------------------------------------------
# CommandAdvisor
# ---------------------------------------------------------------------------

class CommandAdvisor:
    """Maps user intents to the right agent + commands via fuzzy matching."""

    def __init__(self) -> None:
        self._intents = INTENT_MAP
        logger.debug("CommandAdvisor initialized with %d intents", len(self._intents))

    # ----- public API -----

    def suggest(self, query: str) -> list[CommandSuggestion]:
        """Fuzzy match *query* against intent keywords and descriptions.

        Returns a list of :class:`CommandSuggestion` sorted by descending score.
        """
        if not query or not query.strip():
            return []

        query_lower = query.lower().strip()
        results: list[CommandSuggestion] = []

        for intent, info in self._intents.items():
            score = self._score_match(query_lower, intent, info)
            if score > 0:
                results.append(CommandSuggestion(
                    intent=intent,
                    agent=info["agent"],
                    commands=list(info["commands"]),
                    description=info["description"],
                    score=score,
                ))

        results.sort(key=lambda s: s.score, reverse=True)
        logger.debug("Query '%s' matched %d intents", query, len(results))
        return results

    def list_all(self) -> dict[str, list[dict]]:
        """Return all intents grouped by category."""
        grouped: dict[str, list[dict]] = {}
        for intent, info in self._intents.items():
            category = info.get("category", "Other")
            grouped.setdefault(category, []).append({
                "intent": intent,
                "agent": info["agent"],
                "commands": info["commands"],
                "description": info["description"],
            })
        return grouped

    def format_suggestions(self, suggestions: list[CommandSuggestion]) -> str:
        """Format suggestions into a readable string with agent routing info."""
        if not suggestions:
            return "  No matching commands found."

        lines: list[str] = []
        for s in suggestions:
            agent_tag = f"\033[36m{s.agent}\033[0m"
            desc = s.description
            lines.append(f"  \033[1m{s.intent}\033[0m  ->  agent: {agent_tag}  ({desc})")
            for cmd in s.commands:
                lines.append(f"    \033[33m{cmd}\033[0m")
            lines.append("")

        return "\n".join(lines)

    # ----- internals -----

    @staticmethod
    def _score_match(query: str, intent: str, info: dict) -> float:
        """Score how well *query* matches an intent.

        Scoring rules:
        - Exact match on intent keyword: 1.0
        - Intent starts with query (prefix): 0.8
        - Query is a substring of intent: 0.6
        - Query found in description (case-insensitive): 0.4
        - Query found in any command string: 0.3
        - Query found in agent name: 0.25
        - No match: 0.0
        """
        if query == intent:
            return 1.0
        if intent.startswith(query):
            return 0.8
        if query in intent:
            return 0.6

        desc_lower = info.get("description", "").lower()
        if query in desc_lower:
            return 0.4

        for cmd in info.get("commands", []):
            if query in cmd.lower():
                return 0.3

        if query in info.get("agent", "").lower():
            return 0.25

        return 0.0


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def format_all_commands() -> str:
    """Full categorized command reference for ``/commands`` with no args.

    Returns a human-readable string with all intents grouped by category,
    including agent names and available commands.
    """
    advisor = CommandAdvisor()
    grouped = advisor.list_all()

    lines: list[str] = []
    lines.append("")
    lines.append("  \033[1mSmart Command Reference (by category)\033[0m")
    lines.append("  \033[2mUse /commands <query> to search — e.g. /commands build\033[0m")
    lines.append("")

    for category, intents in grouped.items():
        lines.append(f"  \033[1;35m{category}\033[0m")
        for item in intents:
            agent_tag = f"\033[36m{item['agent']}\033[0m"
            lines.append(
                f"    \033[1m{item['intent']:<18}\033[0m"
                f"  {agent_tag:<30}  {item['description']}"
            )
            cmd_str = ", ".join(f"\033[33m{c}\033[0m" for c in item["commands"])
            lines.append(f"      {cmd_str}")
        lines.append("")

    return "\n".join(lines)
