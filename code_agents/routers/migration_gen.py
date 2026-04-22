"""Router for Migration Generator."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.migration_gen")

router = APIRouter(prefix="/db-migrate", tags=["db-migrate"])


class MigrationRequest(BaseModel):
    description: str = Field(..., description="Plain English migration description")
    migration_type: str = Field("auto", description="Type: auto, alembic, django, raw")
    preview: bool = Field(True, description="Preview only, don't write files")


class MigrationResponse(BaseModel):
    migration_sql: str = ""
    rollback_sql: str = ""
    migration_path: str = ""
    model_changes: list[str] = []
    blast_radius: list[str] = []
    migration_type: str = ""
    detected_orm: str = ""
    formatted: str = ""


@router.post("/generate", response_model=MigrationResponse)
async def generate_migration(req: MigrationRequest, request: Request):
    """Generate a DB migration from plain English."""
    from code_agents.knowledge.migration_gen import MigrationGenerator, format_migration

    cwd = getattr(request.state, "repo_path", os.getcwd())
    gen = MigrationGenerator(cwd=cwd, migration_type=req.migration_type)
    output = gen.generate(req.description, preview=req.preview)
    return MigrationResponse(
        migration_sql=output.migration_sql,
        rollback_sql=output.rollback_sql,
        migration_path=output.migration_path,
        model_changes=output.model_changes,
        blast_radius=output.blast_radius,
        migration_type=output.migration_type,
        detected_orm=output.detected_orm,
        formatted=format_migration(output),
    )
