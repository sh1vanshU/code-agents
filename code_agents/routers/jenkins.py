"""
Jenkins CI/CD API: trigger builds, monitor status, and fetch logs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..cicd.jenkins_client import JenkinsClient, JenkinsError

logger = logging.getLogger("code_agents.jenkins")
router = APIRouter(prefix="/jenkins", tags=["jenkins"])


def _get_client() -> JenkinsClient:
    """Build JenkinsClient from environment variables."""
    base_url = os.getenv("JENKINS_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="JENKINS_URL is not set. Configure Jenkins connection in environment.",
        )
    username = os.getenv("JENKINS_USERNAME")
    api_token = os.getenv("JENKINS_API_TOKEN")
    if not username or not api_token:
        raise HTTPException(
            status_code=503,
            detail="JENKINS_USERNAME and JENKINS_API_TOKEN must both be set.",
        )
    return JenkinsClient(
        base_url=base_url,
        username=username,
        api_token=api_token,
    )


class TriggerBuildRequest(BaseModel):
    """Request to trigger a Jenkins build."""
    job_name: Optional[str] = Field(None, description="Jenkins job name (e.g., 'pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz')")
    job_path: Optional[str] = Field(None, description="Alias for job_name (accepted for compatibility)")
    branch: Optional[str] = Field(None, description="Branch name — convenience field, added to parameters as 'branch'")
    parameters: Optional[dict[str, Any]] = Field(None, description="Build parameters — use exact names from /jenkins/jobs/{path}/parameters")

    @property
    def effective_job_name(self) -> str:
        """Return job_name, falling back to job_path for compatibility."""
        name = self.job_name or self.job_path
        if not name:
            raise ValueError("Either job_name or job_path must be provided")
        return name


class WaitForBuildRequest(BaseModel):
    """Request to wait for a build to complete."""
    timeout: Optional[float] = Field(None, description="Max seconds to wait (default: 600)")


@router.get("/jobs")
async def list_jobs(folder: Optional[str] = None):
    """
    List jobs in a Jenkins folder (or root if no folder specified).

    Query params:
      ?folder=pg2/pg2-dev-build-jobs   — list jobs in this folder

    Returns list of jobs with name, type (folder/job), color, and URL.
    Use this to discover available build/deploy jobs.
    """
    try:
        client = _get_client()
        jobs = await client.list_jobs(folder)
        return {
            "folder": folder or "(root)",
            "count": len(jobs),
            "jobs": jobs,
        }
    except JenkinsError as e:
        logger.error("list_jobs failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/jobs/{job_path:path}/parameters")
async def get_job_parameters(job_path: str):
    """
    Get the parameter definitions for a parameterized Jenkins job.

    Path: /jenkins/jobs/pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz/parameters

    Returns parameter names, types, defaults, descriptions, and choices.
    Use this to know what parameters to pass when triggering a build.
    """
    try:
        client = _get_client()
        params = await client.get_job_parameters(job_path)
        return {
            "job_name": job_path,
            "parameters": params,
        }
    except JenkinsError as e:
        logger.error("get_job_parameters failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/build")
async def trigger_build(req: TriggerBuildRequest):
    """
    Trigger a Jenkins build job.

    Returns queue_id for tracking. If branch is specified, it's added as 'branch' parameter.
    """
    try:
        client = _get_client()
        params = dict(req.parameters or {})
        if req.branch and "branch" not in params:
            params["branch"] = req.branch
        result = await client.trigger_build(
            job_name=req.effective_job_name,
            parameters=params if params else None,
        )

        # Try to resolve build number from queue
        if result.get("queue_id"):
            try:
                build_number = await client.get_build_from_queue(result["queue_id"])
                if build_number:
                    result["build_number"] = build_number
                    result["status"] = "started"
            except JenkinsError:
                pass  # Queue lookup failed, client can retry

        logger.info("trigger_build: job=%s queue=%s build=%s",
                     req.effective_job_name, result.get("queue_id"), result.get("build_number"))
        return result
    except JenkinsError as e:
        logger.error("trigger_build failed: %s", e)
        raise HTTPException(
            status_code=422 if e.status_code in (400, 403, 404) else 502,
            detail=str(e),
        )


@router.post("/build-and-wait")
async def trigger_build_and_wait(req: TriggerBuildRequest):
    """
    Trigger a build, poll until complete, and extract build version from logs.

    Streams newline-delimited JSON progress lines so the caller sees live updates:
      {"status":"triggered","build_number":909,"job_name":"..."}
      {"status":"polling","build_number":909,"poll":1,"elapsed":"5s"}
      {"status":"polling","build_number":909,"poll":2,"elapsed":"10s"}
      {"status":"done","build_number":909,"result":"SUCCESS","build_version":"...","duration":"2m 34s","log_tail":"..."}

    The final line contains the full result (same schema as the old blocking response).
    """
    import asyncio
    import json
    import time

    async def _stream_build():
        try:
            client = _get_client()
            client.poll_timeout = 1200.0

            params = dict(req.parameters or {})
            if req.branch and "branch" not in params:
                params["branch"] = req.branch

            # 1. Trigger build
            trigger_result = await client.trigger_build(req.effective_job_name, params if params else None)
            build_number = trigger_result.get("build_number")

            if not build_number and trigger_result.get("queue_id"):
                build_number = await client.get_build_from_queue(trigger_result["queue_id"])

            if not build_number:
                yield json.dumps({
                    "status": "error",
                    "job_name": req.effective_job_name,
                    "error": "Could not determine build number from queue",
                }) + "\n"
                return

            # Emit trigger confirmation
            yield json.dumps({
                "status": "triggered",
                "job_name": req.effective_job_name,
                "build_number": build_number,
            }) + "\n"

            # 2. Poll with progress
            start = time.monotonic()
            poll_count = 0
            deadline = start + client.poll_timeout

            while time.monotonic() < deadline:
                poll_count += 1
                status = await client.get_build_status(req.effective_job_name, build_number)
                elapsed = int(time.monotonic() - start)

                if not status["building"]:
                    # Build finished — extract version and emit final result
                    build_version = None
                    log_tail = ""
                    try:
                        log_text = await client.get_build_log(req.effective_job_name, build_number)
                        build_version = client.extract_build_version(log_text)
                        log_lines = log_text.strip().splitlines()
                        log_tail = "\n".join(log_lines[-100:])
                    except Exception as e:
                        logger.error("build_and_wait: failed to fetch logs: %s", e)

                    _fmt_duration = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
                    final = {
                        **status,
                        "build_version": build_version,
                        "log_tail": log_tail,
                        "duration_display": _fmt_duration,
                    }
                    yield json.dumps({
                        "status": "done",
                        **final,
                    }) + "\n"

                    logger.info(
                        "build_and_wait: job=%s build=#%s result=%s version=%s",
                        req.effective_job_name, build_number, status.get("result"), build_version,
                    )
                    return

                # Emit polling progress
                _fmt_elapsed = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
                yield json.dumps({
                    "status": "polling",
                    "build_number": build_number,
                    "poll": poll_count,
                    "elapsed": _fmt_elapsed,
                }) + "\n"

                await asyncio.sleep(client.poll_interval)

            # Timeout
            yield json.dumps({
                "status": "error",
                "build_number": build_number,
                "error": f"Build did not complete within {client.poll_timeout}s",
            }) + "\n"

        except JenkinsError as e:
            logger.error("build_and_wait failed: %s", e)
            yield json.dumps({"status": "error", "error": str(e)}) + "\n"
        except Exception as e:
            logger.error("build_and_wait unexpected error: %s", e)
            yield json.dumps({"status": "error", "error": str(e)}) + "\n"

    return StreamingResponse(
        _stream_build(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/build/{job_name:path}/{build_number}/status")
async def get_build_status(job_name: str, build_number: int):
    """Get the status of a specific build."""
    try:
        client = _get_client()
        return await client.get_build_status(job_name, build_number)
    except JenkinsError as e:
        logger.error("get_build_status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/build/{job_name:path}/{build_number}/log")
async def get_build_log(job_name: str, build_number: int):
    """Get console output for a build."""
    try:
        client = _get_client()
        log_text = await client.get_build_log(job_name, build_number)
        return {"job_name": job_name, "build_number": build_number, "log": log_text}
    except JenkinsError as e:
        logger.error("get_build_log failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/build/{job_name:path}/last")
async def get_last_build(job_name: str):
    """Get info about the latest build of a job."""
    try:
        client = _get_client()
        return await client.get_last_build(job_name)
    except JenkinsError as e:
        logger.error("get_last_build failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/build/{job_name:path}/{build_number}/wait")
async def wait_for_build(job_name: str, build_number: int, req: Optional[WaitForBuildRequest] = None):
    """
    Long-poll until a build completes.

    Returns the final build status (SUCCESS, FAILURE, UNSTABLE, ABORTED).
    """
    try:
        client = _get_client()
        if req and req.timeout:
            client.poll_timeout = req.timeout
        result = await client.wait_for_build(job_name, build_number)
        return result
    except JenkinsError as e:
        logger.error("wait_for_build failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
