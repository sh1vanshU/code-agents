"""
Elasticsearch: cluster info and search via env-configured connection.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.elasticsearch")

from code_agents.integrations.elasticsearch_client import ElasticsearchConnError, client_from_env, info, search

router = APIRouter(prefix="/elasticsearch", tags=["elasticsearch"])


def _enabled() -> bool:
    return bool(
        os.getenv("ELASTICSEARCH_URL", "").strip() or os.getenv("ELASTICSEARCH_CLOUD_ID", "").strip(),
    )


def _client_or_503():
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail="Elasticsearch is not configured. Set ELASTICSEARCH_URL or ELASTICSEARCH_CLOUD_ID.",
        )
    try:
        return client_from_env()
    except ElasticsearchConnError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/info")
def cluster_info() -> dict[str, Any]:
    """
    Return cluster ``info`` (version, cluster name, UUID). Use to verify connectivity.

    Configure ``ELASTICSEARCH_URL`` and auth (``ELASTICSEARCH_API_KEY`` or user/password).
    """
    es = _client_or_503()
    try:
        return info(es)
    except ElasticsearchConnError as e:
        raise HTTPException(status_code=502 if e.status_code is None else e.status_code, detail=str(e))


class SearchRequest(BaseModel):
    """REST-style search body (``query``, ``size``, ``from``, ``aggs``, …)."""

    index: str = Field(default="*", description="Index name, comma list, or *")
    body: dict[str, Any] = Field(
        default_factory=dict,
        description="Search body, e.g. {\"query\": {\"match_all\": {}}, \"size\": 10}",
    )


@router.post("/search", response_model=dict)
def run_search(req: SearchRequest) -> dict:
    """
    Run a search request against Elasticsearch.

    ``body`` is passed to the client's ``search(..., body=…)`` (elasticsearch-py 8).
    """
    logger.info("Elasticsearch search: index=%s", req.index)
    es = _client_or_503()
    try:
        result = search(es, index=req.index, body=req.body)
        logger.debug("Elasticsearch search returned results for index=%s", req.index)
        return result
    except ElasticsearchConnError as e:
        code = e.status_code or 502
        if code not in (400, 401, 403, 404):
            code = 502
        raise HTTPException(status_code=code, detail=str(e))
