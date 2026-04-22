"""
PR Review Bot: fetch PRs, diffs, post review comments on GitHub.

Requires GITHUB_TOKEN and GITHUB_REPO to be set (503 otherwise).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..cicd.pr_review_client import PRReviewClient, PRReviewError

logger = logging.getLogger("code_agents.routers.pr_review")
router = APIRouter(prefix="/pr-review", tags=["pr-review"])


def _get_client() -> PRReviewClient:
    """Build PRReviewClient from environment variables."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    if not token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN is not set.")
    if not repo:
        raise HTTPException(status_code=503, detail="GITHUB_REPO is not set (expected owner/repo format).")
    return PRReviewClient(token=token, repo=repo)


# ── Models ────────────────────────────────────────────────────────────────

class ReviewComment(BaseModel):
    path: str = Field(description="File path relative to repo root")
    line: int = Field(description="Line number in the diff")
    body: str = Field(description="Comment text")


class PostReviewRequest(BaseModel):
    event: str = Field(default="COMMENT", description="Review event: APPROVE, REQUEST_CHANGES, COMMENT")
    body: str = Field(default="", description="Review summary body")
    comments: list[ReviewComment] = Field(default_factory=list, description="Inline review comments")


class PostCommentRequest(BaseModel):
    body: str = Field(description="Comment text")
    path: str = Field(default="", description="File path for inline comment")
    line: int = Field(default=0, description="Line number for inline comment")


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/pulls")
async def list_pulls(state: str = "open", per_page: int = 10):
    """List pull requests."""
    client = _get_client()
    try:
        pulls = await client.list_pulls(state=state, per_page=per_page)
        return {"total": len(pulls), "pulls": pulls}
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/pulls/{pr_number}")
async def get_pull(pr_number: int):
    """Get PR details."""
    client = _get_client()
    try:
        return await client.get_pull(pr_number)
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/pulls/{pr_number}/diff")
async def get_pull_diff(pr_number: int):
    """Get PR diff as unified diff."""
    client = _get_client()
    try:
        diff = await client.get_pull_diff(pr_number)
        return {"diff": diff}
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/pulls/{pr_number}/files")
async def get_pull_files(pr_number: int):
    """List files changed in a PR."""
    client = _get_client()
    try:
        files = await client.get_pull_files(pr_number)
        return {"total": len(files), "files": files}
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/pulls/{pr_number}/comments")
async def get_pull_comments(pr_number: int):
    """Get review comments on a PR."""
    client = _get_client()
    try:
        comments = await client.get_comments(pr_number)
        return {"total": len(comments), "comments": comments}
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/pulls/{pr_number}/review")
async def post_review(pr_number: int, req: PostReviewRequest):
    """Post a review on a PR with optional inline comments."""
    client = _get_client()
    try:
        comments_dicts = [c.model_dump() for c in req.comments] if req.comments else None
        return await client.post_review(
            pr_number, event=req.event, body=req.body, comments=comments_dicts
        )
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/pulls/{pr_number}/comments")
async def post_comment(pr_number: int, req: PostCommentRequest):
    """Post a comment on a PR (inline if path+line provided)."""
    client = _get_client()
    try:
        return await client.post_comment(
            pr_number, body=req.body, path=req.path, line=req.line
        )
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/pulls/{pr_number}/checks")
async def get_pull_checks(pr_number: int):
    """Get CI check status for a PR."""
    client = _get_client()
    try:
        checks = await client.get_checks(pr_number)
        return {"total": len(checks), "checks": checks}
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/pulls/{pr_number}/auto-review")
async def auto_review(pr_number: int):
    """Trigger an automated review of a PR. Returns review findings."""
    client = _get_client()
    try:
        # Fetch PR details, files, and diff
        pr = await client.get_pull(pr_number)
        files = await client.get_pull_files(pr_number)
        diff = await client.get_pull_diff(pr_number)

        return {
            "pr": pr,
            "files_changed": len(files),
            "files": files,
            "diff_preview": diff[:10000],
            "message": "Review data fetched. Use the code-review agent to analyze and post findings.",
        }
    except PRReviewError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/checklist")
async def review_checklist():
    """Get a standard code review checklist."""
    return {
        "checklist": [
            {"category": "Security", "items": [
                "No hardcoded secrets or credentials",
                "Input validation on all user-facing endpoints",
                "SQL parameterization (no string interpolation)",
                "XSS prevention (output encoding)",
                "Auth/authz checks on protected routes",
            ]},
            {"category": "Correctness", "items": [
                "Logic handles edge cases (null, empty, boundary values)",
                "Error handling covers failure modes",
                "Concurrency safety (no race conditions)",
                "Data types match (no implicit coercions)",
            ]},
            {"category": "Performance", "items": [
                "No N+1 queries",
                "Appropriate indexes for new queries",
                "No unnecessary allocations in hot paths",
                "Async/non-blocking where appropriate",
            ]},
            {"category": "Testing", "items": [
                "Tests cover happy path and error cases",
                "New code has corresponding tests",
                "No flaky tests introduced",
                "Mocking is minimal and focused",
            ]},
            {"category": "Maintainability", "items": [
                "Clear naming (variables, functions, classes)",
                "No dead code or commented-out blocks",
                "Functions are focused (single responsibility)",
                "Public APIs are documented",
            ]},
        ]
    }
