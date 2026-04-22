"""
Redash API integration: run DB queries via Redash using API key or username/password.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agents.integrations.redash_client import RedashClient, RedashError

logger = logging.getLogger("code_agents.redash")
router = APIRouter(prefix="/redash", tags=["redash"])


def _get_client() -> RedashClient:
    """Build RedashClient from environment variables."""
    base_url = os.getenv("REDASH_BASE_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="REDASH_BASE_URL is not set. Configure Redash connection in environment.",
        )
    api_key = os.getenv("REDASH_API_KEY")
    username = os.getenv("REDASH_USERNAME")
    password = os.getenv("REDASH_PASSWORD")
    if not api_key and not (username and password):
        raise HTTPException(
            status_code=503,
            detail="Set either REDASH_API_KEY or both REDASH_USERNAME and REDASH_PASSWORD.",
        )
    return RedashClient(
        base_url=base_url,
        api_key=api_key,
        username=username,
        password=password,
    )


class RunQueryRequest(BaseModel):
    """Request to run an ad-hoc query against a Redash data source."""

    data_source_id: int = Field(..., description="Redash data source ID")
    query: str = Field(..., description="SQL or query text to execute")
    max_age: int = Field(0, ge=0, description="Use cached result if younger than this (seconds); 0 = run fresh")
    parameters: Optional[dict[str, Any]] = Field(None, description="Query parameters for parameterized queries")


class RunSavedQueryRequest(BaseModel):
    """Request to run a saved Redash query by ID."""

    query_id: int = Field(..., description="Redash saved query ID")
    max_age: int = Field(0, ge=0, description="Use cached result if younger than this (seconds); 0 = run fresh")
    parameters: Optional[dict[str, Any]] = Field(None, description="Query parameters")


@router.post("/run-query", response_model=dict)
def run_query(req: RunQueryRequest) -> dict:
    """
    Run an ad-hoc database query via Redash.

    Uses REDASH_BASE_URL and either REDASH_API_KEY or REDASH_USERNAME + REDASH_PASSWORD.
    Executes the query against the given data source and returns columns and rows.
    """
    logger.info("run_query ds=%d query=%r", req.data_source_id, req.query[:120])
    try:
        client = _get_client()
        result = client.run_query(
            data_source_id=req.data_source_id,
            query=req.query,
            max_age=req.max_age,
            parameters=req.parameters,
        )
        row_count = result.get("metadata", {}).get("row_count", "?")
        runtime = result.get("metadata", {}).get("runtime", "?")
        logger.info("run_query result: %s rows, %ss", row_count, runtime)
        logger.debug("run_query columns: %s", [c.get("name", c) for c in result.get("columns", [])])
        return result
    except RedashError as e:
        logger.error("run_query failed: %s (HTTP %s)", e, e.status_code)
        raise HTTPException(
            status_code=422 if e.status_code in (400, 403) else 502,
            detail=e.args[0],
        )


@router.post("/run-saved-query", response_model=dict)
def run_saved_query(req: RunSavedQueryRequest) -> dict:
    """
    Run a saved Redash query by ID.

    Uses REDASH_BASE_URL and either REDASH_API_KEY or REDASH_USERNAME + REDASH_PASSWORD.
    """
    try:
        client = _get_client()
        result = client.run_saved_query(
            query_id=req.query_id,
            max_age=req.max_age,
            parameters=req.parameters,
        )
        return result
    except RedashError as e:
        raise HTTPException(
            status_code=422 if e.status_code in (400, 403) else 502,
            detail=e.args[0],
        )


@router.get("/data-sources", response_model=list)
def list_data_sources() -> list:
    """
    List Redash data sources (to find data_source_id for run-query).
    """
    try:
        client = _get_client()
        return client.list_data_sources()
    except RedashError as e:
        raise HTTPException(
            status_code=502,
            detail=e.args[0],
        )


@router.get("/data-sources/{data_source_id}/schema", response_model=list)
def get_schema(data_source_id: int) -> list:
    """
    Get the schema (tables and columns) for a Redash data source.

    Returns a list of tables with their column names.
    """
    try:
        client = _get_client()
        return client.get_schema(data_source_id)
    except RedashError as e:
        raise HTTPException(
            status_code=502,
            detail=e.args[0],
        )
