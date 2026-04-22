"""
Centralized .env loading for Code Agents.

Three-tier config:
  1. Global:    ~/.code-agents/config.env                  (API keys, server, integrations)
  2. Per-repo:  ~/.code-agents/repos/{repo-name}/config.env  (Jenkins jobs, ArgoCD app, testing)
  3. Legacy:    {repo}/.env.code-agents                     (backward compat — migrated to tier 2)

Repo configs are stored CENTRALLY in ~/.code-agents/repos/ so no .env files
clutter the actual project directory. Repo name is derived from git root basename.

TARGET_REPO_PATH is always derived from cwd — never stored in config files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("code_agents.core.env_loader")

# PEM / CA bundle paths — zsh can accidentally merge ``#compdef`` into the same line as ``export SSL_CERT_FILE=...``
_SSL_CERT_ENV_KEYS = (
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CURL_CA_BUNDLE",
    "REQUESTS_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "GIT_SSL_CAINFO",
)


def sanitize_ssl_cert_environment() -> int:
    """Fix or remove malformed or missing SSL/TLS CA paths in :data:`os.environ`.

    * If :envvar:`CODE_AGENTS_SKIP_EXTRA_CA_CERTS` is ``1`` / ``true`` / ``yes`` / ``on``,
      unset all CA override variables so Node/OpenSSL use the system trust store only
      (skips broken corporate PEM paths and ``Ignoring extra certs`` warnings).
    * Otherwise: strip ``#`` fragments (e.g. zsh ``#compdef`` merged into ``export`` lines),
      normalize paths, and remove variables whose file/dir target does not exist.

    Call after loading dotenv so corporate shells do not break ``cursor-agent`` or httpx.

    Returns:
        Number of environment keys that were changed or removed.
    """
    changed = 0
    skip = os.getenv("CODE_AGENTS_SKIP_EXTRA_CA_CERTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if skip:
        for k in _SSL_CERT_ENV_KEYS:
            if k in os.environ:
                del os.environ[k]
                changed += 1
        if changed:
            logger.warning(
                "CODE_AGENTS_SKIP_EXTRA_CA_CERTS: removed %d SSL/CA override(s); using system CA store",
                changed,
            )
        return changed

    for k in _SSL_CERT_ENV_KEYS:
        raw = os.environ.get(k)
        if not raw or not isinstance(raw, str):
            continue
        cleaned = raw.split("#", 1)[0].strip()
        if not cleaned:
            try:
                del os.environ[k]
            except KeyError:
                pass
            logger.warning(
                "Removed invalid %s (empty after stripping #fragment); using system CAs",
                k,
            )
            changed += 1
            continue
        path = Path(cleaned).expanduser()
        if path.is_file() or (k == "SSL_CERT_DIR" and path.is_dir()):
            new_val = str(path)
            if os.environ.get(k) != new_val:
                os.environ[k] = new_val
                logger.warning(
                    "Sanitized %s: normalized path (was %r)",
                    k,
                    raw[:160],
                )
                changed += 1
        else:
            try:
                del os.environ[k]
            except KeyError:
                pass
            logger.warning(
                "Removed %s=%r (path missing or invalid); using system CAs",
                k,
                raw[:160],
            )
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GLOBAL_ENV_PATH = Path.home() / ".code-agents" / "config.env"
REPOS_DIR = Path.home() / ".code-agents" / "repos"
PER_REPO_FILENAME = ".env.code-agents"  # legacy — kept for backward compat


def _repo_name_from_cwd(cwd: str) -> str:
    """Get repo name from cwd by finding the git root basename."""
    check = cwd
    while True:
        if os.path.isdir(os.path.join(check, ".git")):
            return os.path.basename(check)
        parent = os.path.dirname(check)
        if parent == check:
            break
        check = parent
    # Fallback: use cwd basename
    return os.path.basename(cwd)


def repo_config_path(cwd: str) -> Path:
    """Get the centralized config path for a repo: ~/.code-agents/repos/{name}/config.env"""
    name = _repo_name_from_cwd(cwd)
    return REPOS_DIR / name / "config.env"

# ---------------------------------------------------------------------------
# Variable classification
# ---------------------------------------------------------------------------

# Variables that belong in the global config (shared across all repos)
GLOBAL_VARS = {
    # Core
    "CURSOR_API_KEY", "ANTHROPIC_API_KEY", "CURSOR_API_URL", "CODE_AGENTS_HTTP_ONLY",
    "CODE_AGENTS_LOCAL_LLM_URL", "CODE_AGENTS_LOCAL_LLM_API_KEY", "OLLAMA_API_KEY",
    "CODE_AGENTS_BACKEND", "CODE_AGENTS_CLAUDE_CLI_MODEL", "CODE_AGENTS_NICKNAME",
    "CODE_AGENTS_USER_ROLE",
    # Server
    "HOST", "PORT", "LOG_LEVEL", "AGENTS_DIR",
    "CODE_AGENTS_PUBLIC_BASE_URL", "OPEN_WEBUI_PUBLIC_URL",
    # Atlassian
    "ATLASSIAN_OAUTH_CLIENT_ID", "ATLASSIAN_OAUTH_CLIENT_SECRET",
    "ATLASSIAN_OAUTH_SCOPES", "ATLASSIAN_OAUTH_SUCCESS_REDIRECT",
    "ATLASSIAN_CLOUD_SITE_URL", "CODE_AGENTS_HTTPS_VERIFY", "CODE_AGENTS_SKIP_EXTRA_CA_CERTS",
    # Elasticsearch
    "ELASTICSEARCH_URL", "ELASTICSEARCH_CLOUD_ID", "ELASTICSEARCH_API_KEY",
    "ELASTICSEARCH_USERNAME", "ELASTICSEARCH_PASSWORD",
    "ELASTICSEARCH_CA_CERTS", "ELASTICSEARCH_VERIFY_SSL",
    # Redash
    "REDASH_BASE_URL", "REDASH_API_KEY", "REDASH_USERNAME", "REDASH_PASSWORD",
    # Jenkins (credentials — same server across repos)
    "JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN",
    # ArgoCD (credentials — same cluster across repos)
    "ARGOCD_URL", "ARGOCD_USERNAME", "ARGOCD_PASSWORD",
    # Jira/Confluence (credentials — same instance across repos)
    "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
    # Kibana (credentials — same instance across repos)
    "KIBANA_URL", "KIBANA_USERNAME", "KIBANA_PASSWORD",
    # Notifications
    "CODE_AGENTS_SLACK_WEBHOOK_URL",
    # Voice input
    "CODE_AGENTS_VOICE_ENGINE",
    # UI
    "CODE_AGENTS_SIMPLE_UI",
    # Telemetry
    "CODE_AGENTS_TELEMETRY",
}

# Variables that belong in the per-repo config
REPO_VARS = {
    # Jenkins (job paths — different per repo)
    "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB",
    "JENKINS_DEPLOY_JOB_DEV", "JENKINS_DEPLOY_JOB_QA",
    # ArgoCD (app name — different per repo)
    "ARGOCD_APP_NAME", "ARGOCD_APP_PATTERN", "ARGOCD_VERIFY_SSL",
    # Kubernetes (namespace/context may differ per repo)
    "K8S_NAMESPACE", "K8S_CONTEXT", "KUBECONFIG",
    "K8S_SSH_HOST", "K8S_SSH_KEY", "K8S_SSH_USER", "K8S_SSH_PORT",
    # Kibana (service field — may differ per repo)
    "KIBANA_SERVICE_FIELD",
    # Testing
    "TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD", "TARGET_REPO_REMOTE",
    # Build (command — different per repo)
    "CODE_AGENTS_BUILD_CMD",
    # Jira (project key — different per repo)
    "JIRA_PROJECT_KEY",
    # Rate limiting
    "CODE_AGENTS_RATE_LIMIT_RPM", "CODE_AGENTS_RATE_LIMIT_TPD",
}

# Never stored — always computed at runtime
RUNTIME_VARS = {"TARGET_REPO_PATH"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_all_env(cwd: str | None = None) -> None:
    """
    Load environment from global config and per-repo overrides.

    Load order (later sources override earlier ones):
      1. ~/.code-agents/config.env                    (global defaults)
      2. ~/.code-agents/repos/{repo-name}/config.env  (centralized per-repo — preferred)
      3. {cwd}/.env                                   (legacy fallback)
      4. {cwd}/.env.code-agents                       (legacy per-repo fallback)
      5. Parsed merge of 1–4 applied to :data:`os.environ` (same as ``merged_config_for_cwd``)
      6. TARGET_REPO_PATH                              (always set from cwd at runtime)

    Precedence for keys present in any config file: legacy per-repo > centralized per-repo >
    legacy .env > global. Step 5 ensures this wins over stale variables already in the shell
    (the first dotenv load uses ``override=False`` and would otherwise leave old exports).
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # dotenv not available — env vars must be set manually
        cwd = cwd or os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
        os.environ.setdefault("TARGET_REPO_PATH", cwd)
        sanitize_ssl_cert_environment()
        return

    cwd = cwd or os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    loaded_files: list[str] = []

    def _safe_load(filepath: Path, override: bool = False) -> bool:
        """Load dotenv with detailed error reporting on parse failures."""
        import sys
        import io
        # Capture stderr to detect parse warnings
        old_stderr = sys.stderr
        sys.stderr = captured = io.StringIO()
        try:
            load_dotenv(filepath, override=override)
        finally:
            sys.stderr = old_stderr
        warning = captured.getvalue().strip()
        if warning and "could not parse" in warning.lower():
            # Read the problematic line
            try:
                import re
                line_match = re.search(r'line (\d+)', warning)
                if line_match:
                    line_num = int(line_match.group(1))
                    lines = filepath.read_text().splitlines()
                    if 0 < line_num <= len(lines):
                        bad_line = lines[line_num - 1]
                        logger.warning(
                            "dotenv parse error in %s line %d: %r — %s",
                            filepath, line_num, bad_line, warning,
                        )
                        print(f"  ⚠ Config parse error: {filepath}:{line_num}", file=old_stderr)
                        print(f"    Line content: {bad_line!r}", file=old_stderr)
                        print(f"    Fix: ensure format is KEY=value (no unquoted special chars)", file=old_stderr)
                    else:
                        print(f"  ⚠ {warning} in {filepath}", file=old_stderr)
                else:
                    print(f"  ⚠ {warning} in {filepath}", file=old_stderr)
            except Exception:
                print(f"  ⚠ {warning} in {filepath}", file=old_stderr)
        return True

    # 1. Global config
    if GLOBAL_ENV_PATH.is_file():
        _safe_load(GLOBAL_ENV_PATH, override=False)
        loaded_files.append(str(GLOBAL_ENV_PATH))

    # 2. Centralized per-repo config: ~/.code-agents/repos/{repo-name}/config.env
    centralized = repo_config_path(cwd)
    if centralized.is_file():
        _safe_load(centralized, override=True)
        loaded_files.append(str(centralized))
        logger.info("Centralized repo config loaded: %s", centralized)

    # 3. Legacy per-repo .env (backward compatibility — prefer centralized)
    legacy = Path(cwd) / ".env"
    if legacy.is_file():
        _safe_load(legacy, override=True)
        loaded_files.append(str(legacy))
        logger.debug("Legacy .env loaded from %s", legacy)

    # 4. Legacy per-repo .env.code-agents (backward compat — prefer centralized)
    repo_env = Path(cwd) / PER_REPO_FILENAME
    if repo_env.is_file():
        _safe_load(repo_env, override=True)
        loaded_files.append(str(repo_env))

    # 5. Authoritative merge: same key order as :func:`merged_config_for_cwd` (later files win).
    #    The first ``load_dotenv(..., override=False)`` on global config does not overwrite
    #    variables already set in the parent process (e.g. an old ``export CODE_AGENTS_BACKEND=claude-cli``),
    #    which made ``code-agents init`` / config files show ``local`` while runtime still probed Claude CLI.
    try:
        from code_agents.setup.setup_env import merged_config_for_cwd

        for _k, _v in merged_config_for_cwd(cwd).items():
            os.environ[_k] = _v
    except Exception as _sync_err:
        logger.debug("merged_config → os.environ sync skipped: %s", _sync_err)

    # 6. TARGET_REPO_PATH is always runtime
    os.environ.setdefault("TARGET_REPO_PATH", cwd)

    # 7. Fix PEM paths corrupted by shell (e.g. #compdef on same line as SSL_CERT_FILE)
    _n = sanitize_ssl_cert_environment()
    if _n:
        logger.info("Sanitized %d SSL/CA environment variable(s) (fragments and/or missing paths)", _n)

    logger.info("Environment loaded: %d config files (order: %s)", len(loaded_files), " -> ".join(loaded_files) if loaded_files else "none")


def reload_env_for_repo(repo_path: str) -> dict:
    """
    Load global env + repo-specific env for the given path.

    Combines global config.env with the repo's .env.code-agents.
    Returns the combined env vars dict (does not modify os.environ).
    """
    combined: dict[str, str] = {}

    # Load global config vars
    if GLOBAL_ENV_PATH.is_file():
        try:
            with open(GLOBAL_ENV_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        combined[key] = value
        except OSError:
            pass

    # Overlay repo-specific vars
    repo_env = Path(repo_path) / PER_REPO_FILENAME
    if repo_env.is_file():
        try:
            with open(repo_env) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        combined[key] = value
        except OSError:
            pass

    logger.debug("reload_env_for_repo(%s): %d vars loaded", repo_path, len(combined))
    return combined


def split_vars(env_vars: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Split a dict of env vars into (global_vars, repo_vars)."""
    g, r = {}, {}
    for k, v in env_vars.items():
        if k in RUNTIME_VARS:
            continue  # never store
        elif k in REPO_VARS:
            r[k] = v
        else:
            g[k] = v  # default to global
    logger.debug("split_vars: %d global, %d repo-specific", len(g), len(r))
    return g, r


def split_unset_keys(keys: frozenset[str]) -> tuple[set[str], set[str]]:
    """Partition keys to remove from existing config files (global vs per-repo)."""
    g: set[str] = set()
    r: set[str] = set()
    for k in keys:
        if k in RUNTIME_VARS:
            continue
        if k in REPO_VARS:
            r.add(k)
        else:
            g.add(k)
    return g, r
