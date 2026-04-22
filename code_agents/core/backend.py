from __future__ import annotations

import json
import logging
import os
import shutil
from typing import AsyncIterator, Optional

from .config import AgentConfig
from .cursor_cli import resolve_cursor_cli_path_for_sdk
from .message_types import AssistantMessage, ResultMessage, SystemMessage, TextBlock

logger = logging.getLogger("code_agents.core.backend")

# Track when each session was created: session_id → timestamp
_session_timestamps: dict[str, float] = {}

_SESSION_MAX_AGE_DEFAULT = 3600  # 1 hour


def _enforce_session_age(session_id: Optional[str]) -> Optional[str]:
    """Discard sessions older than max age. Returns session_id or None."""
    if not session_id:
        return None
    import time
    max_age = int(os.getenv("CODE_AGENTS_SESSION_MAX_AGE_SECS", str(_SESSION_MAX_AGE_DEFAULT)))
    ts = _session_timestamps.get(session_id)
    if ts is None:
        # First time seeing this session — record it
        _session_timestamps[session_id] = time.time()
        return session_id
    age = time.time() - ts
    if age > max_age:
        age_str = f"{int(age // 3600)}h {int((age % 3600) // 60)}m" if age >= 3600 else f"{int(age // 60)}m"
        logger.info("Session %s is %s old (max %ds) — starting fresh", session_id, age_str, max_age)
        import sys
        print(f"\n  \033[33m⚠ Session expired ({age_str} old, max {max_age // 60}m). Starting fresh.\033[0m", file=sys.stderr)
        _session_timestamps.pop(session_id, None)
        return None
    return session_id


def record_session_start(session_id: str) -> None:
    """Record when a session was created (called when server returns a new session_id)."""
    import time
    _session_timestamps[session_id] = time.time()


def _cursor_sdk_subprocess_env(api_key: str | None, env_key: str) -> dict[str, str]:
    """Build ``options.env`` for cursor-agent SDK (merged as ``{**os.environ, **options.env}``).

    Calls :func:`code_agents.env_loader.sanitize_ssl_cert_environment` so inherited TLS
    paths are fixed before the subprocess starts (see also ``load_all_env``).
    """
    from .env_loader import sanitize_ssl_cert_environment

    sanitize_ssl_cert_environment()
    out: dict[str, str] = {}
    if api_key:
        out[env_key] = api_key
    return out


def _resolve_openai_http_url_and_key(agent: AgentConfig) -> tuple[str, str]:
    """Resolve OpenAI-compatible base URL and Bearer token for HTTP backends."""
    extra = agent.extra_args or {}
    eb = (agent.backend or "").strip().lower()
    if eb == "local":
        url = (
            str(extra.get("cursor_api_url") or "").strip()
            or os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip()
            or os.getenv("CURSOR_API_URL", "").strip()
        )
        api_key = (str(agent.api_key).strip() if agent.api_key else "")
        if not api_key:
            api_key = os.getenv("CODE_AGENTS_LOCAL_LLM_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("OLLAMA_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("CURSOR_API_KEY", "").strip()
        if not api_key:
            api_key = "local"
        return url, api_key
    url = str(extra.get("cursor_api_url") or "").strip() or os.getenv("CURSOR_API_URL", "").strip()
    api_key = agent.api_key or os.getenv("CURSOR_API_KEY") or ""
    return url, str(api_key).strip() if api_key else ""


async def _run_cursor_http(
    agent: AgentConfig,
    prompt: str,
    model: str,
) -> AsyncIterator:
    """Call an OpenAI-compatible API URL with API key (no cursor-agent CLI or desktop app)."""
    import httpx

    from .message_types import (
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        TextBlock,
    )

    base_url, api_key = _resolve_openai_http_url_and_key(agent)
    if not base_url or not str(base_url).strip():
        eb = (agent.backend or "").strip().lower()
        if eb == "local":
            raise RuntimeError(
                "local backend requires CODE_AGENTS_LOCAL_LLM_URL (or CURSOR_API_URL / extra_args.cursor_api_url). "
                "Set in ~/.code-agents/config.env or run install.sh for Ollama defaults."
            )
        raise RuntimeError(
            "cursor_http backend requires cursor_api_url. "
            "Set extra_args.cursor_api_url in agent YAML or CURSOR_API_URL in environment."
        )
    base_url = str(base_url).rstrip("/")
    if not api_key:
        eb = (agent.backend or "").strip().lower()
        if eb == "local":
            api_key = "local"
        else:
            raise RuntimeError("cursor_http backend requires CURSOR_API_KEY in agent config or environment.")

    messages = []
    if agent.system_prompt and agent.system_prompt.strip():
        messages.append({"role": "system", "content": agent.system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": False}

    _be = (agent.backend or "").strip().lower() or "cursor_http"
    logger.info(
        "%s POST %s/chat/completions model=%s messages=%d (no cursor-agent CLI)",
        _be,
        base_url,
        model,
        len(messages),
    )
    logger.debug("cursor_http request body keys=%s", list(body.keys()))
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            _txt = (e.response.text or "")[:4000]
            logger.error(
                "cursor_http HTTP %s for %s/chat/completions — response snippet: %s",
                e.response.status_code,
                base_url,
                _txt,
            )
            raise RuntimeError(
                f"cursor_http API error HTTP {e.response.status_code} at {base_url}/chat/completions. "
                f"Body snippet: {_txt[:800]}"
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "cursor_http request failed to %s: %s (check VPN, URL, TLS, and that the server is up)",
                base_url,
                e,
            )
            raise RuntimeError(
                f"cursor_http could not reach {base_url}: {e}"
            ) from e
        data = response.json()
    logger.debug("cursor_http response status=%d content_length=%d", response.status_code, len(response.text))

    choices = data.get("choices") or []
    usage = data.get("usage") or {}
    content = ""
    if choices and len(choices) > 0:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            content = str(msg.get("content") or "")
        elif isinstance(msg, str):
            content = msg

    _init_backend = "local" if (agent.backend or "").strip().lower() == "local" else "cursor_http"
    yield SystemMessage(subtype="init", data={"backend": _init_backend})
    yield AssistantMessage(content=[TextBlock(text=content)], model=model)
    yield ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        session_id=data.get("session_id") or "",
        usage=usage if isinstance(usage, dict) else None,
    )


def _patch_cursor_sdk_dash():
    """Strip trailing '-' from cursor-agent-sdk commands.

    Upstream cursor-agent-sdk appends '-' as a positional argument assuming
    the CLI interprets it as 'read from stdin'. The cursor-agent CLI treats
    it as a literal prompt instead. This patch removes '-' so the CLI falls
    back to reading the actual prompt from stdin.

    See: https://github.com/gitcnd/cursor-agent-sdk-python/issues/XXX
    """
    try:
        from cursor_agent_sdk.transport import SubprocessCLITransport
    except ImportError:
        return

    _original = SubprocessCLITransport._build_command

    def _patched(self):
        cmd = _original(self)
        if cmd and cmd[-1] == "-":
            cmd.pop()
        return cmd

    SubprocessCLITransport._build_command = _patched


def _cursor_stderr_indicates_trust_security_failure(stderr: str) -> bool:
    """True when cursor-agent failed in the macOS Security helper (often exit 44) after --trust."""
    s = (stderr or "").lower()
    if "security" not in s:
        return False
    return (
        "security process" in s
        or "security command" in s
        or "code: 44" in s
    )


_patch_cursor_sdk_dash()


def _build_claude_cli_cmd(
    cli_path: str,
    agent: AgentConfig,
    model: str,
    session_id: Optional[str],
    *,
    stream: bool = False,
) -> list[str]:
    """Build the claude CLI command list.  Shared by streaming and non-streaming paths."""
    output_format = "stream-json" if stream else "json"
    cmd = [cli_path, "--print", "--output-format", output_format]
    # Claude CLI requires --verbose when using --output-format=stream-json with --print
    if stream:
        cmd.append("--verbose")

    if model:
        cmd.extend(["--model", model])

    if agent.system_prompt:
        cmd.extend(["--system-prompt", agent.system_prompt])

    # Only resume sessions when explicitly requested (e.g., /resume command).
    # Default: always start fresh to avoid stale context and hallucination.
    _force_new = os.getenv("CODE_AGENTS_FORCE_NEW_SESSION", "true").strip().lower()
    if session_id and _force_new not in ("1", "true", "yes"):
        cmd.extend(["--resume", session_id])
        logger.debug("claude-cli: resuming session %s", session_id)
    else:
        logger.debug("claude-cli: fresh session (force_new=%s, session_id=%s)", _force_new, session_id or "none")

    # Permission mode
    if agent.permission_mode in ("acceptEdits", "bypassPermissions"):
        cmd.append("--dangerously-skip-permissions")

    return cmd


def _build_claude_cli_env() -> dict[str, str]:
    """Build environment dict for the claude CLI subprocess."""
    cli_env = {**os.environ}
    _max_tokens = os.getenv("CODE_AGENTS_CLAUDE_MAX_TOKENS", "500000")
    _compact_window = os.getenv("CODE_AGENTS_CLAUDE_COMPACT_WINDOW", "200000")
    cli_env.setdefault("CLAUDE_CODE_MAX_SESSION_TOKENS", _max_tokens)
    cli_env.setdefault("CLAUDE_CODE_AUTO_COMPACT_WINDOW", _compact_window)
    logger.debug("claude-cli env: MAX_SESSION_TOKENS=%s, AUTO_COMPACT_WINDOW=%s",
                 cli_env.get("CLAUDE_CODE_MAX_SESSION_TOKENS"),
                 cli_env.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"))
    return cli_env


async def _run_claude_cli_stream(
    agent: AgentConfig,
    prompt: str,
    model: str,
    cwd: str,
    session_id: Optional[str] = None,
) -> AsyncIterator:
    """
    Run a query via the Claude CLI with streaming output (--output-format stream-json).

    Yields messages incrementally as the model generates text, so callers see
    output within seconds instead of waiting for the full response.

    Each stdout line is a JSON object.  Key event types:
      - ``{"type": "system", "subtype": "init", ...}`` — session start
      - ``{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}`` — text chunks
      - ``{"type": "result", "subtype": "result", "result": "...", ...}`` — final result
    """
    import asyncio
    import time as _time

    cli_path = shutil.which("claude")
    if not cli_path:
        raise RuntimeError(
            "Claude CLI not found. Install it: npm install -g @anthropic-ai/claude-code\n"
            "Then login: claude (follow browser prompts)"
        )

    cmd = _build_claude_cli_cmd(cli_path, agent, model, session_id, stream=True)
    cmd.append(prompt)

    logger.info("claude-cli-stream: %s model=%s cwd=%s prompt_len=%d", cli_path, model, cwd, len(prompt))
    logger.debug("claude-cli-stream FULL SYSTEM PROMPT:\n%s", agent.system_prompt or "(none)")
    logger.debug("claude-cli-stream FULL USER PROMPT:\n%s", prompt)

    cli_env = _build_claude_cli_env()

    _timeout = int(os.getenv("CODE_AGENTS_CLAUDE_CLI_TIMEOUT", "300"))  # 5 min default
    logger.info("claude-cli-stream: starting subprocess (timeout=%ds)", _timeout)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=cli_env,
    )

    _t0 = _time.monotonic()
    init_yielded = False
    result_yielded = False
    text_yielded = False

    try:
        # Read stdout line-by-line for streaming JSON events
        while True:
            try:
                remaining = _timeout - (_time.monotonic() - _t0)
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                line_bytes = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=remaining
                )
            except asyncio.TimeoutError:
                _elapsed = _time.monotonic() - _t0
                logger.error(
                    "claude-cli-stream: TIMEOUT after %.0fs (limit=%ds), killing PID=%d",
                    _elapsed, _timeout, proc.pid,
                )
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    f"Claude CLI timed out after {_timeout}s. The model may be overloaded or the prompt too large. "
                    f"Increase timeout with CODE_AGENTS_CLAUDE_CLI_TIMEOUT={_timeout * 2}"
                )

            if not line_bytes:
                # EOF — subprocess closed stdout
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("claude-cli-stream: skipping non-JSON line: %s", line[:200])
                continue

            event_type = event.get("type", "")

            # --- system init event ---
            if event_type == "system":
                init_yielded = True
                yield SystemMessage(subtype=event.get("subtype", "init"), data={
                    "backend": "claude-cli",
                    "session_id": event.get("session_id", ""),
                })

            # --- assistant text chunk ---
            elif event_type == "assistant":
                if not init_yielded:
                    init_yielded = True
                    yield SystemMessage(subtype="init", data={"backend": "claude-cli"})
                msg = event.get("message", {})
                content_blocks = msg.get("content", []) if isinstance(msg, dict) else []
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            text_yielded = True
                            yield AssistantMessage(content=[TextBlock(text=text)], model=model)

            # --- final result ---
            elif event_type == "result":
                result_yielded = True
                sid = event.get("session_id", "")
                duration = event.get("duration_ms", 0)
                duration_api = event.get("duration_api_ms", 0)
                cost = event.get("total_cost_usd", 0)
                usage = event.get("usage", {})
                is_error = event.get("is_error", False)
                result_text = event.get("result", "")

                if not init_yielded:
                    init_yielded = True
                    yield SystemMessage(subtype="init", data={
                        "backend": "claude-cli",
                        "session_id": sid,
                        "cost_usd": cost,
                    })

                # Yield the full result text only if no streaming chunks were
                # received — otherwise the text was already yielded incrementally
                # and re-yielding it here causes duplicate display.
                if result_text and not text_yielded:
                    yield AssistantMessage(content=[TextBlock(text=result_text)], model=model)

                yield ResultMessage(
                    subtype=event.get("subtype", "result"),
                    duration_ms=duration,
                    duration_api_ms=duration_api,
                    is_error=is_error,
                    session_id=sid,
                    usage=usage if isinstance(usage, dict) else None,
                )

        # Wait for process to finish
        stderr_data = await proc.stderr.read() if proc.stderr else b""
        await proc.wait()

    except RuntimeError:
        raise
    except Exception:
        proc.kill()
        await proc.wait()
        raise

    _elapsed = _time.monotonic() - _t0
    logger.info("claude-cli-stream: completed in %.1fs (exit=%d)", _elapsed, proc.returncode or 0)

    if proc.returncode != 0:
        error_text = (stderr_data).decode("utf-8", errors="replace").strip() if stderr_data else ""
        logger.error("claude-cli-stream stderr: %s", error_text[:500] if error_text else "(empty)")
        error_lines = [l for l in error_text.splitlines()
                       if "warn:" not in l.lower() and "corporate-ca" not in l.lower()]
        error_msg = "\n".join(error_lines) or f"Claude CLI exited with code {proc.returncode}"
        raise RuntimeError(f"Claude CLI error: {error_msg}")

    # If no structured events were yielded (e.g. empty output), yield defaults
    if not init_yielded:
        yield SystemMessage(subtype="init", data={"backend": "claude-cli"})
    if not result_yielded:
        yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                            is_error=False, session_id="", usage=None)


async def _run_claude_cli(
    agent: AgentConfig,
    prompt: str,
    model: str,
    cwd: str,
    session_id: Optional[str] = None,
    *,
    stream: bool = True,
) -> AsyncIterator:
    """
    Run a query via the Claude CLI (claude --print).

    Uses the user's Claude subscription auth — no API key needed.
    Requires the ``claude`` CLI to be installed and logged in.

    When ``stream=True`` (default), uses ``--output-format stream-json`` with
    ``Popen`` line-by-line reading so callers receive incremental text chunks
    instead of waiting for the full response.

    When ``stream=False``, uses the original ``--output-format json`` path that
    waits for the subprocess to complete before yielding messages.
    """
    if stream:
        async for message in _run_claude_cli_stream(agent, prompt, model, cwd, session_id):
            yield message
        return

    # --- Non-streaming (legacy) path ---
    import asyncio

    cli_path = shutil.which("claude")
    if not cli_path:
        raise RuntimeError(
            "Claude CLI not found. Install it: npm install -g @anthropic-ai/claude-code\n"
            "Then login: claude (follow browser prompts)"
        )

    cmd = _build_claude_cli_cmd(cli_path, agent, model, session_id, stream=False)
    cmd.append(prompt)

    logger.info("claude-cli: %s model=%s cwd=%s prompt_len=%d", cli_path, model, cwd, len(prompt))
    logger.debug("claude-cli FULL SYSTEM PROMPT:\n%s", agent.system_prompt or "(none)")
    logger.debug("claude-cli FULL USER PROMPT:\n%s", prompt)

    # Claude Code session/context limits — prevent runaway token usage
    cli_env = _build_claude_cli_env()

    _timeout = int(os.getenv("CODE_AGENTS_CLAUDE_CLI_TIMEOUT", "300"))  # 5 min default
    logger.info("claude-cli: starting subprocess (timeout=%ds)", _timeout)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=cli_env,
    )

    import time as _time
    _t0 = _time.monotonic()
    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=_timeout
        )
    except asyncio.TimeoutError:
        _elapsed = _time.monotonic() - _t0
        logger.error("claude-cli: TIMEOUT after %.0fs (limit=%ds), killing PID=%d", _elapsed, _timeout, proc.pid)
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"Claude CLI timed out after {_timeout}s. The model may be overloaded or the prompt too large. "
            f"Increase timeout with CODE_AGENTS_CLAUDE_CLI_TIMEOUT={_timeout * 2}"
        )
    _elapsed = _time.monotonic() - _t0
    logger.info("claude-cli: completed in %.1fs (exit=%d, stdout=%d bytes)", _elapsed, proc.returncode or 0, len(stdout_data))

    if proc.returncode != 0:
        error_text = stderr_data.decode("utf-8", errors="replace").strip()
        stdout_text = stdout_data.decode("utf-8", errors="replace").strip()
        logger.error("claude-cli stderr: %s", error_text[:500] if error_text else "(empty)")
        # Try to extract error from JSON stdout (Claude CLI returns JSON even on error)
        if stdout_text:
            logger.error("claude-cli stdout: %s", stdout_text[:500])
            try:
                err_data = json.loads(stdout_text)
                if err_data.get("is_error") and err_data.get("result"):
                    raise RuntimeError(f"Claude CLI: {err_data['result']}")
            except (json.JSONDecodeError, KeyError):
                pass
        # Filter out SSL/cert warnings for user-facing message
        error_lines = [l for l in error_text.splitlines()
                       if "warn:" not in l.lower() and "corporate-ca" not in l.lower()]
        error_msg = "\n".join(error_lines) or f"Claude CLI exited with code {proc.returncode}"
        raise RuntimeError(f"Claude CLI error: {error_msg}")

    # Parse JSON output
    output = stdout_data.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # Fallback: treat as plain text
        yield SystemMessage(subtype="init", data={"backend": "claude-cli"})
        yield AssistantMessage(content=[TextBlock(text=output)], model=model)
        yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                            is_error=False, session_id="", usage=None)
        return

    # Extract from JSON result
    result_text = data.get("result", "")
    sid = data.get("session_id", "")
    duration = data.get("duration_ms", 0)
    duration_api = data.get("duration_api_ms", 0)
    cost = data.get("total_cost_usd", 0)
    usage = data.get("usage", {})

    yield SystemMessage(subtype="init", data={
        "backend": "claude-cli",
        "session_id": sid,
        "cost_usd": cost,
    })
    yield AssistantMessage(content=[TextBlock(text=result_text)], model=model)
    yield ResultMessage(
        subtype="result",
        duration_ms=duration,
        duration_api_ms=duration_api,
        is_error=data.get("is_error", False),
        session_id=sid,
        usage=usage if isinstance(usage, dict) else None,
    )


async def run_agent(
    agent: AgentConfig,
    prompt: str,
    *,
    model_override: Optional[str] = None,
    cwd_override: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AsyncIterator:
    """
    Run a query against the configured backend (cursor or claude) and
    yield SDK messages.  The caller iterates with `async for message in ...`.

    ``model_override`` is the **backend** model id (e.g. composer-2-fast). The OpenAI API
    ``model`` field used to pick an agent by name must not be passed here—use ``None``
    so ``agent.model`` from YAML is used.

    Both SDKs expose identical APIs:
      - query(prompt, options) → AsyncIterator[Message]
      - *AgentOptions(model, cwd, permission_mode, extra_args, resume, system_prompt)
      - Same message types: SystemMessage, AssistantMessage, ResultMessage,
        TextBlock, ToolUseBlock, ToolResultBlock
    """
    import os

    model = model_override or agent.model
    cwd = cwd_override or agent.cwd

    # Session freshness: discard sessions older than max age to avoid stale context.
    # Default: 1 hour. Set CODE_AGENTS_SESSION_MAX_AGE_SECS to override.
    session_id = _enforce_session_age(session_id)

    # OTel span — wraps the entire agent run for distributed tracing
    _span = None
    try:
        from code_agents.observability.otel import get_tracer
        _tracer = get_tracer()
        _span = _tracer.start_span("run_agent")
        _span.set_attribute("agent.name", agent.name)
        _span.set_attribute("agent.backend", agent.backend)
        _span.set_attribute("agent.model", model or "")
        _span.set_attribute("agent.session_id", session_id or "")
    except Exception:
        _span = None  # OTel is optional

    _sys_len = len(agent.system_prompt or "")
    _prompt_len = len(prompt)
    _total = _sys_len + _prompt_len

    logger.info(
        "run_agent START agent=%s backend=%s model=%s session=%s cwd=%s "
        "system_prompt=%d prompt=%d total=%d chars (~%dk tokens)",
        agent.name, agent.backend, model, session_id or "-", cwd,
        _sys_len, _prompt_len, _total, _total // 4,
    )
    if _total > 100000:
        logger.warning(
            "run_agent ⚠ LARGE INPUT: %d chars (~%dk tokens) for agent=%s. "
            "system_prompt=%d, prompt=%d. Consider trimming context.",
            _total, _total // 4, agent.name, _sys_len, _prompt_len,
        )
    logger.debug(
        "run_agent cwd resolution: cwd_override=%r agent.cwd=%r → effective=%r",
        cwd_override, agent.cwd, cwd,
    )
    logger.debug(
        "run_agent details: extra_args=%s api_key=%s permission=%s",
        list((agent.extra_args or {}).keys()),
        "set" if agent.api_key else "unset",
        agent.permission_mode,
    )

    # Check for claude-cli override via environment
    backend = agent.backend
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        backend = "claude-cli"

    if backend == "claude-cli":
        # Map short model names to valid Claude CLI model IDs
        _claude_model_map = {
            "opus": "claude-opus-4-6",
            "opus 4.6": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "sonnet 4.6": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
            "haiku 4.5": "claude-haiku-4-5-20251001",
        }
        cli_model = os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
        # Resolve short names from env var
        cli_model = _claude_model_map.get(cli_model.lower(), cli_model)
        # Only use agent model if it's a valid Claude model ID (starts with "claude-")
        if model and model.startswith("claude-"):
            cli_model = model
        logger.debug("claude-cli model resolution: agent=%s env=%s → %s",
                      model, os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", ""), cli_model)
        async for message in _run_claude_cli(agent, prompt, cli_model, cwd, session_id):
            yield message
        return

    if agent.backend == "cursor_http":
        async for message in _run_cursor_http(agent, prompt, model):
            yield message
        return

    if agent.backend == "local":
        async for message in _run_cursor_http(agent, prompt, model):
            yield message
        return

    # Headless path: avoid cursor-agent CLI (and desktop proxy) when an OpenAI-compatible base URL is set.
    if agent.backend == "cursor":
        _http_base = (agent.extra_args or {}).get("cursor_api_url") or os.getenv("CURSOR_API_URL")
        if _http_base and str(_http_base).strip():
            async for message in _run_cursor_http(agent, prompt, model):
                yield message
            return
        _http_only = os.getenv("CODE_AGENTS_HTTP_ONLY", "").strip().lower() in ("1", "true", "yes")
        if _http_only:
            raise RuntimeError(
                "CODE_AGENTS_HTTP_ONLY=1 but CURSOR_API_URL (or extra_args.cursor_api_url) is not set. "
                "Set CURSOR_API_URL in .env, or unset CODE_AGENTS_HTTP_ONLY to allow the cursor-agent CLI."
            )

    if agent.backend == "claude":
        from claude_agent_sdk import query as sdk_query
        from claude_agent_sdk import ClaudeAgentOptions as OptionsClass
        env_key = "ANTHROPIC_API_KEY"
    else:
        try:
            from cursor_agent_sdk import CursorAgentOptions as OptionsClass
            from cursor_agent_sdk import query as sdk_query
        except ImportError:
            raise RuntimeError(
                "cursor-agent-sdk is not installed (needed for the cursor-agent CLI). "
                "Install with: poetry install --with cursor — "
                "or set CURSOR_API_URL to use HTTP mode without the CLI."
            ) from None
        env_key = "CURSOR_API_KEY"

    api_key = agent.api_key or os.getenv(env_key)
    if agent.backend == "claude":
        env: dict[str, str] = {}
        if api_key:
            env[env_key] = api_key
    else:
        env = _cursor_sdk_subprocess_env(api_key, env_key)

    # Inject --trust so cursor-agent doesn't prompt for workspace trust (headless).
    # Set CODE_AGENTS_CURSOR_TRUST=0 to skip if it triggers macOS Security issues.
    import copy as _copy
    extra = _copy.deepcopy(agent.extra_args or {})
    if agent.backend != "claude":
        _skip_trust = os.getenv("CODE_AGENTS_CURSOR_TRUST", "").strip().lower() in (
            "0", "false", "no", "off",
        )
        if not _skip_trust:
            extra.setdefault("trust", None)  # None = bare flag (--trust)

    # Terminal mode overrides agent YAML permission_mode:
    #   edit mode (shift+tab) → acceptEdits
    #   superpower (/superpower or auto-pilot) → acceptEdits
    #   plan mode → default (read-only planning)
    effective_permission = agent.permission_mode
    try:
        from code_agents.chat.chat_input import is_edit_mode
        if is_edit_mode():
            effective_permission = "acceptEdits"
    except Exception:
        pass
    # Superpower env flag (set by chat session state via env)
    if os.getenv("CODE_AGENTS_SUPERPOWER", "").strip().lower() in ("1", "true", "yes"):
        effective_permission = "acceptEdits"

    _opt_kw: dict = {
        "model": model,
        "cwd": cwd,
        "permission_mode": effective_permission,
        "extra_args": extra,
        "resume": session_id,
        "system_prompt": agent.system_prompt or None,
        "env": env,
    }
    if agent.backend == "cursor":
        _cli_override = resolve_cursor_cli_path_for_sdk()
        if _cli_override:
            _opt_kw["cli_path"] = _cli_override
    options = OptionsClass(**_opt_kw)

    if agent.backend == "cursor":
        _has_trust = "trust" in extra
        logger.info(
            "cursor-agent SDK: invoking subprocess (cursor-agent CLI via SDK) agent=%s model=%s "
            "cwd=%s session=%s permission=%s api_key=%s trust_in_extra=%s extra_keys=%s",
            agent.name,
            model,
            cwd,
            session_id or "-",
            effective_permission,
            "set" if api_key else "unset",
            _has_trust,
            sorted((extra or {}).keys()),
        )
        logger.debug(
            "cursor-agent env: CODE_AGENTS_HTTP_ONLY=%r CURSOR_API_URL_set=%s",
            os.getenv("CODE_AGENTS_HTTP_ONLY", ""),
            bool(
                str((agent.extra_args or {}).get("cursor_api_url") or os.getenv("CURSOR_API_URL") or "").strip()
            ),
        )

    gen = sdk_query(prompt=prompt, options=options)
    yielded_any = False
    try:
        async for message in gen:
            yielded_any = True
            yield message
    except Exception as e:
        if yielded_any or agent.backend == "claude":
            raise
        from .openai_errors import log_cursor_backend_failure, unwrap_process_error

        if agent.backend == "cursor":
            log_cursor_backend_failure(
                e,
                log=logger,
                agent_name=agent.name,
                backend=agent.backend,
                model=model or "",
                cwd=str(cwd),
                phase="sdk_query",
            )
        pe = unwrap_process_error(e)
        stderr = ((getattr(pe, "stderr", None) if pe is not None else None) or "").strip()
        if (
            pe is None
            or "trust" not in extra
            or not _cursor_stderr_indicates_trust_security_failure(stderr)
        ):
            raise
        extra_no_trust = _copy.deepcopy(extra)
        extra_no_trust.pop("trust", None)
        _retry_kw: dict = {
            "model": model,
            "cwd": cwd,
            "permission_mode": effective_permission,
            "extra_args": extra_no_trust,
            "resume": session_id,
            "system_prompt": agent.system_prompt or None,
            "env": env,
        }
        _cli_retry = resolve_cursor_cli_path_for_sdk()
        if _cli_retry:
            _retry_kw["cli_path"] = _cli_retry
        options_retry = OptionsClass(**_retry_kw)
        logger.warning(
            "cursor-agent: retrying without --trust after Security-related stderr (snippet): %s",
            stderr[:1200],
        )
        async for message in sdk_query(prompt=prompt, options=options_retry):
            yield message
