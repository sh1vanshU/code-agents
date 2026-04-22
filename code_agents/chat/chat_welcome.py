"""Welcome messages and agent selection for the chat REPL.

Contains AGENT_ROLES, AGENT_WELCOME data, welcome printing, and
interactive agent selection menu.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_welcome")

from .chat_ui import (
    bold, green, red, cyan, dim,
    _print_welcome as _print_welcome_raw,
    agent_color,
)


# ---------------------------------------------------------------------------
# Agent role descriptions (extracted from YAML system prompts)
# ---------------------------------------------------------------------------

AGENT_ROLES = {
    "code-reasoning": "Analyze code, explain architecture, trace flows (read-only)",
    "code-writer": "Generate and modify code, refactor, implement features",
    "code-reviewer": "Review code for bugs, security issues, style violations",
    "code-tester": "Write tests, debug issues, optimize code quality",
    "redash-query": "Write SQL, query databases, explore schemas via Redash",
    "git-ops": "Git operations: branches, diffs, logs, push",
    "test-coverage": "Run test suites, generate coverage reports, find gaps",
    "jenkins-cicd": "Build and deploy via Jenkins — end-to-end CI/CD",
    "argocd-verify": "Verify ArgoCD deployments, scan pod logs, rollback",
    "qa-regression": "Run regression suites, write missing tests, eliminate manual QA",
    "auto-pilot": "Autonomous orchestrator — delegates to sub-agents, runs full workflows",
    "jira-ops": "Read Jira tickets, Confluence pages, update ticket status",
    "security": "Security audit: OWASP scan, CVE check, secrets detection, compliance review",
    "grafana-ops": "Grafana Ops: query metrics, investigate alerts, correlate deploys",
    "terraform-ops": "Terraform/IaC: plan, review, apply infrastructure changes with safety gates",
    "github-actions": "GitHub Actions: trigger, monitor, retry, and debug workflows",
    "db-ops": "Postgres/DB: safe queries, explain plans, migrations, schema inspection",
    "pr-review": "PR Review Bot: auto-review PRs, post inline comments, enforce quality",
    "debug-agent": "Autonomous debugging: reproduce, trace, root-cause, fix, verify",
}

AGENT_WELCOME = {
    "code-reasoning": (
        "Code Reasoning — Read-Only Analysis · Vicharak (विचारक)",
        [
            "Explain architecture and design patterns",
            "Trace data flows through the codebase",
            "Compare approaches and analyze complexity",
            "Answer 'how does this work?' questions",
        ],
        [
            "Explain the authentication flow in this project",
            "How does the payment processing pipeline work?",
            "What design patterns are used in the routers?",
        ],
    ),
    "code-writer": (
        "Code Writer — Generate & Modify Code · Rachnakar (रचनाकार)",
        [
            "Write new files, modules, and functions",
            "Refactor existing code for clarity",
            "Implement features from requirements",
            "Apply fixes and improvements",
        ],
        [
            "Add input validation to the login function",
            "Refactor the UserService to use dependency injection",
            "Create a retry mechanism for failed API calls",
        ],
    ),
    "code-reviewer": (
        "Code Reviewer — Critical Review · Parikshak (परीक्षक)",
        [
            "Identify bugs and security vulnerabilities",
            "Suggest performance improvements",
            "Flag style violations and anti-patterns",
            "Review test quality and coverage gaps",
        ],
        [
            "Review the auth module for security issues",
            "Check the new payment endpoint for bugs",
            "Review the last 3 commits for quality",
        ],
    ),
    "code-tester": (
        "Code Tester — Testing & Debugging · Nirikshak (निरीक्षक)",
        [
            "Write unit tests, integration tests, and fixtures",
            "Debug failing tests and trace issues",
            "Optimize code quality and readability",
            "Refactor test suites for better coverage",
        ],
        [
            "Write unit tests for the PaymentService class",
            "Debug why test_auth_flow is failing",
            "Add edge case tests for the retry logic",
        ],
    ),
    "redash-query": (
        "Redash Query — SQL & Database · Anveshak (अन्वेषक)",
        [
            "List available data sources and schemas",
            "Write SQL queries from natural language",
            "Execute queries and format results",
            "Explore table structures and relationships",
        ],
        [
            "Show me all data sources available",
            "Write a query for the top 10 users by order count",
            "What tables are in the acqcore0 database?",
        ],
    ),
    "git-ops": (
        "Git Operations — Branches & Releases · Sanrakshak (संरक्षक)",
        [
            "List branches and show current branch",
            "Show diffs between branches",
            "View commit history and logs",
            "Check working tree status",
        ],
        [
            "Show the last 10 commits",
            "What changed between main and this branch?",
            "List all branches with their last commit date",
        ],
    ),
    "test-coverage": (
        "Test Coverage — Tests & Gaps · Sampurna (सम्पूर्ण)",
        [
            "Run test suites (auto-detects pytest/jest/maven/go)",
            "Generate coverage reports",
            "Identify new code lacking test coverage",
            "Report coverage percentages by file",
        ],
        [
            "Run tests and show coverage report",
            "Which files have less than 80% coverage?",
            "Show uncovered lines in the auth module",
        ],
    ),
    "jenkins-cicd": (
        "Jenkins CI/CD — Build & Deploy · Nirmata (निर्माता)",
        [
            "Git pre-check: detect branch, status, uncommitted changes",
            "Build a service (trigger, poll, extract version)",
            "Deploy using the build version — all in one session",
            "Full git → build → deploy → verify workflow",
        ],
        [
            "Build {repo}",
            "Build and deploy {repo}",
            "Deploy the latest build — which environments are available?",
            "What's the status of the last build?",
        ],
    ),
    "argocd-verify": (
        "ArgoCD Verify — Deploy Verification · Pramanik (प्रामाणिक)",
        [
            "Check application sync and health status",
            "List pods and verify image tags",
            "Scan pod logs for errors (ERROR, FATAL, panic)",
            "Trigger rollback to previous revision",
        ],
        [
            "Are all pods healthy after the latest deploy?",
            "Check pod logs for any errors",
            "Rollback to the previous deployment",
        ],
    ),
    "qa-regression": (
        "QA Regression — Automated Testing · Gunvatta (गुणवत्ता)",
        [
            "Run full regression test suite and report results",
            "Write missing tests by analyzing the codebase",
            "Mock external dependencies (APIs, DBs, queues)",
            "Identify untested code paths and coverage gaps",
            "Create test plans for critical flows",
        ],
        [
            "Run the full regression suite and report what's failing",
            "Write tests for all untested code in src/services/",
            "What's the current test coverage? Where are the gaps?",
            "Create integration tests for the payment API endpoints",
        ],
    ),
    "auto-pilot": (
        "Auto-Pilot — Full Autonomy · Sarathi (सारथी)",
        [
            "Execute multi-step workflows end-to-end autonomously",
            "Delegate to 13 specialist agents (code-writer, reviewer, tester, etc.)",
            "Build → Deploy → Verify pipelines without manual switching",
            "Run code reviews, apply fixes, and re-verify automatically",
            "Query databases, check git status, run tests — all in one flow",
        ],
        [
            "Build and deploy {repo} to dev",
            "Review the latest changes, fix issues, and run tests",
            "Run the full CI/CD pipeline for release branch",
            "Check what changed since last deploy, review, and build",
        ],
    ),
    "jira-ops": (
        "Jira & Confluence — Tickets & Wiki · Yojak (योजक)",
        [
            "Read Jira tickets with acceptance criteria and subtasks",
            "Search issues with JQL queries across projects",
            "Transition tickets and add implementation comments",
            "Fetch Confluence pages and extract requirements",
            "Create new issues and subtasks",
        ],
        [
            "Read ticket TEAM-1234 and summarize the acceptance criteria",
            "Search for all open bugs in project TEAM",
            "Move TEAM-1234 to In Progress and add a comment",
            "Find the HLD page in the TEAM Confluence space",
        ],
    ),
    "security": (
        "Security Agent — Cybersecurity Audit · Surakshak (सुरक्षक)",
        [
            "OWASP Top 10 static analysis (injection, XSS, SSRF, broken auth)",
            "Dependency audit: CVEs, outdated packages, license compliance",
            "Secrets detection: hardcoded API keys, tokens, credentials",
            "Attack surface mapping: endpoints, auth, input validation",
            "Compliance review: encryption, data handling, infrastructure",
            "Full security posture report with prioritized remediation",
        ],
        [
            "Run a full security audit on this repo",
            "Scan for hardcoded secrets and API keys",
            "Check dependencies for known CVEs",
            "Map the attack surface — which endpoints are public?",
        ],
    ),
    "github-actions": (
        "GitHub Actions — CI/CD Workflows · Prakriya (प्रक्रिया)",
        [
            "List all workflows and their recent run status",
            "Trigger workflow_dispatch events with custom inputs",
            "Monitor running workflows — poll status and show progress",
            "Debug failed runs — fetch jobs, logs, identify root cause",
            "Retry failed runs and cancel in-progress runs",
        ],
        [
            "List all GitHub Actions workflows",
            "Trigger the CI workflow on main",
            "What's the status of the last workflow run?",
            "Debug why the latest CI run failed",
        ],
    ),
    "db-ops": (
        "Postgres/DB Agent — Safe Queries & Migrations · Sangraha (संग्रह)",
        [
            "Execute safe SQL queries with automatic LIMIT and EXPLAIN",
            "Inspect table schemas, indexes, constraints, and sizes",
            "Generate UP/DOWN migration scripts from natural language",
            "Analyze query execution plans and suggest optimizations",
            "Compare schemas and detect drift between environments",
        ],
        [
            "List all tables in the users database",
            "Show the schema and indexes for the payments table",
            "Explain this query: SELECT * FROM orders JOIN users ON ...",
            "Generate a migration to add an email index on the users table",
        ],
    ),
    "pr-review": (
        "PR Review Bot — Auto-Review & Inline Comments · Samikhyak (समीक्षक)",
        [
            "Auto-review PRs: fetch diff, analyze, post findings",
            "Post inline review comments on specific files/lines",
            "Enforce code quality: security, correctness, performance, style",
            "Generate review checklists based on changed file types",
            "Handle PR webhooks for auto-review on open/update",
        ],
        [
            "Review PR #123",
            "List open pull requests",
            "Post inline comments on the auth changes in PR #45",
            "Show the review checklist for this project",
        ],
    ),
    "grafana-ops": (
        "Grafana Ops — Metrics & Alerts · Prahri (प्रहरी)",
        [
            "Search and browse Grafana dashboards",
            "Query panel metrics with flexible time ranges",
            "Investigate firing alerts and find root cause",
            "Correlate deployments with metric changes (before/after)",
            "Create deploy annotations for tracking",
        ],
        [
            "Show me all firing alerts",
            "Query latency metrics for the payment service — last 6 hours",
            "Did the last deploy affect error rates?",
            "Search dashboards for 'acquiring'",
        ],
    ),
    "terraform-ops": (
        "Terraform/IaC — Infrastructure as Code · Adharshila (आधारशिला)",
        [
            "Run terraform plan with safety review",
            "Apply infrastructure changes with approval gates",
            "Detect infrastructure drift from configuration",
            "Inspect state, outputs, and provider versions",
            "Review plans for security, cost, and blast radius",
        ],
        [
            "Plan the changes in infra/production",
            "Is there any drift in our infrastructure?",
            "Show me all resources in the terraform state",
            "Review and apply the pending infrastructure changes",
        ],
    ),
    "debug-agent": (
        "Debug Agent — Autonomous Debugging · Khojak (खोजक)",
        [
            "Reproduce bugs by running failing tests/commands",
            "Trace errors through code to find root cause",
            "Analyze blast radius of proposed fixes",
            "Auto-fix bugs and verify with tests",
            "Parse Python, JS, Java, Go error outputs",
        ],
        [
            "Debug tests/test_auth.py::test_login",
            "Fix the AttributeError in the payment module",
            "Why is test_checkout failing with a 500 error?",
            "Debug and fix the off-by-one error in merge_sorted",
        ],
    ),
}


def _print_welcome(agent_name: str, repo_path: str = "") -> None:
    """Print welcome for an agent, substituting {repo} with actual repo name."""
    repo_name = os.path.basename(repo_path) if repo_path else "my-project"

    # Deep copy welcome data and substitute {repo} placeholder
    welcome_data = {}
    for k, (title, caps, examples) in AGENT_WELCOME.items():
        welcome_data[k] = (
            title,
            caps,
            [ex.replace("{repo}", repo_name) for ex in examples],
        )
    _print_welcome_raw(agent_name, welcome_data)

    # Show a Gita shloka for inspiration (only if agent has welcome)
    if agent_name in welcome_data:
        try:
            from code_agents.domain.gita_shlokas import format_shloka_rainbow
            print(f"  {format_shloka_rainbow()}")
            print()
        except Exception:
            pass


def _select_agent(agents: dict[str, str]) -> Optional[str]:
    """Interactive agent selection with arrow keys. Returns agent name or None to cancel."""
    import sys

    sorted_agents = sorted(agents.items())
    # Append Cancel as last option
    total = len(sorted_agents)
    selected = 0
    rendered_lines = [0]

    def _render():
        # Clear previous render
        for _ in range(rendered_lines[0]):
            sys.stdout.write("\033[A\033[2K")
        if rendered_lines[0] > 0:
            sys.stdout.write("\r")
        sys.stdout.flush()
        count = 0
        for i, (name, _display) in enumerate(sorted_agents):
            role = AGENT_ROLES.get(name, _display)
            num = f"{i + 1:>2}."
            if i == selected:
                print(f"    {bold(green(f'{num} ❯ {name:<24}'))} {role}")
            else:
                print(f"    {dim(f'{num}   {name:<24}')} {dim(role)}")
            count += 1
        # Cancel option
        if selected == total:
            print(f"    {bold(green(' 0. ❯ Cancel'))}")
        else:
            print(f"    {dim(' 0.   Cancel')}")
        count += 1
        print(f"    {dim('↑↓ navigate · Enter select · Esc cancel')}")
        count += 1
        rendered_lines[0] = count

    print()
    print(bold("  Select an agent:"))
    print()
    _render()

    try:
        import tty, termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            while True:
                ch = os.read(fd, 1)
                if not ch:
                    continue
                b = ch[0]

                # Ctrl+C → cancel
                if b == 0x03:
                    termios.tcsetattr(fd, termios.TCSANOW, old)
                    print()
                    return None

                # Escape byte — could be standalone Esc or start of arrow sequence
                if b == 0x1b:
                    import select
                    ready, _, _ = select.select([fd], [], [], 0.05)
                    if not ready:
                        # Standalone Esc — cancel
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        print()
                        return None
                    rest = os.read(fd, 7)
                    seq = ch + rest
                    seq_str = seq.decode("utf-8", errors="ignore")

                    # Arrow up / left
                    if seq_str in ("\x1b[A", "\x1bOA", "\x1b[D", "\x1bOD"):
                        selected = (selected - 1) % (total + 1)
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        _render()
                        tty.setraw(fd)
                    # Arrow down / right
                    elif seq_str in ("\x1b[B", "\x1bOB", "\x1b[C", "\x1bOC"):
                        selected = (selected + 1) % (total + 1)
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        _render()
                        tty.setraw(fd)
                    continue

                # Enter
                if b in (0x0d, 0x0a):
                    break
                # Number keys 0-9 — quick jump
                c = chr(b)
                if c.isdigit():
                    d = int(c)
                    if d == 0:
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        print()
                        return None
                    if 1 <= d <= total:
                        selected = d - 1
                        termios.tcsetattr(fd, termios.TCSANOW, old)
                        _render()
                        break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)

        print()
        if selected == total:
            return None
        return sorted_agents[selected][0]

    except (ImportError, OSError, ValueError) as _tty_err:
        logger.debug("_select_agent: raw tty failed (%s), using fallback", _tty_err)
        # Fallback: numbered input
        while True:
            try:
                choice = input(f"  {bold('Pick agent')} [1-{total}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if not choice:
                continue
            if choice == "0":
                return None
            try:
                idx = int(choice)
                if 1 <= idx <= total:
                    return sorted_agents[idx - 1][0]
            except ValueError:
                if choice in agents:
                    return choice
            print(red(f"    Enter a number 1-{total}, or an agent name."))
