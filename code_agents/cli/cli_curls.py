"""CLI curls command — API curl reference and agent-specific curl generation."""

from __future__ import annotations

import logging

from .cli_helpers import (
    _colors, _server_url, _load_env,
)

logger = logging.getLogger("code_agents.cli.cli_curls")


def cmd_curls(args: list[str] | None = None):
    """Show curl commands. Optionally filter by category or agent name."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    url = _server_url()
    args = args or []
    filter_key = args[0].lower() if args else None

    # Available categories
    categories = [
        "health", "agents", "git", "testing", "jenkins",
        "argocd", "pipeline", "redash", "elasticsearch",
    ]

    # If filter is an agent name, show curls for that agent
    if filter_key and filter_key not in categories:
        _curls_for_agent(filter_key, url)
        return

    # Show category index if no filter
    if not filter_key:
        print()
        print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
        print(bold(cyan("  ║     Code Agents — API Curl Reference         ║")))
        print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
        print()
        print(bold("  Filter by category:"))
        print(f"    code-agents curls {cyan('health')}         {dim('# health & diagnostics')}")
        print(f"    code-agents curls {cyan('agents')}         {dim('# agent listing & prompts')}")
        print(f"    code-agents curls {cyan('git')}            {dim('# git operations')}")
        print(f"    code-agents curls {cyan('testing')}        {dim('# test execution & coverage')}")
        print(f"    code-agents curls {cyan('jenkins')}        {dim('# Jenkins CI/CD')}")
        print(f"    code-agents curls {cyan('argocd')}         {dim('# ArgoCD deployment')}")
        print(f"    code-agents curls {cyan('pipeline')}       {dim('# CI/CD pipeline')}")
        print(f"    code-agents curls {cyan('redash')}         {dim('# database queries')}")
        print(f"    code-agents curls {cyan('elasticsearch')}  {dim('# search')}")
        print()
        print(bold("  Filter by agent name:"))
        print(f"    code-agents curls {cyan('code-reviewer')}  {dim('# curls for code-reviewer agent')}")
        print(f"    code-agents curls {cyan('git-ops')}        {dim('# curls for git-ops agent')}")
        print(f"    code-agents curls {cyan('<agent-name>')}   {dim('# curls for any agent')}")
        print()

        # List all agents
        try:
            from code_agents.core.config import agent_loader
            agent_loader.load()
            agents = agent_loader.list_agents()
            print(bold("  Available agents:"))
            for a in agents:
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
        except Exception:
            pass
        print()
        return

    # Filtered output -- show only the requested category
    _print_curl_sections(url, filter_key)


def _print_curl_sections(url: str, filt: str | None):
    """Print curl sections, optionally filtered to one category."""
    bold, green, yellow, red, cyan, dim = _colors()

    def section(name: str, key: str):
        """Return True if this section should be printed."""
        return filt is None or filt == key

    if section("Health & Diagnostics", "health"):
        print()
        print(bold("  Health & Diagnostics"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Health check')}")
        print(f"  curl -s {url}/health | python3 -m json.tool")
        print()
        print(f"  {dim('# Full diagnostics (no secrets)')}")
        print(f"  curl -s {url}/diagnostics | python3 -m json.tool")

    if section("Agents", "agents"):
        print()
        print(bold("  Agents"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List all agents')}")
        print(f"  curl -s {url}/v1/agents | python3 -m json.tool")
        print()
        print(f"  {dim('# List models (OpenAI-compatible)')}")
        print(f"  curl -s {url}/v1/models | python3 -m json.tool")
        print()
        print(f"  {dim('# Send a prompt (non-streaming)')}")
        print(f"  curl -s -X POST {url}/v1/agents/code-reasoning/chat/completions \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"Explain this project\"}}]}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Send a prompt (streaming)')}")
        print(f"  curl -N -X POST {url}/v1/agents/code-reasoning/chat/completions \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"What files are here?\"}}], \"stream\": true}}'")
        print()
        print(dim("  Tip: code-agents curls <agent-name>  for agent-specific curls"))

    if section("Git Operations", "git"):
        print()
        print(bold("  Git Operations"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List branches')}")
        print(f"  curl -s {url}/git/branches | python3 -m json.tool")
        print()
        print(f"  {dim('# Current branch')}")
        print(f"  curl -s {url}/git/current-branch | python3 -m json.tool")
        print()
        print(f"  {dim('# Diff between branches')}")
        print(f"  curl -s '{url}/git/diff?base=main&head=HEAD' | python3 -m json.tool")
        print()
        print(f"  {dim('# Commit log')}")
        print(f"  curl -s '{url}/git/log?branch=main&limit=10' | python3 -m json.tool")
        print()
        print(f"  {dim('# Working tree status')}")
        print(f"  curl -s {url}/git/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Push a branch')}")
        print(f"  curl -s -X POST {url}/git/push \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\", \"remote\": \"origin\"}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Fetch from remote')}")
        print(f"  curl -s -X POST '{url}/git/fetch?remote=origin' | python3 -m json.tool")

    if section("Testing & Coverage", "testing"):
        print()
        print(bold("  Testing & Coverage"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Run tests')}")
        print(f"  curl -s -X POST {url}/testing/run \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Run tests on a specific branch')}")
        print(f"  curl -s -X POST {url}/testing/run \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Get coverage report')}")
        print(f"  curl -s {url}/testing/coverage | python3 -m json.tool")
        print()
        print(f"  {dim('# Coverage gaps (new code without tests)')}")
        print(f"  curl -s '{url}/testing/gaps?base=main&head=HEAD' | python3 -m json.tool")

    if section("Jenkins CI/CD", "jenkins"):
        print()
        print(bold("  Jenkins CI/CD"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Trigger a build')}")
        print(f"  curl -s -X POST {url}/jenkins/build \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"job_name\": \"my-project\", \"branch\": \"feature-123\"}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Check build status')}")
        print(f"  curl -s {url}/jenkins/build/my-project/42/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Get build console log')}")
        print(f"  curl -s {url}/jenkins/build/my-project/42/log | python3 -m json.tool")
        print()
        print(f"  {dim('# Wait for build to finish')}")
        print(f"  curl -s -X POST {url}/jenkins/build/my-project/42/wait | python3 -m json.tool")
        print()
        print(f"  {dim('# Last build info')}")
        print(f"  curl -s {url}/jenkins/build/my-project/last | python3 -m json.tool")

    if section("ArgoCD", "argocd"):
        print()
        print(bold("  ArgoCD"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# App sync & health status')}")
        print(f"  curl -s {url}/argocd/apps/my-app/status | python3 -m json.tool")
        print()
        print(f"  {dim('# List pods with image tags')}")
        print(f"  curl -s {url}/argocd/apps/my-app/pods | python3 -m json.tool")
        print()
        print(f"  {dim('# Get pod logs (scan for errors)')}")
        print(f"  curl -s '{url}/argocd/apps/my-app/pods/my-pod-abc/logs?namespace=default&tail=200' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Trigger sync')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/sync \\")
        print(f"    -H 'Content-Type: application/json' -d '{{}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Rollback to previous revision')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/rollback \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"revision\": \"previous\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Deployment history')}")
        print(f"  curl -s {url}/argocd/apps/my-app/history | python3 -m json.tool")
        print()
        print(f"  {dim('# Wait for sync to complete')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/wait-sync | python3 -m json.tool")

    if section("CI/CD Pipeline", "pipeline"):
        print()
        print(bold("  CI/CD Pipeline"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Start a pipeline run')}")
        print(f"  curl -s -X POST {url}/pipeline/start \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Check pipeline status')}")
        print(f"  curl -s {url}/pipeline/RUN_ID/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Advance to next step')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/advance \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"details\": {{\"build_number\": 42}}}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Mark step as failed')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/fail \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"error\": \"Build failed\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Trigger rollback')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/rollback | python3 -m json.tool")
        print()
        print(f"  {dim('# List all pipeline runs')}")
        print(f"  curl -s {url}/pipeline/runs | python3 -m json.tool")

    if section("Redash", "redash"):
        print()
        print(bold("  Redash (Database Queries)"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List data sources')}")
        print(f"  curl -s {url}/redash/data-sources | python3 -m json.tool")
        print()
        print(f"  {dim('# Get table schema')}")
        print(f"  curl -s {url}/redash/data-sources/1/schema | python3 -m json.tool")
        print()
        print(f"  {dim('# Run a SQL query')}")
        print(f"  curl -s -X POST {url}/redash/run-query \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"data_source_id\": 1, \"query\": \"SELECT * FROM users LIMIT 10\"}}' \\")
        print(f"    | python3 -m json.tool")

    if section("Elasticsearch", "elasticsearch"):
        print()
        print(bold("  Elasticsearch"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Cluster info')}")
        print(f"  curl -s {url}/elasticsearch/info | python3 -m json.tool")
        print()
        print(f"  {dim('# Search')}")
        print(f"  curl -s -X POST {url}/elasticsearch/search \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"index\": \"*\", \"body\": {{\"query\": {{\"match_all\": {{}}}}, \"size\": 10}}}}' \\")
        print(f"    | python3 -m json.tool")

    print()
    if filt:
        print(dim(f"  Showing: {filt} | Run 'code-agents curls' for all categories"))
    else:
        print(dim(f"  Replace 'my-app', 'my-project', 'RUN_ID', etc. with your actual values."))
        print(dim(f"  Server URL: {url} (from HOST/PORT in .env)"))
    print()


def _curls_for_agent(agent_name: str, url: str):
    """Show curl commands specific to one agent."""
    bold, green, yellow, red, cyan, dim = _colors()

    # Verify agent exists
    agent_info = None
    try:
        from code_agents.core.config import agent_loader
        agent_loader.load()
        agent_info = agent_loader.get(agent_name)
    except Exception:
        pass

    if not agent_info:
        print()
        print(red(f"  Agent '{agent_name}' not found."))
        print()
        print(bold("  Available agents:"))
        try:
            for a in agent_loader.list_agents():
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
        except Exception:
            pass
        print()
        return

    name = agent_info.name
    display = agent_info.display_name or name
    endpoint = f"{url}/v1/agents/{name}/chat/completions"

    print()
    print(bold(f"  Curls for: {cyan(display)} ({name})"))
    print(bold("  " + "─" * 44))
    print()
    print(f"  {dim('Endpoint:')} {endpoint}")
    print(f"  {dim('Backend:')}  {agent_info.backend}  {dim('Model:')} {agent_info.model}  {dim('Permission:')} {agent_info.permission_mode}")
    print()

    # Non-streaming prompt
    print(f"  {dim('# Send a prompt (non-streaming)')}")
    print(f"  curl -s -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"YOUR PROMPT HERE\"}}]}}' \\")
    print(f"    | python3 -m json.tool")
    print()

    # Streaming prompt
    print(f"  {dim('# Send a prompt (streaming)')}")
    print(f"  curl -N -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"YOUR PROMPT HERE\"}}], \"stream\": true}}'")
    print()

    # With session (multi-turn)
    print(f"  {dim('# Resume a session (multi-turn)')}")
    print(f"  curl -s -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"Follow up question\"}}], \"session_id\": \"SESSION_ID\"}}' \\")
    print(f"    | python3 -m json.tool")
    print()

    # Agent-specific example prompts
    _AGENT_EXAMPLES: dict[str, list[tuple[str, str]]] = {
        "code-reasoning": [
            ("Explain the architecture", "Explain the architecture of this project"),
            ("Trace a data flow", "Trace how a user request flows through the API"),
        ],
        "code-writer": [
            ("Write a function", "Write a function that validates email addresses"),
            ("Refactor code", "Refactor the authentication module to use JWT"),
        ],
        "code-reviewer": [
            ("Review for bugs", "Review this code for bugs and security issues"),
            ("Review a PR", "Review the changes in the latest commit for quality"),
        ],
        "code-tester": [
            ("Write tests", "Write unit tests for the user authentication module"),
            ("Debug a failure", "Debug why the payment processing test is failing"),
        ],
        "redash-query": [
            ("Explore schema", "Show me the tables in the acquiring database"),
            ("Write SQL", "Write a query to find all failed transactions today"),
        ],
        "git-ops": [
            ("Show recent changes", "Show the last 5 commits on the current branch"),
            ("Compare branches", "What changed between main and this branch?"),
        ],
        "test-coverage": [
            ("Run tests", "Run the test suite and show coverage"),
            ("Find gaps", "What new code is missing test coverage?"),
        ],
        "jenkins-cicd": [
            ("Build", "Build pg-acquiring-biz on release branch with java 21"),
            ("Deploy", "Deploy version 1.2.3 to dev"),
            ("Build & Deploy", "Build and deploy pg-acquiring-biz to dev"),
        ],
        "argocd-verify": [
            ("Check pods", "Are all pods healthy after the latest deployment?"),
            ("Scan logs", "Check pod logs for any errors or exceptions"),
        ],
        "pipeline-orchestrator": [
            ("Start pipeline", "Start the deployment pipeline for branch feature-123"),
            ("Pipeline status", "What step is the current pipeline on?"),
        ],
        "agent-router": [
            ("Route request", "I need to review code changes in a PR"),
            ("Pick agent", "Which agent should I use to run database queries?"),
        ],
        "security": [
            ("Security audit", "Run a full security audit on this repo"),
            ("Scan for secrets", "Scan for hardcoded API keys and credentials"),
            ("Check CVEs", "Check dependencies for known vulnerabilities"),
        ],
        "github-actions": [
            ("List workflows", "List all GitHub Actions workflows and their status"),
            ("Trigger workflow", "Trigger the CI workflow on the main branch"),
            ("Debug failure", "Why did the last workflow run fail?"),
        ],
        "grafana-ops": [
            ("Firing alerts", "Show me all currently firing alerts"),
            ("Query metrics", "Query latency metrics for the payment service"),
            ("Correlate deploy", "Did the last deploy affect error rates?"),
        ],
        "terraform-ops": [
            ("Plan changes", "Plan the infrastructure changes in infra/production"),
            ("Detect drift", "Is there any drift in our infrastructure?"),
            ("Show state", "Show all resources in the terraform state"),
        ],
        "db-ops": [
            ("List tables", "Show me all tables in the public schema"),
            ("Explain query", "Explain the execution plan for this query"),
            ("Generate migration", "Generate a migration to add an email index to users"),
        ],
        "pr-review": [
            ("Review PR", "Review PR #123 for security and quality issues"),
            ("List open PRs", "List all open pull requests"),
            ("Auto-review", "Run auto-review on PR #456"),
        ],
    }

    examples = _AGENT_EXAMPLES.get(name, [])
    if examples:
        print(f"  {bold('Example prompts for this agent:')}")
        print()
        for label, prompt_text in examples:
            print(f"  {dim(f'# {label}')}")
            print(f"  curl -s -X POST {endpoint} \\")
            print(f"    -H 'Content-Type: application/json' \\")
            print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"{prompt_text}\"}}]}}' \\")
            print(f"    | python3 -m json.tool")
            print()

    print(dim(f"  Run 'code-agents curls' for all API categories"))
    print()
