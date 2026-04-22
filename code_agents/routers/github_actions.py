"""
GitHub Actions: trigger, monitor, and debug GitHub Actions workflows.

Requires GITHUB_TOKEN and GITHUB_REPO to be set (503 otherwise).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.github_actions_client import GitHubActionsClient, GitHubActionsError

logger = logging.getLogger("code_agents.routers.github_actions")
router = APIRouter(prefix="/github-actions", tags=["github-actions"])


def _get_client() -> GitHubActionsClient:
    """Build GitHubActionsClient from environment variables."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    if not token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN is not set.")
    if not repo:
        raise HTTPException(status_code=503, detail="GITHUB_REPO is not set (expected owner/repo format).")
    return GitHubActionsClient(token=token, repo=repo)


# ── Models ────────────────────────────────────────────────────────────────

class WorkflowDispatchRequest(BaseModel):
    ref: str = Field(default="main", description="Branch or tag to run the workflow on")
    inputs: dict[str, str] = Field(default_factory=dict, description="Workflow input parameters")


class WorkflowRunsRequest(BaseModel):
    branch: str = Field(default="", description="Filter by branch")
    status: str = Field(default="", description="Filter by status: queued, in_progress, completed")
    per_page: int = Field(default=10, ge=1, le=100, description="Results per page")


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/repo")
async def get_repo():
    """Get repository info."""
    client = _get_client()
    try:
        return await client.get_repo()
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/workflows")
async def list_workflows():
    """List all GitHub Actions workflows."""
    client = _get_client()
    try:
        workflows = await client.list_workflows()
        return {"total": len(workflows), "workflows": workflows}
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/workflows/{workflow_id}/runs")
async def get_workflow_runs(workflow_id: int, branch: str = "", status: str = "", per_page: int = 10):
    """Get recent runs for a specific workflow."""
    client = _get_client()
    try:
        runs = await client.get_workflow_runs(workflow_id, branch=branch, status=status, per_page=per_page)
        return {"total": len(runs), "runs": runs}
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/workflows/{workflow_id}/dispatch")
async def dispatch_workflow(workflow_id: int, req: WorkflowDispatchRequest):
    """Trigger a workflow_dispatch event."""
    client = _get_client()
    try:
        return await client.dispatch_workflow(workflow_id, ref=req.ref, inputs=req.inputs)
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    """Get details of a specific workflow run."""
    client = _get_client()
    try:
        return await client.get_run(run_id)
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/runs/{run_id}/jobs")
async def get_run_jobs(run_id: int):
    """List jobs for a workflow run."""
    client = _get_client()
    try:
        jobs = await client.get_run_jobs(run_id)
        return {"total": len(jobs), "jobs": jobs}
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: int):
    """Get logs for a workflow run."""
    client = _get_client()
    try:
        logs = await client.get_run_logs(run_id)
        return {"logs": logs}
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/runs/{run_id}/jobs/{job_id}/logs")
async def get_job_logs(run_id: int, job_id: int):
    """Get logs for a specific job."""
    client = _get_client()
    try:
        logs = await client.get_job_logs(job_id)
        return {"logs": logs}
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: int):
    """Retry failed jobs in a workflow run."""
    client = _get_client()
    try:
        return await client.retry_run(run_id)
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int):
    """Cancel a running workflow."""
    client = _get_client()
    try:
        return await client.cancel_run(run_id)
    except GitHubActionsError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
