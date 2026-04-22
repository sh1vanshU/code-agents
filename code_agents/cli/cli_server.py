"""CLI server management commands — start, shutdown, restart, status, agents, logs, config, doctor."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .cli_helpers import (
    _colors, _server_url, _api_get, _api_post, _load_env,
    _user_cwd, _find_code_agents_home, prompt_yes_no,
    _check_workspace_trust,
)

logger = logging.getLogger("code_agents.cli.cli_server")


def _start_background(repo_path: str):
    """Start the server in background and show a clean summary."""
    bold, green, yellow, red, cyan, dim = _colors()

    from code_agents.core.env_loader import load_all_env
    load_all_env(repo_path)

    os.environ["TARGET_REPO_PATH"] = repo_path
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    base_url = f"http://{display_host}:{port}"
    log_file = _find_code_agents_home() / "logs" / "code-agents.log"

    # Start server as a background subprocess
    code_agents_home = str(_find_code_agents_home())
    server_cmd = [
        sys.executable, "-m", "code_agents.core.main",
    ]
    env = os.environ.copy()
    env["TARGET_REPO_PATH"] = repo_path

    import subprocess
    proc = subprocess.Popen(
        server_cmd,
        cwd=code_agents_home,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=open(str(log_file), "a") if log_file.parent.exists() else subprocess.DEVNULL,
    )

    # Wait briefly and check it started
    import time
    time.sleep(2)
    if proc.poll() is not None:
        print(red("  ✗ Server failed to start. Check logs:"))
        print(f"    {dim(str(log_file))}")
        print()
        return

    # Verify health
    healthy = False
    try:
        import httpx
        r = httpx.get(f"{base_url}/health", timeout=5.0)
        healthy = r.status_code == 200
    except Exception:
        pass

    print()
    if healthy:
        print(green(bold("  ✓ Code Agents is running!")))
    else:
        print(yellow("  ⏳ Server is starting up (may take a few seconds)..."))

    # ── Startup Health Checklist ──
    print()
    print(bold("  Startup Health Check"))
    print(bold("  " + "─" * 40))

    # Server
    if healthy:
        print(green("  ✓ Server"))
    else:
        print(yellow("  ⏳ Server (starting...)"))

    # Backend — actually validate connectivity, not just config
    backend = os.getenv("CODE_AGENTS_BACKEND", "").strip().lower() or "local"
    _backend_ok = False
    try:
        import asyncio
        from code_agents.devops.connection_validator import validate_backend
        _bv_result = asyncio.run(validate_backend())
        if _bv_result.valid:
            print(green(f"  ✓ Backend: {_bv_result.backend} (verified)"))
            _backend_ok = True
        else:
            print(yellow(f"  ⚠ Backend: {_bv_result.backend} — {_bv_result.message}"))
    except Exception as _bv_err:
        # Fallback to config-only check
        cursor_key = os.getenv("CURSOR_API_KEY", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        local_url = os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip()
        cursor_url = os.getenv("CURSOR_API_URL", "").strip()
        if backend == "claude-cli":
            import shutil as _sh
            claude_path = _sh.which("claude")
            if claude_path:
                print(green(f"  ✓ Backend: claude-cli ({claude_path})"))
                _backend_ok = True
            else:
                print(red("  ✗ Backend: claude-cli — 'claude' not found in PATH"))
        elif backend == "claude" and anthropic_key:
            print(green(f"  ✓ Backend: claude API (key: {anthropic_key[:8]}...)"))
            _backend_ok = True
        elif backend == "local" and (local_url or cursor_url):
            _u = local_url or cursor_url
            print(green(f"  ✓ Backend: local (URL configured: {_u[:48]}{'…' if len(_u) > 48 else ''})"))
            _backend_ok = True
        elif cursor_key:
            mode = "HTTP" if cursor_url else "CLI"
            print(green(f"  ✓ Backend: cursor ({mode}, key: {cursor_key[:8]}...)"))
            _backend_ok = True
        else:
            print(red("  ✗ Backend: not configured — run: code-agents init --backend"))

    # Model
    model = os.getenv("CODE_AGENTS_MODEL", "Composer 2 Fast")
    cli_model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "")
    if backend == "claude-cli" and cli_model:
        _model_name = cli_model
    else:
        _model_name = model
    if _backend_ok:
        print(green(f"  ✓ Model: {_model_name}"))
    else:
        print(yellow(f"  ⚠ Model: {_model_name} (backend not verified)"))
        _log_path = _find_code_agents_home() / "logs" / "code-agents.log"
        print(dim(f"  · Backend probe details: tail -n 80 {_log_path}"))

    # Agents — verify via diagnostics endpoint (actually queries loaded agents)
    if healthy:
        try:
            import httpx
            diag = httpx.get(f"{base_url}/diagnostics", timeout=5.0).json()
            agent_count = len(diag.get("agents", []))
            if agent_count > 0:
                print(green(f"  ✓ Agents: {agent_count} loaded"))
            else:
                print(yellow("  ⚠ Agents: 0 loaded — check agents/ directory"))
        except Exception:
            print(dim("  · Agents: checking..."))
    else:
        print(dim("  · Agents: waiting for server..."))

    # Integrations — quick config check (no connectivity test at startup)
    _integrations = []
    if os.getenv("JENKINS_URL"):
        _integrations.append("Jenkins")
    if os.getenv("ARGOCD_URL"):
        _integrations.append("ArgoCD")
    if os.getenv("JIRA_URL"):
        _integrations.append("Jira")
    if os.getenv("KIBANA_URL"):
        _integrations.append("Kibana")
    if os.getenv("REDASH_BASE_URL"):
        _integrations.append("Redash")
    if _integrations:
        print(green(f"  ✓ Integrations: {', '.join(_integrations)}"))
    else:
        print(dim("  · Integrations: none configured"))

    # Git repo
    if os.path.isdir(os.path.join(repo_path, ".git")):
        try:
            _branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=repo_path,
            ).stdout.strip()
            print(green(f"  ✓ Git: {os.path.basename(repo_path)} ({_branch})"))
        except Exception:
            print(green(f"  ✓ Git: {os.path.basename(repo_path)}"))
    else:
        print(yellow("  ! Git: no repo detected at target path"))

    # Config files
    from code_agents.core.env_loader import GLOBAL_ENV_PATH, repo_config_path
    _centralized = repo_config_path(repo_path)
    if _centralized.is_file():
        print(green(f"  ✓ Config: centralized ({_centralized.parent.name}/config.env)"))
    elif os.path.isfile(os.path.join(repo_path, ".env.code-agents")):
        print(green("  ✓ Config: legacy (.env.code-agents)"))
    else:
        print(dim("  · Config: no repo config (global only)"))

    print()
    print(f"  {bold('Target repo:')}  {repo_path}")
    print(f"  {bold('Logs:')}         {log_file}")
    print(f"  {bold('PID:')}          {proc.pid}")
    print()
    print(f"  {bold('Quick Links:')}")
    print(f"    Chat UI:           {cyan(f'{base_url}/ui')}")
    print(f"    Telemetry:         {cyan(f'{base_url}/telemetry-dashboard')}")
    print(f"    API Health:        {cyan(f'{base_url}/health')}")
    print(f"    API Docs:          {cyan(f'{base_url}/docs')}")
    print()
    print(f"  {bold('Verify (copy & paste in another terminal):')}")
    print()
    print(f"    {dim('# Health check')}")
    print(f"    curl -s {base_url}/health | python3 -m json.tool")
    print()
    print(f"    {dim('# List all agents')}")
    print(f"    curl -s {base_url}/v1/agents | python3 -m json.tool")
    print()
    print(f"    {dim('# Full diagnostics')}")
    print(f"    curl -s {base_url}/diagnostics | python3 -m json.tool")
    print()
    print(f"    {dim('# Send a prompt to an agent')}")
    print(f"    curl -s -X POST {base_url}/v1/agents/code-reasoning/chat/completions \\")
    print(f"      -H 'Content-Type: application/json' \\")
    print(f"      -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"What files are in this project?\"}}]}}' \\")
    print(f"      | python3 -m json.tool")
    print()
    print(f"  {bold('CLI commands:')}")
    print(f"    code-agents status                  {dim('# check server health')}")
    print(f"    code-agents agents                  {dim('# list agents')}")
    print(f"    code-agents logs                    {dim('# tail logs')}")
    print(f"    code-agents test                    {dim('# run tests')}")
    print(f"    code-agents diff main HEAD          {dim('# see changes')}")
    print(f"    code-agents pipeline start           {dim('# start CI/CD')}")
    print(f"    code-agents shutdown                 {dim('# stop the server')}")
    print()


def cmd_start():
    """Start the server in background pointing at the current directory."""
    _load_env()
    cwd = _user_cwd()

    # Pre-flight: check workspace trust before starting server
    if not _check_workspace_trust(cwd):
        return

    # Foreground mode only if explicitly requested (for debugging)
    if "--fg" in sys.argv or "--foreground" in sys.argv:
        bold, green, _, _, cyan, dim = _colors()
        host = os.getenv("HOST", "0.0.0.0")
        port = os.getenv("PORT", "8000")
        print()
        print(bold(cyan("  Starting Code Agents (foreground)...")))
        print(dim(f"  Target repo: {cwd}"))
        print(dim(f"  Server:      http://{host}:{port}"))
        print(dim(f"  Logs:        {_find_code_agents_home()}/logs/code-agents.log"))
        print(dim("  Press Ctrl+C to stop"))
        print()
        from code_agents.core.main import main as run_server
        run_server()
        return

    _start_background(cwd)


def cmd_shutdown():
    """Shutdown the running code-agents server by killing the process on its port."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    port = os.getenv("PORT", "8000")

    print()
    print(bold(f"  Shutting down Code Agents on port {port}..."))

    # Find process on the port
    try:
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True, text=True,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        if pids:
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            import time
            time.sleep(1)
            # Verify killed
            check = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            remaining = [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]
            if remaining:
                # Force kill
                for pid in remaining:
                    os.kill(int(pid), 9)  # SIGKILL
                print(green(f"  ✓ Server force-stopped (PID: {', '.join(pids)})"))
            else:
                print(green(f"  ✓ Server stopped (PID: {', '.join(pids)})"))
        else:
            print(green(f"  ✓ No server running on port {port}"))
    except Exception as e:
        print(yellow(f"  Could not find server process on port {port}: {e}"))
        print(f"  Try manually: {bold(f'kill $(lsof -ti:{port})')}")
    print()


def cmd_restart():
    """Restart the code-agents server (shutdown + start)."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    port = os.getenv("PORT", "8000")

    print()
    print(bold(cyan("  Restarting Code Agents...")))
    print()

    # Shutdown
    try:
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True, text=True,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        if pids:
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            import time
            time.sleep(1)
            # Force kill stragglers
            check = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            remaining = [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]
            for pid in remaining:
                os.kill(int(pid), 9)  # SIGKILL
            print(green(f"  ✓ Server stopped (PID: {', '.join(pids)})"))
        else:
            print(dim(f"  No server was running on port {port}"))
    except Exception as e:
        print(yellow(f"  Could not stop server: {e}"))

    # Pull latest + refresh TS terminal deps (use canonical install dir)
    _home = _find_code_agents_home()
    if (_home / ".git").is_dir():
        print(dim("  Pulling latest changes..."))
        _pull = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(_home), capture_output=True, text=True,
            timeout=30,
        )
        if _pull.returncode == 0:
            _out = _pull.stdout.strip()
            if "Already up to date" in _out:
                print(dim(f"  Already up to date."))
            else:
                print(green(f"  ✓ Pulled latest changes."))
        else:
            print(yellow(f"  ! git pull failed — continuing with current version."))

    # Reinstall Python deps (re-lock if pyproject.toml changed)
    print(dim("  Installing Python dependencies..."))
    _poetry = subprocess.run(
        ["poetry", "install", "--quiet"],
        cwd=str(_home), capture_output=True, text=True,
        timeout=120,
    )
    if _poetry.returncode != 0 and "lock" in (_poetry.stderr or _poetry.stdout or "").lower():
        print(dim("  Lock file stale — regenerating..."))
        subprocess.run(
            ["poetry", "lock"],
            cwd=str(_home), capture_output=True, text=True,
            timeout=180,
        )
        _poetry = subprocess.run(
            ["poetry", "install", "--quiet"],
            cwd=str(_home), capture_output=True, text=True,
            timeout=120,
        )
    if _poetry.returncode == 0:
        print(green("  ✓ Python dependencies updated."))
    else:
        print(yellow("  ! poetry install had issues (server may still work)."))

    # Refresh TS terminal deps
    _ts_dir = _home / "terminal"
    if (_ts_dir / "package.json").is_file():
        print(dim("  Installing TS terminal dependencies..."))
        _npm = subprocess.run(
            ["npm", "ci", "--quiet"],
            cwd=str(_ts_dir), capture_output=True, text=True,
            timeout=120,
        )
        if _npm.returncode == 0:
            print(green("  ✓ TS terminal dependencies updated."))
        else:
            print(yellow("  ! npm ci had issues (chat will auto-install on first use)."))

    # Start
    print()
    _start_background(cwd)


def cmd_status():
    """Check server health and show configuration."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    print()
    print(bold("  Code Agents Status"))
    print(bold("  " + "─" * 40))

    # Check if server is running
    data = _api_get("/health")
    if data and data.get("status") == "ok":
        print(green("  ✓ Server is running"))
    else:
        print(red("  ✗ Server is not running"))
        print(dim(f"    Start with: code-agents start"))
        print()
        # Still show local config
        cwd = _user_cwd()
        env_file = os.path.join(cwd, ".env")
        print(f"  Repo:     {cyan(cwd)}")
        print(f"  .env:     {'exists' if os.path.exists(env_file) else red('not found — run: code-agents init')}")
        print()
        return

    # Get diagnostics
    url = _server_url()
    diag = _api_get("/diagnostics")
    if diag:
        print(f"  URL:      {cyan(url)}")
        print(f"  Version:  {diag.get('package_version', '?')}")
        print(f"  Agents:   {len(diag.get('agents', []))}")
        print(f"  Repo:     {cyan(os.getenv('TARGET_REPO_PATH', _user_cwd()))}")
        print()
        print(bold("  Integrations:"))
        print(f"    Jenkins:       {'✓ configured' if diag.get('jenkins_configured') else '✗ not configured'}")
        print(f"    ArgoCD:        {'✓ configured' if diag.get('argocd_configured') else '✗ not configured'}")
        print(f"    Elasticsearch: {'✓ configured' if diag.get('elasticsearch_configured') else '✗ not configured'}")
        print(f"    Pipeline:      {'✓ enabled' if diag.get('pipeline_enabled') else '✗ not enabled'}")
        print()
        print(bold("  Quick curl commands:"))
        print(f"    curl -s {url}/health | python3 -m json.tool")
        print(f"    curl -s {url}/v1/agents | python3 -m json.tool")
        print(f"    curl -s {url}/diagnostics | python3 -m json.tool")
    print()


def cmd_agents():
    """List all available agents."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    data = _api_get("/v1/agents")
    if not data:
        # Server not running — load agents from YAML directly
        print(bold("  Available Agents (from YAML):"))
        print()
        try:
            from code_agents.core.config import agent_loader
            agent_loader.load()
            agents = agent_loader.list_agents()
            for a in agents:
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
                print(f"      backend={a.backend}  model={a.model}  permission={a.permission_mode}")
            print(f"\n  Total: {bold(str(len(agents)))} agents")
        except Exception as e:
            print(red(f"  Error loading agents: {e}"))
        print()
        return

    # Server may return {"data": [...]}, {"agents": [...]}, or a plain list
    if isinstance(data, dict):
        agents = data.get("data") or data.get("agents") or []
    elif isinstance(data, list):
        agents = data
    else:
        agents = []
    print()
    print(bold("  Available Agents:"))
    print()
    for a in agents:
        name = a.get("name", "?")
        display = a.get("display_name", "")
        endpoint = a.get("endpoint", f"/v1/agents/{name}/chat/completions")
        print(f"    {cyan(name):<28} {dim(display)}")
        print(f"      {dim(endpoint)}")
    print(f"\n  Total: {bold(str(len(agents)))} agents")
    print()


def cmd_logs(args: list[str]):
    """Tail the log file."""
    bold, green, yellow, red, cyan, dim = _colors()
    log_file = _find_code_agents_home() / "logs" / "code-agents.log"

    if not log_file.exists():
        print(yellow(f"  No log file yet: {log_file}"))
        print(dim("  Start the server first: code-agents start"))
        return

    lines = args[0] if args else "50"
    print(dim(f"  Tailing {log_file} (last {lines} lines, Ctrl+C to stop)"))
    print()
    os.execvp("tail", ["tail", "-f", "-n", lines, str(log_file)])


def cmd_config():
    """Show current configuration (from .env in current directory)."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    cwd = _user_cwd()
    env_file = os.path.join(cwd, ".env")

    print()
    print(bold("  Code Agents Configuration"))
    print(bold("  " + "─" * 40))
    print(f"  Directory:  {cyan(cwd)}")
    print(f"  .env file:  {green('found') if os.path.exists(env_file) else red('not found')}")
    print()

    if not os.path.exists(env_file):
        print(yellow("  Run 'code-agents init' to create .env"))
        print()
        return

    from code_agents.setup.setup import parse_env_file
    env = parse_env_file(Path(env_file))

    # Show config grouped, mask secrets
    secret_keys = {"CURSOR_API_KEY", "ANTHROPIC_API_KEY", "JENKINS_API_TOKEN", "ARGOCD_PASSWORD",
                   "ATLASSIAN_OAUTH_CLIENT_SECRET", "REDASH_PASSWORD", "REDASH_API_KEY",
                   "ELASTICSEARCH_API_KEY", "ELASTICSEARCH_PASSWORD"}

    groups = [
        ("Core", ["CURSOR_API_KEY", "CURSOR_API_URL", "ANTHROPIC_API_KEY"]),
        ("Server", ["HOST", "PORT", "LOG_LEVEL"]),
        ("Repository", ["TARGET_REPO_PATH", "TARGET_REPO_REMOTE"]),
        ("Testing", ["TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD"]),
        ("Jenkins", ["JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN", "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB", "JENKINS_DEPLOY_JOB_DEV", "JENKINS_DEPLOY_JOB_QA"]),
        ("ArgoCD", ["ARGOCD_URL", "ARGOCD_USERNAME", "ARGOCD_PASSWORD", "ARGOCD_APP_NAME"]),
    ]

    for group_name, keys in groups:
        group_vars = {k: env[k] for k in keys if k in env}
        if group_vars:
            print(f"  {bold(group_name)}:")
            for k, v in group_vars.items():
                if k in secret_keys and v:
                    display = v[:4] + "•" * 8 + v[-4:] if len(v) > 12 else "••••••"
                else:
                    display = v or dim("(empty)")
                print(f"    {k:<30} {display}")
            print()


from .cli_doctor import cmd_doctor  # noqa: F401
