"""
Git operations API: inspect branches, diffs, logs, and push code on a target repository.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.git_client import GitClient, GitOpsError

logger = logging.getLogger("code_agents.git_ops")
router = APIRouter(prefix="/git", tags=["git"])


def _resolve_repo_path(repo_path: Optional[str] = None) -> str:
    """Resolve repo path: request param → env var → cwd."""
    path = repo_path or os.getenv("TARGET_REPO_PATH") or os.getcwd()
    if not os.path.isdir(path):
        raise HTTPException(status_code=422, detail=f"Repository path does not exist: {path}")
    return path


def _get_client(repo_path: Optional[str] = None) -> GitClient:
    """Build GitClient from request param, env var, or cwd."""
    return GitClient(repo_path=_resolve_repo_path(repo_path))


class PushRequest(BaseModel):
    """Request to push a branch to remote."""
    branch: str = Field(..., description="Branch name to push")
    remote: str = Field("origin", description="Remote name (default: origin)")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class CheckoutRequest(BaseModel):
    """Request to switch branches."""
    branch: str = Field(..., description="Branch to switch to")
    create: bool = Field(False, description="Create branch if it doesn't exist")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class StashRequest(BaseModel):
    """Request to stash/pop working changes."""
    action: str = Field("push", description="push, pop, list, drop, show")
    message: str = Field("", description="Stash message (for push only)")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class MergeRequest(BaseModel):
    """Request to merge a branch."""
    branch: str = Field(..., description="Branch to merge into current")
    no_ff: bool = Field(False, description="Force merge commit (--no-ff)")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class AddRequest(BaseModel):
    """Request to stage files."""
    files: Optional[list[str]] = Field(None, description="Files to stage (null = all)")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class CommitRequest(BaseModel):
    """Request to create a commit."""
    message: str = Field(..., description="Commit message")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class DiffQuery(BaseModel):
    """Query parameters for diff endpoint."""
    base: str = Field("main", description="Base branch/ref")
    head: str = Field(..., description="Head branch/ref to compare")


@router.get("/branches")
async def list_branches(repo_path: Optional[str] = None):
    """List all local and remote branches in the target repository."""
    try:
        client = _get_client(repo_path)
        return {"branches": await client.list_branches(), "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("list_branches failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/current-branch")
async def current_branch(repo_path: Optional[str] = None):
    """Get the current branch of the target repository."""
    try:
        client = _get_client(repo_path)
        branch = await client.current_branch()
        return {"branch": branch, "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("current_branch failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/diff")
async def get_diff(base: str = "main", head: str = "HEAD", repo_path: Optional[str] = None):
    """Show diff between two branches/refs in the target repository."""
    try:
        client = _get_client(repo_path)
        result = await client.diff(base=base, head=head)
        result["repo_path"] = client.repo_path
        logger.info("diff %s...%s: %d files, +%d/-%d", base, head,
                     result["files_changed"], result["insertions"], result["deletions"])
        return result
    except GitOpsError as e:
        logger.error("diff failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.get("/log")
async def get_log(branch: str = "HEAD", limit: int = 20, repo_path: Optional[str] = None):
    """Show commit log for a branch in the target repository."""
    try:
        client = _get_client(repo_path)
        commits = await client.log(branch=branch, limit=min(limit, 100))
        return {"branch": branch, "commits": commits, "count": len(commits), "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("log failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.post("/push")
async def push_branch(req: PushRequest):
    """Push a branch to remote. Never force-pushes."""
    try:
        client = _get_client(req.repo_path)
        result = await client.push(branch=req.branch, remote=req.remote)
        result["repo_path"] = client.repo_path
        logger.info("push %s to %s: success", req.branch, req.remote)
        return result
    except GitOpsError as e:
        logger.error("push failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.get("/status")
async def get_status(repo_path: Optional[str] = None):
    """Get working tree status of the target repository."""
    try:
        client = _get_client(repo_path)
        result = await client.status()
        result["repo_path"] = client.repo_path
        return result
    except GitOpsError as e:
        logger.error("status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/fetch")
async def fetch_remote(remote: str = "origin", repo_path: Optional[str] = None):
    """Fetch latest from remote."""
    try:
        client = _get_client(repo_path)
        output = await client.fetch(remote=remote)
        return {"remote": remote, "output": output, "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/checkout")
async def checkout_branch(req: CheckoutRequest):
    """Switch to a branch. Set create=true to create it first."""
    try:
        client = _get_client(req.repo_path)
        result = await client.checkout(branch=req.branch, create=req.create)
        result["repo_path"] = client.repo_path
        logger.info("checkout %s (create=%s): success", req.branch, req.create)
        return result
    except GitOpsError as e:
        logger.error("checkout failed: %s", e)
        status = 409 if "dirty" in str(e).lower() else 422 if "Invalid" in str(e) else 502
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/stash")
async def stash_changes(req: StashRequest):
    """Stash or restore working changes. Actions: push, pop, list, drop, show."""
    try:
        client = _get_client(req.repo_path)
        result = await client.stash(action=req.action, message=req.message)
        result["repo_path"] = client.repo_path
        logger.info("stash %s: done", req.action)
        return result
    except GitOpsError as e:
        logger.error("stash failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.post("/merge")
async def merge_branch(req: MergeRequest):
    """Merge a branch into the current branch."""
    try:
        client = _get_client(req.repo_path)
        result = await client.merge(branch=req.branch, no_ff=req.no_ff)
        result["repo_path"] = client.repo_path
        logger.info("merge %s: success", req.branch)
        return result
    except GitOpsError as e:
        logger.error("merge failed: %s", e)
        raise HTTPException(status_code=409 if "conflict" in str(e).lower() else 502, detail=str(e))


@router.post("/add")
async def stage_files(req: AddRequest):
    """Stage files for commit. Pass null for files to stage all."""
    try:
        client = _get_client(req.repo_path)
        result = await client.add(files=req.files)
        result["repo_path"] = client.repo_path
        return result
    except GitOpsError as e:
        logger.error("add failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.post("/commit")
async def create_commit(req: CommitRequest):
    """Create a commit with the given message."""
    try:
        client = _get_client(req.repo_path)
        result = await client.commit(message=req.message)
        result["repo_path"] = client.repo_path
        logger.info("commit %s: %s", result.get("hash", ""), req.message[:50])
        return result
    except GitOpsError as e:
        logger.error("commit failed: %s", e)
        raise HTTPException(status_code=422 if "empty" in str(e).lower() else 502, detail=str(e))
