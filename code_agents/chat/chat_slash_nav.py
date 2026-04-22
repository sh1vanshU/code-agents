"""Navigation & help slash commands: /help, /quit, /exit, /restart, /open, /setup."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_nav")

import subprocess
import time

from .chat_ui import bold, green, yellow, red, cyan, dim, magenta
from .chat_server import _server_url, _check_server


def _restart_server(server_url: str) -> None:
    """Restart the code-agents server so new env vars take effect."""
    port = server_url.rsplit(":", 1)[-1].split("/")[0] if ":" in server_url else "8000"
    print(dim(f"\n  Restarting server on port {port}..."))
    try:
        # Find and kill existing server
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True, text=True,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        if pids:
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            time.sleep(1)
            # Force kill stragglers
            check = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            remaining = [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]
            for pid in remaining:
                try:
                    os.kill(int(pid), 9)  # SIGKILL
                except ProcessLookupError:
                    pass

        # Start server in background (same as cli_server._start_background)
        repo_path = os.getenv("TARGET_REPO_PATH", os.getcwd())
        code_agents_home = Path.home() / ".code-agents"
        log_file = code_agents_home / "logs" / "code-agents.log"
        env = os.environ.copy()
        env["TARGET_REPO_PATH"] = repo_path
        subprocess.Popen(
            [sys.executable, "-m", "code_agents.core.main"],
            cwd=str(code_agents_home),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=open(str(log_file), "a") if log_file.parent.exists() else subprocess.DEVNULL,
        )
        time.sleep(2)
        if _check_server(server_url):
            print(green("  ✓ Server restarted successfully."))
        else:
            print(yellow("  ⚠ Server may still be starting. Check with 'code-agents status'."))
    except Exception as e:
        logger.warning("Server restart failed: %s", e)
        print(yellow(f"  ⚠ Could not restart: {e}"))
        print(dim("  Run 'code-agents restart' manually."))


def _handle_navigation(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle navigation-related slash commands."""

    if command in ("/quit", "/exit", "/q", "/bye"):
        return "quit"

    elif command == "/restart":
        import subprocess as _sp
        port = os.getenv("PORT", "8000")
        print()
        print(bold(cyan("  Restarting server...")))
        # Kill existing
        try:
            result = _sp.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
            if pids:
                for pid in pids:
                    os.kill(int(pid), 15)
                import time
                time.sleep(1)
                # Force kill stragglers
                check = _sp.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
                for pid in [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]:
                    os.kill(int(pid), 9)
                print(green(f"  ✓ Server stopped"))
        except Exception:
            pass
        # Start new
        cwd = state.get("repo_path", os.getcwd())
        code_agents_home = str(Path(__file__).resolve().parent.parent)
        env = os.environ.copy()
        env["TARGET_REPO_PATH"] = cwd
        log_dir = Path(code_agents_home) / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "code-agents.log"
        _sp.Popen(
            [sys.executable, "-m", "code_agents.core.main"],
            cwd=code_agents_home,
            env=env,
            stdout=_sp.DEVNULL,
            stderr=open(str(log_file), "a"),
        )
        import time
        for _ in range(10):
            time.sleep(1)
            if _check_server(_server_url()):
                print(green(f"  ✓ Server restarted at {_server_url()}"))
                break
        else:
            print(red(f"  ✗ Server failed to restart. Check: code-agents logs"))
        print()

    elif command == "/help":
        print()
        print(bold("  Chat Commands:"))
        print(f"    {cyan('/quit'):<16} Exit chat")
        print(f"    {cyan('/agent <name>'):<16} Switch to another agent permanently")
        print(f"    {cyan('/agents'):<16} List all available agents")
        print(f"    {cyan('/run <cmd>'):<16} Run a shell command in the repo directory")
        print(f"    {cyan('/exec <cmd>'):<16} Run command and send output to agent for analysis")
        print(f"    {cyan('/open'):<16} View last response in pager (less/editor)")
        print(f"    {cyan('/restart'):<16} Restart the server")
        print(f"    {cyan('/rules'):<16} Show active rules for current agent")
        print(f"    {cyan('/tokens'):<16} Show token usage (session, daily, monthly)")
        print(f"    {cyan('/skills'):<16} List skills for current agent (or /skills <agent>)")
        print(f"    {cyan('/endpoints'):<16} Show discovered endpoints (rest|grpc|kafka|scan|run)")
        print(f"    {cyan('/session'):<16} Show current session ID")
        print(f"    {cyan('/history'):<16} List previous chat sessions")
        print(f"    {cyan('/resume <id>'):<16} Resume a chat by session ID")
        print(f"    {cyan('/delete-chat <id>'):<16} Delete a chat by session ID")
        print(f"    {cyan('/clear'):<16} Clear session (fresh start, same agent)")
        print(f"    {cyan('/setup [section]'):<16} Configure integrations (jenkins, argocd, redash, testing)")
        print(f"    {cyan('/memory'):<16} Show agent memory (learnings persisted across sessions)")
        print(f"    {cyan('/memory clear'):<16} Clear memory for current agent")
        print(f"    {cyan('/memory list'):<16} List all agents with saved memories")
        print(f"    {cyan('/btw <msg>'):<16} Inject a side message into agent context")
        print(f"    {cyan('/btw'):<16} Show current side messages")
        print(f"    {cyan('/btw clear'):<16} Clear all side messages")
        print(f"    {cyan('/repo'):<16} List registered repos")
        print(f"    {cyan('/repo <name>'):<16} Switch to another repo without restarting")
        print(f"    {cyan('/repo add <path>'):<16} Register a new repo")
        print(f"    {cyan('/repo remove <name>'):<16} Unregister a repo")
        print(f"    {cyan('/generate-tests <file>'):<16} Generate unit + integration tests for a source file")
        print(f"    {cyan('/qa-suite'):<16} Generate full QA regression suite (analyze repo, create tests)")
        print(f"    {cyan('/blame <file> <line>'):<16} Deep blame: who, what PR, Jira ticket, full context")
        print(f"    {cyan('/investigate <error>'):<16} Search logs, correlate deploys, find root cause")
        print(f"    {cyan('/review-reply [PR#]'):<16} Fetch PR comments and generate replies/fixes")
        print(f"    {cyan('/flags [--stale]'):<16} Scan codebase for feature flags and their states")
        print(f"    {cyan('/kb <topic>'):<16} Search team knowledge base (chat history, code, docs)")
        print(f"    {cyan('/kb --rebuild'):<16} Re-index the knowledge base")
        print(f"    {cyan('/kb --stats'):<16} Show KB statistics by source")
        print(f"    {cyan('/model <name>'):<16} Switch model mid-conversation")
        print(f"    {cyan('/backend <name>'):<16} Switch backend mid-conversation (cursor, claude, claude-cli)")
        print(f"    {cyan('/pair'):<16} Pair programming mode — watches file changes, suggests improvements")
        print(f"    {cyan('/deps <name>'):<16} Dependency tree: who calls it, what it calls, circular deps")
        print(f"    {cyan('/impact <file>'):<16} Impact analysis: dependents, tests, endpoints, risk")
        print(f"    {cyan('/pr-preview [base]'):<16} Preview PR: diff stats, risk score, affected tests")
        print(f"    {cyan('/verify [on|off]'):<16} Toggle auto-verify: code-reviewer checks code-writer output")
        print(f"    {cyan('/compile'):<16} Run compile check (Java/Go/TypeScript)")
        print(f"    {cyan('/solve <problem>'):<16} Describe a problem, get recommended agent/command/skill")
        print(f"    {cyan('/help'):<16} Show this help")
        print()
        print(bold("  Inline agent delegation:"))
        print(f"    {cyan('/<agent> <prompt>'):<16}")
        print(f"    Send a one-shot prompt to another agent without switching.")
        print()
        print(bold("  Skill invocation:"))
        print(f"    {cyan('/<agent>:<skill>'):<16}")
        print(f"    Invoke a reusable skill workflow on an agent.")
        print(f"    {cyan('/<agent>:<skill> <context>'):<16}")
        print(f"    Invoke skill with extra context from user.")
        print(f"    Agents can also auto-load skills by outputting {cyan('[SKILL:name]')} in responses.")
        print()
        print(bold("  Command execution:"))
        print(f"    When an agent suggests shell commands (in ```bash blocks),")
        print(f"    you'll be prompted to run them with Tab selector.")
        print()
        print(f"    {dim('Examples:')}")
        print(f"    {dim('/code-reviewer Review the auth module')}")
        print(f"    {dim('/jenkins-cicd:build Build pg-acquiring-biz')}")
        print(f"    {dim('/jenkins-cicd:deploy Deploy version 1.2.3 to dev')}")
        print(f"    {dim('/run git status')}")
        print()

    elif command == "/open":
        # Open last output in pager or editor
        last_output = state.get("_last_output", "")
        if not last_output:
            print(dim("  No output to view."))
            return None
        import tempfile
        import subprocess as _sp
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="code-agents-") as f:
            f.write(last_output)
            tmp_path = f.name
        pager = os.environ.get("PAGER", "less -R")
        try:
            _sp.run(pager.split() + [tmp_path])
        except FileNotFoundError:
            # Fallback: try open on macOS
            try:
                _sp.run(["open", tmp_path])
            except FileNotFoundError:
                print(f"  {dim(f'Saved to: {tmp_path}')}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    elif command == "/setup":
        sections = {
            "jenkins": ["JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN", "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB", "JENKINS_DEPLOY_JOB_DEV", "JENKINS_DEPLOY_JOB_QA"],
            "argocd": ["ARGOCD_URL", "ARGOCD_USERNAME", "ARGOCD_PASSWORD"],
            "redash": ["REDASH_URL", "REDASH_API_KEY"],
            "testing": ["TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD"],
            "build": ["CODE_AGENTS_BUILD_CMD"],
            "k8s": ["K8S_NAMESPACE", "K8S_CONTEXT", "KUBECONFIG", "K8S_SSH_HOST", "K8S_SSH_KEY", "K8S_SSH_USER"],
            "kibana": ["KIBANA_URL", "KIBANA_USERNAME", "KIBANA_PASSWORD"],
            "jira": ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"],
            "notifications": ["CODE_AGENTS_SLACK_WEBHOOK_URL"],
        }

        if not arg:
            # Show available sections
            print()
            print(bold("  Configure integrations:"))
            for name in sections:
                print(f"    {cyan(f'/setup {name}')}")
            print()
            return None

        section = arg.lower().strip()
        if section not in sections:
            print(yellow(f"  Unknown section: {section}"))
            print(dim(f"  Available: {', '.join(sections.keys())}"))
            return None

        # Default values for first-time setup
        defaults = {
            "ARGOCD_URL": "https://argocd.pgnonprod.example.com",
            "ARGOCD_USERNAME": "admin",
            "ARGOCD_PASSWORD": "",
            "ARGOCD_APP_PATTERN": "{env}-project-bombay-{app}",
        }

        # Prompt for each var
        print()
        print(bold(f"  Configure {section}:"))
        repo = state.get("repo_path", ".")
        env_file = os.path.join(repo, ".env.code-agents")

        values = {}
        for var in sections[section]:
            current = os.getenv(var, "") or defaults.get(var, "")
            prompt_text = f"  {var}"
            if current:
                prompt_text += f" [{dim(current[:30] + '...' if len(current) > 30 else current)}]"
            prompt_text += ": "
            try:
                val = input(prompt_text).strip()
                if val:
                    values[var] = val
                elif current:
                    values[var] = current
            except (EOFError, KeyboardInterrupt):
                print(dim("\n  Cancelled."))
                return None

        # Auto-add app pattern for argocd if not already set
        if section == "argocd" and "ARGOCD_APP_PATTERN" not in values:
            pattern = os.getenv("ARGOCD_APP_PATTERN", "").strip()
            if not pattern:
                pattern = "{env}-project-bombay-{app}"
                values["ARGOCD_APP_PATTERN"] = pattern
                print(dim(f"  App pattern: {pattern}"))

        # Write to .env.code-agents
        if values:
            with open(env_file, "a") as f:
                f.write(f"\n# {section.upper()} (configured via /setup)\n")
                for k, v in values.items():
                    f.write(f"{k}={v}\n")
                    os.environ[k] = v
            print(green(f"  ✓ Saved to {env_file}"))

            # Prompt to restart server so new env vars take effect
            server_url = _server_url()
            if _check_server(server_url):
                try:
                    restart = input(f"\n  {bold('Restart server to apply changes?')} [Y/n]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    restart = "n"
                if restart in ("", "y", "yes"):
                    _restart_server(server_url)
                else:
                    print(dim("  Run 'code-agents restart' later to apply changes."))
        print()

    else:
        return "_not_handled"

    return None
