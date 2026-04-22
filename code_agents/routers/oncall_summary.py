"""Router for On-Call Log Summarizer."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.oncall_summary")

router = APIRouter(prefix="/oncall-summary", tags=["oncall-summary"])


class OncallSummaryRequest(BaseModel):
    hours: int = Field(12, description="Hours to look back")
    channel: str = Field("oncall", description="Slack channel name")
    log_path: str = Field("", description="Path to log file")


class OncallSummaryResponse(BaseModel):
    total_alerts: int = 0
    alert_groups: list[dict] = []
    patterns: list[str] = []
    top_services: list[dict] = []
    standup_update: str = ""
    action_items: list[str] = []
    formatted: str = ""


@router.post("/generate", response_model=OncallSummaryResponse)
async def generate_oncall_summary(req: OncallSummaryRequest, request: Request):
    """Generate on-call alert summary."""
    from code_agents.domain.oncall_summary import OncallSummarizer, format_oncall_summary
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    summarizer = OncallSummarizer(
        cwd=cwd, hours=req.hours, channel=req.channel, log_path=req.log_path,
    )
    report = summarizer.generate()
    return OncallSummaryResponse(
        total_alerts=report.total_alerts,
        alert_groups=[asdict(g) for g in report.alert_groups],
        patterns=report.patterns,
        top_services=report.top_services,
        standup_update=report.standup_update,
        action_items=report.action_items,
        formatted=format_oncall_summary(report),
    )
