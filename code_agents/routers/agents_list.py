import logging
import time

from fastapi import APIRouter, HTTPException

from code_agents.core.config import agent_loader

logger = logging.getLogger("code_agents.routers.agents_list")

router = APIRouter()


def _model_entry(agent, now: int):
    """Single OpenAI-style model entry for an agent."""
    return {
        "id": agent.name,
        "object": "model",
        "created": now,
        "owned_by": agent.backend,
        "permission": [],
        "root": agent.name,
        "parent": None,
    }


@router.get("/v1/agents/{agent_name}/models")
def list_agent_models(agent_name: str):
    """OpenAI-compatible model list for one agent. Use as base URL for a single-integration connection (e.g. Open WebUI)."""
    logger.debug("Fetching models for agent=%s", agent_name)
    agent = agent_loader.get(agent_name)
    if agent is None:
        available = [a.name for a in agent_loader.list_agents()]
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available: {available}",
        )
    now = int(time.time())
    return {"object": "list", "data": [_model_entry(agent, now)]}


@router.get("/v1/agents")
def list_agents():
    """List all available agents with their configuration."""
    agents = agent_loader.list_agents()
    logger.info("Listing agents: %d available", len(agents))
    return {
        "object": "list",
        "data": [
            {
                "name": a.name,
                "display_name": a.display_name,
                "backend": a.backend,
                "model": a.model,
                "endpoint": "/v1/agents/" + a.name + "/chat/completions",
            }
            for a in agents
        ],
    }


@router.get("/v1/models")
def list_models():
    """OpenAI-compatible model listing (all agents exposed as models)."""
    now = int(time.time())
    return {
        "object": "list",
        "data": [_model_entry(a, now) for a in agent_loader.list_agents()],
    }
