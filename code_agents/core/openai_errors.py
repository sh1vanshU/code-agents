"""OpenAI-style error JSON + helpers (shared by app and routers; no circular imports)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

logger = logging.getLogger("code_agents.core.openai_errors")


def openai_style_error(
    message: str, error_type: str = "internal_error", code: str = "cursor_agent_error"
) -> dict:
    return {"error": {"message": message, "type": error_type, "code": code}}


def log_cursor_backend_failure(
    exc: BaseException,
    *,
    log: logging.Logger | None = None,
    prefix: str = "",
    agent_name: str = "",
    backend: str = "",
    model: str = "",
    cwd: str = "",
    phase: str = "",
) -> Any:
    """Emit detailed logs when the Cursor backend (cursor-agent subprocess) fails.

    Returns the unwrapped :class:`ProcessError` when found, else ``None``.
    Safe to call for any exception (non-Process errors are logged with traceback).
    """
    lg = log or logger
    head = f"{prefix}[agent={agent_name} backend={backend} model={model!r} cwd={cwd!r} phase={phase}] "
    pe = unwrap_process_error(exc)
    if pe is not None:
        stderr = (getattr(pe, "stderr", None) or "").strip()
        stdout = (getattr(pe, "stdout", None) or "").strip()
        exit_code = getattr(pe, "exit_code", None)
        cmd = getattr(pe, "cmd", None)
        lg.error(
            "%scursor-agent subprocess failed: exit_code=%r cmd=%r stderr_chars=%d stdout_chars=%d",
            head,
            exit_code,
            cmd,
            len(stderr),
            len(stdout),
        )
        if stderr:
            lg.error("%scursor-agent stderr (full):\n%s", head, stderr[:24000])
        elif lg.isEnabledFor(logging.DEBUG):
            lg.debug("%sProcessError had empty stderr; repr=%r", head, pe)
        if stdout:
            lg.error("%scursor-agent stdout (snippet):\n%s", head, stdout[:8000])
        return pe
    lg.error("%sBackend error (not a ProcessError): %s", head, exc, exc_info=True)
    return None


def unwrap_process_error(exc: BaseException | None):
    """Find ProcessError inside ExceptionGroup / __cause__ chains (Python 3.11+)."""
    if exc is None:
        return None
    try:
        from cursor_agent_sdk._errors import ProcessError
    except ImportError:
        return None
    if isinstance(exc, ProcessError):
        return exc
    try:
        from builtins import BaseExceptionGroup
    except ImportError:
        BaseExceptionGroup = ()  # type: ignore[misc,assignment]
    if BaseExceptionGroup and isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = unwrap_process_error(sub)
            if found is not None:
                return found
    cause = exc.__cause__
    if cause is not None:
        return unwrap_process_error(cause)
    return None


def format_process_error_message(exc) -> str:
    """Human-readable message for ProcessError (HTTP JSON and SSE error chunks)."""
    msg = str(exc)
    stderr = (getattr(exc, "stderr", None) or "").strip()
    logger.debug(
        "format_process_error_message: exit_code=%r stderr_len=%d",
        getattr(exc, "exit_code", None),
        len(stderr),
    )
    if stderr:
        msg += f". cursor-agent stderr: {stderr!r}"
    msg += (
        " Hint: run the Cursor desktop app on this machine, or set CURSOR_API_URL in .env "
        "(OpenAI-compatible /chat/completions base; see README), or use a Claude backend agent."
    )
    # Avoid lone surrogates breaking json.dumps in JSONResponse.render.
    try:
        msg.encode("utf-8")
    except UnicodeEncodeError:
        msg = msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    return msg


def process_error_json_response(exc) -> JSONResponse:
    msg = format_process_error_message(exc)
    try:
        return JSONResponse(
            status_code=502,
            content=openai_style_error(msg, error_type="process_error", code="cursor_agent_failed"),
        )
    except Exception:
        safe = repr(msg)[:8000]
        return JSONResponse(
            status_code=502,
            content=openai_style_error(
                safe,
                error_type="process_error",
                code="cursor_agent_failed",
            ),
        )
