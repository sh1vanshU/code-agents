import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from code_agents.core.config import agent_loader
from code_agents.core.models import CompletionRequest
from code_agents.core.openai_errors import (
    log_cursor_backend_failure,
    process_error_json_response,
    unwrap_process_error,
)
from code_agents.core.stream import stream_response, collect_response

logger = logging.getLogger("code_agents.completions")
router = APIRouter()


def _norm_model_label(value: str) -> str:
    """Match Open WebUI / client labels to YAML `model` (hyphen vs space)."""
    return value.strip().lower().replace(" ", "-").replace("_", "-")


def _resolve_agent(model: str | None):
    """Resolve agent by name (e.g. code-reasoning) or by model label (e.g. Composer 2 Fast)."""
    if not model or not model.strip():
        default = agent_loader.default
        if default is None:
            raise HTTPException(
                status_code=400,
                detail="No model specified and no agents loaded. Set 'model' in request body.",
            )
        return default
    # Try exact agent name first
    stripped = model.strip()
    agent = agent_loader.get(stripped)
    if agent is not None:
        return agent
    # Some clients send display_name (e.g. "Primary — Subagent Router") instead of YAML name
    for a in agent_loader.list_agents():
        if a.display_name and a.display_name.strip().lower() == stripped.lower():
            return a
    # Fallback: find first agent whose .model matches (e.g. "Composer 2 Fast" vs "composer-2-fast")
    want = _norm_model_label(model)
    for a in agent_loader.list_agents():
        if a.model and _norm_model_label(a.model) == want:
            return a
    available = [a.name for a in agent_loader.list_agents()]
    raise HTTPException(
        status_code=404,
        detail=f"Model/agent '{model}' not found. Available: {available}",
    )


async def _handle_completions(agent, req: CompletionRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages required")

    prompt_preview = ""
    if req.messages:
        last = req.messages[-1].content or ""
        prompt_preview = last[:120] + ("..." if len(last) > 120 else "")

    logger.info(
        "Agent=%s stream=%s session=%s prompt=%r",
        agent.name, req.stream, req.session_id or "-", prompt_preview,
    )
    logger.debug(
        "Agent=%s backend=%s model=%s messages=%d cwd=%s",
        agent.name, agent.backend, agent.model, len(req.messages), req.cwd,
    )

    if req.stream:
        return StreamingResponse(
            stream_response(agent, req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        return await collect_response(agent, req)
    except Exception as e:
        pe = unwrap_process_error(e)
        if pe is not None and getattr(agent, "backend", None) == "cursor":
            log_cursor_backend_failure(
                e,
                log=logger,
                agent_name=agent.name,
                backend=agent.backend,
                model=getattr(agent, "model", "") or "",
                cwd=getattr(req, "cwd", None) or "",
                phase="collect_response",
            )
        elif pe is not None:
            _stderr = (getattr(pe, "stderr", None) or "").strip()
            logger.error(
                "Agent=%s subprocess failed exit=%s stderr=%s",
                agent.name,
                getattr(pe, "exit_code", -1),
                _stderr[:4000],
            )
        else:
            logger.error("Agent=%s error: %s", agent.name, e, exc_info=True)
        # Direct ProcessError or nested under ExceptionGroup / __cause__ (Python 3.11+).
        if pe is not None:
            return process_error_json_response(pe)
        raise


@router.post("/v1/chat/completions")
async def openai_chat_completions(req: CompletionRequest):
    """OpenAI-style endpoint: model is passed in request body. Used by Open WebUI and other clients."""
    agent = _resolve_agent(req.model)
    return await _handle_completions(agent, req)


@router.post("/v1/agents/{agent_name}/chat/completions")
async def chat_completions(agent_name: str, req: CompletionRequest):
    agent = agent_loader.get(agent_name)
    if agent is None:
        available = [a.name for a in agent_loader.list_agents()]
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available: {available}",
        )
    return await _handle_completions(agent, req)
