"""
Pipeline orchestration API: manage 7-step CI/CD pipeline runs.

Steps: connect → review/test → plan → build → deploy → verify → rollback
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.pipeline_state import pipeline_manager, StepStatus

logger = logging.getLogger("code_agents.devops.pipeline")
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class StartPipelineRequest(BaseModel):
    """Request to start a new pipeline run."""
    branch: str = Field(..., description="Git branch to deploy")
    repo_path: Optional[str] = Field(None, description="Override target repo path (default: TARGET_REPO_PATH env or cwd)")
    build_job: Optional[str] = Field(None, description="Jenkins build job name (default from JENKINS_BUILD_JOB)")
    deploy_job: Optional[str] = Field(None, description="Jenkins deploy job name (default from JENKINS_DEPLOY_JOB)")
    argocd_app: Optional[str] = Field(None, description="ArgoCD application name (default from ARGOCD_APP_NAME)")


class AdvanceRequest(BaseModel):
    """Request to execute and advance the current pipeline step."""
    details: Optional[dict] = Field(None, description="Additional details for the current step")


class FailRequest(BaseModel):
    """Request to mark the current step as failed."""
    error: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Error details")


@router.post("/start")
async def start_pipeline(req: StartPipelineRequest):
    """
    Start a new CI/CD pipeline run.

    Creates a pipeline run tracking the 7-step process:
    1. Connect to repo   2. Review & test   3. Plan
    4. Build             5. Deploy          6. Verify
    7. Rollback (if needed)
    """
    repo_path = req.repo_path or os.getenv("TARGET_REPO_PATH") or os.getcwd()
    if not os.path.isdir(repo_path):
        raise HTTPException(
            status_code=422,
            detail=f"Repository path does not exist: {repo_path}",
        )

    build_job = req.build_job or os.getenv("JENKINS_BUILD_JOB")
    deploy_job = req.deploy_job or os.getenv("JENKINS_DEPLOY_JOB")
    argocd_app = req.argocd_app or os.getenv("ARGOCD_APP_NAME")

    run = pipeline_manager.create_run(
        branch=req.branch,
        repo_path=repo_path,
        build_job=build_job,
        deploy_job=deploy_job,
        argocd_app=argocd_app,
    )
    # Mark step 1 as in-progress
    pipeline_manager.start_step(run.run_id)

    logger.info("Pipeline started: run_id=%s branch=%s", run.run_id, req.branch)
    return run.to_dict()


@router.get("/{run_id}/status")
async def get_pipeline_status(run_id: str):
    """Get the current status of a pipeline run."""
    run = pipeline_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")
    return run.to_dict()


@router.post("/{run_id}/advance")
async def advance_pipeline(run_id: str, req: Optional[AdvanceRequest] = None):
    """
    Mark the current step as successful and advance to the next step.

    Optionally include details about the completed step (e.g., build_number, coverage_pct).
    """
    run = pipeline_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")

    current_step = run.current_step
    if run.step_status[current_step] == StepStatus.FAILED:
        raise HTTPException(
            status_code=422,
            detail=f"Step {current_step} ({run.step_status[current_step].value}) has failed. "
                   f"Fix the issue or rollback before advancing.",
        )

    # Store details if provided
    if req and req.details:
        pipeline_manager.set_step_details(run_id, current_step, req.details)
        # Track build_number if provided
        if "build_number" in req.details:
            run.build_number = req.details["build_number"]
        if "previous_revision" in req.details:
            run.previous_revision = req.details["previous_revision"]

    # Advance
    run = pipeline_manager.advance(run_id)
    logger.info("Pipeline %s advanced to step %d", run_id, run.current_step)
    return run.to_dict()


@router.post("/{run_id}/fail")
async def fail_pipeline_step(run_id: str, req: FailRequest):
    """Mark the current pipeline step as failed."""
    run = pipeline_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")

    run = pipeline_manager.fail_step(run_id, error=req.error, details=req.details)
    logger.warning("Pipeline %s step %d failed: %s", run_id, run.current_step, req.error)

    # Determine if rollback is recommended
    recommended_action = None
    if run.current_step >= 4:  # Deploy or later
        recommended_action = "rollback"

    result = run.to_dict()
    result["recommended_action"] = recommended_action
    return result


@router.post("/{run_id}/rollback")
async def rollback_pipeline(run_id: str):
    """
    Trigger rollback: skip remaining steps and jump to step 6 (rollback).

    The client should then call the ArgoCD rollback endpoint to actually revert.
    """
    run = pipeline_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")

    run = pipeline_manager.trigger_rollback(run_id)
    logger.warning("Pipeline %s rolling back from step %d", run_id, run.current_step)

    result = run.to_dict()
    result["rollback_info"] = {
        "argocd_app": run.argocd_app,
        "previous_revision": run.previous_revision,
        "instruction": (
            f"Call POST /argocd/apps/{run.argocd_app}/rollback with "
            f'{{"revision": {run.previous_revision or "\"previous\""}}}'
            if run.argocd_app else "No ArgoCD app configured"
        ),
    }
    return result


@router.get("/runs")
async def list_pipeline_runs():
    """List all pipeline runs."""
    runs = pipeline_manager.list_runs()
    return {
        "runs": [r.to_dict() for r in runs],
        "count": len(runs),
    }
