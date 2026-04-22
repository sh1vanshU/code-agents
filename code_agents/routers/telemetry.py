"""Telemetry API — usage analytics endpoints."""
import logging

from fastapi import APIRouter

logger = logging.getLogger("code_agents.routers.telemetry")

from code_agents.observability.telemetry import get_summary, get_agent_usage, get_top_commands, get_error_summary, is_enabled

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/summary")
async def summary(days: int = 1):
    logger.info("Telemetry summary requested: days=%d", days)
    if not is_enabled():
        return {"enabled": False}
    return get_summary(days)


@router.get("/agents")
async def agents(days: int = 7):
    logger.debug("Telemetry agent usage requested: days=%d", days)
    if not is_enabled():
        return {"enabled": False}
    return get_agent_usage(days)


@router.get("/commands")
async def commands(days: int = 7, limit: int = 10):
    if not is_enabled():
        return {"enabled": False}
    return get_top_commands(days, limit)


@router.get("/errors")
async def errors(days: int = 7):
    if not is_enabled():
        return {"enabled": False}
    return get_error_summary(days)
