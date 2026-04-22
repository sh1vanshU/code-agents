"""
Jira & Confluence API endpoints.

Exposes Jira issue CRUD, JQL search, transitions, and Confluence page access.
Requires JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN environment variables.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.jira_client import JiraClient, JiraError

logger = logging.getLogger("code_agents.jira")
router = APIRouter(prefix="/jira", tags=["jira"])


def _get_client() -> JiraClient:
    """Build JiraClient from environment variables. Raises 503 if JIRA_URL not set."""
    jira_url = os.getenv("JIRA_URL", "").strip()
    if not jira_url:
        raise HTTPException(status_code=503, detail="JIRA_URL not configured. Run: code-agents init or /setup jira")
    return JiraClient(
        base_url=jira_url,
        email=os.getenv("JIRA_EMAIL", ""),
        api_token=os.getenv("JIRA_API_TOKEN", ""),
    )


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class JqlSearchRequest(BaseModel):
    jql: str = Field(..., description="JQL query string")
    max_results: int = Field(50, description="Maximum results to return")


class CreateIssueRequest(BaseModel):
    project: str = Field(..., description="Project key (e.g. 'TEAM')")
    summary: str = Field(..., description="Issue summary/title")
    description: str = Field("", description="Issue description text")
    issue_type: str = Field("Task", description="Issue type (Task, Bug, Story, Sub-task)")


class CommentRequest(BaseModel):
    body: str = Field(..., description="Comment text")


class TransitionRequest(BaseModel):
    transition_id: str = Field(..., description="Transition ID (e.g. '31')")
    comment: Optional[str] = Field(None, description="Optional comment to add with transition")


class CqlSearchRequest(BaseModel):
    cql: str = Field(..., description="CQL query string (e.g. \"space = 'TEAM' and title ~ 'HLD'\")")


# ------------------------------------------------------------------
# Jira endpoints
# ------------------------------------------------------------------

@router.get("/issue/{key}")
async def get_issue(key: str):
    """Get Jira ticket details including summary, status, acceptance criteria, subtasks."""
    try:
        client = _get_client()
        return await client.get_issue(key)
    except JiraError as e:
        logger.error("get_issue(%s) failed: %s", key, e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.post("/search")
async def search_issues(req: JqlSearchRequest):
    """Search Jira issues using JQL."""
    try:
        client = _get_client()
        return await client.search_issues(req.jql, req.max_results)
    except JiraError as e:
        logger.error("search_issues failed: %s", e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.post("/issue")
async def create_issue(req: CreateIssueRequest):
    """Create a new Jira issue."""
    try:
        client = _get_client()
        return await client.create_issue(req.project, req.summary, req.description, req.issue_type)
    except JiraError as e:
        logger.error("create_issue failed: %s", e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.post("/issue/{key}/comment")
async def add_comment(key: str, req: CommentRequest):
    """Add a comment to a Jira issue."""
    try:
        client = _get_client()
        return await client.add_comment(key, req.body)
    except JiraError as e:
        logger.error("add_comment(%s) failed: %s", key, e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.get("/issue/{key}/transitions")
async def get_transitions(key: str):
    """Get available transitions for a Jira issue."""
    try:
        client = _get_client()
        return await client.get_transitions(key)
    except JiraError as e:
        logger.error("get_transitions(%s) failed: %s", key, e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.post("/issue/{key}/transition")
async def transition_issue(key: str, req: TransitionRequest):
    """Transition a Jira issue to a new status."""
    try:
        client = _get_client()
        return await client.transition_issue(key, req.transition_id, req.comment)
    except JiraError as e:
        logger.error("transition_issue(%s) failed: %s", key, e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


# ------------------------------------------------------------------
# Confluence endpoints
# ------------------------------------------------------------------

@router.get("/confluence/{page_id}")
async def get_confluence_page(page_id: str):
    """Get a Confluence page by ID with full body content."""
    try:
        client = _get_client()
        return await client.get_confluence_page(page_id)
    except JiraError as e:
        logger.error("get_confluence_page(%s) failed: %s", page_id, e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))


@router.post("/confluence/search")
async def search_confluence(req: CqlSearchRequest):
    """Search Confluence pages using CQL."""
    try:
        client = _get_client()
        return await client.search_confluence(req.cql)
    except JiraError as e:
        logger.error("search_confluence failed: %s", e)
        raise HTTPException(status_code=e.status_code or 502, detail=str(e))
