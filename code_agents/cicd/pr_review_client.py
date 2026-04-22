"""
PR Review client — fetch PRs, diffs, post review comments via GitHub/Bitbucket API.

Supports GitHub REST API. Config: GITHUB_TOKEN, GITHUB_REPO (owner/repo format).
Can be extended for Bitbucket via BITBUCKET_* env vars.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.pr_review_client")


class PRReviewError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class PRReviewClient:
    """GitHub Pull Request review client."""

    def __init__(
        self,
        token: str = "",
        repo: str = "",
        api_url: str = "https://api.github.com",
        timeout: float = 30.0,
    ):
        self.token = token
        self.repo = repo  # owner/repo
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.AsyncClient(
            base_url=self.api_url,
            headers=headers,
            timeout=self.timeout,
        )

    # ── Pull Requests ────────────────────────────────────────────────────

    async def list_pulls(self, state: str = "open", per_page: int = 10) -> list[dict]:
        """List pull requests."""
        async with self._client() as client:
            r = await client.get(
                f"/repos/{self.repo}/pulls",
                params={"state": state, "per_page": per_page},
            )
            if r.status_code != 200:
                raise PRReviewError(f"List PRs failed: {r.status_code} {r.text[:200]}", r.status_code)
            return [self._format_pr(pr) for pr in r.json()]

    async def get_pull(self, pr_number: int) -> dict:
        """Get PR details."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/pulls/{pr_number}")
            if r.status_code != 200:
                raise PRReviewError(f"PR fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return self._format_pr(r.json())

    async def get_pull_diff(self, pr_number: int) -> str:
        """Get PR diff as unified diff text."""
        async with self._client() as client:
            r = await client.get(
                f"/repos/{self.repo}/pulls/{pr_number}",
                headers={"Accept": "application/vnd.github.v3.diff"},
            )
            if r.status_code != 200:
                raise PRReviewError(f"PR diff failed: {r.status_code} {r.text[:200]}", r.status_code)
            return r.text[:50000]  # Cap diff size

    async def get_pull_files(self, pr_number: int) -> list[dict]:
        """List files changed in a PR."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/pulls/{pr_number}/files", params={"per_page": 100})
            if r.status_code != 200:
                raise PRReviewError(f"PR files failed: {r.status_code} {r.text[:200]}", r.status_code)
            return [
                {
                    "filename": f.get("filename", ""),
                    "status": f.get("status", ""),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "changes": f.get("changes", 0),
                    "patch": (f.get("patch", "") or "")[:5000],
                }
                for f in r.json()
            ]

    # ── Comments ─────────────────────────────────────────────────────────

    async def get_comments(self, pr_number: int) -> list[dict]:
        """Get review comments on a PR."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/pulls/{pr_number}/comments", params={"per_page": 100})
            if r.status_code != 200:
                raise PRReviewError(f"Comments fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return [
                {
                    "id": c.get("id"),
                    "user": c.get("user", {}).get("login", ""),
                    "body": c.get("body", ""),
                    "path": c.get("path", ""),
                    "line": c.get("line"),
                    "created_at": c.get("created_at", ""),
                }
                for c in r.json()
            ]

    async def post_comment(self, pr_number: int, body: str, path: str = "", line: int = 0, commit_id: str = "") -> dict:
        """Post a review comment on a PR. If path+line specified, posts inline."""
        async with self._client() as client:
            if path and line:
                # Inline comment requires commit_id
                if not commit_id:
                    # Fetch PR to get latest commit
                    pr = await self.get_pull(pr_number)
                    commit_id = pr.get("head_sha", "")
                if not commit_id:
                    raise PRReviewError("Cannot post inline comment: no commit SHA found for PR", 400)
                payload: dict[str, Any] = {
                    "body": body,
                    "path": path,
                    "line": line,
                    "commit_id": commit_id,
                }
                r = await client.post(f"/repos/{self.repo}/pulls/{pr_number}/comments", json=payload)
            else:
                # General comment (issue comment)
                r = await client.post(
                    f"/repos/{self.repo}/issues/{pr_number}/comments",
                    json={"body": body},
                )
            if r.status_code not in (200, 201):
                raise PRReviewError(f"Comment post failed: {r.status_code} {r.text[:200]}", r.status_code)
            return {"id": r.json().get("id"), "status": "posted"}

    # ── Reviews ──────────────────────────────────────────────────────────

    async def post_review(
        self,
        pr_number: int,
        event: str = "COMMENT",
        body: str = "",
        comments: list[dict] | None = None,
    ) -> dict:
        """Post a review on a PR. event: APPROVE, REQUEST_CHANGES, COMMENT."""
        payload: dict[str, Any] = {"event": event}
        if body:
            payload["body"] = body
        if comments:
            payload["comments"] = comments

        async with self._client() as client:
            r = await client.post(f"/repos/{self.repo}/pulls/{pr_number}/reviews", json=payload)
            if r.status_code not in (200, 201):
                raise PRReviewError(f"Review post failed: {r.status_code} {r.text[:200]}", r.status_code)
            return {"id": r.json().get("id"), "state": event, "status": "posted"}

    # ── Checks ───────────────────────────────────────────────────────────

    async def get_checks(self, pr_number: int) -> list[dict]:
        """Get CI check status for a PR."""
        # First get the PR's head SHA
        pr = await self.get_pull(pr_number)
        head_sha = pr.get("head_sha", "")
        if not head_sha:
            return []

        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/commits/{head_sha}/check-runs", params={"per_page": 100})
            if r.status_code != 200:
                raise PRReviewError(f"Checks fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return [
                {
                    "name": c.get("name", ""),
                    "status": c.get("status", ""),
                    "conclusion": c.get("conclusion"),
                    "html_url": c.get("html_url", ""),
                    "started_at": c.get("started_at", ""),
                    "completed_at": c.get("completed_at", ""),
                }
                for c in r.json().get("check_runs", [])
            ]

    # ── Helpers ──────────────────────────────────────────────────────────

    def _format_pr(self, pr: dict) -> dict:
        return {
            "number": pr.get("number"),
            "title": pr.get("title", ""),
            "state": pr.get("state", ""),
            "author": pr.get("user", {}).get("login", ""),
            "head_branch": pr.get("head", {}).get("ref", ""),
            "base_branch": pr.get("base", {}).get("ref", ""),
            "head_sha": pr.get("head", {}).get("sha", ""),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            "mergeable": pr.get("mergeable"),
            "draft": pr.get("draft", False),
            "html_url": pr.get("html_url", ""),
            "created_at": pr.get("created_at", ""),
            "updated_at": pr.get("updated_at", ""),
        }
