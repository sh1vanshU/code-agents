"""Router for Incident Postmortem Writer."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.postmortem")

router = APIRouter(prefix="/postmortem", tags=["postmortem"])


class PostmortemRequest(BaseModel):
    time_from: str = Field("", description="Start of time range")
    time_to: str = Field("", description="End of time range")
    service: str = Field("", description="Service name filter")
    format: str = Field("md", description="Output format: md or json")


class PostmortemResponse(BaseModel):
    title: str = ""
    severity_level: str = ""
    timeline_count: int = 0
    root_cause: str = ""
    impact: str = ""
    action_items: list[dict] = []
    commits_count: int = 0
    formatted: str = ""


@router.post("/generate", response_model=PostmortemResponse)
async def generate_postmortem(req: PostmortemRequest, request: Request):
    """Generate an incident postmortem report."""
    from code_agents.domain.postmortem import PostmortemWriter, format_postmortem
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    writer = PostmortemWriter(
        cwd=cwd, time_from=req.time_from, time_to=req.time_to, service=req.service,
    )
    report = writer.generate()
    return PostmortemResponse(
        title=report.title,
        severity_level=report.severity_level,
        timeline_count=len(report.timeline),
        root_cause=report.root_cause,
        impact=report.impact,
        action_items=[asdict(a) for a in report.action_items],
        commits_count=len(report.commits_in_range),
        formatted=format_postmortem(report, req.format),
    )
