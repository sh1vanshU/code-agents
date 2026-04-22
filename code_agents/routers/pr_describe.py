"""Router for PR Description Generator."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.pr_describe")

router = APIRouter(prefix="/pr-describe", tags=["pr-describe"])


class PRDescribeRequest(BaseModel):
    base: str = Field("main", description="Base branch to diff against")
    format: str = Field("md", description="Output format: md or json")
    include_reviewers: bool = Field(True, description="Include reviewer suggestions")
    include_risk: bool = Field(True, description="Include risk assessment")


class PRDescribeResponse(BaseModel):
    title: str = ""
    summary: str = ""
    changes: list[str] = []
    risk_areas: list[dict] = []
    test_coverage: dict = {}
    suggested_reviewers: list[dict] = []
    diff_stats: dict = {}
    commit_count: int = 0
    files_changed: list[str] = []
    formatted: str = ""


@router.post("/generate", response_model=PRDescribeResponse)
async def generate_pr_description(req: PRDescribeRequest, request: Request):
    """Generate a PR description from branch diff."""
    from code_agents.git_ops.pr_describe import PRDescriptionGenerator, format_pr_description
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    gen = PRDescriptionGenerator(
        cwd=cwd, base=req.base,
        include_reviewers=req.include_reviewers, include_risk=req.include_risk,
    )
    desc = gen.generate()
    data = asdict(desc)
    data["formatted"] = format_pr_description(desc, req.format)
    return PRDescribeResponse(**data)
