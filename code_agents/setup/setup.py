"""
Interactive one-command setup wizard for Code Agents.

Usage:
    poetry run code-agents-setup

Walks through Python checks, dependency installation, key prompts,
.env generation, and optionally starts the server.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.setup")

# Re-export from split modules for backward compatibility
from .setup_ui import (  # noqa: F401
    bold, green, yellow, red, cyan, dim,
    prompt, prompt_yes_no, prompt_choice,
    validate_url, validate_port, validate_job_path, clean_job_path,
)
from .setup_env import (  # noqa: F401
    _ENV_SECTIONS, parse_env_file, _write_env_to_path, write_env_file,
    merged_config_for_cwd,
)

# ---------------------------------------------------------------------------
# ANSI color helpers (no dependencies)
# ---------------------------------------------------------------------------


# UI helpers moved to setup_ui.py, env management moved to setup_env.py

def print_banner():
    print()
    print(bold(cyan("  ╔══════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Interactive Setup    ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════╝")))
    print()


def check_python() -> None:
    """Step 1: Verify Python >= 3.10."""
    print(bold("[1/7] Checking Python version..."))
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        print(green(f"  ✓ Python {version_str}"))
    else:
        print(red(f"  ✗ Python {version_str} — requires 3.10+"))
        print(red("    Install Python 3.10+ and try again."))
        sys.exit(1)
    print()


def check_dependencies() -> None:
    """Step 2: Check/install required packages."""
    print(bold("[2/7] Checking dependencies..."))
    missing = []
    for pkg in ["fastapi", "uvicorn", "pydantic", "yaml", "httpx"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        print(green("  ✓ All required packages installed"))
    else:
        print(yellow(f"  ! Missing packages: {', '.join(missing)}"))
        has_poetry = shutil.which("poetry") and Path("pyproject.toml").exists()
        if has_poetry:
            if prompt_yes_no("Install with poetry?", default=True):
                print(dim("    Running: poetry install ..."))
                result = subprocess.run(
                    ["poetry", "install"], capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(green("  ✓ Dependencies installed"))
                else:
                    print(red(f"  ✗ Poetry install failed:\n{result.stderr[:500]}"))
                    sys.exit(1)
            else:
                print(yellow("  Skipping — some features may not work."))
        else:
            req_file = Path("requirements.txt")
            if req_file.exists():
                if prompt_yes_no("Install with pip?", default=True):
                    print(dim(f"    Running: pip install -r requirements.txt ..."))
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        print(green("  ✓ Dependencies installed"))
                    else:
                        print(red(f"  ✗ pip install failed:\n{result.stderr[:500]}"))
                        sys.exit(1)
            else:
                print(red("  ✗ Neither poetry nor requirements.txt found."))
                print(red("    Install manually: pip install fastapi uvicorn pydantic pyyaml httpx"))
                sys.exit(1)
    print()


def detect_target_repo() -> dict[str, str]:
    """Step 3: Detect or prompt for the target repository path."""
    print(bold("[3/7] Target Repository"))
    cwd = os.getcwd()
    git_dir = os.path.join(cwd, ".git")

    if os.path.isdir(git_dir):
        print(f"  Detected git repo at: {cyan(cwd)}")
        if prompt_yes_no("Use this as TARGET_REPO_PATH?", default=True):
            print(green(f"  ✓ TARGET_REPO_PATH={cwd}"))
            print()
            return {"TARGET_REPO_PATH": cwd}

    # Manual entry
    path = prompt(
        "Path to target repository",
        default=cwd,
        required=True,
        validator=lambda v: os.path.isdir(v),
        error_msg="Directory does not exist.",
    )
    print(green(f"  ✓ TARGET_REPO_PATH={path}"))
    print()
    return {"TARGET_REPO_PATH": path}


def _discover_claude_models(claude_path: Optional[str] = None) -> list[str]:
    """Query Claude CLI for available models. Returns model ID list or empty."""
    if not claude_path:
        return []
    try:
        proc = subprocess.run(
            [claude_path, "-p", "list all available claude model IDs you support, one per line, model IDs only",
             "--model", "haiku", "--output-format", "text", "--max-turns", "1"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode != 0:
            return []
        # Parse model IDs from output (lines starting with "claude-")
        models = []
        for line in proc.stdout.strip().splitlines():
            line = line.strip().rstrip(".")
            if line.startswith("claude-") and " " not in line:
                models.append(line)
        # Deduplicate and sort: opus first, then sonnet, then haiku
        seen = set()
        unique = []
        for m in models:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        # Sort by capability
        def _sort_key(m: str) -> int:
            if "opus" in m: return 0
            if "sonnet" in m: return 1
            if "haiku" in m: return 2
            return 3
        unique.sort(key=_sort_key)
        return unique if unique else []
    except Exception as e:
        logger.debug("Model discovery failed: %s", e)
        return []


def prompt_backend_keys() -> tuple[dict[str, str], frozenset[str]]:
    """Step 4: Backend API keys. Returns (env dict, keys to remove from merged config when switching backend)."""
    print(bold("[4/7] Backend Configuration"))
    choice = prompt_choice(
        "Which backend?",
        [
            "Local LLM (Ollama / OpenAI-compatible — default)",
            "Cursor (needs CURSOR_API_KEY)",
            "Claude API (needs ANTHROPIC_API_KEY)",
            "Claude CLI (uses your Claude subscription — no API key)",
            "Cursor + Claude API (both)",
        ],
        default=1,
    )

    env = {}

    if choice == 1:  # Local OpenAI-compatible HTTP
        env["CODE_AGENTS_BACKEND"] = "local"
        env["CODE_AGENTS_LOCAL_LLM_URL"] = prompt(
            "CODE_AGENTS_LOCAL_LLM_URL",
            default="http://127.0.0.1:11434/v1",
            validator=lambda v: validate_url(v),
            error_msg="Must be a valid URL (http://...)",
        )
        env["CODE_AGENTS_LOCAL_LLM_API_KEY"] = prompt(
            "CODE_AGENTS_LOCAL_LLM_API_KEY",
            default="local",
            required=True,
        )
        env["CODE_AGENTS_MODEL"] = prompt(
            "CODE_AGENTS_MODEL",
            default="qwen2.5-coder:7b",
            required=True,
        )

    if choice in (2, 5):  # Cursor
        env["CODE_AGENTS_BACKEND"] = "cursor"
        env["CURSOR_API_KEY"] = prompt(
            "CURSOR_API_KEY",
            secret=True,
            required=True,
        )
        url = prompt(
            "Cursor API URL (blank for CLI mode)",
            validator=lambda v: validate_url(v),
            error_msg="Must be a valid URL (https://...)",
        )
        if url:
            env["CURSOR_API_URL"] = url

    if choice in (3, 5):  # Claude API
        if choice == 3:
            env["CODE_AGENTS_BACKEND"] = "claude"
        env["ANTHROPIC_API_KEY"] = prompt(
            "ANTHROPIC_API_KEY",
            secret=True,
            required=True,
        )

    if choice == 4:  # Claude CLI
        env["CODE_AGENTS_BACKEND"] = "claude-cli"
        # Check if claude is installed
        import shutil
        claude_path = shutil.which("claude")
        if claude_path:
            print(green(f"    ✓ Claude CLI found ({claude_path})"))
        else:
            print(yellow("    ⚠ Claude CLI not found — install: npm install -g @anthropic-ai/claude-code"))

        # Model selection — query CLI for available models
        models = _discover_claude_models(claude_path)
        print()
        if models:
            # Build display names
            display = []
            for m in models:
                if "opus" in m:
                    display.append(f"{m} (most capable)")
                elif "sonnet" in m:
                    display.append(f"{m} (fast + capable)")
                elif "haiku" in m:
                    display.append(f"{m} (fastest)")
                else:
                    display.append(m)
            # Default to sonnet if available
            default_idx = next((i for i, m in enumerate(models) if "sonnet" in m), 0) + 1
            model_choice = prompt_choice("Which model?", display, default=default_idx)
            env["CODE_AGENTS_CLAUDE_CLI_MODEL"] = models[model_choice - 1]
        else:
            # Fallback if discovery fails
            model_choice = prompt_choice(
                "Which model?",
                ["claude-opus-4-6 (most capable)", "claude-sonnet-4-6 (fast + capable)", "claude-haiku-4-5-20251001 (fastest)"],
                default=2,
            )
            model_map = {1: "claude-opus-4-6", 2: "claude-sonnet-4-6", 3: "claude-haiku-4-5-20251001"}
            env["CODE_AGENTS_CLAUDE_CLI_MODEL"] = model_map[model_choice]

    if choice == 5:
        env["CODE_AGENTS_BACKEND"] = "cursor"  # primary, claude as fallback for hybrid

    print()
    # Not Claude CLI: remove stale CLI-only model from any previous install
    unset = frozenset({"CODE_AGENTS_CLAUDE_CLI_MODEL"}) if choice != 4 else frozenset()
    return env, unset


def prompt_server_config() -> dict[str, str]:
    """Step 5: Server host and port."""
    print(bold("[5/7] Server Configuration"))
    host = prompt("HOST", default="0.0.0.0")
    port = prompt(
        "PORT",
        default="8000",
        validator=validate_port,
        error_msg="Must be a number 1-65535.",
    )
    print()
    return {"HOST": host, "PORT": port}


def prompt_cicd_pipeline() -> dict[str, str]:
    """Step 6: CI/CD pipeline — Jenkins, ArgoCD, Testing."""
    print(bold("[6/7] CI/CD Pipeline (optional)"))
    env: dict[str, str] = {}

    # Jenkins
    if prompt_yes_no("Configure Jenkins?", default=False):
        print(dim("    Jenkins base URL without job path"))
        print(dim("    Example: https://jenkins.mycompany.com/"))
        env["JENKINS_URL"] = prompt(
            "JENKINS_URL",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        print(dim("    Jenkins user with API token access"))
        env["JENKINS_USERNAME"] = prompt("JENKINS_USERNAME", required=True)
        print(dim("    Manage Jenkins → Users → Configure → API Token"))
        env["JENKINS_API_TOKEN"] = prompt("JENKINS_API_TOKEN", secret=True, required=True)
        print()
        print(dim("    Use the folder path from your Jenkins URL, separated by /"))
        print(dim("    Example: If your Jenkins URL is:"))
        print(dim("      https://jenkins.company.com/job/folder/job/subfolder/job/my-service/"))
        print(dim("    Then the job path is: folder/subfolder/my-service"))
        print(dim("    DO NOT include 'job/' prefix — just use folder names separated by /"))
        print()
        env["JENKINS_BUILD_JOB"] = prompt(
            "JENKINS_BUILD_JOB",
            required=True,
            validator=validate_job_path,
            transform=clean_job_path,
            error_msg="Enter a job path like 'folder/subfolder/my-service', not a full URL.",
        )
        print(dim("    Deploy job path (same as build job if same pipeline)"))
        env["JENKINS_DEPLOY_JOB"] = prompt(
            "JENKINS_DEPLOY_JOB",
            default=env.get("JENKINS_BUILD_JOB", ""),
            validator=validate_job_path,
            error_msg="Enter a job path, not a full URL.",
        )

    # ArgoCD
    if prompt_yes_no("Configure ArgoCD?", default=False):
        print(dim("    ArgoCD server URL"))
        print(dim("    Example: https://argocd-acquiring.pg2prod.example.com"))
        env["ARGOCD_URL"] = prompt(
            "ARGOCD_URL",
            default="https://argocd.pgnonprod.example.com",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        print(dim("    ArgoCD login credentials (exchanges for a session JWT automatically)"))
        env["ARGOCD_USERNAME"] = prompt("ARGOCD_USERNAME", default="admin", required=True)
        env["ARGOCD_PASSWORD"] = prompt("ARGOCD_PASSWORD", secret=True, required=True)
        default_pattern = "{env}-project-bombay-{app}"
        print(dim(f"    App name pattern: {default_pattern}"))
        print(dim("    Resolves to e.g.: dev-stable-project-bombay-pg-acquiring-biz"))
        if not prompt_yes_no("    Is this pattern correct?", default=True):
            env["ARGOCD_APP_PATTERN"] = prompt("ARGOCD_APP_PATTERN", default=default_pattern, required=True)
        else:
            env["ARGOCD_APP_PATTERN"] = default_pattern

    # Testing overrides
    if prompt_yes_no("Configure testing overrides?", default=True):
        print(dim("    Hint: Shell command to run tests. Leave blank to auto-detect (pytest/jest/maven/go)"))
        print(dim("    Example: pytest --cov --cov-report=xml:coverage.xml"))
        cmd = prompt("TARGET_TEST_COMMAND (blank for auto-detect)")
        if cmd:
            env["TARGET_TEST_COMMAND"] = cmd
        print(dim("    Hint: Minimum coverage % required (default: 100)"))
        threshold = prompt("TARGET_COVERAGE_THRESHOLD", default="100")
        if threshold != "100":
            env["TARGET_COVERAGE_THRESHOLD"] = threshold

    print()
    return env


def prompt_integrations() -> dict[str, str]:
    """Step 7: Optional integrations — Elasticsearch, Atlassian, Redash."""
    print(bold("[7/7] Other Integrations (optional)"))
    env: dict[str, str] = {}

    # Elasticsearch
    if prompt_yes_no("Configure Elasticsearch?", default=True):
        env["ELASTICSEARCH_URL"] = prompt(
            "ELASTICSEARCH_URL",
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        api_key = prompt("ELASTICSEARCH_API_KEY (blank to skip)")
        if api_key:
            env["ELASTICSEARCH_API_KEY"] = api_key

    # Atlassian OAuth
    if prompt_yes_no("Configure Atlassian OAuth?", default=True):
        env["ATLASSIAN_OAUTH_CLIENT_ID"] = prompt("ATLASSIAN_OAUTH_CLIENT_ID", required=True)
        env["ATLASSIAN_OAUTH_CLIENT_SECRET"] = prompt(
            "ATLASSIAN_OAUTH_CLIENT_SECRET", secret=True, required=True,
        )
        env["ATLASSIAN_CLOUD_SITE_URL"] = prompt(
            "ATLASSIAN_CLOUD_SITE_URL (e.g. https://company.atlassian.net)",
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )

    # Redash
    if prompt_yes_no("Configure Redash?", default=True):
        env["REDASH_BASE_URL"] = prompt(
            "REDASH_BASE_URL",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        api_key = prompt("REDASH_API_KEY (blank for username/password auth)")
        if api_key:
            env["REDASH_API_KEY"] = api_key
        else:
            env["REDASH_USERNAME"] = prompt("REDASH_USERNAME", required=True)
            env["REDASH_PASSWORD"] = prompt("REDASH_PASSWORD", secret=True, required=True)

    print()
    return env


# ---------------------------------------------------------------------------
# .env file writer
# ---------------------------------------------------------------------------


# _ENV_SECTIONS, parse_env_file, _write_env_to_path, write_env_file -> setup_env.py

def start_server() -> None:
    """Load .env and start the Code Agents server."""
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
    except ImportError:
        pass

    print(bold(cyan("  Starting Code Agents...")))
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")
    print(dim(f"  Server: http://{host}:{port}"))
    print(dim("  Press Ctrl+C to stop.\n"))

    from code_agents.core.main import main as run_server
    run_server()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    try:
        print_banner()
        check_python()
        check_dependencies()

        env_vars: dict[str, str] = {}
        env_vars.update(detect_target_repo())
        backend_env, backend_unset = prompt_backend_keys()
        env_vars.update(backend_env)
        env_vars.update(prompt_server_config())
        env_vars.update(prompt_cicd_pipeline())
        env_vars.update(prompt_integrations())

        # Filter out empty values
        env_vars = {k: v for k, v in env_vars.items() if v}

        print(bold("━" * 44))
        write_env_file(env_vars, unset_keys=backend_unset)

        if prompt_yes_no("Start the server now?", default=True):
            start_server()
        else:
            print()
            print(green("  Setup complete!"))
            print(f"  Run the server with: {cyan('poetry run code-agents')}")
            print()

    except KeyboardInterrupt:
        print(yellow("\n\n  Setup cancelled."))
        sys.exit(0)
    except EOFError:
        print(yellow("\n\n  Setup cancelled (no input)."))
        sys.exit(0)


if __name__ == "__main__":
    main()
