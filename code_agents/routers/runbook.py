"""Router for Runbook Executor."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.runbook")

router = APIRouter(prefix="/runbook", tags=["runbook"])


class RunbookListResponse(BaseModel):
    runbooks: list[dict] = []


class RunbookExecuteRequest(BaseModel):
    name: str = Field(..., description="Runbook name or path")
    dry_run: bool = Field(True, description="Dry run mode")


class RunbookExecuteResponse(BaseModel):
    runbook_name: str = ""
    status: str = ""
    steps_completed: int = 0
    steps_failed: int = 0
    total_steps: int = 0
    results: list[dict] = []
    total_duration_ms: float = 0
    formatted: str = ""


@router.get("/list", response_model=RunbookListResponse)
async def list_runbooks(request: Request):
    """List available runbooks."""
    from code_agents.knowledge.runbook import RunbookExecutor
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    executor = RunbookExecutor(cwd=cwd)
    runbooks = executor.list_runbooks()
    return RunbookListResponse(
        runbooks=[asdict(rb) for rb in runbooks],
    )


@router.post("/execute", response_model=RunbookExecuteResponse)
async def execute_runbook(req: RunbookExecuteRequest, request: Request):
    """Execute a runbook."""
    from code_agents.knowledge.runbook import RunbookExecutor, format_execution
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    executor = RunbookExecutor(cwd=cwd, dry_run=req.dry_run)
    spec = executor.load(req.name)
    if not spec:
        return RunbookExecuteResponse(
            runbook_name=req.name, status="not_found",
            formatted=f"Runbook not found: {req.name}",
        )

    execution = executor.execute(spec)
    return RunbookExecuteResponse(
        runbook_name=spec.name,
        status=execution.status,
        steps_completed=execution.steps_completed,
        steps_failed=execution.steps_failed,
        total_steps=len(spec.steps),
        results=[asdict(r) for r in execution.results],
        total_duration_ms=execution.total_duration_ms,
        formatted=format_execution(execution),
    )
