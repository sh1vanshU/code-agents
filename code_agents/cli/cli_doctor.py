"""CLI doctor command — comprehensive health check and diagnostics."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .cli_helpers import (
    _colors, _server_url, _api_get, _load_env,
    _user_cwd, _find_code_agents_home,
)

logger = logging.getLogger("code_agents.cli.cli_doctor")


def cmd_doctor():
    """Diagnose common issues — comprehensive health check."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    issues = 0
    warnings = 0

    print()
    print(bold("  Code Agents Doctor"))
    print(bold("  " + "═" * 50))

    # ── Environment ──
    print()
    print(bold("  Environment"))
    print(bold("  " + "─" * 40))

    # Python
    if sys.version_info >= (3, 10):
        print(green(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    else:
        print(red(f"  ✗ Python {sys.version_info.major}.{sys.version_info.minor} — requires 3.10+"))
        issues += 1

    # Poetry
    import shutil
    if shutil.which("poetry"):
        print(green("  ✓ Poetry installed"))
    else:
        print(yellow("  ! Poetry not found in PATH"))
        warnings += 1

    # Git
    if shutil.which("git"):
        print(green("  ✓ Git installed"))
    else:
        print(red("  ✗ Git not found — required for git-ops"))
        issues += 1

    # ── Repository ──
    print()
    print(bold("  Repository"))
    print(bold("  " + "─" * 40))

    # Git repo
    git_root = None
    check = cwd
    while True:
        if os.path.isdir(os.path.join(check, ".git")):
            git_root = check
            break
        parent = os.path.dirname(check)
        if parent == check:
            break
        check = parent

    if git_root:
        repo_name = os.path.basename(git_root)
        print(green(f"  ✓ Git repo: {repo_name} ({git_root})"))
    else:
        print(yellow("  ! No git repo detected — chat/git-ops won't know your project"))
        warnings += 1

    # Config files
    from code_agents.core.env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME
    from code_agents.setup.setup import parse_env_file

    if GLOBAL_ENV_PATH.is_file():
        g_vars = parse_env_file(GLOBAL_ENV_PATH)
        print(green(f"  ✓ Global config: {GLOBAL_ENV_PATH} ({len(g_vars)} variables)"))
    else:
        print(red(f"  ✗ No global config — run: code-agents init"))
        issues += 1

    repo_env = os.path.join(cwd, PER_REPO_FILENAME)
    if os.path.isfile(repo_env):
        r_vars = parse_env_file(Path(repo_env))
        print(green(f"  ✓ Repo config: {repo_env} ({len(r_vars)} variables)"))
    else:
        print(dim(f"  · No repo config ({PER_REPO_FILENAME}) — optional"))

    # Legacy .env fallback
    legacy_env = os.path.join(cwd, ".env")
    if os.path.isfile(legacy_env):
        print(yellow(f"  ! Legacy .env found — consider running: code-agents migrate"))
        warnings += 1
    elif os.path.isdir(legacy_env):
        print(dim(f"  · .env is a directory (ignored)"))

    # ── Backend ──
    print()
    print(bold("  Backend"))
    print(bold("  " + "─" * 40))

    be = os.getenv("CODE_AGENTS_BACKEND", "").strip().lower() or "local"
    print(dim(f"  · Effective backend: {be}"))

    # API keys
    cursor_key = os.getenv("CURSOR_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    cursor_url = os.getenv("CURSOR_API_URL", "")
    local_llm_url = os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip()

    if cursor_key:
        print(green(f"  ✓ CURSOR_API_KEY set ({cursor_key[:8]}...)"))
    else:
        if be in ("cursor", "cursor_http"):
            print(yellow("  ! CURSOR_API_KEY not set"))
        else:
            print(dim("  · CURSOR_API_KEY not set (only needed for Cursor backend)"))

    if anthropic_key:
        print(green(f"  ✓ ANTHROPIC_API_KEY set ({anthropic_key[:8]}...)"))
    else:
        print(dim("  · ANTHROPIC_API_KEY not set (optional)"))

    if local_llm_url:
        print(green(f"  ✓ CODE_AGENTS_LOCAL_LLM_URL set"))
    else:
        print(dim("  · CODE_AGENTS_LOCAL_LLM_URL not set"))

    if cursor_url:
        print(green(f"  ✓ CURSOR_API_URL set (HTTP mode for Cursor)"))
    else:
        print(dim("  · CURSOR_API_URL not set"))

    if be == "claude-cli":
        has_backend = True
    elif be == "local":
        has_backend = bool(local_llm_url or cursor_url)
    elif be == "cursor":
        has_backend = bool(cursor_key)
    elif be == "claude":
        has_backend = bool(anthropic_key)
    elif be == "cursor_http":
        has_backend = bool(cursor_url and cursor_key)
    else:
        has_backend = bool(cursor_key or anthropic_key or local_llm_url or cursor_url)

    if not has_backend:
        print(red("  ✗ No backend configured — run: code-agents init (local needs CODE_AGENTS_LOCAL_LLM_URL or CURSOR_API_URL)"))
        issues += 1

    # Workspace trust (only for CLI mode with cursor backend)
    if be == "cursor" and cursor_key and not cursor_url:
        import subprocess as _sp
        from code_agents.core.cursor_cli import cursor_cli_display_name, cursor_cli_on_path

        cli_path = cursor_cli_on_path()
        _cli_hint = cursor_cli_display_name()
        if cli_path:
            try:
                _trust_result = _sp.run(
                    [cli_path, "--print", "--output-format", "stream-json", "agent", "-"],
                    cwd=cwd, input="hi", capture_output=True, text=True, timeout=10,
                )
                if "Workspace Trust Required" in (_trust_result.stderr or ""):
                    # Auto-trust with --trust flag
                    print(dim("  · Trusting workspace..."))
                    _fix = _sp.run(
                        [cli_path, "--trust", "--print", "--output-format", "stream-json", "agent", "-"],
                        cwd=cwd, input="hi", capture_output=True, text=True, timeout=15,
                    )
                    if "Workspace Trust Required" not in (_fix.stderr or ""):
                        print(green(f"  ✓ Workspace auto-trusted by {_cli_hint}"))
                    else:
                        print(red(f"  ✗ Workspace not trusted — auto-trust failed"))
                        print(dim(f"    Run: cd {cwd} && {_cli_hint} agent"))
                        issues += 1
                else:
                    print(green(f"  ✓ Workspace trusted by {_cli_hint}"))
            except (Exception,):
                print(dim("  · Could not check workspace trust"))

    # cursor-agent-sdk
    try:
        import cursor_agent_sdk
        print(green("  ✓ cursor-agent-sdk installed"))
    except ImportError:
        if be == "cursor" and cursor_key and not cursor_url:
            print(yellow("  ! cursor-agent-sdk not installed (needed for Cursor CLI backend)"))
            warnings += 1
        else:
            print(dim("  · cursor-agent-sdk not installed (optional for local / HTTP-only)"))

    # claude-agent-sdk (core dependency)
    try:
        import claude_agent_sdk
        print(green("  ✓ claude-agent-sdk installed"))
    except ImportError:
        print(red("  ✗ claude-agent-sdk not installed — run: poetry install"))
        issues += 1

    # ── Server ──
    print()
    print(bold("  Server"))
    print(bold("  " + "─" * 40))

    url = _server_url()
    data = _api_get("/health")
    if data and data.get("status") == "ok":
        print(green(f"  ✓ Server running at {url}"))
        # Check agents loaded
        diag = _api_get("/diagnostics")
        if diag:
            agent_count = len(diag.get("agents", []))
            print(green(f"  ✓ {agent_count} agents loaded"))
            print(f"    Version: {diag.get('package_version', '?')}")
    else:
        print(yellow(f"  ! Server not running at {url}"))
        print(dim(f"    Start with: code-agents start"))
        warnings += 1

    # Logs
    log_dir = _find_code_agents_home() / "logs"
    log_file = log_dir / "code-agents.log"
    if log_file.exists():
        size = log_file.stat().st_size
        size_str = f"{size / 1024:.0f}KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f}MB"
        print(green(f"  ✓ Log file: {size_str}"))
    elif log_dir.exists():
        print(dim("  · Log directory exists (no log file yet)"))
    else:
        print(dim("  · No log directory (created on first server start)"))

    # ── Integrations ──
    print()
    print(bold("  Integrations"))
    print(bold("  " + "─" * 40))

    # Jenkins
    jenkins_url = os.getenv("JENKINS_URL", "")
    if jenkins_url:
        jenkins_user = os.getenv("JENKINS_USERNAME", "")
        jenkins_token = os.getenv("JENKINS_API_TOKEN", "")
        jenkins_build = os.getenv("JENKINS_BUILD_JOB", "")
        jenkins_deploy_dev = os.getenv("JENKINS_DEPLOY_JOB_DEV", "")
        jenkins_deploy_qa = os.getenv("JENKINS_DEPLOY_JOB_QA", "")
        jenkins_deploy = os.getenv("JENKINS_DEPLOY_JOB", "")
        if jenkins_user and jenkins_token:
            print(green(f"  ✓ Jenkins: {jenkins_url}"))
            print(f"    User: {jenkins_user} | Token: {'*' * min(len(jenkins_token), 6)}{'…' if len(jenkins_token) > 6 else ''}")
            if jenkins_build:
                print(f"    Build job: {jenkins_build}")
            else:
                print(yellow("    ! JENKINS_BUILD_JOB not set"))
                warnings += 1
            if jenkins_deploy_dev:
                print(f"    Deploy job (Dev): {jenkins_deploy_dev}")
            elif jenkins_deploy:
                print(f"    Deploy job: {jenkins_deploy}")
            else:
                print(dim("    · JENKINS_DEPLOY_JOB_DEV not set (optional)"))
            if jenkins_deploy_qa:
                print(f"    Deploy job (QA):  {jenkins_deploy_qa}")
            else:
                print(dim("    · JENKINS_DEPLOY_JOB_QA not set (optional)"))
            # Warn if job looks like a full URL
            for job_var, job_val in [("BUILD", jenkins_build), ("DEPLOY_JOB_DEV", jenkins_deploy_dev), ("DEPLOY_JOB_QA", jenkins_deploy_qa)]:
                if job_val and job_val.startswith("http"):
                    print(red(f"    ✗ JENKINS_{job_var} looks like a URL — use job path only"))
                    print(dim(f"      e.g. 'pg2/pg2-dev-build-jobs' not '{job_val}'"))
                    issues += 1
        else:
            print(red("  ✗ Jenkins URL set but missing USERNAME or API_TOKEN"))
            issues += 1
    else:
        print(dim("  · Jenkins not configured"))

    # ArgoCD
    argocd_url = os.getenv("ARGOCD_URL", "")
    if argocd_url:
        argocd_user = os.getenv("ARGOCD_USERNAME", "")
        argocd_pass = os.getenv("ARGOCD_PASSWORD", "")
        argocd_app = os.getenv("ARGOCD_APP_NAME", "")
        if argocd_user and argocd_pass:
            print(green(f"  ✓ ArgoCD: {argocd_url}"))
            print(f"    User: {argocd_user} | Password: {'*' * min(len(argocd_pass), 6)}{'…' if len(argocd_pass) > 6 else ''}")
            if argocd_app:
                print(f"    App: {argocd_app}")
            else:
                print(yellow("    ! ARGOCD_APP_NAME not set"))
                warnings += 1
        else:
            print(red("  ✗ ARGOCD_URL set but ARGOCD_USERNAME/ARGOCD_PASSWORD missing"))
            issues += 1
    else:
        print(dim("  · ArgoCD not configured"))

    # Elasticsearch
    es_url = os.getenv("ELASTICSEARCH_URL", "") or os.getenv("ELASTICSEARCH_CLOUD_ID", "")
    es_api_key = os.getenv("ELASTICSEARCH_API_KEY", "")
    es_user = os.getenv("ELASTICSEARCH_USERNAME", "")
    es_pass = os.getenv("ELASTICSEARCH_PASSWORD", "")
    if es_url:
        if es_api_key or (es_user and es_pass):
            _es_display = os.getenv("ELASTICSEARCH_URL", es_url)
            _es_auth = "API key" if es_api_key else f"user: {es_user}"
            print(green(f"  ✓ Elasticsearch: {_es_display}"))
            print(f"    Auth: {_es_auth}")
        else:
            print(yellow(f"  ! Elasticsearch URL set but missing API_KEY or USERNAME/PASSWORD"))
            warnings += 1
    else:
        print(dim("  · Elasticsearch not configured"))

    # Jira
    jira_url = os.getenv("JIRA_URL", "")
    if jira_url:
        jira_email = os.getenv("JIRA_EMAIL", "")
        jira_token = os.getenv("JIRA_API_TOKEN", "")
        if jira_email and jira_token:
            print(green(f"  ✓ Jira: {jira_url}"))
            print(f"    Email: {jira_email} | Token: {'*' * min(len(jira_token), 6)}{'…' if len(jira_token) > 6 else ''}")
        else:
            print(red("  ✗ JIRA_URL set but missing EMAIL or API_TOKEN"))
            issues += 1
    else:
        print(dim("  · Jira not configured"))

    # Kibana
    kibana_url = os.getenv("KIBANA_URL", "")
    if kibana_url:
        kibana_user = os.getenv("KIBANA_USERNAME", "")
        kibana_pass = os.getenv("KIBANA_PASSWORD", "")
        if kibana_user and kibana_pass:
            print(green(f"  ✓ Kibana: {kibana_url}"))
            print(f"    User: {kibana_user} | Password: {'*' * min(len(kibana_pass), 6)}{'…' if len(kibana_pass) > 6 else ''}")
        else:
            print(yellow("  ! KIBANA_URL set but missing USERNAME or PASSWORD"))
            warnings += 1
    else:
        print(dim("  · Kibana not configured"))

    # Grafana
    grafana_url = os.getenv("GRAFANA_URL", "")
    if grafana_url:
        grafana_user = os.getenv("GRAFANA_USERNAME", "")
        grafana_pass = os.getenv("GRAFANA_PASSWORD", "")
        if grafana_user and grafana_pass:
            print(green(f"  ✓ Grafana: {grafana_url}"))
            print(f"    User: {grafana_user} | Password: {'*' * min(len(grafana_pass), 6)}{'…' if len(grafana_pass) > 6 else ''}")
        else:
            print(yellow("  ! GRAFANA_URL set but missing USERNAME or PASSWORD"))
            warnings += 1
    else:
        print(dim("  · Grafana not configured"))

    # Redash
    redash_url = os.getenv("REDASH_BASE_URL", "")
    redash_api_key = os.getenv("REDASH_API_KEY", "")
    redash_user = os.getenv("REDASH_USERNAME", "")
    redash_pass = os.getenv("REDASH_PASSWORD", "")
    if redash_url:
        if redash_api_key or (redash_user and redash_pass):
            _redash_auth = "API key" if redash_api_key else f"user: {redash_user}"
            print(green(f"  ✓ Redash: {redash_url}"))
            print(f"    Auth: {_redash_auth}")
        else:
            print(yellow(f"  ! Redash URL set but missing API_KEY or USERNAME/PASSWORD"))
            warnings += 1
    else:
        print(dim("  · Redash not configured"))

    # ── Integration Connectivity ──
    print()
    print(bold("  Integration Connectivity"))
    print(bold("  " + "─" * 40))

    try:
        import requests as _requests
        _has_requests = True
    except ImportError:
        _has_requests = False

    if not _has_requests:
        print(dim("  · requests library not installed — skipping connectivity checks"))
    else:
        _any_integration = False

        # Jenkins reachable
        if jenkins_url and os.getenv("JENKINS_USERNAME", "") and os.getenv("JENKINS_API_TOKEN", ""):
            _any_integration = True
            try:
                _resp = _requests.get(
                    f"{jenkins_url.rstrip('/')}/api/json",
                    auth=(os.getenv("JENKINS_USERNAME", ""), os.getenv("JENKINS_API_TOKEN", "")),
                    timeout=5,
                )
                if _resp.status_code < 400:
                    print(green(f"  ✓ Jenkins reachable ({_resp.status_code})"))
                else:
                    print(yellow(f"  ! Jenkins returned HTTP {_resp.status_code}"))
                    warnings += 1
            except Exception as _e:
                print(yellow(f"  ! Jenkins unreachable: {_e}"))
                warnings += 1

        # ArgoCD healthy — authenticate first, then check version
        _argocd_user = os.getenv("ARGOCD_USERNAME", "")
        _argocd_pass = os.getenv("ARGOCD_PASSWORD", "")
        if argocd_url and _argocd_user and _argocd_pass:
            _any_integration = True
            # Strip UI paths like /applications that users sometimes paste
            import re as _re
            _argocd_base = _re.sub(r'/(applications|settings|projects)(/.*)?$', '', argocd_url.rstrip("/"))
            try:
                # Get session token
                _login_resp = _requests.post(
                    f"{_argocd_base}/api/v1/session",
                    json={"username": _argocd_user, "password": _argocd_pass},
                    timeout=5,
                )
                if _login_resp.status_code != 200:
                    print(yellow(f"  ! ArgoCD login failed (HTTP {_login_resp.status_code})"))
                    warnings += 1
                else:
                    _token = _login_resp.json().get("token", "")
                    _resp = _requests.get(
                        f"{_argocd_base}/api/version",
                        headers={"Authorization": f"Bearer {_token}"},
                        timeout=5,
                    )
                    if _resp.status_code < 400:
                        _ver = _resp.json().get("Version", "")
                        _ver_info = f" {_ver}" if _ver else ""
                        print(green(f"  ✓ ArgoCD reachable{_ver_info}"))
                    else:
                        print(yellow(f"  ! ArgoCD returned HTTP {_resp.status_code}"))
                        warnings += 1
            except Exception as _e:
                print(yellow(f"  ! ArgoCD unreachable: {_e}"))
                warnings += 1

        # Jira connected
        if jira_url and os.getenv("JIRA_EMAIL", "") and os.getenv("JIRA_API_TOKEN", ""):
            _any_integration = True
            try:
                _resp = _requests.get(
                    f"{jira_url.rstrip('/')}/rest/api/2/myself",
                    auth=(os.getenv("JIRA_EMAIL", ""), os.getenv("JIRA_API_TOKEN", "")),
                    timeout=5,
                )
                if _resp.status_code < 400:
                    print(green(f"  ✓ Jira reachable ({_resp.status_code})"))
                else:
                    print(yellow(f"  ! Jira returned HTTP {_resp.status_code}"))
                    warnings += 1
            except Exception as _e:
                print(yellow(f"  ! Jira unreachable: {_e}"))
                warnings += 1

        # Kibana up
        if kibana_url and os.getenv("KIBANA_USERNAME", "") and os.getenv("KIBANA_PASSWORD", ""):
            _any_integration = True
            try:
                _resp = _requests.get(
                    f"{kibana_url.rstrip('/')}/api/status",
                    auth=(os.getenv("KIBANA_USERNAME", ""), os.getenv("KIBANA_PASSWORD", "")),
                    timeout=5,
                )
                if _resp.status_code < 400:
                    print(green(f"  ✓ Kibana reachable ({_resp.status_code})"))
                else:
                    print(yellow(f"  ! Kibana returned HTTP {_resp.status_code}"))
                    warnings += 1
            except Exception as _e:
                print(yellow(f"  ! Kibana unreachable: {_e}"))
                warnings += 1

        # Grafana up
        if grafana_url and os.getenv("GRAFANA_USERNAME", "") and os.getenv("GRAFANA_PASSWORD", ""):
            _any_integration = True
            try:
                _resp = _requests.get(
                    f"{grafana_url.rstrip('/')}/api/health",
                    auth=(os.getenv("GRAFANA_USERNAME", ""), os.getenv("GRAFANA_PASSWORD", "")),
                    timeout=5,
                )
                if _resp.status_code < 400:
                    print(green(f"  ✓ Grafana reachable ({_resp.status_code})"))
                else:
                    print(yellow(f"  ! Grafana returned HTTP {_resp.status_code}"))
                    warnings += 1
            except Exception as _e:
                print(yellow(f"  ! Grafana unreachable: {_e}"))
                warnings += 1

        # Elasticsearch reachable
        if es_url and (es_api_key or (es_user and es_pass)):
            _any_integration = True
            try:
                _es_base = os.getenv("ELASTICSEARCH_URL", "")
                if _es_base:
                    _es_headers: dict[str, str] = {}
                    _es_auth = None
                    if es_api_key:
                        _es_headers["Authorization"] = f"ApiKey {es_api_key}"
                    elif es_user and es_pass:
                        _es_auth = (es_user, es_pass)
                    _resp = _requests.get(
                        _es_base.rstrip("/"),
                        headers=_es_headers,
                        auth=_es_auth,
                        timeout=5,
                        verify=True,
                    )
                    if _resp.status_code < 400:
                        _es_info = ""
                        try:
                            _es_json = _resp.json()
                            _es_ver = _es_json.get("version", {}).get("number", "")
                            _es_name = _es_json.get("cluster_name", "")
                            if _es_ver:
                                _es_info = f" v{_es_ver}"
                            if _es_name:
                                _es_info += f" ({_es_name})"
                        except Exception:
                            pass
                        print(green(f"  ✓ Elasticsearch reachable{_es_info}"))
                    else:
                        print(yellow(f"  ! Elasticsearch returned HTTP {_resp.status_code}"))
                        warnings += 1
                else:
                    print(dim("  · Elasticsearch uses Cloud ID — connectivity check requires ELASTICSEARCH_URL"))
            except Exception as _e:
                print(yellow(f"  ! Elasticsearch unreachable: {_e}"))
                warnings += 1

        # Redash reachable
        if redash_url and (redash_api_key or (redash_user and redash_pass)):
            _any_integration = True
            try:
                _redash_headers: dict[str, str] = {}
                _redash_auth = None
                if redash_api_key:
                    _redash_headers["Authorization"] = f"Key {redash_api_key}"
                elif redash_user and redash_pass:
                    _redash_auth = (redash_user, redash_pass)
                _resp = _requests.get(
                    f"{redash_url.rstrip('/')}/api/session",
                    headers=_redash_headers,
                    auth=_redash_auth,
                    timeout=5,
                )
                if _resp.status_code < 400:
                    print(green(f"  ✓ Redash reachable ({_resp.status_code})"))
                else:
                    print(yellow(f"  ! Redash returned HTTP {_resp.status_code}"))
                    warnings += 1
            except Exception as _e:
                print(yellow(f"  ! Redash unreachable: {_e}"))
                warnings += 1

        if not _any_integration:
            print(dim("  · No integrations configured — nothing to check"))

    # ── Git Health ──
    if git_root:
        print()
        print(bold("  Git Health"))
        print(bold("  " + "─" * 40))

        # Current branch
        try:
            _branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            _current_branch = _branch_result.stdout.strip()
            if _current_branch:
                print(green(f"  ✓ Branch: {_current_branch}"))
        except Exception:
            _current_branch = None
            print(dim("  · Could not determine current branch"))

        # Clean tree
        try:
            _status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            _dirty_lines = [l for l in _status_result.stdout.strip().splitlines() if l.strip()]
            if _dirty_lines:
                print(yellow(f"  ! Working tree has {len(_dirty_lines)} modified/untracked file(s)"))
                warnings += 1
            else:
                print(green("  ✓ Working tree clean"))
        except Exception:
            print(dim("  · Could not check working tree status"))

        # Behind remote
        try:
            _behind_result = subprocess.run(
                ["git", "rev-list", "HEAD..@{upstream}", "--count"],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            if _behind_result.returncode == 0:
                _behind_count = int(_behind_result.stdout.strip())
                if _behind_count > 0:
                    print(yellow(f"  ! {_behind_count} commit(s) behind remote"))
                    warnings += 1
                else:
                    print(green("  ✓ Up to date with remote"))
        except Exception:
            print(dim("  · Could not check remote status (no upstream?)"))

        # Ahead of remote
        try:
            _ahead_result = subprocess.run(
                ["git", "rev-list", "@{upstream}..HEAD", "--count"],
                cwd=cwd, capture_output=True, text=True, timeout=10,
            )
            if _ahead_result.returncode == 0:
                _ahead_count = int(_ahead_result.stdout.strip())
                if _ahead_count > 0:
                    print(dim(f"  · {_ahead_count} commit(s) ahead of remote"))
        except Exception:
            pass  # already warned about no upstream above

        # Merge conflicts
        _merge_head = os.path.join(git_root, ".git", "MERGE_HEAD")
        if os.path.isfile(_merge_head):
            print(yellow("  ! Merge in progress — resolve conflicts before proceeding"))
            warnings += 1

    # ── Build & Test ──
    print()
    print(bold("  Build & Test"))
    print(bold("  " + "─" * 40))

    # Build check
    _build_cmd = os.getenv("CODE_AGENTS_BUILD_CMD", "")
    if _build_cmd:
        print(dim(f"  · Running build: {_build_cmd}"))
        try:
            _build_result = subprocess.run(
                _build_cmd, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=120,
            )
            if _build_result.returncode == 0:
                print(green("  ✓ Build passed"))
            else:
                _stderr_line = (_build_result.stderr or "").strip().splitlines()[-1] if _build_result.stderr else ""
                print(yellow(f"  ! Build failed (exit {_build_result.returncode})"))
                if _stderr_line:
                    print(dim(f"    {_stderr_line[:120]}"))
                warnings += 1
        except subprocess.TimeoutExpired:
            print(yellow("  ! Build timed out (120s limit)"))
            warnings += 1
        except Exception as _e:
            print(yellow(f"  ! Build error: {_e}"))
            warnings += 1
    else:
        print(dim("  · CODE_AGENTS_BUILD_CMD not set — skipping build check"))

    # Test check
    _test_cmd = os.getenv("CODE_AGENTS_TEST_CMD", "")
    if not _test_cmd:
        # Auto-detect test runner
        if os.path.isfile(os.path.join(cwd, "pyproject.toml")) or os.path.isfile(os.path.join(cwd, "pytest.ini")):
            _test_cmd = "python -m pytest --tb=no -q"
        elif os.path.isfile(os.path.join(cwd, "pom.xml")):
            _test_cmd = "mvn test -q"
        elif os.path.isfile(os.path.join(cwd, "package.json")):
            _test_cmd = "npm test"

    if _test_cmd:
        print(dim(f"  · Running tests: {_test_cmd}"))
        try:
            _test_result = subprocess.run(
                _test_cmd, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=120,
            )
            if _test_result.returncode == 0:
                # Show summary line (last non-empty line of stdout)
                _out_lines = [l for l in (_test_result.stdout or "").strip().splitlines() if l.strip()]
                _summary = _out_lines[-1] if _out_lines else "passed"
                print(green(f"  ✓ Tests passed — {_summary[:120]}"))
            else:
                _out_lines = [l for l in (_test_result.stdout or "").strip().splitlines() if l.strip()]
                _summary = _out_lines[-1] if _out_lines else "failed"
                print(yellow(f"  ! Tests failed (exit {_test_result.returncode}) — {_summary[:120]}"))
                warnings += 1
        except subprocess.TimeoutExpired:
            print(yellow("  ! Tests timed out (120s limit)"))
            warnings += 1
        except Exception as _e:
            print(yellow(f"  ! Test error: {_e}"))
            warnings += 1
    else:
        print(dim("  · No test runner detected — skipping test check"))

    # ── IDE Extensions ──
    print()
    print(bold("  IDE Extensions"))
    print(bold("  " + "─" * 40))

    import shutil as _ext_shutil

    # Node.js / npm
    _node = _ext_shutil.which("node")
    _npm = _ext_shutil.which("npm")
    if _node:
        try:
            _node_result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            _node_ver = _node_result.stdout.strip() if _node_result.returncode == 0 else None
            print(green(f"  ✓ Node.js {_node_ver or '(version unknown)'}"))
        except Exception:
            print(yellow("  ! Node.js found but version check failed"))
            warnings += 1
    else:
        print(red("  ✗ Node.js not found — required for VS Code extension"))
        print(dim("    Install: https://nodejs.org/ or brew install node"))
        issues += 1

    if _npm:
        try:
            _npm_result = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5)
            _npm_ver = _npm_result.stdout.strip() if _npm_result.returncode == 0 else None
            print(green(f"  ✓ npm {_npm_ver or '(version unknown)'}"))
        except Exception:
            print(yellow("  ! npm found but version check failed"))
            warnings += 1
    else:
        print(red("  ✗ npm not found — required for VS Code extension"))
        print(dim("    Comes with Node.js: https://nodejs.org/"))
        issues += 1

    # Java
    _java = _ext_shutil.which("java")
    if _java:
        try:
            _java_result = subprocess.run(["java", "--version"], capture_output=True, text=True, timeout=5)
            _java_ver = _java_result.stdout.strip().split("\n")[0] if _java_result.returncode == 0 else None
            print(green(f"  ✓ Java {_java_ver or '(version unknown)'}"))
        except Exception:
            print(yellow("  ! Java found but version check failed"))
            warnings += 1
    else:
        print(yellow("  ! Java not found — needed for IntelliJ plugin build"))
        print(dim("    Install: https://adoptium.net/ or brew install openjdk@17"))
        warnings += 1

    # Gradle
    _gradle = _ext_shutil.which("gradle")
    _code_agents_home = _find_code_agents_home()
    _gradlew = _code_agents_home / "extensions" / "intellij" / "gradlew"
    if _gradlew.exists():
        print(green("  ✓ Gradle wrapper (gradlew) available"))
    elif _gradle:
        try:
            _gradle_ver = subprocess.run(["gradle", "--version"], capture_output=True, text=True, timeout=5).stdout.strip().split("\n")[0]
            print(green(f"  ✓ {_gradle_ver}"))
        except Exception:
            print(green("  ✓ Gradle installed"))
        print(dim("    Run 'code-agents plugin build intellij' to generate gradlew"))
    else:
        print(yellow("  ! Gradle not found — needed for IntelliJ plugin build"))
        print(dim("    Install: brew install gradle"))
        warnings += 1

    # VS Code CLI
    _code = _ext_shutil.which("code")
    if _code:
        print(green("  ✓ VS Code CLI (code) available"))
    else:
        print(dim("  · VS Code CLI (code) not in PATH"))
        print(dim("    VS Code → Cmd+Shift+P → 'Shell Command: Install code in PATH'"))

    # Extension build status
    _ext_base = _code_agents_home / "extensions"
    _vscode_built = (_ext_base / "vscode" / "dist" / "extension.js").exists()
    _webview_built = (_ext_base / "vscode" / "webview-ui" / "build" / "index.html").exists()
    _ij_built = (_ext_base / "intellij" / "build" / "distributions").exists()

    if _vscode_built and _webview_built:
        print(green("  ✓ VS Code extension: built"))
    elif _webview_built:
        print(yellow("  ! VS Code extension: webview built, extension not compiled"))
        print(dim("    Run: code-agents plugin build vscode"))
        warnings += 1
    else:
        print(yellow("  ! VS Code extension: not built"))
        print(dim("    Run: code-agents plugin build vscode"))
        warnings += 1

    if _ij_built:
        print(green("  ✓ IntelliJ plugin: built"))
    else:
        print(dim("  · IntelliJ plugin: not built"))
        print(dim("    Run: code-agents plugin build intellij"))

    print(green("  ✓ Chrome extension: ready (no build needed)"))

    # ── Summary ──
    print()
    print(bold("  " + "═" * 50))
    if issues == 0 and warnings == 0:
        print(green(bold("  ✓ All checks passed!")))
    elif issues == 0:
        print(yellow(f"  {warnings} warning(s), no critical issues"))
    else:
        print(red(f"  {issues} issue(s), {warnings} warning(s)"))
        print(dim("  Fix issues and run 'code-agents doctor' again"))
    print()
