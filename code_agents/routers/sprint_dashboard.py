"""Router for Sprint Velocity Dashboard."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.sprint_dashboard")

router = APIRouter(prefix="/sprint-dashboard", tags=["sprint-dashboard"])


class SprintDashboardRequest(BaseModel):
    period_days: int = Field(14, description="Days to analyze")
    sprint: str = Field("current", description="Sprint name")


class SprintDashboardResponse(BaseModel):
    sprint_name: str = ""
    period_days: int = 0
    start_date: str = ""
    end_date: str = ""
    throughput: dict = {}
    cycle_time: dict = {}
    contributors: list[dict] = []
    blockers: list[dict] = []
    top_files: list[dict] = []
    commit_activity: dict = {}
    weekly_summary: str = ""
    formatted: str = ""


@router.post("/report", response_model=SprintDashboardResponse)
async def generate_sprint_dashboard(req: SprintDashboardRequest, request: Request):
    """Generate sprint velocity dashboard."""
    from code_agents.domain.sprint_dashboard import SprintDashboard, format_sprint_dashboard
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    dashboard = SprintDashboard(cwd=cwd, period_days=req.period_days, sprint=req.sprint)
    report = dashboard.generate()
    data = asdict(report)
    data["formatted"] = format_sprint_dashboard(report)
    return SprintDashboardResponse(**data)
