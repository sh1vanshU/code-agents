"""Option definitions for Claude Code-style command panels.

Each function returns ``(title, subtitle, options_list)`` ready for ``show_panel()``.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("code_agents.chat.command_panel_options")


def get_model_options(current_model: str = "") -> tuple[str, str, list[dict]]:
    """Options for /model panel."""
    if not current_model:
        current_model = os.getenv("CODE_AGENTS_MODEL", "Composer 2 Fast")

    models = [
        ("Composer 2 Fast", "Default Cursor model · fast responses"),
        ("claude-opus-4-6", "Claude Opus 4.6 · most capable for complex work"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 · best for everyday tasks"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 · fastest for quick answers"),
    ]

    # Add env override if set and not in list
    env_model = os.getenv("CODE_AGENTS_MODEL", "")
    if env_model and not any(m[0] == env_model for m in models):
        models.insert(0, (env_model, "From CODE_AGENTS_MODEL env var"))

    options = []
    for name, desc in models:
        options.append({
            "name": name,
            "description": desc,
            "active": name == current_model,
        })

    return ("Select model", "Switch between models. Applies to this session.", options)


def get_backend_options(current_backend: str = "") -> tuple[str, str, list[dict]]:
    """Options for /backend panel."""
    if not current_backend:
        current_backend = os.getenv("CODE_AGENTS_BACKEND", "local")

    backends = [
        ("local", "Local LLM · OpenAI-compatible (Ollama, LM Studio, vLLM)"),
        ("cursor", "Cursor Composer via CLI or HTTP"),
        ("claude", "Claude API · requires ANTHROPIC_API_KEY"),
        ("claude-cli", "Claude Code CLI · requires npm install @anthropic-ai/claude-code"),
    ]

    options = []
    for name, desc in backends:
        options.append({
            "name": name,
            "description": desc,
            "active": name == current_backend,
        })

    return ("Select backend", "Switch the AI backend for this session.", options)


def get_agent_options(current_agent: str, available_agents: list[str] | None = None) -> tuple[str, str, list[dict]]:
    """Options for /agent panel."""
    # Agent descriptions (from AGENT_ROLES or hardcoded)
    _descriptions = {
        "auto-pilot": "Full SDLC orchestration · delegates to all agents",
        "code-reasoning": "Code analysis, exploration, architecture tracing",
        "code-writer": "Generate and modify code, implement features",
        "code-reviewer": "Code review for bugs, security, style",
        "code-tester": "Write tests, debug failures, test infrastructure",
        "test-coverage": "Coverage analysis, autonomous boost to target %",
        "qa-regression": "Full regression suites, baseline comparison",
        "git-ops": "Git workflows · branch, merge, push, conflict resolution",
        "jenkins-cicd": "Build, deploy, and ArgoCD verification",
        "argocd-verify": "Advanced ArgoCD · rollback, canary, incidents",
        "jira-ops": "Jira tickets, Confluence, sprint management",
        "redash-query": "SQL queries via Redash, database exploration",
        "security": "OWASP scanning, CVE audit, secrets detection",
    }

    if not available_agents:
        available_agents = sorted(_descriptions.keys())

    options = []
    for name in available_agents:
        desc = _descriptions.get(name, "")
        options.append({
            "name": name,
            "description": desc,
            "active": name == current_agent,
        })

    return ("Switch agent", "Choose a specialist agent for your task.", options)


def get_theme_options(current_theme: str = "") -> tuple[str, str, list[dict]]:
    """Options for /theme panel."""
    if not current_theme:
        current_theme = os.getenv("CODE_AGENTS_THEME", "dark")

    themes = [
        ("dark", "Full color dark theme"),
        ("light", "Full color light theme"),
        ("dark-colorblind", "Accessible dark theme · deuteranopia-safe"),
        ("light-colorblind", "Accessible light theme · deuteranopia-safe"),
        ("dark-ansi", "Dark theme · 16 ANSI colors only"),
        ("light-ansi", "Light theme · 16 ANSI colors only"),
    ]

    options = []
    for name, desc in themes:
        options.append({
            "name": name,
            "description": desc,
            "active": name == current_theme,
        })

    return ("Select theme", "Change color scheme for the chat interface.", options)


def get_confirm_options() -> tuple[str, str, list[dict]]:
    """Options for requirement confirmation toggle."""
    return ("Requirement confirmation", "Spec-before-execution gate.", [
        {"name": "on", "description": "Agent produces spec before executing", "active": False},
        {"name": "off", "description": "Agent executes directly", "active": False},
    ])


def get_setup_options() -> tuple[str, str, list[dict]]:
    """Options for /setup panel — choose what to configure."""
    sections = [
        ("backend", "API keys and backend selection", _is_configured("CURSOR_API_KEY") or _is_configured("ANTHROPIC_API_KEY")),
        ("jenkins", "Jenkins server URL, credentials, build/deploy jobs", _is_configured("JENKINS_URL")),
        ("argocd", "ArgoCD server URL, credentials, app naming", _is_configured("ARGOCD_URL")),
        ("jira", "Jira/Confluence URL, email, API token", _is_configured("JIRA_URL")),
        ("slack", "Slack webhook URL and bot token", _is_configured("CODE_AGENTS_SLACK_WEBHOOK_URL")),
        ("kibana", "Kibana/Elasticsearch URL for log search", _is_configured("KIBANA_URL")),
        ("grafana", "Grafana metrics URL and credentials", _is_configured("GRAFANA_URL")),
        ("redash", "Redash URL and API key for SQL queries", _is_configured("REDASH_URL")),
        ("kubernetes", "K8s cluster context and namespace", _is_configured("K8S_CONTEXT")),
        ("all", "Run full setup wizard (all sections)", False),
    ]

    options = []
    for name, desc, configured in sections:
        status = " ✓ configured" if configured else ""
        options.append({
            "name": name,
            "description": f"{desc}{status}",
            "active": configured,
        })

    return ("Setup wizard", "Choose what to configure for this project.", options)


def get_commands_categories() -> tuple[str, str, list[dict]]:
    """Category-level options for /commands interactive browser."""
    categories = [
        ("Setup & Config", "init, setup, migrate, rules, export, plugin, completions"),
        ("Server", "start, restart, shutdown, status, doctor, config, logs"),
        ("Git Operations", "branches, diff, commit, changelog, pre-push, auto-review, pr-preview"),
        ("CI/CD & Testing", "test, review, pipeline, release, coverage-boost, gen-tests, qa-suite"),
        ("Code Analysis", "deadcode, flags, config-diff, security, audit, complexity, techdebt, apidoc, onboard"),
        ("Incident & On-Call", "incident, oncall-report, standup, morning, env-health, watchdog, sprint-velocity, sprint-report"),
        ("Information", "agents, curls, repos, sessions, version, version-bump, api-check, perf-baseline, help, readme"),
    ]
    options = []
    for name, desc in categories:
        options.append({"name": name, "description": desc, "active": False})
    return ("Commands", "Browse all CLI commands by category. Select to drill down.", options)


def get_commands_for_category(category: str) -> tuple[str, str, list[dict]]:
    """Return commands within a category for /commands drill-down."""

    _CATEGORY_COMMANDS = {
        "Setup & Config": [
            ("init", "Initialize code-agents in current repo", ["--profile", "--backend", "--server", "--jenkins", "--argocd", "--jira", "--kibana", "--grafana", "--redash", "--elastic", "--atlassian", "--testing", "--build", "--k8s", "--notifications", "--slack", "--extensions"]),
            ("setup", "Full interactive setup wizard (7 steps)", []),
            ("migrate", "Migrate legacy .env to centralized config", []),
            ("rules", "Manage persistent agent rules", ["list", "create", "edit", "delete"]),
            ("export", "Export for Claude Code or Cursor", ["--claude-code", "--cursor", "--all", "--output", "--install"]),
            ("plugin", "Manage IDE extensions", ["list", "build", "install", "test", "dev", "watch", "status", "open", "publish", "vscode", "intellij", "chrome", "all"]),
            ("completions", "Generate shell completion", ["--install", "--zsh", "--bash"]),
        ],
        "Server": [
            ("start", "Start the server", ["--fg", "--foreground"]),
            ("restart", "Restart server (shutdown + start)", []),
            ("shutdown", "Stop the running server", []),
            ("status", "Health check, version, agent count", []),
            ("doctor", "Diagnose environment, integrations, git, build", []),
            ("config", "Show config (secrets masked)", []),
            ("logs", "Tail the log file (live)", ["<N>"]),
        ],
        "Git Operations": [
            ("branches", "List all branches, highlight current", []),
            ("diff", "Diff between branches", ["<base>", "<head>"]),
            ("commit", "Smart commit — conventional message from staged diff", ["--auto", "--dry-run"]),
            ("changelog", "Generate changelog from conventional commits", ["--write", "--version"]),
            ("pre-push", "Pre-push checklist — tests, secrets, lint", ["install", "check"]),
            ("auto-review", "Automated code review — diff analysis + AI", ["<base>", "<head>"]),
            ("pr-preview", "Preview what a PR would look like", ["<base>"]),
        ],
        "CI/CD & Testing": [
            ("test", "Run tests (auto-detects pytest/maven/jest/go)", ["<branch>"]),
            ("review", "AI code review via code-reviewer agent", ["<base>", "<head>"]),
            ("pipeline", "6-step CI/CD pipeline", ["start", "status", "advance", "rollback"]),
            ("release", "End-to-end release automation", ["<version>", "--dry-run", "--skip-deploy", "--skip-jira", "--skip-tests"]),
            ("coverage-boost", "Auto-boost test coverage — scan, analyze, generate", ["--dry-run", "--target", "--commit"]),
            ("gen-tests", "AI test generation — auto-delegate, write & verify", ["<path>", "--verify", "--dry-run", "--max", "--all"]),
            ("watch", "Watch mode — auto-lint, auto-test, auto-fix on save", ["<path>", "--lint-only", "--test-only", "--no-fix", "--interval"]),
            ("qa-suite", "Generate QA regression test suite", ["--analyze", "--write", "--commit"]),
        ],
        "Code Analysis": [
            ("deadcode", "Find dead code — unused imports, functions, endpoints", ["--language", "--json"]),
            ("flags", "List feature flags in codebase", ["--stale", "--matrix", "--json"]),
            ("config-diff", "Compare configs across environments", ["<env_a>", "<env_b>", "--json"]),
            ("security", "OWASP security scan", ["--json", "--category"]),
            ("audit", "Audit dependencies for CVEs, licenses, outdated", ["--vuln", "--licenses", "--outdated", "--json"]),
            ("complexity", "Analyze code complexity (cyclomatic, nesting)", ["--language", "--json"]),
            ("techdebt", "Scan for tech debt (TODOs, deprecated, skipped)", ["--json"]),
            ("apidoc", "Generate API documentation from source code", ["--markdown", "--openapi", "--json"]),
            ("onboard", "Generate onboarding guide for new developers", ["--save", "--full"]),
        ],
        "Incident & On-Call": [
            ("incident", "Investigate a service incident (runbook + RCA)", ["<service>", "--rca", "--save"]),
            ("oncall-report", "Weekly on-call handoff report", ["--days", "--save", "--slack"]),
            ("standup", "AI standup from git activity", []),
            ("morning", "Morning autopilot — git pull, build, Jira, tests", []),
            ("env-health", "Dashboard: ArgoCD, Jenkins, Jira, Kibana, Grafana health", []),
            ("watchdog", "Post-deploy monitoring — error rate + latency", ["--minutes"]),
            ("sprint-velocity", "Track sprint velocity from Jira", ["--sprints", "--json"]),
            ("sprint-report", "Sprint summary from Jira + git + builds", ["--days", "--save", "--slack"]),
        ],
        "Information": [
            ("agents", "List all agents with backend/model/permissions", []),
            ("curls", "Copy-pasteable curl commands for all API endpoints", ["<cat>", "<agent>"]),
            ("repos", "Manage multi-repo support", ["add", "remove"]),
            ("sessions", "List/manage saved chat sessions", ["--all"]),
            ("version", "Show version info", []),
            ("version-bump", "Bump version", ["major", "minor", "patch"]),
            ("api-check", "Compare API endpoints for breaking changes", ["<base-ref>"]),
            ("perf-baseline", "Record or compare performance baseline", ["--compare", "--show", "--clear", "--iterations"]),
            ("help", "Full help with all commands and examples", []),
            ("readme", "Display README in terminal with rich formatting", []),
        ],
    }

    commands = _CATEGORY_COMMANDS.get(category, [])
    options = []
    for name, desc, _subs in commands:
        sub_hint = f"  [{', '.join(_subs[:4])}{'...' if len(_subs) > 4 else ''}]" if _subs else ""
        options.append({"name": name, "description": f"{desc}{sub_hint}", "active": False})

    return (category, "Select a command to run. Esc to go back.", options)


def get_subcommands_for_command(category: str, command: str) -> list[str]:
    """Return subcommand/flag list for a command, or empty list."""
    _, _, opts = get_commands_for_category(category)
    # Rebuild from category data
    _CATEGORY_COMMANDS = {}
    # Re-call to get the raw data
    cat_title, _, cat_opts = get_commands_for_category(category)
    # We need the sub list — let's just look it up directly
    _ALL_SUBS = {
        "init": ["--profile", "--backend", "--server", "--jenkins", "--argocd", "--jira", "--kibana", "--grafana", "--redash", "--elastic", "--atlassian", "--testing", "--build", "--k8s", "--notifications", "--slack", "--extensions"],
        "rules": ["list", "create", "edit", "delete"],
        "export": ["--claude-code", "--cursor", "--all", "--output", "--install"],
        "plugin": ["list", "build", "install", "test", "dev", "watch", "status", "open", "publish", "vscode", "intellij", "chrome", "all"],
        "completions": ["--install", "--zsh", "--bash"],
        "start": ["--fg", "--foreground"],
        "commit": ["--auto", "--dry-run"],
        "changelog": ["--write", "--version"],
        "pre-push": ["install", "check"],
        "pipeline": ["start", "status", "advance", "rollback"],
        "release": ["--dry-run", "--skip-deploy", "--skip-jira", "--skip-tests"],
        "coverage-boost": ["--dry-run", "--target", "--commit"],
        "gen-tests": ["--verify", "--dry-run", "--max", "--all"],
        "watch": ["--lint-only", "--test-only", "--no-fix", "--interval"],
        "qa-suite": ["--analyze", "--write", "--commit"],
        "deadcode": ["--language", "--json"],
        "flags": ["--stale", "--matrix", "--json"],
        "config-diff": ["--json"],
        "security": ["--json", "--category"],
        "audit": ["--vuln", "--licenses", "--outdated", "--json"],
        "complexity": ["--language", "--json"],
        "techdebt": ["--json"],
        "apidoc": ["--markdown", "--openapi", "--json"],
        "onboard": ["--save", "--full"],
        "incident": ["--rca", "--save"],
        "oncall-report": ["--days", "--save", "--slack"],
        "watchdog": ["--minutes"],
        "sprint-velocity": ["--sprints", "--json"],
        "sprint-report": ["--days", "--save", "--slack"],
        "repos": ["add", "remove"],
        "sessions": ["--all"],
        "version-bump": ["major", "minor", "patch"],
        "perf-baseline": ["--compare", "--show", "--clear", "--iterations"],
    }
    return _ALL_SUBS.get(command, [])


def _is_configured(env_var: str) -> bool:
    """Check if an env var is set and non-empty."""
    return bool(os.getenv(env_var, "").strip())
