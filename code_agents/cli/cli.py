"""
Code Agents CLI — unified entry point for all commands.

Usage:
    code-agents <command> [options]

Run 'code-agents help' for full command list.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.cli.cli")


# ---------------------------------------------------------------------------
# Helpers (extracted to cli_helpers.py)
# ---------------------------------------------------------------------------

from .cli_helpers import (  # noqa: F401
    _find_code_agents_home, _user_cwd, _load_env, _colors,
    _server_url, _api_get, _api_post, prompt_yes_no,
    _check_workspace_trust,
)


# ---------------------------------------------------------------------------
# Re-export from split modules for backward compatibility
# ---------------------------------------------------------------------------

from .cli_server import (  # noqa: F401
    _start_background,
    cmd_start, cmd_shutdown, cmd_restart, cmd_status,
    cmd_agents, cmd_logs, cmd_config, cmd_doctor,
)

from .cli_git import (  # noqa: F401
    cmd_diff, cmd_branches, cmd_commit, cmd_review,
    cmd_pr_preview, cmd_auto_review,
)

from .cli_cicd import (  # noqa: F401
    cmd_test, cmd_pipeline, _print_pipeline_status,
    cmd_release, cmd_coverage_boost, cmd_qa_suite,
)

from .cli_analysis import (  # noqa: F401
    cmd_deadcode, cmd_flags, cmd_security, cmd_complexity,
    cmd_techdebt, cmd_config_diff, cmd_api_check, cmd_apidoc,
    cmd_audit,
)
from .cli_dead_code import cmd_dead_code_eliminate  # noqa: F401

from .cli_reports import (  # noqa: F401
    cmd_standup, cmd_oncall_report, cmd_sprint_report,
    cmd_sprint_velocity, cmd_incident, cmd_morning,
    cmd_env_health, cmd_perf_baseline,
)

from .cli_cost import cmd_cost  # noqa: F401
from .cli_undo import cmd_undo  # noqa: F401
from .cli_skill import cmd_skill  # noqa: F401
from .cli_voice import cmd_voice  # noqa: F401

from .cli_tools import (  # noqa: F401
    cmd_onboard, cmd_watchdog, cmd_pre_push, cmd_changelog,
    cmd_version, cmd_version_bump, cmd_update, cmd_curls,
    cmd_rules, cmd_migrate, cmd_repos, cmd_sessions,
)


# ============================================================================
# COMMANDS
# ============================================================================


_INIT_SECTIONS = {
    "--profile":  "User profile (name, role/designation)",
    "--backend":  "Backend API keys (Cursor/Claude)",
    "--server":   "Server host and port",
    "--jenkins":  "Jenkins CI/CD build and deploy",
    "--argocd":   "ArgoCD deployment verification",
    "--jira":     "Jira/Confluence (URL, email, API token, project key)",
    "--kibana":   "Kibana log viewer (URL, credentials)",
    "--grafana":  "Grafana metrics (URL, credentials)",
    "--redash":   "Redash database queries",
    "--elastic":  "Elasticsearch integration",
    "--atlassian": "Atlassian OAuth (Jira/Confluence)",
    "--testing":  "Testing overrides (command, coverage threshold)",
    "--build":    "Local build command (CODE_AGENTS_BUILD_CMD)",
    "--k8s":      "Kubernetes (namespace, context, SSH)",
    "--notifications": "Slack webhook for alerts",
    "--slack":    "Slack Bot Bridge (bot token, signing secret)",
    "--extensions": "IDE extensions (build VS Code/IntelliJ plugins)",
}


def cmd_init():
    """Initialize code-agents in the current repository.

    Usage:
      code-agents init               # full wizard (all sections)
      code-agents init --jenkins     # update Jenkins config only
      code-agents init --redash      # update Redash config only
      code-agents init --argocd      # update ArgoCD config only
      code-agents init --backend     # update API keys only
      code-agents init --server      # update host/port only
      code-agents init --elastic     # update Elasticsearch only
      code-agents init --atlassian   # update Atlassian OAuth only
      code-agents init --testing     # update test command/threshold only
      code-agents init jenkins-cicd  # alias for --jenkins (agent names work too)
    """
    from code_agents.setup.setup import (
        prompt, prompt_yes_no, prompt_choice, prompt_cicd_pipeline,
        prompt_integrations, write_env_file, validate_url, validate_port,
    )
    bold, green, yellow, red, cyan, dim = _colors()

    cwd = _user_cwd()
    code_agents_home = _find_code_agents_home()
    args = sys.argv[2:]  # everything after 'init'

    # Normalize positional args to flags: 'backend' → '--backend'
    args = [a if a.startswith("--") else f"--{a}" for a in args]

    # Normalize common aliases (e.g. --jenkins-cicd → --jenkins)
    _INIT_ALIASES = {
        "--jenkins-cicd": "--jenkins",
        "--jira-ops": "--jira",
        "--argocd-deploy": "--argocd",
        "--kibana-logs": "--kibana",
        "--grafana-metrics": "--grafana",
        "--k8s-deploy": "--k8s",
        "--slack-bot": "--slack",
        "--notify": "--notifications",
    }
    args = [_INIT_ALIASES.get(a, a) for a in args]

    # Determine which sections to run
    section_flags = [a for a in args if a in _INIT_SECTIONS]
    run_all = not section_flags  # no flags = full wizard

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Init Repository          ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()

    if run_all:
        if os.path.isdir(os.path.join(cwd, ".git")):
            print(green(f"  ✓ Git repo detected: {cwd}"))
        else:
            print(yellow(f"  ! No .git found in: {cwd}"))
            if not prompt_yes_no("Continue anyway?", default=True):
                print(yellow("  Cancelled."))
                return
        print(f"  Code Agents installed at: {dim(str(code_agents_home))}")

        # ── Smart Init: detect existing config and ask what to modify ──
        from code_agents.core.env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME, repo_config_path
        from code_agents.setup.setup import merged_config_for_cwd

        _existing_cfg = merged_config_for_cwd(cwd)
        _has_any_config = (
            GLOBAL_ENV_PATH.is_file()
            or repo_config_path(cwd).is_file()
            or (Path(cwd) / ".env").is_file()
            or Path(cwd, PER_REPO_FILENAME).is_file()
        )

        if _has_any_config:
            print()
            print(bold("  Existing configuration detected:"))
            # Show what's configured
            _sections_status = {}
            _sections_status["Backend"] = "✓" if any(
                k in _existing_cfg for k in (
                    "CURSOR_API_KEY", "ANTHROPIC_API_KEY", "CODE_AGENTS_BACKEND",
                    "CODE_AGENTS_LOCAL_LLM_URL",
                )
            ) else "·"
            _sections_status["Server"] = "✓" if any(k in _existing_cfg for k in ("HOST", "PORT")) else "·"
            _sections_status["User Profile"] = "✓" if any(k in _existing_cfg for k in ("CODE_AGENTS_NICKNAME", "CODE_AGENTS_USER_ROLE")) else "·"
            _sections_status["Jenkins"] = "✓" if "JENKINS_URL" in _existing_cfg else "·"
            _sections_status["ArgoCD"] = "✓" if "ARGOCD_URL" in _existing_cfg else "·"
            _sections_status["Jira"] = "✓" if "JIRA_URL" in _existing_cfg else "·"
            _sections_status["Kibana"] = "✓" if "KIBANA_URL" in _existing_cfg else "·"
            _sections_status["Grafana"] = "✓" if "GRAFANA_URL" in _existing_cfg else "·"
            _sections_status["Redash"] = "✓" if any(
                k in _existing_cfg for k in ("REDASH_BASE_URL", "REDASH_URL")
            ) else "·"
            _sections_status["Testing"] = "✓" if any(
                k in _existing_cfg for k in ("TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD", "CODE_AGENTS_TEST_CMD")
            ) else "·"
            _sections_status["Notifications"] = "✓" if "CODE_AGENTS_SLACK_WEBHOOK_URL" in _existing_cfg else "·"

            for _sec_name, _sec_status in _sections_status.items():
                _icon = green(f"  {_sec_status}") if _sec_status == "✓" else dim(f"  {_sec_status}")
                print(f"  {_icon} {_sec_name}")

            print()
            _modify_choice = prompt_choice(
                "Config already exists. What would you like to do?",
                [
                    "Modify specific sections",
                    "Re-run full wizard (overwrites all)",
                    "Cancel",
                ],
                default=1,
            )

            if _modify_choice == 3:
                print(dim("  Cancelled."))
                return
            elif _modify_choice == 1:
                # Let user pick which sections to modify (multi-select)
                _section_list = [
                    ("--backend", "Backend (API keys, model)"),
                    ("--server", "Server (host, port)"),
                    ("--profile", "User Profile (name, role)"),
                    ("--jenkins", "Jenkins CI/CD"),
                    ("--argocd", "ArgoCD"),
                    ("--jira", "Jira / Confluence"),
                    ("--kibana", "Kibana"),
                    ("--grafana", "Grafana"),
                    ("--redash", "Redash"),
                    ("--testing", "Testing"),
                    ("--notifications", "Notifications (Slack)"),
                ]
                _section_names = [desc for _, desc in _section_list]
                _section_statuses = []
                for _, desc in _section_list:
                    _key = desc.split(" (")[0].split(" /")[0]
                    _s = _sections_status.get(_key, "·")
                    _section_statuses.append("✓" if _s == "✓" else "·")
                print(bold("  Select sections to modify:"))
                print(dim("  Enter the numbers of the sections to update (works in every terminal)."))
                from code_agents.agent_system.questionnaire import prompt_indices_numeric
                _selected_indices = prompt_indices_numeric(
                    "Sections:",
                    _section_names,
                    _section_statuses,
                )
                if not _selected_indices:
                    print(dim("  No sections selected. Cancelled."))
                    return
                section_flags = [_section_list[i][0] for i in _selected_indices]
                run_all = False
                _selected_desc = ", ".join(_section_list[i][1] for i in _selected_indices)
                print(f"\n  Updating: {bold(_selected_desc)}")
            # else: _modify_choice == 2 → run_all stays True
    else:
        sections_desc = ", ".join(_INIT_SECTIONS[f] for f in section_flags)
        print(f"  Updating: {bold(sections_desc)}")
        print(f"  Repo: {cwd}")
    print()

    # ── Smart Project Detection ──
    print(bold("  Scanning project..."))
    print()
    from code_agents.analysis.project_scanner import scan_project, format_scan_report
    project = scan_project(cwd)
    if project.detected:
        print(format_scan_report(project))
        print()

    # Load existing config to merge with (same overlay order as load_all_env)
    from code_agents.setup.setup import merged_config_for_cwd

    existing = merged_config_for_cwd(cwd)

    env_vars: dict[str, str] = {}
    init_unset_keys: set[str] = set()

    def _init_backend_choice_default(ex: dict) -> int:
        """1–5 index for prompt_choice from saved CODE_AGENTS_BACKEND (not inferred from keys alone).

        When backend is unset, default to **1 = Local LLM** so init matches agent YAML / product default.
        Keys alone do not change the highlighted option (avoids e.g. Anthropic key forcing Claude API).
        """
        b = (ex.get("CODE_AGENTS_BACKEND") or "").strip().lower()
        has_a = bool((ex.get("ANTHROPIC_API_KEY") or "").strip())
        if b == "local":
            return 1
        if b == "claude-cli":
            return 4
        if b == "claude":
            return 3
        if b == "cursor":
            return 5 if has_a else 2
        if not b:
            return 1
        return 1

    # Backend
    if run_all or "--backend" in section_flags:
        print(bold("  Backend Configuration"))
        choice = prompt_choice(
            "Which backend?",
            [
                "Local LLM (Ollama / OpenAI-compatible — default)",
                "Cursor (needs CURSOR_API_KEY)",
                "Claude API (needs ANTHROPIC_API_KEY)",
                "Claude CLI (uses your Claude subscription — no API key)",
                "Both Cursor + Claude API",
            ],
            default=_init_backend_choice_default(existing),
        )
        if choice == 1:
            env_vars["CODE_AGENTS_BACKEND"] = "local"
            env_vars["CODE_AGENTS_LOCAL_LLM_URL"] = prompt(
                "CODE_AGENTS_LOCAL_LLM_URL",
                default=existing.get("CODE_AGENTS_LOCAL_LLM_URL") or "http://127.0.0.1:11434/v1",
                validator=validate_url,
                error_msg="Must be a valid URL",
            )
            env_vars["CODE_AGENTS_LOCAL_LLM_API_KEY"] = prompt(
                "CODE_AGENTS_LOCAL_LLM_API_KEY",
                default=existing.get("CODE_AGENTS_LOCAL_LLM_API_KEY") or "local",
                required=True,
            )
            env_vars["CODE_AGENTS_MODEL"] = prompt(
                "CODE_AGENTS_MODEL",
                default=existing.get("CODE_AGENTS_MODEL") or "qwen2.5-coder:7b",
                required=True,
            )
        if choice in (2, 5):
            env_vars["CURSOR_API_KEY"] = prompt("CURSOR_API_KEY", default=existing.get("CURSOR_API_KEY", ""), secret=True, required=True)
            url = prompt("Cursor API URL (blank for CLI mode)", default=existing.get("CURSOR_API_URL", ""), validator=validate_url, error_msg="Must be a valid URL")
            if url:
                env_vars["CURSOR_API_URL"] = url
        if choice in (3, 5):
            env_vars["ANTHROPIC_API_KEY"] = prompt("ANTHROPIC_API_KEY", default=existing.get("ANTHROPIC_API_KEY", ""), secret=True, required=True)
        if choice == 2:
            env_vars["CODE_AGENTS_BACKEND"] = "cursor"
        elif choice == 3:
            env_vars["CODE_AGENTS_BACKEND"] = "claude"
        elif choice == 4:
            env_vars["CODE_AGENTS_BACKEND"] = "claude-cli"
            print(dim("    Claude CLI uses your Claude Pro/Max subscription."))
            print(dim("    Make sure you're logged in: run 'claude' in terminal first."))
            model = prompt("Claude model", default=existing.get("CODE_AGENTS_CLAUDE_CLI_MODEL") or "claude-sonnet-4-6")
            env_vars["CODE_AGENTS_CLAUDE_CLI_MODEL"] = model
        elif choice == 5:
            env_vars["CODE_AGENTS_BACKEND"] = "cursor"
        # Switching away from Claude CLI: drop stale CLI model so merge does not keep old value
        if choice in (1, 2, 3, 5):
            init_unset_keys.add("CODE_AGENTS_CLAUDE_CLI_MODEL")
        print()

    # Server
    if run_all or "--server" in section_flags:
        print(bold("  Server Configuration"))
        env_vars["HOST"] = prompt("HOST", default=existing.get("HOST", "0.0.0.0"))
        env_vars["PORT"] = prompt("PORT", default=existing.get("PORT", "8000"), validator=validate_port, error_msg="Must be 1-65535")
        print()

    # Jenkins
    if run_all or "--jenkins" in section_flags:
        should_configure = True if "--jenkins" in section_flags else prompt_yes_no("Configure Jenkins?", default=True)
        if should_configure:
            from code_agents.setup.setup import validate_job_path, clean_job_path
            print(dim("    Jenkins base URL without job path"))
            print(dim("    Example: https://jenkins.pg2nonprod.example.com/"))
            env_vars["JENKINS_URL"] = prompt(
                "JENKINS_URL",
                default=existing.get("JENKINS_URL", "https://jenkins.pg2nonprod.example.com/"),
                required=True, validator=validate_url, error_msg="Must be a valid URL.",
            )
            print(dim("    Example: shivanshu1.gupta@example.com"))
            env_vars["JENKINS_USERNAME"] = prompt("JENKINS_USERNAME", default=existing.get("JENKINS_USERNAME", ""), required=True)
            print(dim("    Manage Jenkins → Users → Configure → API Token"))
            env_vars["JENKINS_API_TOKEN"] = prompt("JENKINS_API_TOKEN", default=existing.get("JENKINS_API_TOKEN", ""), secret=True, required=True)
            print()
            print(dim("    Extract folder path from Jenkins URL (no 'job/' prefix)"))
            print(dim("    Example: pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"))
            env_vars["JENKINS_BUILD_JOB"] = prompt(
                "JENKINS_BUILD_JOB",
                default=existing.get("JENKINS_BUILD_JOB", "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"),
                required=True, validator=validate_job_path,
                transform=clean_job_path,
                error_msg="Enter folder path, not full URL.",
            )
            print(dim("    Deploy job — Dev environment"))
            print(dim("    Example: pg2/pg2-dev-build-jobs/deploy/PG2-DEV-DEPLOY-PIPELINE"))
            env_vars["JENKINS_DEPLOY_JOB_DEV"] = prompt(
                "JENKINS_DEPLOY_JOB_DEV",
                default=existing.get("JENKINS_DEPLOY_JOB_DEV", existing.get("JENKINS_DEPLOY_JOB", "")),
                validator=validate_job_path, transform=clean_job_path,
                error_msg="Enter folder path.",
            )
            print(dim("    Deploy job — QA environment"))
            print(dim("    Example: pg2/pg2-qa-build-jobs/deploy/PG2-QA-DEPLOY-PIPELINE"))
            env_vars["JENKINS_DEPLOY_JOB_QA"] = prompt(
                "JENKINS_DEPLOY_JOB_QA",
                default=existing.get("JENKINS_DEPLOY_JOB_QA", existing.get("JENKINS_DEPLOY_JOB", "")),
                validator=validate_job_path, transform=clean_job_path,
                error_msg="Enter folder path.",
            )
            # Keep JENKINS_DEPLOY_JOB as fallback (defaults to dev)
            env_vars["JENKINS_DEPLOY_JOB"] = env_vars["JENKINS_DEPLOY_JOB_DEV"]
            print()

    # ArgoCD
    if run_all or "--argocd" in section_flags:
        should_configure = True if "--argocd" in section_flags else prompt_yes_no("Configure ArgoCD?", default=True)
        if should_configure:
            print(dim("    Example: https://argocd-acquiring.pg2prod.example.com"))
            env_vars["ARGOCD_URL"] = prompt("ARGOCD_URL", default=existing.get("ARGOCD_URL", "https://argocd.pgnonprod.example.com"), required=True, validator=validate_url, error_msg="Must be a valid URL.")
            print(dim("    ArgoCD login credentials (exchanges for a session JWT automatically)"))
            env_vars["ARGOCD_USERNAME"] = prompt("ARGOCD_USERNAME", default=existing.get("ARGOCD_USERNAME", "admin"), required=True)
            env_vars["ARGOCD_PASSWORD"] = prompt("ARGOCD_PASSWORD", default=existing.get("ARGOCD_PASSWORD", ""), secret=True, required=True)
            default_pattern = existing.get("ARGOCD_APP_PATTERN", "{env}-project-bombay-{app}")
            print(dim(f"    App name pattern: {default_pattern}"))
            print(dim("    Resolves to e.g.: dev-stable-project-bombay-pg-acquiring-biz"))
            if not prompt_yes_no("    Is this pattern correct?", default=True):
                env_vars["ARGOCD_APP_PATTERN"] = prompt("ARGOCD_APP_PATTERN", default=default_pattern, required=True)
            else:
                env_vars["ARGOCD_APP_PATTERN"] = default_pattern
            print()

    # Testing — auto-detect or manual
    detected_test = project.test_cmd if project.test_cmd else ""
    current_test = existing.get("TARGET_TEST_COMMAND", "")
    if "--testing" in section_flags or (run_all and (detected_test or current_test)):
        test_default = detected_test or current_test
        if test_default and "--testing" not in section_flags:
            print(bold("  Test Command"))
            print(f"    Auto-detected: {cyan(test_default)}")
            choice = prompt_choice("Use this test command?", ["Yes — use as-is", "Edit — modify it", "Skip"], default=1)
            if choice == 1:
                env_vars["TARGET_TEST_COMMAND"] = test_default
            elif choice == 2:
                env_vars["TARGET_TEST_COMMAND"] = prompt("TARGET_TEST_COMMAND", default=test_default, required=True)
            print()
        else:
            print(bold("  Test Command"))
            print(dim("    Leave blank for auto-detect (pytest/jest/maven/go)"))
            cmd = prompt("TARGET_TEST_COMMAND", default=test_default or "")
            if cmd:
                env_vars["TARGET_TEST_COMMAND"] = cmd
            print()
        # Coverage threshold
        threshold = prompt("TARGET_COVERAGE_THRESHOLD", default=existing.get("TARGET_COVERAGE_THRESHOLD", "80"))
        if threshold != "80":
            env_vars["TARGET_COVERAGE_THRESHOLD"] = threshold

        # QA Suite offer — detect no tests exist
        from code_agents.generators.qa_suite_generator import QASuiteGenerator
        _qa_gen = QASuiteGenerator(cwd=cwd)
        _qa_gen._detect_stack()
        if _qa_gen.analysis.language:
            _qa_gen._check_existing_tests()
            if not _qa_gen.analysis.has_existing_tests:
                print()
                print(yellow("  No test files detected in this repo."))
                if prompt_yes_no("Generate a QA regression test suite?", default=True):
                    _qa_gen._discover_endpoints()
                    _qa_gen._discover_services()
                    _qa_gen._discover_repositories()
                    _qa_gen.generate_suite()
                    from code_agents.generators.qa_suite_generator import format_analysis as _fmt_qa
                    print()
                    print(_fmt_qa(_qa_gen.analysis))
                    print()
                    print(dim(f"  Run 'code-agents qa-suite --write' to write files to disk."))
                    print(dim(f"  Or use /qa-suite in chat for agent-guided generation."))

    elif run_all:
        should_configure = prompt_yes_no("Configure testing overrides?", default=True)
        if should_configure:
            cmd = prompt("TARGET_TEST_COMMAND", default=existing.get("TARGET_TEST_COMMAND", ""))
            if cmd:
                env_vars["TARGET_TEST_COMMAND"] = cmd
            threshold = prompt("TARGET_COVERAGE_THRESHOLD", default=existing.get("TARGET_COVERAGE_THRESHOLD", "80"))
            if threshold != "80":
                env_vars["TARGET_COVERAGE_THRESHOLD"] = threshold
            print()

    # Integrations (only in full wizard or specific flags)
    if run_all:
        env_vars.update(prompt_integrations())
    else:
        if "--redash" in section_flags:
            from code_agents.setup.setup import validate_url as _vurl
            print(bold("  Redash Configuration"))
            print(dim("    Example: http://10.215.50.126/"))
            env_vars["REDASH_BASE_URL"] = prompt("REDASH_BASE_URL", default=existing.get("REDASH_BASE_URL", ""), required=True, validator=_vurl, error_msg="Must be a valid URL.")
            api_key = prompt("REDASH_API_KEY (blank for username/password)", default=existing.get("REDASH_API_KEY", ""))
            if api_key:
                env_vars["REDASH_API_KEY"] = api_key
            else:
                env_vars["REDASH_USERNAME"] = prompt("REDASH_USERNAME", default=existing.get("REDASH_USERNAME", ""), required=True)
                env_vars["REDASH_PASSWORD"] = prompt("REDASH_PASSWORD", default=existing.get("REDASH_PASSWORD", ""), secret=True, required=True)
            print()

        if "--elastic" in section_flags:
            print(bold("  Elasticsearch Configuration"))
            env_vars["ELASTICSEARCH_URL"] = prompt("ELASTICSEARCH_URL", default=existing.get("ELASTICSEARCH_URL", ""), required=True)
            api_key = prompt("ELASTICSEARCH_API_KEY (blank to skip)", default=existing.get("ELASTICSEARCH_API_KEY", ""))
            if api_key:
                env_vars["ELASTICSEARCH_API_KEY"] = api_key
            print()

        if "--atlassian" in section_flags:
            print(bold("  Atlassian OAuth Configuration"))
            env_vars["ATLASSIAN_CLOUD_SITE_URL"] = prompt("ATLASSIAN_CLOUD_SITE_URL", default=existing.get("ATLASSIAN_CLOUD_SITE_URL", ""), required=True)
            env_vars["ATLASSIAN_OAUTH_CLIENT_ID"] = prompt("ATLASSIAN_OAUTH_CLIENT_ID", default=existing.get("ATLASSIAN_OAUTH_CLIENT_ID", ""), required=True)
            env_vars["ATLASSIAN_OAUTH_CLIENT_SECRET"] = prompt("ATLASSIAN_OAUTH_CLIENT_SECRET", default=existing.get("ATLASSIAN_OAUTH_CLIENT_SECRET", ""), secret=True, required=True)
            print()

    # Profile
    if run_all or "--profile" in section_flags:
        should_configure = True if "--profile" in section_flags else True  # always ask in full wizard
        if should_configure:
            print(bold("  User Profile"))
            env_vars["CODE_AGENTS_NICKNAME"] = prompt("Your name/nickname", default=existing.get("CODE_AGENTS_NICKNAME", "you"))
            from code_agents.agent_system.questionnaire import ask_question
            current_role = (existing.get("CODE_AGENTS_USER_ROLE") or "").strip()
            _role_labels = [
                "Junior Engineer", "Senior Engineer", "Lead Engineer",
                "Principal Engineer / Architect", "Engineering Manager",
            ]
            if not current_role or "--profile" in section_flags:
                _role_default_idx = 2  # Lead Engineer — prior default
                if current_role:
                    _matched = False
                    for _i, _lab in enumerate(_role_labels):
                        if _lab == current_role:
                            _role_default_idx = _i
                            _matched = True
                            break
                    if not _matched:
                        _role_default_idx = len(_role_labels)  # "Other — describe in detail"
                answer = ask_question(
                    question="What is your role/designation?",
                    options=_role_labels,
                    allow_other=True, default=_role_default_idx,
                )
                env_vars["CODE_AGENTS_USER_ROLE"] = answer["answer"]
            print()

    # Jira/Confluence
    if "--jira" in section_flags:
        print(bold("  Jira/Confluence Configuration"))
        env_vars["JIRA_URL"] = prompt("JIRA_URL", default=existing.get("JIRA_URL", ""), required=True)
        env_vars["JIRA_EMAIL"] = prompt("JIRA_EMAIL", default=existing.get("JIRA_EMAIL", ""), required=True)
        env_vars["JIRA_API_TOKEN"] = prompt("JIRA_API_TOKEN", default=existing.get("JIRA_API_TOKEN", ""), secret=True, required=True)
        env_vars["JIRA_PROJECT_KEY"] = prompt("JIRA_PROJECT_KEY", default=existing.get("JIRA_PROJECT_KEY", ""))
        print()

    # Kibana
    if "--kibana" in section_flags:
        print(bold("  Kibana Log Viewer"))
        env_vars["KIBANA_URL"] = prompt("KIBANA_URL", default=existing.get("KIBANA_URL", ""), required=True)
        env_vars["KIBANA_USERNAME"] = prompt("KIBANA_USERNAME", default=existing.get("KIBANA_USERNAME", ""))
        env_vars["KIBANA_PASSWORD"] = prompt("KIBANA_PASSWORD", default=existing.get("KIBANA_PASSWORD", ""), secret=True)
        print()

    # Grafana
    if "--grafana" in section_flags:
        print(bold("  Grafana Metrics"))
        env_vars["GRAFANA_URL"] = prompt("GRAFANA_URL", default=existing.get("GRAFANA_URL", ""), required=True)
        env_vars["GRAFANA_USERNAME"] = prompt("GRAFANA_USERNAME", default=existing.get("GRAFANA_USERNAME", ""))
        env_vars["GRAFANA_PASSWORD"] = prompt("GRAFANA_PASSWORD", default=existing.get("GRAFANA_PASSWORD", ""), secret=True)
        print()

    # Build — auto-detect or manual
    detected_build = project.build_cmd if project.build_cmd else ""
    current_build = existing.get("CODE_AGENTS_BUILD_CMD", "")
    if "--build" in section_flags or (run_all and (detected_build or current_build)):
        build_default = detected_build or current_build
        if build_default and "--build" not in section_flags:
            print(bold("  Local Build Command"))
            print(f"    Auto-detected: {cyan(build_default)}")
            choice = prompt_choice("Use this build command?", ["Yes — use as-is", "Edit — modify it", "Skip"], default=1)
            if choice == 1:
                env_vars["CODE_AGENTS_BUILD_CMD"] = build_default
            elif choice == 2:
                print(dim("    Use && for multiple commands on one line"))
                print(dim("    Example: export JAVA_HOME=$(/usr/libexec/java_home -v 21) && mvn clean install"))
                env_vars["CODE_AGENTS_BUILD_CMD"] = prompt("CODE_AGENTS_BUILD_CMD", default=build_default, required=True)
            print()
        elif "--build" in section_flags:
            print(bold("  Local Build Command"))
            print(dim("    Use && for multiple commands on one line"))
            print(dim("    Example: export JAVA_HOME=$(/usr/libexec/java_home -v 21) && mvn clean install"))
            env_vars["CODE_AGENTS_BUILD_CMD"] = prompt("CODE_AGENTS_BUILD_CMD", default=build_default or "", required=True)
            print()

    # K8s
    if "--k8s" in section_flags:
        print(bold("  Kubernetes Configuration"))
        env_vars["K8S_NAMESPACE"] = prompt("K8S_NAMESPACE", default=existing.get("K8S_NAMESPACE", "default"))
        env_vars["K8S_CONTEXT"] = prompt("K8S_CONTEXT (blank for current)", default=existing.get("K8S_CONTEXT", ""))
        ssh = prompt("K8S_SSH_HOST (blank for local kubectl)", default=existing.get("K8S_SSH_HOST", ""))
        if ssh:
            env_vars["K8S_SSH_HOST"] = ssh
            env_vars["K8S_SSH_USER"] = prompt("K8S_SSH_USER", default=existing.get("K8S_SSH_USER", ""), required=True)
            env_vars["K8S_SSH_KEY"] = prompt("K8S_SSH_KEY", default=existing.get("K8S_SSH_KEY", ""))
        print()

    # Notifications
    if "--notifications" in section_flags:
        print(bold("  Notifications"))
        env_vars["CODE_AGENTS_SLACK_WEBHOOK_URL"] = prompt("Slack webhook URL", default=existing.get("CODE_AGENTS_SLACK_WEBHOOK_URL", ""), required=True)
        print()

    # Slack Bot Bridge
    if "--slack" in section_flags:
        print(bold("  Slack Bot Bridge"))
        env_vars["CODE_AGENTS_SLACK_BOT_TOKEN"] = prompt("Slack Bot OAuth token (xoxb-...)", default=existing.get("CODE_AGENTS_SLACK_BOT_TOKEN", ""), required=True)
        env_vars["CODE_AGENTS_SLACK_SIGNING_SECRET"] = prompt("Slack app signing secret", default=existing.get("CODE_AGENTS_SLACK_SIGNING_SECRET", ""), required=True)
        print()

    # IDE Extensions
    if run_all or "--extensions" in section_flags:
        should_build = True if "--extensions" in section_flags else prompt_yes_no("Build IDE extensions?", default=True)
        if should_build:
            print(bold("  IDE Extensions"))
            _ext_dir = Path(__file__).parent.parent.parent / "extensions"
            import subprocess as _sp
            import shutil

            # Auto-install Node.js/npm if missing
            if not shutil.which("npm"):
                print(dim("    npm not found — attempting to install Node.js..."))
                if shutil.which("brew"):
                    try:
                        _sp.run(["brew", "install", "node"], check=True, capture_output=True, timeout=120)
                        print(green("    ✓ Node.js installed via Homebrew"))
                    except Exception:
                        print(dim("    ✗ Node.js install failed"))
                        print(dim("    Install manually: https://nodejs.org/"))
                elif sys.platform == "linux":
                    try:
                        _sp.run(["sudo", "apt-get", "install", "-y", "nodejs", "npm"], check=True, capture_output=True, timeout=120)
                        print(green("    ✓ Node.js installed via apt"))
                    except Exception:
                        print(dim("    ✗ Node.js install failed"))
                        print(dim("    Install manually: https://nodejs.org/"))
                else:
                    print(dim("    Install Node.js from: https://nodejs.org/"))
                    print(dim("    Then re-run: code-agents init --extensions"))

            if shutil.which("npm"):
                _vscode_dir = _ext_dir / "vscode"
                if (_vscode_dir / "package.json").exists():
                    print(dim("    Building VS Code extension..."))
                    try:
                        from code_agents.tools.vscode_extension import (
                            build_vscode_extension,
                            install_vsix_with_code_cli,
                            newest_vsix,
                            run_vsce_package,
                        )

                        build_vscode_extension(_vscode_dir)
                        print(green("    ✓ VS Code extension built"))
                        _vsix_path = newest_vsix(_vscode_dir)
                        if _vsix_path is None:
                            print(dim("    Packaging VS Code extension (.vsix)..."))
                            _rc = run_vsce_package(_vscode_dir, capture_output=True)
                            if _rc == 0:
                                _vsix_path = newest_vsix(_vscode_dir)
                                if _vsix_path:
                                    print(green(f"    ✓ Packaged: {_vsix_path.name}"))
                            else:
                                print(dim("    ✗ .vsix packaging failed — run: code-agents plugin validate --fix"))
                                print(dim("       then: code-agents plugin package vscode"))
                        if shutil.which("code"):
                            if _vsix_path:
                                try:
                                    install_vsix_with_code_cli(_vsix_path)
                                    print(green("    ✓ Installed into VS Code"))
                                except Exception:
                                    print(dim(f"    Install manually: code --install-extension {_vsix_path}"))
                            else:
                                print(dim("    No .vsix — run: code-agents plugin package vscode"))
                        else:
                            print(dim("    VS Code CLI not found — install 'code' command from VS Code"))
                            if _vsix_path:
                                print(dim(f"    Or install from VSIX: {_vsix_path}"))
                    except Exception as e:
                        print(dim(f"    ✗ VS Code build failed: {e}"))
                        print(dim("    Run manually: code-agents plugin build vscode && code-agents plugin package vscode"))

                # Copy webview to IntelliJ resources
                _ij_dir = _ext_dir / "intellij"
                _webview_build = _vscode_dir / "webview-ui" / "build"
                if _webview_build.exists() and _ij_dir.exists():
                    _ij_webview = _ij_dir / "src" / "main" / "resources" / "webview"
                    _ij_webview.mkdir(parents=True, exist_ok=True)
                    _idx = _webview_build / "index.html"
                    if _idx.exists():
                        shutil.copy2(str(_idx), str(_ij_webview / "index.html"))
                    _assets_src = _webview_build / "assets"
                    _assets_dst = _ij_webview / "assets"
                    if _assets_src.exists():
                        if _assets_dst.exists():
                            shutil.rmtree(str(_assets_dst))
                        shutil.copytree(str(_assets_src), str(_assets_dst))
                    print(green("    ✓ Webview copied to IntelliJ resources"))
            else:
                print(dim("    npm not found — skipping extension build"))
                print(dim("    Install Node.js: https://nodejs.org/"))

            # Auto-install Gradle if missing (for IntelliJ)
            if not shutil.which("gradle") and not (_ext_dir / "intellij" / "gradlew").exists():
                if shutil.which("java"):
                    print(dim("    Gradle not found — attempting to install..."))
                    if shutil.which("brew"):
                        try:
                            _sp.run(["brew", "install", "gradle"], check=True, capture_output=True, timeout=120)
                            print(green("    ✓ Gradle installed via Homebrew"))
                        except Exception:
                            print(dim("    ✗ Gradle install failed — install: brew install gradle"))
                    elif sys.platform == "linux":
                        try:
                            _sp.run(["sudo", "apt-get", "install", "-y", "gradle"], check=True, capture_output=True, timeout=120)
                            print(green("    ✓ Gradle installed via apt"))
                        except Exception:
                            print(dim("    ✗ Gradle install failed — install manually"))
                else:
                    print(dim("    Java not found — skipping IntelliJ build"))
                    print(dim("    Install: https://adoptium.net/ or brew install openjdk@17"))

            if shutil.which("gradle") or ((_ext_dir / "intellij" / "gradlew").exists()):
                print(dim("    Building IntelliJ plugin..."))
                _gradle = str(_ext_dir / "intellij" / "gradlew") if (_ext_dir / "intellij" / "gradlew").exists() else "gradle"
                try:
                    if _gradle == "gradle":
                        _sp.run(["gradle", "wrapper", "--gradle-version=8.13"], cwd=str(_ext_dir / "intellij"), check=True, capture_output=True)
                        _gradle = str(_ext_dir / "intellij" / "gradlew")
                    _sp.run([_gradle, "buildPlugin"], cwd=str(_ext_dir / "intellij"), check=True, capture_output=True, timeout=300)
                    print(green("    ✓ IntelliJ plugin built"))
                    print(dim("    Install: code-agents plugin install intellij"))
                except Exception as e:
                    print(dim(f"    ✗ IntelliJ build failed: {e}"))
                    print(dim("    Run manually: cd extensions/intellij && ./gradlew buildPlugin"))
            else:
                print(dim("    Gradle not found — skipping IntelliJ build"))
                print(dim("    Install: brew install gradle"))
            print()

    env_vars = {k: v for k, v in env_vars.items() if v}

    if not env_vars and not init_unset_keys:
        print(dim("  No changes to save."))
        return

    print(bold("━" * 44))
    original_dir = _user_cwd()
    os.chdir(cwd)
    write_env_file(env_vars, unset_keys=frozenset(init_unset_keys))
    os.chdir(original_dir)

    # Create .code-agents/.ignore if it doesn't exist
    _ignore_dir = Path(cwd) / ".code-agents"
    _ignore_dir.mkdir(parents=True, exist_ok=True)
    _ignore_file = _ignore_dir / ".ignore"
    if not _ignore_file.exists():
        _ignore_file.write_text(
            "# Files and directories agents should NOT read or index.\n"
            "# Gitignore-style patterns. Lines starting with # are comments.\n"
            "# Prefix with ! to force-include a file.\n"
            "#\n"
            "# Examples:\n"
            "#   *.log             # ignore all log files\n"
            "#   /vendor/          # ignore vendor directory\n"
            "#   secret*.json      # ignore secret config files\n"
            "#   !important.log    # force-include this file\n"
            "\n"
            "# Common ignores\n"
            "*.log\n"
            "*.env\n"
            "*.key\n"
            "*.pem\n"
            "*.p12\n"
            "*.jks\n"
            "credentials*\n"
            "secrets*\n"
            ".env.*\n"
            "node_modules/\n"
            "target/\n"
            "dist/\n"
            "build/\n"
            ".gradle/\n"
            "__pycache__/\n"
            "*.pyc\n"
        )
        print(green(f"  ✓ Created: {_ignore_file}"))

    print()
    from code_agents.core.env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME
    print(green(f"  ✓ Initialized in: {cwd}"))
    print(f"  Global config: {cyan(str(GLOBAL_ENV_PATH))}")
    print(f"  Repo config:   {cyan(os.path.join(cwd, PER_REPO_FILENAME))}")
    print()

    # Show Quick Links
    _init_port = env_vars.get("PORT") or os.getenv("PORT", "8000")
    _init_host = env_vars.get("HOST") or os.getenv("HOST", "0.0.0.0")
    _init_base = f"http://127.0.0.1:{_init_port}" if _init_host == "0.0.0.0" else f"http://{_init_host}:{_init_port}"

    print(f"  {bold('Quick Links:')}")
    print(f"    Chat UI:           {cyan(f'{_init_base}/ui')}")
    print(f"    Telemetry:         {cyan(f'{_init_base}/telemetry-dashboard')}")
    print(f"    API Health:        {cyan(f'{_init_base}/health')}")
    print(f"    API Docs:          {cyan(f'{_init_base}/docs')}")
    print()

    # Background endpoint scan
    import threading

    def _bg_scan(repo_path):
        from code_agents.cicd.endpoint_scanner import background_scan
        background_scan(repo_path)

    repo = os.getenv("TARGET_REPO_PATH") or os.getcwd()
    threading.Thread(target=_bg_scan, args=(repo,), daemon=True).start()
    print(dim("  ⏳ Scanning endpoints in background..."))

    # Background regression baseline
    def _bg_regression(repo_path):
        try:
            from code_agents.cicd.testing_client import TestingClient
            import asyncio, json as _json, time as _time
            client = TestingClient(repo_path)
            result = asyncio.run(client.run_tests())
            baseline_dir = Path(repo_path) / ".code-agents"
            baseline_dir.mkdir(parents=True, exist_ok=True)
            baseline_file = baseline_dir / f"{Path(repo_path).name}.regression-baseline.json"
            baseline = {
                "timestamp": _time.time(),
                "passed": result.get("passed", 0),
                "failed": result.get("failed", 0),
                "total": result.get("total", 0),
                "exit_code": result.get("exit_code", -1),
            }
            baseline_file.write_text(_json.dumps(baseline, indent=2))
        except Exception:
            pass  # silently fail — baseline is optional

    threading.Thread(target=_bg_regression, args=(repo,), daemon=True).start()
    print(dim("  ⏳ Building regression baseline in background..."))

    # Check if server is already running
    port = os.getenv("PORT", "8000")
    server_running = False
    try:
        import httpx
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        server_running = r.status_code == 200
    except Exception:
        pass

    if server_running:
        print(yellow(f"  Server is already running on port {port}."))
        if prompt_yes_no("Restart the server to apply new config?", default=True):
            cmd_restart()
        else:
            print(dim("  Config saved. Restart manually: code-agents restart"))
            print()
    elif prompt_yes_no("Start the server now?", default=True):
        _start_background(cwd)
    else:
        print()
        print(bold("  Next steps:"))
        print(f"    code-agents start       {dim('# start the server')}")
        print(f"    code-agents status      {dim('# check server health')}")
        print(f"    code-agents agents      {dim('# list available agents')}")
        print()


# ============================================================================
# MAIN DISPATCHER
# ============================================================================


COMMANDS = {
    "init":      ("Initialize code-agents in current repo",        cmd_init),
    "migrate":   ("Migrate legacy .env to centralized config",     cmd_migrate),
    "audit":     ("Audit dependencies for CVEs, licenses, outdated", None),  # special handling (takes args)
    "rules":     ("Manage rules [list|create|edit|delete]",        None),  # special handling
    "start":     ("Start the server",                               cmd_start),
    "restart":   ("Restart the server (shutdown + start)",          cmd_restart),
    "chat":      ("Interactive chat with agents",                   None),  # special handling
    "shutdown":  ("Shutdown the server",                              cmd_shutdown),
    "status":    ("Check server health and config",                 cmd_status),
    "agents":    ("List all available agents",                      cmd_agents),
    "repos":     ("List and manage registered repos",               None),  # special handling
    "sessions":  ("List saved chat sessions",                       None),  # special handling
    "config":    ("Show current .env configuration",                cmd_config),
    "doctor":    ("Diagnose common issues",                         cmd_doctor),
    "logs":      ("Tail the log file",                              None),  # special handling
    "diff":      ("Show git diff between branches",                 None),
    "branches":  ("List git branches",                              cmd_branches),
    "test":      ("Run tests on the target repo",                   None),
    "review":    ("Review code changes with AI",                    cmd_review),
    "pipeline":  ("Manage CI/CD pipeline [start|status|advance|rollback]", None),
    "setup":     ("Full interactive setup wizard",                  None),
    "curls":     ("Show all API curl commands",                     cmd_curls),
    "update":    ("Update code-agents to latest version",            cmd_update),
    "version":   ("Show version info",                              cmd_version),
    "version-bump": ("Bump version (major/minor/patch)",           cmd_version_bump),
    "standup":   ("Generate AI standup from git activity",          cmd_standup),
    "incident":  ("Investigate a service incident (runbook + RCA)", None),  # special handling (takes args)
    "release":   ("Automate release process end-to-end",            None),  # special handling (takes args)
    "oncall-report": ("Generate on-call handoff report",            None),  # special handling (takes args)
    "deadcode":  ("Find dead code — unused imports, functions, endpoints", None),  # special handling (takes args)
    "dead-code-eliminate": ("Cross-file dead code detection + safe removal", None),  # special handling (takes args)
    "commit":    ("Smart commit — conventional message from staged diff", None),  # special handling (takes args)
    "config-diff": ("Compare configs across environments",          None),  # special handling (takes args)
    "flags":     ("List feature flags in codebase",                 None),  # special handling (takes args)
    "onboard":   ("Generate onboarding guide for new developers",   None),  # special handling (takes args)
    "coverage-boost": ("Auto-boost test coverage — scan, analyze, generate tests", None),  # special handling (takes args)
    "gen-tests": ("AI test generation — auto-delegate to code-tester, write & verify", None),  # special handling (takes args)
    "watch": ("Watch mode — auto-lint, auto-test, auto-fix on file save", None),  # special handling (takes args)
    "sprint-velocity": ("Track sprint velocity across sprints from Jira", None),  # special handling (takes args)
    "security":  ("OWASP security scan — find vulnerabilities in code", None),  # special handling (takes args)
    "api-check": ("Compare API endpoints with last release for breaking changes", None),  # special handling (takes args)
    "qa-suite":  ("Generate QA regression test suite for the repo", None),  # special handling (takes args)
    "pr-preview": ("Preview what a PR would look like before creating it", None),  # special handling (takes args)
    "sprint-report": ("Generate sprint summary from Jira + git + builds", None),  # special handling (takes args)
    "apidoc":    ("Generate API documentation from source code",    None),  # special handling (takes args)
    "perf-baseline": ("Record or compare performance baseline",     None),  # special handling (takes args)
    "completions": ("Generate shell completion script",             None),  # special handling
    "complexity": ("Analyze code complexity (cyclomatic, nesting depth)", None),  # special handling (takes args)
    "techdebt":  ("Scan for tech debt (TODOs, deprecated, skipped tests)", None),  # special handling (takes args)
    "changelog": ("Generate changelog from conventional commits",   None),  # special handling (takes args)
    "changelog-gen": ("Generate changelog with PR enrichment between refs", None),  # special handling (takes args)
    "env-health": ("Check environment health (ArgoCD, Jenkins, Jira, Kibana)", None),  # special handling (takes args)
    "morning":   ("Morning autopilot — git pull, build, Jira, tests, alerts", None),  # special handling (takes args)
    "pre-push-check": ("Pre-push checklist — tests, secrets, TODOs, lint", None),  # special handling (takes args)
    "pre-push":  ("Pre-push checklist [install|check]",             None),  # special handling (takes args)
    "watchdog":  ("Post-deploy watchdog — monitor error rate after deploy", None),  # special handling (takes args)
    "auto-review": ("Automated code review — diff analysis + AI review", None),  # special handling (takes args)
    "debug":     ("Autonomous debug — reproduce, trace, root-cause, fix, verify", None),  # special handling (takes args)
    "review-fix": ("AI code review with auto-fix — review + fix + PR comments", None),  # special handling (takes args)
    "bench-compare": ("Compare benchmark runs for quality regressions", None),  # special handling (takes args)
    "bench-trend": ("Show benchmark quality trend over time", None),  # special handling (takes args)
    "export":    ("Export agents/skills for Claude Code or Cursor [--claude-code|--cursor|--all]", None),  # handler set after definition
    "translate": ("Translate code between languages (regex-based scaffolding)", None),  # special handling (takes args)
    "lang-migrate": ("Migrate a module to another programming language", None),  # special handling (takes args)
    "preview": ("Live preview server — serve static files with auto-reload", None),  # special handling (takes args)
}


def cmd_export(args: list[str] = None):
    """Export code-agents for Claude Code CLI plugin or Cursor IDE."""
    args = args or []

    do_claude = "--claude-code" in args or "--all" in args
    do_cursor = "--cursor" in args or "--all" in args
    output = None
    install = "--install" in args

    for i, a in enumerate(args):
        if a == "--output" and i + 1 < len(args):
            output = args[i + 1]

    if not do_claude and not do_cursor:
        print("  Usage: code-agents export [--claude-code] [--cursor] [--all]")
        print()
        print("  Options:")
        print("    --claude-code    Export as Claude Code CLI plugin")
        print("    --cursor         Export .cursorrules + .cursor/ for Cursor IDE")
        print("    --all            Export for both Claude Code and Cursor")
        print("    --output DIR     Output directory (default: ./code-agents-plugin)")
        print("    --install        Auto-install after export")
        print()
        print("  Examples:")
        print("    code-agents export --claude-code")
        print("    code-agents export --cursor --install")
        print("    code-agents export --all --output ~/my-export")
        return

    from pathlib import Path
    agents_dir = str(Path(__file__).resolve().parent.parent.parent / "agents")

    if do_claude:
        from code_agents.tools.plugin_exporter import export_claude_code_plugin
        plugin_dir = output or "code-agents-plugin"
        print(f"  Exporting Claude Code plugin to: {plugin_dir}")
        stats = export_claude_code_plugin(plugin_dir, agents_dir)
        print(f"  ✓ Exported {stats.get('agents', 0)} agents, {stats.get('skills', 0)} skills")
        if install:
            import subprocess
            print("  Installing into Claude Code...")
            result = subprocess.run(
                ["claude", "plugin", "install", "--plugin-dir", plugin_dir],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print("  ✓ Plugin installed into Claude Code")
            else:
                print(f"  ✗ Install failed: {result.stderr.strip()}")
                print(f"  Manual: claude --plugin-dir {plugin_dir}")
        print()

    if do_cursor:
        from code_agents.tools.cursor_exporter import export_cursor
        repo_path = os.getenv("TARGET_REPO_PATH", os.getcwd())
        print(f"  Exporting Cursor config to: {repo_path}")
        stats = export_cursor(repo_path, agents_dir)
        print(f"  ✓ Generated .cursorrules ({stats.get('agents', 0)} agents, {stats.get('skills', 0)} skills)")
        print(f"  ✓ Generated .cursor/mcp.json")
        print()


# ---------------------------------------------------------------------------
# Completions and help (extracted to cli_completions.py)
# ---------------------------------------------------------------------------

from .cli_completions import (  # noqa: F401
    _AGENT_NAMES_FOR_COMPLETION, _SUBCOMMANDS,
    _generate_zsh_completion, _generate_bash_completion,
    cmd_completions, cmd_help,
)


def cmd_plugin(args: list[str] = None):
    """Manage IDE extensions — build, install, test, publish."""
    args = args or sys.argv[2:]
    sub = args[0] if args else "list"
    name = args[1] if len(args) > 1 else "all"

    from pathlib import Path
    import subprocess as sp
    import shutil

    ext_dir = Path(__file__).resolve().parent.parent.parent / "extensions"
    if not ext_dir.exists():
        print("  Extensions directory not found.")
        return

    repo_root = ext_dir.parent

    plugins = {
        "vscode": {
            "dir": ext_dir / "vscode",
            "built": (ext_dir / "vscode" / "dist" / "extension.js").exists(),
            "package": list((ext_dir / "vscode").glob("*.vsix")),
        },
        "intellij": {
            "dir": ext_dir / "intellij",
            "built": (ext_dir / "intellij" / "build" / "distributions").exists(),
            "package": list((ext_dir / "intellij" / "build" / "distributions").glob("*.zip")) if (ext_dir / "intellij" / "build" / "distributions").exists() else [],
        },
        "chrome": {
            "dir": ext_dir / "chrome",
            "built": (ext_dir / "chrome" / "manifest.json").exists(),
            "package": [],
        },
    }

    if sub == "list":
        print()
        print("  IDE Extensions")
        print("  " + "─" * 40)
        for pname, info in plugins.items():
            status = "✓ built" if info["built"] else "· not built"
            pkg = f" ({info['package'][0].name})" if info["package"] else ""
            print(f"  {pname:12s}  {status}{pkg}")
        print()
        print("  Commands:")
        print("    code-agents plugin build [name|all]    Build extension")
        print("    code-agents plugin install [name]      Install into IDE")
        print("    code-agents plugin test [name|all]     Run tests")
        print("    code-agents plugin dev [name]          Dev mode instructions")
        print("    code-agents plugin watch [name]        Hot-reload dev server")
        print("    code-agents plugin status              Server + build status")
        print("    code-agents plugin open [name]         Open in IDE")
        print("    code-agents plugin publish [name]      Publish to marketplace")
        print("    code-agents plugin validate [--fix]    Check package.json repository fields (vsce)")
        print("    code-agents plugin package [name]      Build .vsix (vscode) with validation")
        print()
        return

    if sub == "validate":
        from code_agents.tools.extension_repositories import (
            apply_default_repositories,
            format_validation_failure,
            validate_extension_repositories,
        )
        if "--fix" in args:
            dry = "--dry-run" in args
            ok, msgs = apply_default_repositories(repo_root, dry_run=dry)
            for m in msgs:
                print(f"  {m}")
            if not ok:
                _, errs = validate_extension_repositories(repo_root)
                print(format_validation_failure(repo_root, errs))
                return
            print("  ✓ Extension package.json repository fields are valid.")
            return
        ok, errs = validate_extension_repositories(repo_root)
        if ok:
            print("  ✓ Extension package.json repository fields are valid.")
            return
        print(format_validation_failure(repo_root, errs))
        return

    targets = list(plugins.keys()) if name == "all" else [name]
    for t in targets:
        if t not in plugins:
            print(f"  Unknown plugin: {t} (available: vscode, intellij, chrome)")
            continue

    if sub == "build":
        from code_agents.tools.vscode_extension import build_vscode_extension

        for t in targets:
            p = plugins.get(t)
            if not p:
                continue
            print(f"  Building {t}...")
            try:
                if t == "vscode":
                    build_vscode_extension(p["dir"])
                    print(f"  ✓ {t} built → dist/extension.js")
                elif t == "intellij":
                    gradle = str(p["dir"] / "gradlew") if (p["dir"] / "gradlew").exists() else "gradle"
                    if gradle == "gradle" and shutil.which("gradle"):
                        sp.run(["gradle", "wrapper", "--gradle-version=8.13"], cwd=str(p["dir"]), check=True, capture_output=True)
                        gradle = str(p["dir"] / "gradlew")
                    sp.run([gradle, "buildPlugin"], cwd=str(p["dir"]), check=True, capture_output=True, timeout=300)
                    print(f"  ✓ {t} built → build/distributions/")
                elif t == "chrome":
                    print(f"  ✓ {t} is static (no build needed)")
            except Exception as e:
                print(f"  ✗ {t} build failed: {e}")

    elif sub == "install":
        from code_agents.tools.vscode_extension import install_vsix_with_code_cli, newest_vsix

        for t in targets:
            p = plugins.get(t)
            if not p:
                continue
            try:
                if t == "vscode":
                    vsix = newest_vsix(p["dir"])
                    if vsix is None:
                        print(f"  No .vsix found. Run: code-agents plugin build vscode")
                        print(f"  Then: code-agents plugin package vscode")
                        continue
                    install_vsix_with_code_cli(vsix)
                    print(f"  ✓ VS Code extension installed: {vsix.name}")
                elif t == "intellij":
                    zips = list((p["dir"] / "build" / "distributions").glob("*.zip")) if (p["dir"] / "build" / "distributions").exists() else []
                    if not zips:
                        print(f"  No plugin ZIP found. Run: code-agents plugin build intellij")
                        continue
                    print(f"  ✓ IntelliJ plugin built: {zips[0].name}")
                    print(f"  Install manually: IDE → Settings → Plugins → Install from disk → {zips[0]}")
                elif t == "chrome":
                    print(f"  Chrome extension at: {p['dir']}")
                    print(f"  Install: chrome://extensions → Load unpacked → select {p['dir']}")
            except Exception as e:
                print(f"  ✗ {t} install failed: {e}")

    elif sub == "test":
        for t in targets:
            p = plugins.get(t)
            if not p:
                continue
            print(f"  Testing {t}...")
            try:
                if t == "vscode":
                    sp.run(["npm", "test"], cwd=str(p["dir"]), check=True)
                elif t == "intellij":
                    gradle = str(p["dir"] / "gradlew") if (p["dir"] / "gradlew").exists() else "gradle"
                    sp.run([gradle, "test"], cwd=str(p["dir"]), check=True, timeout=120)
                elif t == "chrome":
                    print(f"  No tests for Chrome extension")
            except Exception as e:
                print(f"  ✗ {t} tests failed: {e}")

    elif sub == "dev":
        t = targets[0] if targets else "vscode"
        p = plugins.get(t)
        if not p:
            return
        print(f"  Starting {t} dev mode...")
        if t == "vscode":
            print(f"  Run these in separate terminals:")
            print(f"    cd extensions/vscode && npm run watch")
            print(f"    cd extensions/vscode/webview-ui && npm run dev")
            print(f"    Press F5 in VS Code to launch Extension Dev Host")
        elif t == "intellij":
            print(f"  Run: cd extensions/intellij && ./gradlew runIde")

    elif sub == "package":
        from code_agents.tools.extension_repositories import validate_or_exit
        from code_agents.tools.vscode_extension import newest_vsix, run_vsce_package

        pname = args[1] if len(args) > 1 else "vscode"
        if pname != "vscode":
            print(f"  Only vscode supports .vsix packaging here (got {pname!r}).")
            return
        validate_or_exit(repo_root)
        p = plugins["vscode"]
        print("  Packaging VS Code extension (.vsix)...")
        r = run_vsce_package(p["dir"])
        if r == 0:
            vsix = newest_vsix(p["dir"])
            if vsix:
                print(f"  ✓ Created: {vsix}")
        else:
            print("  ✗ @vscode/vsce package failed — fix errors above, or run: code-agents plugin validate")
        return

    elif sub == "publish":
        t = targets[0] if targets else "vscode"
        p = plugins.get(t)
        if not p:
            return
        if t == "vscode":
            from code_agents.tools.extension_repositories import validate_or_exit

            validate_or_exit(repo_root)
            print(f"  Publishing VS Code extension...")
            sp.run(["npx", "--yes", "@vscode/vsce", "publish"], cwd=str(p["dir"]))
        elif t == "intellij":
            gradle = str(p["dir"] / "gradlew") if (p["dir"] / "gradlew").exists() else "gradle"
            print(f"  Publishing IntelliJ plugin...")
            sp.run([gradle, "publishPlugin"], cwd=str(p["dir"]))

    elif sub == "watch":
        t = targets[0] if targets else "vscode"
        p = plugins.get(t)
        if not p:
            return
        print(f"  Starting {t} watch mode (hot-reload)...")
        if t == "vscode":
            import threading
            def _watch_ext():
                sp.run(["node", "esbuild.mjs", "--watch"], cwd=str(p["dir"]))
            def _watch_webview():
                sp.run(["npx", "vite", "--host"], cwd=str(p["dir"] / "webview-ui"))
            print("  Starting extension watcher + webview dev server...")
            print("  Press Ctrl+C to stop")
            t1 = threading.Thread(target=_watch_ext, daemon=True)
            t2 = threading.Thread(target=_watch_webview, daemon=True)
            t1.start()
            t2.start()
            try:
                while t1.is_alive() or t2.is_alive():
                    t1.join(timeout=1)
                    t2.join(timeout=1)
            except KeyboardInterrupt:
                print("\n  Stopped.")
        elif t == "intellij":
            gradle = str(p["dir"] / "gradlew") if (p["dir"] / "gradlew").exists() else "gradle"
            sp.run([gradle, "runIde"], cwd=str(p["dir"]))

    elif sub == "status":
        from .cli_helpers import _server_url, _api_get
        url = _server_url()
        data = _api_get("/health")
        print()
        if data and data.get("status") == "ok":
            print(f"  ✓ Server connected at {url}")
            diag = _api_get("/diagnostics")
            if diag:
                print(f"    Agents: {len(diag.get('agents', []))}")
                print(f"    Version: {diag.get('package_version', '?')}")
        else:
            print(f"  ✗ Server not running at {url}")
            print(f"    Start with: code-agents start")
        print()
        for pname, info in plugins.items():
            status = "✓ built" if info["built"] else "· not built"
            print(f"  {pname:12s}  {status}")
        print()

    elif sub == "open":
        t = targets[0] if targets else "vscode"
        if t == "vscode":
            if shutil.which("code"):
                sp.run(["code", "--goto", str(ext_dir / "vscode" / "src" / "extension.ts")])
                print("  ✓ Opened VS Code extension project")
            else:
                print("  VS Code CLI not in PATH")
                print("  VS Code → Cmd+Shift+P → 'Shell Command: Install code in PATH'")
        elif t == "intellij":
            if sys.platform == "darwin":
                sp.run(["open", str(ext_dir / "intellij")])
            elif sys.platform == "linux":
                sp.run(["xdg-open", str(ext_dir / "intellij")])
            else:
                print(f"  Open: {ext_dir / 'intellij'}")
        elif t == "chrome":
            print(f"  Chrome extension at: {ext_dir / 'chrome'}")
            print(f"  Load: chrome://extensions → Load unpacked → select the folder")

    else:
        print(f"  Unknown subcommand: {sub}")
        print(f"  Usage: code-agents plugin [list|build|install|test|dev|publish|watch|status|open] [name]")


def cmd_readme(args: list[str] = None):
    """Display the project README in the terminal with rich formatting."""
    from pathlib import Path

    # Find README — check user's CWD first, then code-agents installation
    cwd = _user_cwd()
    readme_path = None

    for candidate in [
        Path(cwd) / "README.md",
        Path(cwd) / "readme.md",
        Path(__file__).resolve().parent.parent.parent / "README.md",
    ]:
        if candidate.exists():
            readme_path = candidate
            break

    if not readme_path:
        print("  No README.md found.")
        return

    content = readme_path.read_text(encoding="utf-8")

    # Try rich markdown rendering first
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        console = Console()
        md = Markdown(content)
        console.print(md)
        return
    except ImportError:
        pass

    # Fallback: basic ANSI color rendering
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

    for line in content.split("\n"):
        if line.startswith("# "):
            print(f"\n{BOLD}{CYAN}{line[2:]}{RESET}\n")
        elif line.startswith("## "):
            print(f"\n{BOLD}{GREEN}{line[3:]}{RESET}")
        elif line.startswith("### "):
            print(f"\n{BOLD}{YELLOW}{line[4:]}{RESET}")
        elif line.startswith("```"):
            print(f"{DIM}{line}{RESET}")
        elif line.startswith("- ") or line.startswith("* "):
            print(f"  {DIM}•{RESET} {line[2:]}")
        elif line.startswith("| "):
            print(f"  {DIM}{line}{RESET}")
        else:
            print(f"  {line}")


def _resolve_cli_handler(fn: Any) -> Any:
    """Re-resolve a handler from its defining module so tests can patch originals."""
    if not callable(fn):
        return fn
    mod_name = getattr(fn, "__module__", None)
    name = getattr(fn, "__name__", None)
    if not mod_name or not name:
        return fn
    try:
        mod = importlib.import_module(mod_name)
        return getattr(mod, name, fn)
    except Exception:
        return fn


def main():
    """CLI entry point — dispatches to subcommands via registry."""
    from .registry import COMMAND_REGISTRY

    args = sys.argv[1:]
    if not args:
        cmd_start()
        return

    command = args[0].lower()
    rest = args[1:]

    entry = COMMAND_REGISTRY.get(command)
    if not entry:
        for _cmd, e in COMMAND_REGISTRY.items():
            if command in e.aliases:
                entry = e
                break

    try:
        if entry:
            h = entry.handler
            if h == "special:chat":
                if "--legacy" in rest:
                    # Legacy Python REPL
                    from code_agents.chat.chat import chat_main
                    chat_main([a for a in rest if a != "--legacy"])
                else:
                    # Default: TypeScript terminal (direct Ink, no oclif build needed)
                    import subprocess as _sp
                    _ts_root = _find_code_agents_home() / "terminal"
                    _ts_chat = _ts_root / "bin" / "chat.ts"
                    if _ts_chat.exists():
                        # Auto-install node_modules if missing
                        if not (_ts_root / "node_modules").exists():
                            print("  Installing TS terminal dependencies...")
                            _sp.run(["npm", "ci", "--quiet"], cwd=str(_ts_root),
                                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                        _sp.run(["npx", "tsx", str(_ts_chat)] + rest)
                    else:
                        # Fallback to Python REPL if TS terminal not available
                        from code_agents.chat.chat import chat_main
                        chat_main(rest)
            elif h == "special:setup":
                from code_agents.setup.setup import main as setup_main
                setup_main()
            elif entry.takes_args:
                _resolve_cli_handler(h)(rest)
            else:
                _resolve_cli_handler(h)()
        else:
            print(f"  Unknown command: {command}")
            print(f"  Run 'code-agents help' for usage.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n  Cancelled.")
    except EOFError:
        print("\n  Cancelled.")


if __name__ == "__main__":
    main()
