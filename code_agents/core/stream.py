from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
from typing import Any, Iterator, Optional

from .context_manager import ContextManager
from code_agents.agent_system.rules_loader import load_rules
from code_agents.reviews.style_matcher import get_style_prompt

logger = logging.getLogger(__name__)

from .backend import run_agent

# Agents that benefit from style guide injection
_STYLE_AGENTS = {"code-writer", "code-reasoning", "code-tester", "qa-regression"}


def _inject_context(agent, cwd: str = ""):
    """Inject rules + user profile + style guide into agent system prompt. Returns a copy if modified."""
    rules_text = load_rules(agent.name, cwd or os.getenv("TARGET_REPO_PATH"))
    user_role = os.getenv("CODE_AGENTS_USER_ROLE", "")
    user_name = os.getenv("CODE_AGENTS_NICKNAME", "")
    repo_path = cwd or os.getenv("TARGET_REPO_PATH", "")
    style_text = get_style_prompt(repo_path) if repo_path and agent.name in _STYLE_AGENTS else ""

    # Always-on formatting hint (~30 tokens, improves readability)
    _fmt_hint = "FORMAT: Use markdown tables for structured data (comparisons, lists, status). Keep responses concise."

    if not rules_text and not user_role and not style_text:
        agent = copy.deepcopy(agent)
        agent.system_prompt = (agent.system_prompt or "") + f"\n\n{_fmt_hint}"
        return agent

    agent = copy.deepcopy(agent)
    agent.system_prompt = (agent.system_prompt or "") + f"\n\n{_fmt_hint}"
    if rules_text:
        agent.system_prompt = f"{rules_text}\n\n{agent.system_prompt or ''}"
    if style_text:
        agent.system_prompt = (agent.system_prompt or "") + f"\n\n{style_text}"
    if user_role:
        role_hints = {
            "Junior Engineer": "Explain reasoning step by step. Include examples.",
            "Senior Engineer": "Be concise. Focus on non-obvious aspects.",
            "Lead Engineer": "Focus on architecture, trade-offs, risk, cross-team impacts.",
            "Principal Engineer / Architect": "Strategic, system-wide, long-term maintainability.",
            "Engineering Manager": "Status summaries, timeline impacts, business context.",
        }
        hint = role_hints.get(user_role, "")
        name_str = f" ({user_name})" if user_name and user_name != "you" else ""
        agent.system_prompt = (agent.system_prompt or "") + f"\n\nUser: {user_role}{name_str}. {hint}"

    return agent
from .config import AgentConfig
from .models import CompletionRequest, Message
from .openai_errors import (
    format_process_error_message,
    log_cursor_backend_failure,
    unwrap_process_error,
)

TOOL_RESULT_MAX_LINES = 30


# ── SSE helpers ──────────────────────────────────────────────────────────────

def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def make_chunk(
    cid: str,
    model: str,
    created: int,
    delta: dict,
    finish_reason: Optional[str] = None,
) -> str:
    return sse({
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "system_fingerprint": None,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
            "logprobs": None,
        }],
    })


# ── Formatting ───────────────────────────────────────────────────────────────

def _trim_to_tail(text: str, max_lines: int = TOOL_RESULT_MAX_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return f"... ({len(lines) - max_lines} lines omitted) ...\n" + "\n".join(lines[-max_lines:])


def format_tool_use(block: Any) -> str:
    args = json.dumps(block.input, indent=2) if isinstance(block.input, dict) else str(block.input)
    return f"\n\n> **Using tool: {block.name}**\n> ```json\n> {args}\n> ```\n\n"


def format_tool_result(block: Any) -> str:
    if isinstance(block.content, list):
        content = json.dumps(block.content, indent=2)
    elif isinstance(block.content, str):
        content = block.content
    else:
        content = str(block.content) if block.content else ""
    content = _trim_to_tail(content)
    return f"\n\n**Tool Result** (`{block.tool_use_id}`):\n```\n{content}\n```\n\n"


def iter_tool_result_chunks(block: Any, chunk_lines: int = 5) -> Iterator[str]:
    """Yield tool result content in small line-based chunks for streaming."""
    if isinstance(block.content, list):
        content = json.dumps(block.content, indent=2)
    elif isinstance(block.content, str):
        content = block.content
    else:
        content = str(block.content) if block.content else ""
    content = _trim_to_tail(content)

    # Header chunk
    yield f"\n\n**Tool Result** (`{block.tool_use_id}`):\n```\n"

    # Stream content in small line groups
    lines = content.splitlines(keepends=True)
    for i in range(0, len(lines), chunk_lines):
        yield "".join(lines[i : i + chunk_lines])

    # Closing fence
    yield "\n```\n\n"


def last_user_message(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user" and m.content:
            return m.content
    return ""


def build_prompt(messages: list[Message]) -> str:
    """Build a prompt from messages.

    If there are multiple user/assistant turns, pack the full conversation
    history into a single prompt so the SDK has full context — even if
    the session_id expired. Single-turn requests just use the last user
    message directly.

    Smart Context Window: when messages exceed the configured window
    (CODE_AGENTS_CONTEXT_WINDOW, default 5 pairs), trims older context
    while preserving system prompts, the first user message, and any
    messages containing code blocks.
    """
    # Apply smart context trimming before building the prompt
    ctx = ContextManager()
    msg_dicts = [{"role": m.role, "content": m.content or ""} for m in messages]
    trimmed_dicts = ctx.trim_messages(msg_dicts)

    # Convert back to Message objects
    trimmed = [Message(role=d["role"], content=d["content"]) for d in trimmed_dicts]

    non_system = [m for m in trimmed if m.role != "system"]
    if len(non_system) > 1:
        parts = []
        for m in non_system:
            label = "Human" if m.role == "user" else "Assistant"
            parts.append(f"{label}: {m.content}")
        return "\n\n".join(parts)
    return last_user_message(trimmed)


# ── Streaming response ──────────────────────────────────────────────────────

async def stream_response(agent: AgentConfig, req: CompletionRequest):
    """
    Async generator that yields OpenAI-compliant SSE chunks.

    Tool activity (ToolUseBlock / ToolResultBlock) is rendered as:
      - reasoning_content delta   when stream_tool_activity=True
      - silently consumed         when stream_tool_activity=False

    Session ID is returned in the final chunk when include_session=True.
    """
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = req.model or agent.model
    prompt = build_prompt(req.messages)

    # OTel span — wraps the SSE streaming response for distributed tracing
    _otel_span = None
    try:
        from code_agents.observability.otel import get_tracer
        _otel_tracer = get_tracer()
        _otel_span = _otel_tracer.start_span("stream_response")
        _otel_span.set_attribute("agent.name", agent.name)
        _otel_span.set_attribute("agent.model", model or "")
        _otel_span.set_attribute("stream.cid", cid)
    except Exception:
        _otel_span = None  # OTel is optional

    # Inject rules + user profile into agent system prompt
    agent = _inject_context(agent, req.cwd or "")

    # Merge Session Memory from chat system message into agent's system_prompt.
    # build_prompt() strips system messages, so Session Memory must go here.
    for _msg in req.messages:
        if _msg.role == "system" and _msg.content and "[Session Memory" in _msg.content:
            _mem_start = _msg.content.find("[Session Memory")
            _mem_end = _msg.content.find("[End Session Memory]")
            if _mem_start >= 0 and _mem_end >= 0:
                _mem_block = _msg.content[_mem_start:_mem_end + len("[End Session Memory]")]
                agent = copy.deepcopy(agent)
                agent.system_prompt = (agent.system_prompt or "") + f"\n\n{_mem_block}"
                logger.info("Session Memory injected into system_prompt (%d chars)", len(_mem_block))
            break

    # Smart context: inject delegation hints only when the request suggests out-of-scope work
    if req.messages:
        try:
            from code_agents.agent_system.smart_orchestrator import SmartOrchestrator
            _orch = SmartOrchestrator()
            _last_msg = last_user_message(req.messages)
            if _last_msg:
                _analysis = _orch.analyze_request(_last_msg)
                _best = _analysis.get("best_agent", "")
                # Auto-pilot: always inject smart context
                if agent.name == "auto-pilot" and _analysis.get("context_injection"):
                    agent = copy.deepcopy(agent)
                    agent.system_prompt = (agent.system_prompt or "") + "\n\n" + _analysis["context_injection"]
                # Other agents: inject delegation hints only when request targets a different agent
                elif _best and _best != agent.name and _best != "auto-pilot":
                    _hints = SmartOrchestrator.get_delegation_hints(agent.name)
                    if _hints:
                        agent = copy.deepcopy(agent)
                        agent.system_prompt = (agent.system_prompt or "") + "\n\n" + _hints
        except Exception as e:
            logger.debug("SmartOrchestrator failed (non-fatal): %s", e)

    show_tools = req.stream_tool_activity if req.stream_tool_activity is not None else agent.stream_tool_activity
    show_session = req.include_session if req.include_session is not None else agent.include_session

    captured_session_id: Optional[str] = None
    chunk_count = 0
    text_bytes = 0
    tool_calls = 0
    response_parts: list[str] = []
    start_time = time.time()

    # Detailed prompt composition logging — diagnose what's largest
    _sys_prompt_len = len(agent.system_prompt or "")
    _user_msgs = [m for m in req.messages if m.role == "user"]
    _asst_msgs = [m for m in req.messages if m.role == "assistant"]
    _sys_msgs = [m for m in req.messages if m.role == "system"]
    _total_input = _sys_prompt_len + len(prompt)

    logger.info(
        "[%s] stream_response START agent=%s model=%s total_input=%d chars "
        "system_prompt=%d user_msgs=%d(%d chars) asst_msgs=%d(%d chars) "
        "sys_context=%d(%d chars) session=%s cwd=%s",
        cid, agent.name, model, _total_input,
        _sys_prompt_len,
        len(_user_msgs), sum(len(m.content or "") for m in _user_msgs),
        len(_asst_msgs), sum(len(m.content or "") for m in _asst_msgs),
        len(_sys_msgs), sum(len(m.content or "") for m in _sys_msgs),
        req.session_id or "-", req.cwd or "(none)",
    )

    # Warn if prompt is very large (>100k chars ≈ ~25k tokens)
    if _total_input > 100000:
        logger.warning(
            "[%s] ⚠ LARGE PROMPT: %d chars (~%dk tokens). Breakdown: "
            "system_prompt=%d, user_messages=%d, assistant_messages=%d, system_context=%d",
            cid, _total_input, _total_input // 4,
            _sys_prompt_len,
            sum(len(m.content or "") for m in _user_msgs),
            sum(len(m.content or "") for m in _asst_msgs),
            sum(len(m.content or "") for m in _sys_msgs),
        )

    # Sanitize cwd — prevent path traversal via request parameter
    _safe_cwd = req.cwd
    if _safe_cwd:
        from pathlib import Path as _Path
        _resolved = _Path(_safe_cwd).resolve()
        # Block if cwd contains '..' or resolves outside home/workspace
        if ".." in _safe_cwd or not _resolved.is_dir():
            logger.warning("[%s] Rejected unsafe cwd=%r (resolved=%r)", cid, _safe_cwd, str(_resolved))
            _safe_cwd = None

    logger.debug("[%s] agent.cwd=%r req.cwd=%r → effective=%r", cid, agent.cwd, _safe_cwd, _safe_cwd or agent.cwd)
    logger.debug("[%s] system_prompt_preview=%r", cid, (agent.system_prompt or "")[:300])
    logger.debug("[%s] user_prompt_preview=%r", cid, prompt[:300])

    # OpenAI-compatible clients expect an initial chunk before backend work.
    yield make_chunk(cid, model, created, {"role": "assistant", "content": ""})

    try:
        async for message in run_agent(
            agent,
            prompt,
            model_override=None,
            cwd_override=_safe_cwd,
            session_id=req.session_id,
        ):
            if type(message).__name__ == "SystemMessage" and getattr(message, "subtype", None) == "init":
                sid = message.data.get("session_id")
                if sid:
                    captured_session_id = sid
                logger.debug("[%s] SystemMessage init session=%s", cid, sid or "-")

            elif type(message).__name__ == "AssistantMessage":
                for block in message.content:
                    if type(block).__name__ == "TextBlock" and getattr(block, "text", None) is not None:
                        if block.text == "":
                            logger.debug("[%s] Skipping empty TextBlock", cid)
                            continue
                        chunk_count += 1
                        text_bytes += len(block.text)
                        response_parts.append(block.text)
                        yield make_chunk(cid, model, created, {"content": block.text})

                    elif type(block).__name__ == "ToolUseBlock":
                        tool_calls += 1
                        logger.info("[%s] ToolUse: %s (id=%s)", cid, block.name, getattr(block, "id", "-"))
                        logger.debug("[%s] ToolUse input: %s", cid, str(getattr(block, "input", ""))[:500])
                        if show_tools:
                            yield make_chunk(cid, model, created, {
                                "reasoning_content": format_tool_use(block),
                            })

                    elif type(block).__name__ == "ToolResultBlock":
                        content_preview = str(getattr(block, "content", ""))[:200]
                        logger.info("[%s] ToolResult: id=%s len=%d", cid, getattr(block, "tool_use_id", "-"), len(str(getattr(block, "content", ""))))
                        logger.debug("[%s] ToolResult preview: %s", cid, content_preview)
                        if show_tools:
                            try:
                                for piece in iter_tool_result_chunks(block):
                                    yield make_chunk(cid, model, created, {
                                        "reasoning_content": piece,
                                    })
                            except Exception as e:
                                logger.warning("[%s] Tool result formatting error: %s", cid, e)
                                yield make_chunk(cid, model, created, {
                                    "reasoning_content": "[Tool result formatting error]",
                                })

            elif type(message).__name__ == "ResultMessage":
                if message.session_id:
                    captured_session_id = message.session_id
                elapsed = time.time() - start_time
                logger.info(
                    "[%s] stream_response DONE agent=%s chunks=%d text_bytes=%d tool_calls=%d elapsed=%.1fs session=%s",
                    cid, agent.name, chunk_count, text_bytes, tool_calls, elapsed, captured_session_id or "-",
                )
                if response_parts:
                    from .logging_config import log_agent_response
                    _output_tokens = 0
                    if hasattr(message, "usage") and message.usage:
                        _output_tokens = message.usage.get("completion_tokens", 0) or message.usage.get("output_tokens", 0)
                    log_agent_response(agent.name, "".join(response_parts), tokens=_output_tokens)
                if hasattr(message, "usage") and message.usage:
                    logger.info("[%s] usage: %s", cid, message.usage)

                final_chunk: dict[str, Any] = {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "system_fingerprint": None,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                        "logprobs": None,
                    }],
                }
                if show_session and captured_session_id:
                    final_chunk["session_id"] = captured_session_id
                # Include usage data in final chunk for client-side token tracking
                usage_data = getattr(message, "usage", None)
                if not usage_data and text_bytes:
                    # Estimate tokens when backend doesn't provide them (~4 chars per token)
                    est_input = len(prompt) // 4 if prompt else 0
                    est_output = text_bytes // 4
                    usage_data = {
                        "input_tokens": est_input,
                        "output_tokens": est_output,
                        "estimated": True,
                    }
                if usage_data:
                    final_chunk["usage"] = usage_data
                if hasattr(message, "duration_ms"):
                    final_chunk["duration_ms"] = message.duration_ms

                yield sse(final_chunk)
                yield "data: [DONE]\n\n"
                return

        final: dict[str, Any] = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
                "logprobs": None,
            }],
        }
        if show_session and captured_session_id:
            final["session_id"] = captured_session_id
        yield sse(final)
    except Exception as e:
        pe = unwrap_process_error(e)
        if pe is not None:
            if agent.backend == "cursor":
                log_cursor_backend_failure(
                    e,
                    log=logger,
                    prefix=f"[{cid}] ",
                    agent_name=agent.name,
                    backend=agent.backend,
                    model=model,
                    cwd=str(_safe_cwd or agent.cwd or ""),
                    phase="stream_response",
                )
            else:
                _stderr = (getattr(pe, "stderr", None) or "").strip()
                logger.error(
                    "[%s] agent=%s backend=%s subprocess exit=%s stderr_len=%s",
                    cid,
                    agent.name,
                    agent.backend,
                    getattr(pe, "exit_code", None),
                    len(_stderr),
                )
                if _stderr:
                    logger.error("[%s] subprocess stderr:\n%s", cid, _stderr[:16000])
        else:
            logger.exception(
                "[%s] Stream error from agent backend (agent=%s backend=%s)",
                cid,
                agent.name,
                agent.backend,
            )
        try:
            err_text = format_process_error_message(pe) if pe is not None else str(e)
        except Exception as fmt_err:
            logger.warning("Error formatting process error: %s", fmt_err)
            err_text = str(e)
        final_err: dict[str, Any] = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n[Error: {err_text}]"},
                "finish_reason": "stop",
                "logprobs": None,
            }],
        }
        if show_session and captured_session_id:
            final_err["session_id"] = captured_session_id
        yield sse(final_err)
    yield "data: [DONE]\n\n"


# ── Non-streaming response ──────────────────────────────────────────────────

async def collect_response(agent: AgentConfig, req: CompletionRequest) -> dict:
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = req.model or agent.model
    prompt = build_prompt(req.messages)

    # Inject rules + user profile into agent system prompt
    agent = _inject_context(agent, req.cwd or "")

    # Smart context for auto-pilot
    if agent.name == "auto-pilot" and req.messages:
        try:
            from code_agents.agent_system.smart_orchestrator import SmartOrchestrator
            _orch = SmartOrchestrator()
            _last_msg = last_user_message(req.messages)
            if _last_msg:
                _analysis = _orch.analyze_request(_last_msg)
                if _analysis.get("context_injection"):
                    agent = copy.deepcopy(agent)
                    agent.system_prompt = (agent.system_prompt or "") + "\n\n" + _analysis["context_injection"]
        except Exception:
            pass

    show_tools = req.stream_tool_activity if req.stream_tool_activity is not None else agent.stream_tool_activity
    show_session = req.include_session if req.include_session is not None else agent.include_session

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    captured_session_id: Optional[str] = None
    usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    tool_calls = 0
    start_time = time.time()

    logger.info(
        "[%s] collect_response START agent=%s model=%s prompt_len=%d messages=%d session=%s",
        cid, agent.name, model, len(prompt), len(req.messages), req.session_id or "-",
    )
    logger.debug("[%s] prompt_preview=%r", cid, prompt[:200])

    async for message in run_agent(
        agent,
        prompt,
        model_override=None,
        cwd_override=req.cwd,
        session_id=req.session_id,
    ):
        if type(message).__name__ == "SystemMessage" and getattr(message, "subtype", None) == "init":
            sid = message.data.get("session_id")
            if sid:
                captured_session_id = sid
            logger.debug("[%s] SystemMessage init session=%s", cid, sid or "-")

        elif type(message).__name__ == "AssistantMessage":
            for block in message.content:
                if type(block).__name__ == "TextBlock" and getattr(block, "text", None):
                    content_parts.append(block.text)

                elif type(block).__name__ == "ToolUseBlock":
                    tool_calls += 1
                    logger.info("[%s] ToolUse: %s (id=%s)", cid, block.name, getattr(block, "id", "-"))
                    logger.debug("[%s] ToolUse input: %s", cid, str(getattr(block, "input", ""))[:500])
                    if show_tools:
                        reasoning_parts.append(format_tool_use(block))

                elif type(block).__name__ == "ToolResultBlock":
                    logger.info("[%s] ToolResult: id=%s len=%d", cid, getattr(block, "tool_use_id", "-"), len(str(getattr(block, "content", ""))))
                    if show_tools:
                        reasoning_parts.append(format_tool_result(block))

        elif type(message).__name__ == "ResultMessage":
            if message.session_id:
                captured_session_id = message.session_id
            elapsed = time.time() - start_time
            logger.info(
                "[%s] collect_response DONE agent=%s content_len=%d tool_calls=%d elapsed=%.1fs session=%s",
                cid, agent.name, sum(len(p) for p in content_parts), tool_calls, elapsed, captured_session_id or "-",
            )
            if content_parts:
                from .logging_config import log_agent_response
                _output_tokens = 0
                if message.usage:
                    _output_tokens = message.usage.get("completion_tokens", 0) or message.usage.get("output_tokens", 0)
                log_agent_response(agent.name, "".join(content_parts), tokens=_output_tokens)
            if message.usage:
                usage = {
                    "prompt_tokens": message.usage.get("prompt_tokens", 0),
                    "completion_tokens": message.usage.get("completion_tokens", 0),
                    "total_tokens": message.usage.get("total_tokens", 0),
                }

    msg: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts) or "",
    }
    if reasoning_parts:
        msg["reasoning_content"] = "".join(reasoning_parts)

    response: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "system_fingerprint": None,
        "choices": [{
            "index": 0,
            "message": msg,
            "finish_reason": "stop",
            "logprobs": None,
        }],
        "usage": usage,
    }

    if show_session and captured_session_id:
        response["session_id"] = captured_session_id

    return response
