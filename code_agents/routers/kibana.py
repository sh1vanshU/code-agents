"""
Kibana log viewer: search logs, list indices, aggregate errors.

Queries Elasticsearch behind Kibana for structured log search.
Requires KIBANA_URL to be set (503 otherwise).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.kibana_client import KibanaClient, KibanaError

logger = logging.getLogger("code_agents.routers.kibana")
router = APIRouter(prefix="/kibana", tags=["kibana"])


def _get_client() -> KibanaClient:
    """Build KibanaClient from environment variables."""
    kibana_url = os.getenv("KIBANA_URL")
    if not kibana_url:
        raise HTTPException(
            status_code=503,
            detail="KIBANA_URL is not set. Configure Kibana connection in environment.",
        )
    return KibanaClient(
        kibana_url=kibana_url,
        username=os.getenv("KIBANA_USERNAME", ""),
        password=os.getenv("KIBANA_PASSWORD", ""),
    )


# ── Models ────────────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    index: str = Field(default="logs-*", description="Elasticsearch index pattern")
    query: str = Field(default="*", description="Lucene query string")
    service: str = Field(default="", description="Filter by service/app name")
    log_level: str = Field(default="", description="Filter by log level (ERROR, WARN, INFO, etc.)")
    time_range: str = Field(default="15m", description="Time range: 5m, 15m, 30m, 1h, 3h, 6h, 12h, 24h")
    size: int = Field(default=100, ge=1, le=1000, description="Max results to return")


class ErrorSummaryRequest(BaseModel):
    index: str = Field(default="logs-*", description="Elasticsearch index pattern")
    service: str = Field(default="", description="Filter by service/app name")
    time_range: str = Field(default="1h", description="Time range: 5m, 15m, 30m, 1h, 3h, 6h, 24h")
    top_n: int = Field(default=10, ge=1, le=50, description="Number of top error patterns")


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/indices")
async def list_indices():
    """List available Kibana index patterns."""
    client = _get_client()
    try:
        indices = await client.get_indices()
        return {"indices": indices}
    except KibanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/search")
async def search_logs(req: SearchRequest):
    """Search logs by query, service, log level, and time range."""
    logger.info("Kibana search: index=%s, query=%s, service=%s, time_range=%s", req.index, req.query, req.service, req.time_range)
    client = _get_client()
    try:
        results = await client.search_logs(
            index=req.index,
            query=req.query,
            service=req.service,
            log_level=req.log_level,
            time_range=req.time_range,
            size=req.size,
        )
        logger.info("Kibana search returned %d results", len(results))
        return {"total": len(results), "logs": results}
    except KibanaError as exc:
        logger.error("Kibana search failed: %s", exc)
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/errors")
async def error_summary(req: ErrorSummaryRequest):
    """Aggregate top error patterns from logs."""
    client = _get_client()
    try:
        patterns = await client.error_summary(
            index=req.index,
            service=req.service,
            time_range=req.time_range,
            top_n=req.top_n,
        )
        return {"total_patterns": len(patterns), "errors": patterns}
    except KibanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
