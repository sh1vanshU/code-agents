"""Router for Code Review Buddy."""

from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.review_buddy")

router = APIRouter(prefix="/review-buddy", tags=["review-buddy"])


class ReviewBuddyRequest(BaseModel):
    staged_only: bool = Field(True, description="Review staged changes only")
    auto_fix: bool = Field(False, description="Auto-fix where possible")


class ReviewBuddyResponse(BaseModel):
    files_reviewed: int = 0
    total_findings: int = 0
    score: float = 100.0
    grade: str = "A"
    by_severity: dict = {}
    by_category: dict = {}
    findings: list[dict] = []
    fixes_applied: int = 0
    formatted: str = ""


@router.post("/check", response_model=ReviewBuddyResponse)
async def run_review_buddy(req: ReviewBuddyRequest, request: Request):
    """Run pre-push code review."""
    from code_agents.reviews.review_buddy import ReviewBuddy, format_review
    from dataclasses import asdict

    cwd = getattr(request.state, "repo_path", os.getcwd())
    buddy = ReviewBuddy(cwd=cwd, staged_only=req.staged_only, auto_fix=req.auto_fix)
    report = buddy.check()
    return ReviewBuddyResponse(
        files_reviewed=report.files_reviewed,
        total_findings=report.score.total_findings,
        score=report.score.score,
        grade=report.score.grade,
        by_severity=report.score.by_severity,
        by_category=report.score.by_category,
        findings=[asdict(f) for f in report.findings],
        fixes_applied=report.fixes_applied,
        formatted=format_review(report),
    )
