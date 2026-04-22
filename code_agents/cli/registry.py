"""CLI command registry — single source of truth for all CLI commands."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Union

logger = logging.getLogger("code_agents.cli.registry")

from .cli_analysis import (
    cmd_api_check,
    cmd_apidoc,
    cmd_audit,
    cmd_complexity,
    cmd_config_diff,
    cmd_deadcode,
    cmd_flags,
    cmd_security,
    cmd_techdebt,
)
from .cli_cicd import (
    cmd_coverage,
    cmd_coverage_boost,
    cmd_gen_tests,
    cmd_pipeline,
    cmd_qa_suite,
    cmd_release,
    cmd_test,
    cmd_watch,
)
from .cli_completions import cmd_completions, cmd_help
from .cli_git import (
    cmd_auto_review,
    cmd_branches,
    cmd_commit,
    cmd_diff,
    cmd_pr_preview,
)
from .cli_review import cmd_review
from .cli_reports import (
    cmd_env_health,
    cmd_incident,
    cmd_morning,
    cmd_oncall_report,
    cmd_perf_baseline,
    cmd_sprint_report,
    cmd_sprint_velocity,
    cmd_standup,
)
from .cli_server import (
    cmd_agents,
    cmd_config,
    cmd_doctor,
    cmd_logs,
    cmd_restart,
    cmd_shutdown,
    cmd_start,
    cmd_status,
)
from .cli_cost import cmd_cost
from .cli_mindmap import cmd_mindmap
from .cli_undo import cmd_undo
from .cli_skill import cmd_skill
from .cli_voice import cmd_voice
from .cli_pair import cmd_pair
from .cli_index import cmd_index
from .cli_replay import cmd_replay
from .cli_dep_impact import cmd_dep_impact
from .cli_pci import cmd_pci_scan
from .cli_owasp import cmd_owasp_scan
from .cli_migrate_tracing import cmd_migrate_tracing
from .cli_txn_flow import cmd_txn_flow
from .cli_hooks import cmd_hook_run, cmd_install_hooks
from .cli_idempotency import cmd_idempotency
from .cli_state_machine import cmd_validate_states
from .cli_profiler import cmd_profiler
from .cli_schema import cmd_schema
from .cli_tail import cmd_tail
from .cli_api_docs import cmd_api_docs
from .cli_load_test import cmd_load_test
from .cli_tech_debt import cmd_tech_debt
from .cli_translate import cmd_translate
from .cli_acquirer import cmd_acquirer_health
from .cli_recon import cmd_recon
from .cli_settlement import cmd_settlement
from .cli_retry import cmd_retry_audit
from .cli_batch import cmd_batch
from .cli_spec import cmd_spec_validate
from .cli_bg import cmd_bg
from .cli_ci_heal import cmd_ci_heal
from .cli_smell import cmd_smell
from .cli_dead_code import cmd_dead_code_eliminate
from .cli_imports import cmd_imports
from .cli_adr import cmd_adr
from .cli_clones import cmd_clones
from .cli_naming import cmd_naming_audit
from .cli_ci_run import cmd_ci_run
from .cli_pr_respond import cmd_pr_respond
from .cli_screenshot import cmd_screenshot
from .cli_mutate import cmd_mutate_test
from .cli_encryption_audit import cmd_encryption_audit
from .cli_vuln_chain import cmd_vuln_chain
from .cli_input_audit import cmd_input_audit
from .cli_rate_limit_audit import cmd_rate_limit_audit
from .cli_privacy_scan import cmd_privacy_scan
from .cli_compliance import cmd_compliance_report
from .cli_type_adder import cmd_add_types
from .cli_comment_audit import cmd_comment_audit
from .cli_secret_rotation import cmd_secret_rotation
from .cli_acl_matrix import cmd_acl_matrix
from .cli_session_audit import cmd_session_audit
from .cli_archaeology import cmd_archaeology
from .cli_perf_proof import cmd_perf_proof
from .cli_contract_test import cmd_contract_test
from .cli_self_bench import cmd_self_bench
from .cli_audit import cmd_full_audit
from .cli_prop_test import cmd_prop_test
from .cli_test_style import cmd_test_style
from .cli_visual_test import cmd_visual_test
from .cli_browse import cmd_browse
from .cli_team_kb import cmd_team_kb
from .cli_onboard_new import cmd_onboard_tour
from .cli_features import (
    cmd_benchmark,
    cmd_bench_compare,
    cmd_bench_trend,
    cmd_debug,
    cmd_join,
    cmd_pipeline_exec,
    cmd_review_fix,
    cmd_share,
    cmd_workspace,
)
from .cli_lang_migrate import cmd_lang_migrate
from .cli_snippet import cmd_snippet
from .cli_env_diff import cmd_env_diff
from .cli_ownership import cmd_ownership
from .cli_velocity import cmd_velocity_predict
from .cli_preview import cmd_preview
from .cli_productivity import (
    cmd_db_migrate,
    cmd_dep_upgrade,
    cmd_explain,
    cmd_oncall_summary,
    cmd_postmortem,
    cmd_pr_describe,
    cmd_review_buddy,
    cmd_runbook,
    cmd_sprint_dashboard,
    cmd_test_impact,
)
from .cli_explain import cmd_explain_code
from .cli_code_nav import (
    cmd_usage_trace,
    cmd_codebase_nav,
    cmd_git_story,
    cmd_call_chain,
    cmd_code_examples,
    cmd_dep_graph_viz,
)
from .cli_debug_tools import (
    cmd_stack_decode,
    cmd_log_analyze,
    cmd_env_diff,
    cmd_leak_scan,
    cmd_deadlock_scan,
)
from .cli_test_tools import (
    cmd_edge_cases,
    cmd_mock_build,
    cmd_test_fix,
    cmd_integration_scaffold,
)
from .cli_api_tools import (
    cmd_endpoint_gen,
    cmd_api_sync,
    cmd_response_optimize,
    cmd_rest_to_grpc,
    cmd_api_changelog,
)
from .cli_db_tools import (
    cmd_query_optimize,
    cmd_schema_design,
    cmd_orm_review,
)
from .cli_postmortem_gen import cmd_postmortem_gen
from .cli_changelog import cmd_changelog_v2
from .cli_pr_split import cmd_pr_split
from .cli_license_audit import cmd_license_audit
from .cli_config_validator import cmd_validate_config
from .cli_release_notes import cmd_release_notes
from .cli_dashboard import cmd_dashboard
from .cli_slack import cmd_slack
from .cli_tools import (
    cmd_changelog,
    cmd_curls,
    cmd_migrate,
    cmd_onboard,
    cmd_pre_push,
    cmd_repos,
    cmd_rules,
    cmd_sessions,
    cmd_update,
    cmd_version,
    cmd_version_bump,
    cmd_watchdog,
)

SpecialHandler = Literal["special:chat", "special:setup"]
Handler = Union[Callable[..., Any], SpecialHandler]


@dataclass
class CommandEntry:
    help: str
    handler: Handler
    takes_args: bool = False
    aliases: list[str] = field(default_factory=list)


def _build_command_registry() -> dict[str, CommandEntry]:
    from .cli import cmd_init, cmd_plugin, cmd_readme

    return {
        "help": CommandEntry(
            help="Show help",
            handler=cmd_help,
            takes_args=False,
            aliases=["--help", "-h"],
        ),
        "version": CommandEntry(
            help="Show version info",
            handler=cmd_version,
            takes_args=False,
            aliases=["--version", "-v"],
        ),
        "update": CommandEntry(
            help="Update code-agents to latest version",
            handler=cmd_update,
            takes_args=False,
        ),
        "init": CommandEntry(
            help="Initialize code-agents in current repo",
            handler=cmd_init,
            takes_args=False,
        ),
        "start": CommandEntry(
            help="Start the server",
            handler=cmd_start,
            takes_args=False,
        ),
        "restart": CommandEntry(
            help="Restart the server (shutdown + start)",
            handler=cmd_restart,
            takes_args=False,
        ),
        "chat": CommandEntry(
            help="Interactive chat with agents (--legacy for Python REPL)",
            handler="special:chat",
            takes_args=True,
        ),
        "repos": CommandEntry(
            help="List and manage registered repos",
            handler=cmd_repos,
            takes_args=True,
        ),
        "sessions": CommandEntry(
            help="List saved chat sessions",
            handler=cmd_sessions,
            takes_args=True,
        ),
        "shutdown": CommandEntry(
            help="Shutdown the server",
            handler=cmd_shutdown,
            takes_args=False,
        ),
        "status": CommandEntry(
            help="Check server health and config",
            handler=cmd_status,
            takes_args=False,
        ),
        "agents": CommandEntry(
            help="List all available agents",
            handler=cmd_agents,
            takes_args=False,
        ),
        "config": CommandEntry(
            help="Show current .env configuration",
            handler=cmd_config,
            takes_args=False,
        ),
        "doctor": CommandEntry(
            help="Diagnose common issues",
            handler=cmd_doctor,
            takes_args=False,
        ),
        "logs": CommandEntry(
            help="Tail the log file",
            handler=cmd_logs,
            takes_args=True,
        ),
        "diff": CommandEntry(
            help="Show git diff between branches",
            handler=cmd_diff,
            takes_args=True,
        ),
        "branches": CommandEntry(
            help="List git branches",
            handler=cmd_branches,
            takes_args=False,
        ),
        "test": CommandEntry(
            help="Run tests on the target repo",
            handler=cmd_test,
            takes_args=True,
        ),
        "coverage": CommandEntry(
            help="Lightweight coverage report (batch mode, memory-safe)",
            handler=cmd_coverage,
            takes_args=True,
        ),
        "review": CommandEntry(
            help="AI code review with inline terminal diff",
            handler=cmd_review,
            takes_args=True,
            aliases=["code-review"],
        ),
        "pipeline": CommandEntry(
            help="Manage CI/CD pipeline [start|status|advance|rollback]",
            handler=cmd_pipeline,
            takes_args=True,
        ),
        "curls": CommandEntry(
            help="Show all API curl commands",
            handler=cmd_curls,
            takes_args=True,
        ),
        "setup": CommandEntry(
            help="Full interactive setup wizard",
            handler="special:setup",
            takes_args=False,
        ),
        "migrate": CommandEntry(
            help="Migrate legacy .env to centralized config",
            handler=cmd_migrate,
            takes_args=False,
        ),
        "rules": CommandEntry(
            help="Manage rules [list|create|edit|delete]",
            handler=cmd_rules,
            takes_args=True,
        ),
        "incident": CommandEntry(
            help="Investigate a service incident (runbook + RCA)",
            handler=cmd_incident,
            takes_args=True,
        ),
        "release": CommandEntry(
            help="Automate release process end-to-end",
            handler=cmd_release,
            takes_args=True,
        ),
        "oncall-report": CommandEntry(
            help="Generate on-call handoff report",
            handler=cmd_oncall_report,
            takes_args=True,
        ),
        "commit": CommandEntry(
            help="Smart commit — conventional message from staged diff",
            handler=cmd_commit,
            takes_args=False,
        ),
        "standup": CommandEntry(
            help="Generate AI standup from git activity",
            handler=cmd_standup,
            takes_args=False,
        ),
        "deadcode": CommandEntry(
            help="Find dead code — unused imports, functions, endpoints",
            handler=cmd_deadcode,
            takes_args=True,
        ),
        "dead-code-eliminate": CommandEntry(
            help="Cross-file dead code detection + safe removal",
            handler=cmd_dead_code_eliminate,
            takes_args=True,
            aliases=["eliminate-dead", "dce"],
        ),
        "config-diff": CommandEntry(
            help="Compare configs across environments",
            handler=cmd_config_diff,
            takes_args=True,
        ),
        "flags": CommandEntry(
            help="List feature flags in codebase",
            handler=cmd_flags,
            takes_args=True,
        ),
        "onboard": CommandEntry(
            help="Generate onboarding guide for new developers",
            handler=cmd_onboard,
            takes_args=True,
        ),
        "coverage-boost": CommandEntry(
            help="Auto-boost test coverage — scan, analyze, generate tests",
            handler=cmd_coverage_boost,
            takes_args=True,
        ),
        "gen-tests": CommandEntry(
            help="AI test generation — auto-delegate to code-tester, write & verify",
            handler=cmd_gen_tests,
            takes_args=True,
            aliases=["generate-tests", "testgen"],
        ),
        "watch": CommandEntry(
            help="Watch mode — auto-lint, auto-test, auto-fix on file save",
            handler=cmd_watch,
            takes_args=True,
        ),
        "version-bump": CommandEntry(
            help="Bump version (major/minor/patch)",
            handler=cmd_version_bump,
            takes_args=True,
        ),
        "security": CommandEntry(
            help="OWASP security scan — find vulnerabilities in code",
            handler=cmd_security,
            takes_args=True,
        ),
        "sprint-velocity": CommandEntry(
            help="Track sprint velocity across sprints from Jira",
            handler=cmd_sprint_velocity,
            takes_args=True,
        ),
        "api-check": CommandEntry(
            help="Compare API endpoints with last release for breaking changes",
            handler=cmd_api_check,
            takes_args=True,
        ),
        "qa-suite": CommandEntry(
            help="Generate QA regression test suite for the repo",
            handler=cmd_qa_suite,
            takes_args=True,
        ),
        "pr-preview": CommandEntry(
            help="Preview what a PR would look like before creating it",
            handler=cmd_pr_preview,
            takes_args=True,
        ),
        "sprint-report": CommandEntry(
            help="Generate sprint summary from Jira + git + builds",
            handler=cmd_sprint_report,
            takes_args=True,
        ),
        "apidoc": CommandEntry(
            help="Generate API documentation from source code",
            handler=cmd_apidoc,
            takes_args=True,
        ),
        "api-docs": CommandEntry(
            help="Automated API docs — scan routes, generate OpenAPI/Markdown/HTML",
            handler=cmd_api_docs,
            takes_args=True,
        ),
        "perf-baseline": CommandEntry(
            help="Record or compare performance baseline",
            handler=cmd_perf_baseline,
            takes_args=True,
        ),
        "audit": CommandEntry(
            help="Audit dependencies for CVEs, licenses, outdated",
            handler=cmd_audit,
            takes_args=True,
        ),
        "completions": CommandEntry(
            help="Generate shell completion script",
            handler=cmd_completions,
            takes_args=True,
        ),
        "complexity": CommandEntry(
            help="Analyze code complexity (cyclomatic, nesting depth)",
            handler=cmd_complexity,
            takes_args=True,
        ),
        "techdebt": CommandEntry(
            help="Scan for tech debt (TODOs, deprecated, skipped tests)",
            handler=cmd_techdebt,
            takes_args=True,
        ),
        "tech-debt": CommandEntry(
            help="Deep tech debt scan — TODOs, complexity, test gaps, deps, dead code",
            handler=cmd_tech_debt,
            takes_args=True,
            aliases=["debt-scan", "debt"],
        ),
        "changelog": CommandEntry(
            help="Generate changelog from conventional commits",
            handler=cmd_changelog,
            takes_args=True,
        ),
        "changelog-gen": CommandEntry(
            help="Generate changelog with PR enrichment: changelog-gen <from>..<to>",
            handler=cmd_changelog_v2,
            takes_args=True,
        ),
        "env-health": CommandEntry(
            help="Check environment health (ArgoCD, Jenkins, Jira, Kibana)",
            handler=cmd_env_health,
            takes_args=True,
        ),
        "morning": CommandEntry(
            help="Morning autopilot — git pull, build, Jira, tests, alerts",
            handler=cmd_morning,
            takes_args=True,
        ),
        "pre-push": CommandEntry(
            help="Pre-push checklist [install|check]",
            handler=cmd_pre_push,
            takes_args=True,
            aliases=["pre-push-check"],
        ),
        "watchdog": CommandEntry(
            help="Post-deploy watchdog — monitor error rate after deploy",
            handler=cmd_watchdog,
            takes_args=True,
        ),
        "auto-review": CommandEntry(
            help="Automated code review — diff analysis + AI review",
            handler=cmd_auto_review,
            takes_args=True,
        ),
        "export": CommandEntry(
            help="Export agents/skills for Claude Code or Cursor [--claude-code|--cursor|--all]",
            handler="code_agents.cli.cli:cmd_export",
            takes_args=True,
            aliases=["export-skills", "export-plugin"],
        ),
        "plugin": CommandEntry(
            help="Manage IDE extensions [list|build|install|test|dev|publish]",
            handler=cmd_plugin,
            takes_args=True,
            aliases=["plugins", "extension", "extensions"],
        ),
        "readme": CommandEntry(
            help="Display README in terminal with rich formatting",
            handler=cmd_readme,
            takes_args=False,
        ),
        "slack": CommandEntry(
            help="Manage Slack integration [test|send|status|channels]",
            handler=cmd_slack,
            takes_args=True,
        ),
        "cost": CommandEntry(
            help="Token usage and cost dashboard",
            handler=cmd_cost,
            takes_args=True,
            aliases=["costs", "tokens", "usage"],
        ),
        "undo": CommandEntry(
            help="Undo last agent action (file edits, git commits)",
            handler=cmd_undo,
            takes_args=True,
            aliases=["rollback"],
        ),
        "skill": CommandEntry(
            help="Skill marketplace [list|search|install|remove|info]",
            handler=cmd_skill,
            takes_args=True,
            aliases=["skills"],
        ),
        "voice": CommandEntry(
            help="Voice mode — speak to chat with agents",
            handler=cmd_voice,
            takes_args=True,
        ),
        "pair": CommandEntry(
            help="AI pair programming — watch files, suggest improvements",
            handler=cmd_pair,
            takes_args=True,
            aliases=["pair-mode"],
        ),
        "index": CommandEntry(
            help="Build or inspect the RAG code index [--force|--stats]",
            handler=cmd_index,
            takes_args=True,
            aliases=["rag-index"],
        ),
        "debug": CommandEntry(
            help="Autonomous debug — reproduce, trace, root-cause, fix, verify",
            handler=cmd_debug,
            takes_args=True,
            aliases=["dbg"],
        ),
        "review-fix": CommandEntry(
            help="AI code review with auto-fix — review + fix suggestions + PR comments",
            handler=cmd_review_fix,
            takes_args=True,
            aliases=["smart-review"],
        ),
        "benchmark": CommandEntry(
            help="Run agent benchmarks — measure quality & latency across models",
            handler=cmd_benchmark,
            takes_args=True,
            aliases=["bench"],
        ),
        "bench-compare": CommandEntry(
            help="Compare benchmark runs for quality regressions",
            handler=cmd_bench_compare,
            takes_args=True,
        ),
        "bench-trend": CommandEntry(
            help="Show benchmark quality trend over time",
            handler=cmd_bench_trend,
            takes_args=True,
        ),
        "workspace": CommandEntry(
            help="Multi-repo workspace [add|remove|list|status]",
            handler=cmd_workspace,
            takes_args=True,
            aliases=["ws"],
        ),
        "agent-pipeline": CommandEntry(
            help="Agent pipelines — declarative agent chains [list|create|run|templates]",
            handler=cmd_pipeline_exec,
            takes_args=True,
            aliases=["agent-pipe"],
        ),
        "share": CommandEntry(
            help="Start live collaboration — share session with teammates",
            handler=cmd_share,
            takes_args=True,
        ),
        "join": CommandEntry(
            help="Join a live collaboration session by code",
            handler=cmd_join,
            takes_args=True,
        ),
        # --- Productivity features ---
        "pr-describe": CommandEntry(
            help="Generate PR description from branch diff",
            handler=cmd_pr_describe,
            takes_args=True,
            aliases=["pr-desc"],
        ),
        "postmortem": CommandEntry(
            help="Generate incident postmortem from time range",
            handler=cmd_postmortem,
            takes_args=True,
            aliases=["post-mortem"],
        ),
        "postmortem-gen": CommandEntry(
            help="Auto-generate structured incident postmortem with timeline and root cause",
            handler=cmd_postmortem_gen,
            takes_args=True,
            aliases=["pm-gen"],
        ),
        "dep-upgrade": CommandEntry(
            help="Scan and upgrade outdated dependencies",
            handler=cmd_dep_upgrade,
            takes_args=True,
            aliases=["deps"],
        ),
        "review-buddy": CommandEntry(
            help="Pre-push code review against conventions",
            handler=cmd_review_buddy,
            takes_args=True,
            aliases=["buddy"],
        ),
        "db-migrate": CommandEntry(
            help="Generate DB migration from plain English",
            handler=cmd_db_migrate,
            takes_args=True,
            aliases=["migration"],
        ),
        "oncall-summary": CommandEntry(
            help="Summarize on-call alerts + generate standup",
            handler=cmd_oncall_summary,
            takes_args=True,
        ),
        "test-impact": CommandEntry(
            help="Analyze which tests are impacted by changes",
            handler=cmd_test_impact,
            takes_args=True,
            aliases=["smart-test"],
        ),
        "runbook": CommandEntry(
            help="Execute runbooks with safety gates",
            handler=cmd_runbook,
            takes_args=True,
        ),
        "sprint-dashboard": CommandEntry(
            help="Sprint velocity dashboard with cycle time",
            handler=cmd_sprint_dashboard,
            takes_args=True,
            aliases=["sprint-dash"],
        ),
        "explain": CommandEntry(
            help="Ask questions about the codebase",
            handler=cmd_explain,
            takes_args=True,
            aliases=["ask", "qa"],
        ),
        "explain-code": CommandEntry(
            help="Explain a code block, function, or file with static analysis",
            handler=cmd_explain_code,
            takes_args=True,
            aliases=["xplain"],
        ),
        "usage-trace": CommandEntry(
            help="Find all usages of a symbol across the codebase",
            handler=cmd_usage_trace,
            takes_args=True,
            aliases=["trace", "where-used"],
        ),
        "nav": CommandEntry(
            help="Semantic codebase search — find where concepts are implemented",
            handler=cmd_codebase_nav,
            takes_args=True,
            aliases=["codebase-nav", "search-code"],
        ),
        "git-story": CommandEntry(
            help="Reconstruct the full story behind a line of code",
            handler=cmd_git_story,
            takes_args=True,
            aliases=["blame-story", "code-story"],
        ),
        "call-chain": CommandEntry(
            help="Show full call tree (callers and callees) for a function",
            handler=cmd_call_chain,
            takes_args=True,
            aliases=["callers", "callees"],
        ),
        "examples": CommandEntry(
            help="Find code examples for a concept or library usage",
            handler=cmd_code_examples,
            takes_args=True,
            aliases=["code-examples", "show-usage"],
        ),
        "dep-graph": CommandEntry(
            help="Dependency graph with Mermaid/DOT visualization",
            handler=cmd_dep_graph_viz,
            takes_args=True,
            aliases=["deps", "dependency-graph"],
        ),
        # --- Session 2: Debugging + Testing Tools ---
        "stack-decode": CommandEntry(
            help="Decode stack traces — map to code, explain error, suggest fix",
            handler=cmd_stack_decode,
            takes_args=True,
            aliases=["decode-stack", "stacktrace"],
        ),
        "log-analyze": CommandEntry(
            help="Analyze logs — correlate, timeline, root cause",
            handler=cmd_log_analyze,
            takes_args=True,
            aliases=["analyze-logs", "log-parse"],
        ),
        "env-diff": CommandEntry(
            help="Diff environment config files",
            handler=cmd_env_diff,
            takes_args=True,
            aliases=["diff-env", "config-diff-files"],
        ),
        "leak-scan": CommandEntry(
            help="Scan for memory leak patterns",
            handler=cmd_leak_scan,
            takes_args=True,
            aliases=["memory-leak", "leak-detect"],
        ),
        "deadlock-scan": CommandEntry(
            help="Scan for concurrency hazards — race conditions, deadlocks",
            handler=cmd_deadlock_scan,
            takes_args=True,
            aliases=["concurrency-scan", "race-detect"],
        ),
        "edge-cases": CommandEntry(
            help="Suggest untested edge cases for a function",
            handler=cmd_edge_cases,
            takes_args=True,
            aliases=["suggest-tests", "edge-case"],
        ),
        "mock-build": CommandEntry(
            help="Generate mock implementation for a class",
            handler=cmd_mock_build,
            takes_args=True,
            aliases=["build-mock", "generate-mock"],
        ),
        "test-fix": CommandEntry(
            help="Diagnose failing tests and suggest fixes",
            handler=cmd_test_fix,
            takes_args=True,
            aliases=["fix-test", "test-diagnose"],
        ),
        "integration-scaffold": CommandEntry(
            help="Generate docker-compose + test fixtures for integration testing",
            handler=cmd_integration_scaffold,
            takes_args=True,
            aliases=["scaffold", "test-infra"],
        ),
        "mindmap": CommandEntry(
            help="Generate visual mindmap of the repository",
            handler=cmd_mindmap,
            takes_args=True,
            aliases=["mind-map"],
        ),
        "migrate-tracing": CommandEntry(
            help="Migrate legacy tracing (Jaeger/DD/Zipkin) to OpenTelemetry",
            handler=cmd_migrate_tracing,
            takes_args=True,
            aliases=["otel-migrate"],
        ),
        "txn-flow": CommandEntry(
            help="Visualize transaction flow from logs or code state machines",
            handler=cmd_txn_flow,
            takes_args=True,
            aliases=["transaction-flow"],
        ),
        "impact": CommandEntry(
            help="Dependency impact scanner — analyze upgrade risk before upgrading",
            handler=cmd_dep_impact,
            takes_args=True,
            aliases=["dep-impact"],
        ),
        "install-hooks": CommandEntry(
            help="Install AI-powered git hooks (pre-commit, pre-push)",
            handler=cmd_install_hooks,
            takes_args=True,
            aliases=["hooks"],
        ),
        "hook-run": CommandEntry(
            help="Run git hook analysis (called by hook scripts)",
            handler=cmd_hook_run,
            takes_args=True,
        ),
        "pci-scan": CommandEntry(
            help="PCI-DSS compliance scanner for payment gateway code",
            handler=cmd_pci_scan,
            takes_args=True,
            aliases=["pci"],
        ),
        "owasp-scan": CommandEntry(
            help="OWASP Top 10 security scanner for codebase vulnerabilities",
            handler=cmd_owasp_scan,
            takes_args=True,
            aliases=["owasp"],
        ),
        "replay": CommandEntry(
            help="Agent replay / time travel debugging — replay, fork, search traces",
            handler=cmd_replay,
            takes_args=True,
            aliases=["traces"],
        ),
        "audit-idempotency": CommandEntry(
            help="Scan payment endpoints for idempotency key issues",
            handler=cmd_idempotency,
            takes_args=True,
            aliases=["idempotency-audit"],
        ),
        "tail": CommandEntry(
            help="Live tail — stream logs with anomaly detection",
            handler=cmd_tail,
            takes_args=True,
            aliases=["live-tail"],
        ),
        "validate-states": CommandEntry(
            help="Validate transaction state machines in code (enums, transition maps)",
            handler=cmd_validate_states,
            takes_args=True,
            aliases=["state-machine"],
        ),
        "acquirer-health": CommandEntry(
            help="Monitor payment acquirer success rates, latency, and errors",
            handler=cmd_acquirer_health,
            takes_args=True,
            aliases=["acq-health"],
        ),
        "translate": CommandEntry(
            help="Translate code between languages (regex-based scaffolding)",
            handler=cmd_translate,
            takes_args=True,
            aliases=["code-translate"],
        ),
        "profiler": CommandEntry(
            help="Performance profiler — cProfile hotspots and optimization suggestions",
            handler=cmd_profiler,
            takes_args=True,
            aliases=["profile", "perf-profile"],
        ),
        "schema": CommandEntry(
            help="Database schema visualizer — ER diagrams from DB or SQL files",
            handler=cmd_schema,
            takes_args=True,
            aliases=["schema-viz", "erd"],
        ),
        "dashboard": CommandEntry(
            help="Code health dashboard — tests, coverage, complexity, PRs",
            handler=cmd_dashboard,
            takes_args=True,
            aliases=["health", "health-dashboard"],
        ),
        "retry-audit": CommandEntry(
            help="Payment retry strategy analyzer — detect retry anti-patterns",
            handler=cmd_retry_audit,
            takes_args=True,
            aliases=["retry-scan"],
        ),
        "recon": CommandEntry(
            help="Payment reconciliation debugger — compare orders vs settlements",
            handler=cmd_recon,
            takes_args=True,
            aliases=["reconcile", "recon-debug"],
        ),
        "load-test": CommandEntry(
            help="Generate load test scripts (k6, Locust, JMeter) from API endpoints",
            handler=cmd_load_test,
            takes_args=True,
            aliases=["loadtest", "load-test-gen"],
        ),
        "settlement": CommandEntry(
            help="Settlement file parser & validator — parse Visa/MC/UPI files, validate, compare",
            handler=cmd_settlement,
            takes_args=True,
            aliases=["settle", "settlement-parse"],
        ),
        "bg": CommandEntry(
            help="Background agent manager — list, stop, view background tasks",
            handler=cmd_bg,
            takes_args=True,
            aliases=["background", "bg-tasks"],
        ),
        "batch": CommandEntry(
            help="Batch operations — apply instruction across many files in parallel",
            handler=cmd_batch,
            takes_args=True,
            aliases=["batch-ops"],
        ),
        "ci-heal": CommandEntry(
            help="CI pipeline self-healing — diagnose failures, apply fixes, re-trigger",
            handler=cmd_ci_heal,
            takes_args=True,
            aliases=["self-heal", "ci-fix"],
        ),
        "ci-run": CommandEntry(
            help="Headless CI mode — run agent tasks non-interactively",
            handler=cmd_ci_run,
            takes_args=True,
            aliases=["headless", "ci-mode"],
        ),
        "mutate-test": CommandEntry(
            help="Mutation testing — inject faults, verify tests catch them",
            handler=cmd_mutate_test,
            takes_args=True,
            aliases=["mutation-test", "mutate"],
        ),
        "pr-respond": CommandEntry(
            help="Respond to PR review comments — address feedback, push fixes, reply in-thread",
            handler=cmd_pr_respond,
            takes_args=True,
            aliases=["pr-thread"],
        ),
        "screenshot": CommandEntry(
            help="Screenshot-to-code — generate UI from screenshot or description",
            handler=cmd_screenshot,
            takes_args=True,
            aliases=["screenshot-to-code", "s2c"],
        ),
        "spec-validate": CommandEntry(
            help="Validate spec/PRD/Jira requirements against codebase implementation",
            handler=cmd_spec_validate,
            takes_args=True,
            aliases=["spec-check", "validate-spec"],
        ),
        "smell": CommandEntry(
            help="Code smell detector — god classes, long methods, deep nesting, data clumps",
            handler=cmd_smell,
            takes_args=True,
            aliases=["code-smell", "smells"],
        ),
        "imports": CommandEntry(
            help="Import optimizer — unused, circular, heavy, wildcard, duplicate, shadowed",
            handler=cmd_imports,
            takes_args=True,
            aliases=["import-optimizer", "optimize-imports"],
        ),
        "adr": CommandEntry(
            help="Generate Architecture Decision Records (ADRs)",
            handler=cmd_adr,
            takes_args=True,
            aliases=["decision"],
        ),
        "clones": CommandEntry(
            help="Detect code clones (duplicated code blocks) in the codebase",
            handler=cmd_clones,
            takes_args=True,
            aliases=["clone-detect", "duplicates"],
        ),
        "naming-audit": CommandEntry(
            help="Audit naming conventions — mixed styles, abbreviations, single-char vars",
            handler=cmd_naming_audit,
            takes_args=True,
            aliases=["naming", "name-check"],
        ),
        "encryption-audit": CommandEntry(
            help="Scan for weak encryption — MD5, DES, ECB, small keys, hardcoded secrets",
            handler=cmd_encryption_audit,
            takes_args=True,
            aliases=["crypto-audit"],
        ),
        "vuln-chain": CommandEntry(
            help="Vulnerability dependency chain — trace CVEs through transitive deps",
            handler=cmd_vuln_chain,
            takes_args=True,
            aliases=["vuln-scan", "dep-vuln"],
        ),
        "input-audit": CommandEntry(
            help="Input validation coverage — find endpoints missing validation",
            handler=cmd_input_audit,
            takes_args=True,
            aliases=["input-scan", "validation-audit"],
        ),
        "rate-limit-audit": CommandEntry(
            help="Audit endpoints for missing rate limiting — auth/payment flagged critical",
            handler=cmd_rate_limit_audit,
            takes_args=True,
            aliases=["ratelimit-audit", "rl-audit"],
        ),
        "privacy-scan": CommandEntry(
            help="Data privacy scanner — PII in logs, consent, deletion, GDPR/DPDP",
            handler=cmd_privacy_scan,
            takes_args=True,
            aliases=["privacy-audit", "pii-scan"],
        ),
        "compliance-report": CommandEntry(
            help="Compliance report generator — PCI, SOC2, GDPR control mapping",
            handler=cmd_compliance_report,
            takes_args=True,
            aliases=["compliance", "compliance-gen"],
        ),
        "add-types": CommandEntry(
            help="Add type annotations to untyped Python functions",
            handler=cmd_add_types,
            takes_args=True,
            aliases=["type-adder", "add-annotations"],
        ),
        "comment-audit": CommandEntry(
            help="Audit code comments — obvious, stale, TODO without ticket, commented code",
            handler=cmd_comment_audit,
            takes_args=True,
            aliases=["audit-comments"],
        ),
        "secret-rotation": CommandEntry(
            help="Track secret rotation — find stale secrets, generate runbooks",
            handler=cmd_secret_rotation,
            takes_args=True,
            aliases=["rotate-secrets"],
        ),
        "acl-matrix": CommandEntry(
            help="Generate ACL matrix — roles, endpoints, escalation paths",
            handler=cmd_acl_matrix,
            takes_args=True,
            aliases=["acl"],
        ),
        "session-audit": CommandEntry(
            help="Audit session management — JWT expiry, cookies, fixation, logout",
            handler=cmd_session_audit,
            takes_args=True,
            aliases=["audit-sessions"],
        ),
        "archaeology": CommandEntry(
            help="Code archaeology — trace origin and intent behind any line of code",
            handler=cmd_archaeology,
            takes_args=True,
            aliases=["archaeo", "dig"],
        ),
        "perf-proof": CommandEntry(
            help="Performance benchmark with statistical proof of optimization",
            handler=cmd_perf_proof,
            takes_args=True,
            aliases=["perf-bench"],
        ),
        "contract-test": CommandEntry(
            help="Generate API contract tests (Pact/JSON Schema) from route definitions",
            handler=cmd_contract_test,
            takes_args=True,
            aliases=["contract-tests", "pact"],
        ),
        "self-bench": CommandEntry(
            help="Self-benchmark agent quality — review, test gen, bug detection",
            handler=cmd_self_bench,
            takes_args=True,
            aliases=["self-benchmark"],
        ),
        "lang-migrate": CommandEntry(
            help="Migrate a module to another programming language",
            handler=cmd_lang_migrate,
            takes_args=True,
            aliases=["lang-migration"],
        ),
        "preview": CommandEntry(
            help="Live preview server — serve static files with auto-reload",
            handler=cmd_preview,
            takes_args=True,
            aliases=["live-preview"],
        ),
        "full-audit": CommandEntry(
            help="Global audit orchestrator — run ALL scanners, quality gates, unified report",
            handler=cmd_full_audit,
            takes_args=True,
            aliases=["audit-all", "global-audit"],
        ),
        "snippet": CommandEntry(
            help="Smart snippet library [search|save|list|delete|show]",
            handler=cmd_snippet,
            takes_args=True,
            aliases=["snippets"],
        ),
        "env-diff": CommandEntry(
            help="Compare environment configs (.env.dev vs .env.staging)",
            handler=cmd_env_diff,
            takes_args=True,
            aliases=["envdiff"],
        ),
        "ownership": CommandEntry(
            help="Code ownership map — git blame analysis, bus factor, CODEOWNERS",
            handler=cmd_ownership,
            takes_args=True,
            aliases=["code-ownership", "codeowners"],
        ),
        "velocity-predict": CommandEntry(
            help="Sprint velocity predictor — capacity from git history",
            handler=cmd_velocity_predict,
            takes_args=True,
            aliases=["velocity"],
        ),
        "pr-split": CommandEntry(
            help="Suggest how to split a large branch diff into smaller PRs",
            handler=cmd_pr_split,
            takes_args=True,
            aliases=["split-pr"],
        ),
        "license-audit": CommandEntry(
            help="Audit dependency licenses for compliance (GPL, AGPL, unknown)",
            handler=cmd_license_audit,
            takes_args=True,
            aliases=["license-check"],
        ),
        "validate-config": CommandEntry(
            help="Validate config files (YAML, JSON, TOML, .env) for syntax and typos",
            handler=cmd_validate_config,
            takes_args=True,
            aliases=["config-validate"],
        ),
        "release-notes": CommandEntry(
            help="Generate release notes from git history between two refs",
            handler=cmd_release_notes,
            takes_args=True,
            aliases=["relnotes"],
        ),
        # --- Feature 36-56: Testing, Browser, KB, Onboarding ---
        "prop-test": CommandEntry(
            help="Generate Hypothesis property-based tests from source code",
            handler=cmd_prop_test,
            takes_args=True,
            aliases=["property-test", "hypothesis"],
        ),
        "test-style": CommandEntry(
            help="Analyze project test style or generate style-matching tests",
            handler=cmd_test_style,
            takes_args=True,
            aliases=["style-test"],
        ),
        "visual-test": CommandEntry(
            help="Visual regression testing — capture and compare page snapshots",
            handler=cmd_visual_test,
            takes_args=True,
            aliases=["visual-regression"],
        ),
        "browse": CommandEntry(
            help="Browser agent — fetch page, extract text, scrape API docs",
            handler=cmd_browse,
            takes_args=True,
            aliases=["browser"],
        ),
        "team-kb": CommandEntry(
            help="Team knowledge base [list|add|get|search|delete]",
            handler=cmd_team_kb,
            takes_args=True,
            aliases=["kb", "knowledge-base"],
        ),
        "onboard-tour": CommandEntry(
            help="Generate onboarding tour for new developers",
            handler=cmd_onboard_tour,
            takes_args=False,
            aliases=["tour"],
        ),
        # --- Session 3: API + Database Tools ---
        "endpoint-gen": CommandEntry(
            help="Generate CRUD endpoints for a resource",
            handler=cmd_endpoint_gen,
            takes_args=True,
            aliases=["gen-endpoint", "crud-gen"],
        ),
        "api-sync": CommandEntry(
            help="Check API spec/code sync — detect drift between OpenAPI and routes",
            handler=cmd_api_sync,
            takes_args=True,
            aliases=["spec-sync"],
        ),
        "response-optimize": CommandEntry(
            help="Scan API responses for optimization — pagination, N+1, field selection",
            handler=cmd_response_optimize,
            takes_args=True,
            aliases=["optimize-response", "resp-opt"],
        ),
        "rest-to-grpc": CommandEntry(
            help="Convert REST endpoints to gRPC proto definitions",
            handler=cmd_rest_to_grpc,
            takes_args=True,
            aliases=["grpc-gen", "proto-gen"],
        ),
        "api-changelog": CommandEntry(
            help="Generate API changelog between two spec versions",
            handler=cmd_api_changelog,
            takes_args=True,
            aliases=["api-diff"],
        ),
        "query-optimize": CommandEntry(
            help="Analyze SQL query for optimization — SELECT *, missing LIMIT, wildcards",
            handler=cmd_query_optimize,
            takes_args=True,
            aliases=["optimize-query", "sql-optimize"],
        ),
        "schema-design": CommandEntry(
            help="Design database schema from entity JSON definitions",
            handler=cmd_schema_design,
            takes_args=True,
            aliases=["design-schema"],
        ),
        "orm-review": CommandEntry(
            help="Scan ORM code for anti-patterns — N+1, raw SQL, lazy loading",
            handler=cmd_orm_review,
            takes_args=True,
            aliases=["review-orm", "orm-audit"],
        ),
    }


COMMAND_REGISTRY: dict[str, CommandEntry] = _build_command_registry()
