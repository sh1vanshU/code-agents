"""
Async connection validator for backend health checks.

Validates that the configured backend (local/cursor/claude/claude-cli) is reachable
and authenticated before starting or resuming a chat session.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("code_agents.devops.connection_validator")


@dataclass
class ValidationResult:
    """Result of a backend connection validation."""
    valid: bool
    backend: str
    message: str
    details: Optional[dict] = None


async def validate_cursor_cli() -> ValidationResult:
    """Validate cursor-agent CLI is installed and responsive."""
    from code_agents.core.cursor_cli import cursor_cli_display_name, cursor_cli_on_path

    cli_path = cursor_cli_on_path()
    if not cli_path:
        _name = cursor_cli_display_name()
        return ValidationResult(
            valid=False,
            backend="cursor",
            message=f"{_name} CLI not found (set CODE_AGENTS_CURSOR_CLI or install). Or set CODE_AGENTS_BACKEND=claude-cli",
        )

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        # Check for HTTP mode fallback
        api_url = os.getenv("CURSOR_API_URL", "").strip()
        if not api_url:
            return ValidationResult(
                valid=False,
                backend="cursor",
                message="CURSOR_API_KEY not set. Configure via: code-agents init",
            )

    return ValidationResult(
        valid=True,
        backend="cursor",
        message="Cursor CLI found and API key configured",
        details={"cli_path": cli_path, "has_api_key": bool(api_key)},
    )


def _resolve_local_llm_base_url() -> str:
    """OpenAI-compatible base URL for local LLM (prefers CODE_AGENTS_LOCAL_LLM_URL)."""
    return (
        os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip()
        or os.getenv("CURSOR_API_URL", "").strip()
    )


def _local_llm_bearer_token() -> str:
    """Bearer token for OpenAI-compatible /v1 requests (Ollama local vs Ollama Cloud)."""
    return (
        os.getenv("CODE_AGENTS_LOCAL_LLM_API_KEY", "").strip()
        or os.getenv("OLLAMA_API_KEY", "").strip()
        or os.getenv("CURSOR_API_KEY", "").strip()
        or "local"
    )


async def validate_local_llm() -> ValidationResult:
    """Validate local OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, etc.)."""
    import httpx

    api_url = _resolve_local_llm_base_url()
    if not api_url:
        return ValidationResult(
            valid=False,
            backend="local",
            message=(
                "CODE_AGENTS_LOCAL_LLM_URL not set. "
                "Example: http://127.0.0.1:11434/v1 — or set CODE_AGENTS_BACKEND=cursor for Cursor CLI/cloud."
            ),
        )

    api_key = _local_llm_bearer_token()
    _is_ollama_cloud = "ollama.com" in api_url.lower()

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(
                api_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                return ValidationResult(
                    valid=True,
                    backend="local",
                    message=f"Local LLM API reachable at {api_url}",
                    details={"url": api_url},
                )
            if r.status_code in (401, 403):
                _hint = (
                    " — for Ollama Cloud set OLLAMA_API_KEY or CODE_AGENTS_LOCAL_LLM_API_KEY (ollama.com/settings/keys)"
                    if _is_ollama_cloud
                    else " — check CODE_AGENTS_LOCAL_LLM_API_KEY (local Ollama ignores placeholder keys)"
                )
                return ValidationResult(
                    valid=False,
                    backend="local",
                    message=f"Local LLM API returned {r.status_code}{_hint}",
                )
            return ValidationResult(
                valid=False,
                backend="local",
                message=f"Local LLM API returned unexpected status {r.status_code}",
            )
    except httpx.ConnectError:
        if _is_ollama_cloud:
            return ValidationResult(
                valid=False,
                backend="local",
                message=(
                    f"Cannot reach Ollama Cloud at {api_url} (HTTPS). "
                    "Check network/VPN/firewall; set OLLAMA_API_KEY in config for auth. "
                    "For a daemon on this machine use http://127.0.0.1:11434/v1 instead."
                ),
            )
        return ValidationResult(
            valid=False,
            backend="local",
            message=f"Cannot connect to local LLM at {api_url} (is Ollama running?)",
        )
    except Exception as e:
        return ValidationResult(
            valid=False,
            backend="local",
            message=f"Local LLM check failed: {e}",
        )


async def validate_cursor_http() -> ValidationResult:
    """Validate cursor HTTP endpoint is reachable."""
    import httpx

    api_url = os.getenv("CURSOR_API_URL", "").strip()
    if not api_url:
        return ValidationResult(
            valid=False,
            backend="cursor_http",
            message="CURSOR_API_URL not set",
        )

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return ValidationResult(
            valid=False,
            backend="cursor_http",
            message="CURSOR_API_KEY not set",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Just check connectivity — don't send a real query
            r = await client.get(api_url.rstrip("/") + "/models", headers={
                "Authorization": f"Bearer {api_key}",
            })
            if r.status_code in (200, 401, 403):
                # 200 = reachable + authed, 401/403 = reachable but auth issue
                if r.status_code == 200:
                    return ValidationResult(
                        valid=True, backend="cursor_http",
                        message=f"Cursor API reachable at {api_url}",
                    )
                return ValidationResult(
                    valid=False, backend="cursor_http",
                    message=f"Cursor API returned {r.status_code} — check CURSOR_API_KEY",
                )
            return ValidationResult(
                valid=False, backend="cursor_http",
                message=f"Cursor API returned unexpected status {r.status_code}",
            )
    except httpx.ConnectError:
        return ValidationResult(
            valid=False, backend="cursor_http",
            message=f"Cannot connect to Cursor API at {api_url}",
        )
    except Exception as e:
        return ValidationResult(
            valid=False, backend="cursor_http",
            message=f"Cursor API check failed: {e}",
        )


async def validate_claude_sdk() -> ValidationResult:
    """Validate Anthropic API key is set and the SDK is importable."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return ValidationResult(
            valid=False,
            backend="claude",
            message="ANTHROPIC_API_KEY not set. Configure via: code-agents init",
        )

    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return ValidationResult(
            valid=False,
            backend="claude",
            message="claude-agent-sdk not installed. Run: poetry install",
        )

    # Quick API validation — list models
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if r.status_code == 200:
                return ValidationResult(
                    valid=True, backend="claude",
                    message="Anthropic API key valid",
                    details={"key_prefix": api_key[:8] + "..."},
                )
            elif r.status_code in (401, 403):
                return ValidationResult(
                    valid=False, backend="claude",
                    message="Anthropic API key invalid or expired",
                )
            return ValidationResult(
                valid=True, backend="claude",
                message="Anthropic API key set (could not verify — network issue)",
                details={"status": r.status_code},
            )
    except Exception:
        # Network issue — key is set, assume valid
        return ValidationResult(
            valid=True, backend="claude",
            message="Anthropic API key configured (offline — cannot verify)",
        )


async def validate_claude_cli() -> ValidationResult:
    """Validate Claude CLI is installed and logged in."""
    cli_path = shutil.which("claude")
    if not cli_path:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message="Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code",
        )

    # Step 1: Check version (fast)
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr_v = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        version = stdout.decode("utf-8", errors="replace").strip()
        err_v = stderr_v.decode("utf-8", errors="replace").strip() if stderr_v else ""

        if proc.returncode != 0:
            logger.warning(
                "Claude CLI --version failed (exit %s): stdout=%r stderr=%r",
                proc.returncode,
                version[:200],
                err_v[:500],
            )
            return ValidationResult(
                valid=False,
                backend="claude-cli",
                message=f"Claude CLI exited with code {proc.returncode}. Run: claude (to login)",
            )
    except asyncio.TimeoutError:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message="Claude CLI timed out. It may need login: run `claude` in terminal",
        )
    except Exception as e:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message=f"Claude CLI check failed: {e}",
        )

    # Step 2: Validate authentication by sending a minimal prompt
    try:
        model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
        logger.info(
            "Claude CLI auth probe: model=%r (CODE_AGENTS_CLAUDE_CLI_MODEL) cli=%r",
            model,
            cli_path,
        )
        auth_proc = await asyncio.create_subprocess_exec(
            cli_path, "-p", "reply with ok", "--model", model,
            "--output-format", "text", "--max-turns", "1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        auth_stdout, auth_stderr = await asyncio.wait_for(auth_proc.communicate(), timeout=15.0)
        auth_out = auth_stdout.decode("utf-8", errors="replace").strip()
        auth_err = auth_stderr.decode("utf-8", errors="replace").strip()

        if auth_proc.returncode == 0 and auth_out:
            logger.info("Claude CLI auth probe succeeded (version line: %s)", version[:80])
            return ValidationResult(
                valid=True,
                backend="claude-cli",
                message=f"Claude CLI authenticated (version: {version})",
                details={"cli_path": cli_path, "version": version, "authenticated": True},
            )
        # Auth failed — check stderr for clues
        logger.warning(
            "Claude CLI auth probe failed: exit=%s model=%r stdout=%r stderr=%r",
            auth_proc.returncode,
            model,
            auth_out[:300],
            auth_err[:800],
        )
        if "login" in auth_err.lower() or "auth" in auth_err.lower() or "sign in" in auth_err.lower():
            return ValidationResult(
                valid=False,
                backend="claude-cli",
                message=f"Claude CLI not authenticated. Run: claude (to login). stderr: {auth_err[:100]}",
            )
        if "rate" in auth_err.lower() or "limit" in auth_err.lower():
            # Rate limited but authenticated
            return ValidationResult(
                valid=True,
                backend="claude-cli",
                message=f"Claude CLI authenticated (rate limited, version: {version})",
                details={"cli_path": cli_path, "version": version, "authenticated": True},
            )
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message=f"Claude CLI auth check failed (exit {auth_proc.returncode}): {auth_err[:150]}",
        )
    except asyncio.TimeoutError:
        # Timeout on auth check — CLI exists but may be slow; treat as valid
        return ValidationResult(
            valid=True,
            backend="claude-cli",
            message=f"Claude CLI ready (version: {version}, auth check timed out)",
            details={"cli_path": cli_path, "version": version, "authenticated": "unknown"},
        )
    except Exception as e:
        # Fallback: version worked so CLI is at least installed
        return ValidationResult(
            valid=True,
            backend="claude-cli",
            message=f"Claude CLI ready (version: {version}, auth check skipped: {e})",
            details={"cli_path": cli_path, "version": version},
        )


async def validate_backend(backend: Optional[str] = None) -> ValidationResult:
    """
    Validate the active backend connection.

    Detects the backend from CODE_AGENTS_BACKEND env var or the provided override.
    Returns a ValidationResult with status and message.
    """
    explicit_override = backend is not None
    if backend is None:
        backend = os.getenv("CODE_AGENTS_BACKEND", "").strip()
    if not backend:
        backend = "local"

    # Stale per-repo config (~/.code-agents/repos/<repo>/config.env) often still has
    # claude-cli while global ~/.code-agents/config.env defines local + Ollama URL — later
    # tier wins in merge and triggers Claude org auth errors. If a local LLM URL is set,
    # validate that instead (only when backend came from env, not an explicit override).
    if not explicit_override and backend == "claude-cli":
        _llm = os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip()
        if _llm:
            logger.warning(
                "CODE_AGENTS_BACKEND=claude-cli but CODE_AGENTS_LOCAL_LLM_URL is set — validating local LLM. "
                "Remove CODE_AGENTS_BACKEND from ~/.code-agents/repos/<repo>/config.env or set it to local."
            )
            backend = "local"

    logger.info("Validating backend connection: %s", backend or "auto-detect")
    if backend == "claude-cli":
        return await validate_claude_cli()
    elif backend == "claude":
        return await validate_claude_sdk()
    elif backend == "cursor_http":
        return await validate_cursor_http()
    elif backend == "local":
        return await validate_local_llm()
    elif backend == "cursor":
        api_url = os.getenv("CURSOR_API_URL", "").strip()
        if api_url:
            return await validate_cursor_http()
        return await validate_cursor_cli()
    else:
        logger.warning("Unknown CODE_AGENTS_BACKEND=%r — validating as local", backend)
        return await validate_local_llm()


async def validate_server_and_backend(server_url: str, backend: Optional[str] = None) -> list[ValidationResult]:
    """
    Validate both server connectivity and backend in parallel.

    Returns a list of ValidationResults (server + backend).
    """
    import httpx

    async def check_server() -> ValidationResult:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{server_url}/health")
                if r.status_code == 200:
                    return ValidationResult(
                        valid=True, backend="server",
                        message=f"Server running at {server_url}",
                    )
                return ValidationResult(
                    valid=False, backend="server",
                    message=f"Server returned {r.status_code}",
                )
        except Exception:
            return ValidationResult(
                valid=False, backend="server",
                message=f"Server not reachable at {server_url}",
            )

    # Run server check and backend validation in parallel
    server_result, backend_result = await asyncio.gather(
        check_server(),
        validate_backend(backend),
    )
    logger.info("Validation results: server=%s, backend=%s", server_result.valid, backend_result.valid)
    return [server_result, backend_result]


def validate_sync(backend: Optional[str] = None) -> ValidationResult:
    """Synchronous wrapper for validate_backend. For use in non-async contexts."""
    try:
        loop = asyncio.get_running_loop()
        # Already in an async context — can't use asyncio.run
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, validate_backend(backend)).result(timeout=10)
    except RuntimeError:
        result = asyncio.run(validate_backend(backend))
        logger.debug("Sync validation result: valid=%s, message=%s", result.valid, result.message)
        return result
