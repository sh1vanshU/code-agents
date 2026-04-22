"""API router for database development tools."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.db_tools")
router = APIRouter(prefix="/db-tools", tags=["db-tools"])


class QueryOptimizeRequest(BaseModel):
    query: str = Field(..., description="SQL query to analyze")
    cwd: Optional[str] = None


class SchemaDesignRequest(BaseModel):
    entities: str = Field(..., description="Entity JSON definition or file path")
    cwd: Optional[str] = None


class OrmReviewRequest(BaseModel):
    cwd: Optional[str] = None


def _cwd(cwd: Optional[str]) -> str:
    return cwd or os.environ.get("TARGET_REPO_PATH") or os.getcwd()


@router.post("/query-optimize")
async def query_optimize(req: QueryOptimizeRequest):
    from code_agents.api.query_optimizer import QueryOptimizer, QueryOptimizerConfig

    config = QueryOptimizerConfig(cwd=_cwd(req.cwd))
    result = QueryOptimizer(config).analyze(req.query)
    return asdict(result)


@router.post("/schema-design")
async def schema_design(req: SchemaDesignRequest):
    from code_agents.api.schema_designer import SchemaDesigner, SchemaDesignerConfig

    config = SchemaDesignerConfig(cwd=_cwd(req.cwd))
    result = SchemaDesigner(config).design(req.entities)
    return asdict(result)


@router.post("/orm-review")
async def orm_review(req: OrmReviewRequest):
    from code_agents.api.orm_reviewer import OrmReviewer, OrmReviewConfig

    config = OrmReviewConfig(cwd=_cwd(req.cwd))
    result = OrmReviewer(config).scan()
    return asdict(result)
