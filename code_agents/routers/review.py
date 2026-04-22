"""Review router — AI code review with auto-fix API endpoints."""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("code_agents.routers.review")

router = APIRouter(prefix="/review", tags=["review"])


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    base: str = Field("main", description="Base branch/ref")
    head: str = Field("HEAD", description="Head branch/ref")
    fix: bool = Field(False, description="Auto-fix findings")
    post_comments: bool = Field(False, description="Post PR comments")
    pr_id: str = Field("", description="PR ID for posting comments")
    severity_filter: str = Field("", description="Filter by severity (comma-separated)")
    min_confidence: float = Field(0.7, description="Min confidence for fixes", ge=0, le=1)


class ReviewFindingResponse(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    message: str


class FixSuggestionResponse(BaseModel):
    finding_index: int
    file: str
    line: int
    original_code: str
    fixed_code: str
    explanation: str
    confidence: float


class SeverityScoreResponse(BaseModel):
    total_findings: int
    final_score: float
    grade: str
    by_severity: dict = {}
    by_category: dict = {}


class ReviewResponse(BaseModel):
    base: str
    head: str
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    score: int = 100
    severity_breakdown: SeverityScoreResponse = SeverityScoreResponse(
        total_findings=0, final_score=100, grade="A"
    )
    findings: list[ReviewFindingResponse] = []
    fix_suggestions: list[FixSuggestionResponse] = []
    fixes_applied: int = 0
    fixes_failed: int = 0
    fixes_skipped: int = 0
    comments_posted: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=ReviewResponse)
async def run_review(req: ReviewRequest, request: Request):
    """Run AI code review with optional auto-fix."""
    from code_agents.reviews.review_autofix import ReviewAutoFixer, calculate_severity_score

    cwd = getattr(request.state, "repo_path", os.getcwd())

    fixer = ReviewAutoFixer(cwd=cwd, min_confidence=req.min_confidence)
    report = fixer.run(
        base=req.base,
        head=req.head,
        fix=req.fix,
        post_comments=req.post_comments,
        pr_id=req.pr_id,
        severity_filter=req.severity_filter,
    )

    review = report.review
    severity = calculate_severity_score(review.findings)

    return ReviewResponse(
        base=review.base,
        head=review.head,
        files_changed=review.files_changed,
        lines_added=review.lines_added,
        lines_removed=review.lines_removed,
        score=review.score,
        severity_breakdown=SeverityScoreResponse(
            total_findings=severity.get("total_findings", 0),
            final_score=severity.get("final_score", 100),
            grade=severity.get("grade", "A"),
            by_severity=severity.get("by_severity", {}),
            by_category=severity.get("by_category", {}),
        ),
        findings=[
            ReviewFindingResponse(
                file=f.file, line=f.line,
                severity=f.severity, category=f.category,
                message=f.message,
            )
            for f in review.findings
        ],
        fix_suggestions=[
            FixSuggestionResponse(
                finding_index=s.finding_index,
                file=s.file, line=s.line,
                original_code=s.original_code,
                fixed_code=s.fixed_code,
                explanation=s.explanation,
                confidence=s.confidence,
            )
            for s in report.fix_suggestions
        ],
        fixes_applied=report.fixes_applied,
        fixes_failed=report.fixes_failed,
        fixes_skipped=report.fixes_skipped,
        comments_posted=report.comments_posted,
        summary=review.summary,
    )


@router.post("/rollback")
async def rollback_fixes(backup_dir: str, request: Request):
    """Rollback applied fixes from a backup directory."""
    from code_agents.reviews.review_autofix import ReviewAutoFixer

    cwd = getattr(request.state, "repo_path", os.getcwd())
    fixer = ReviewAutoFixer(cwd=cwd)
    fixer.rollback(backup_dir)
    return {"status": "rolled_back", "backup_dir": backup_dir}


@router.get("/status")
async def review_status():
    """Check review engine availability."""
    return {
        "available": True,
        "features": [
            "static_analysis", "ai_review", "auto_fix",
            "pr_comments", "severity_scoring", "rollback",
        ],
        "supported_hosts": ["bitbucket", "github"],
    }
