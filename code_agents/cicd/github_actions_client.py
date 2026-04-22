"""
GitHub Actions client — trigger, monitor, and debug GitHub Actions workflows.

Queries GitHub REST API for workflow management.
Config: GITHUB_TOKEN, GITHUB_REPO (owner/repo format)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.github_actions_client")


class GitHubActionsError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class GitHubActionsClient:
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

    @staticmethod
    def _parse_json(r: httpx.Response) -> Any:
        """Safely parse JSON response, raising on decode failure."""
        try:
            return r.json()
        except (ValueError, RuntimeError) as e:
            raise GitHubActionsError(f"Invalid JSON response: {r.text[:200]}", r.status_code) from e

    # ── Repository Info ──────────────────────────────────────────────────

    async def get_repo(self) -> dict:
        """Get repository info."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}")
            if r.status_code != 200:
                raise GitHubActionsError(f"Repo fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = self._parse_json(r)
            return {
                "full_name": data.get("full_name", ""),
                "default_branch": data.get("default_branch", ""),
                "private": data.get("private", False),
                "html_url": data.get("html_url", ""),
            }

    # ── Workflows ────────────────────────────────────────────────────────

    async def list_workflows(self) -> list[dict]:
        """List all workflows in the repository."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/actions/workflows")
            if r.status_code != 200:
                raise GitHubActionsError(f"Workflows fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = self._parse_json(r)
            return [
                {
                    "id": w.get("id"),
                    "name": w.get("name", ""),
                    "path": w.get("path", ""),
                    "state": w.get("state", ""),
                    "html_url": w.get("html_url", ""),
                }
                for w in data.get("workflows", [])
            ]

    async def get_workflow_runs(
        self, workflow_id: int | str, branch: str = "", status: str = "", per_page: int = 10
    ) -> list[dict]:
        """Get recent runs for a workflow."""
        params: dict[str, Any] = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/actions/workflows/{workflow_id}/runs", params=params)
            if r.status_code != 200:
                raise GitHubActionsError(f"Workflow runs fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = self._parse_json(r)
            return [self._format_run(run) for run in data.get("workflow_runs", [])]

    # ── Workflow Dispatch ────────────────────────────────────────────────

    async def dispatch_workflow(
        self, workflow_id: int | str, ref: str = "main", inputs: dict[str, str] | None = None
    ) -> dict:
        """Trigger a workflow_dispatch event."""
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs
        async with self._client() as client:
            r = await client.post(
                f"/repos/{self.repo}/actions/workflows/{workflow_id}/dispatches",
                json=payload,
            )
            if r.status_code not in (204, 200):
                raise GitHubActionsError(f"Workflow dispatch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return {"status": "dispatched", "workflow_id": workflow_id, "ref": ref}

    # ── Runs ─────────────────────────────────────────────────────────────

    async def get_run(self, run_id: int) -> dict:
        """Get a specific workflow run."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/actions/runs/{run_id}")
            if r.status_code != 200:
                raise GitHubActionsError(f"Run fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return self._format_run(self._parse_json(r))

    async def get_run_jobs(self, run_id: int) -> list[dict]:
        """List jobs for a workflow run."""
        async with self._client() as client:
            r = await client.get(f"/repos/{self.repo}/actions/runs/{run_id}/jobs")
            if r.status_code != 200:
                raise GitHubActionsError(f"Run jobs fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = self._parse_json(r)
            return [
                {
                    "id": j.get("id"),
                    "name": j.get("name", ""),
                    "status": j.get("status", ""),
                    "conclusion": j.get("conclusion"),
                    "started_at": j.get("started_at", ""),
                    "completed_at": j.get("completed_at", ""),
                    "steps": [
                        {
                            "name": s.get("name", ""),
                            "status": s.get("status", ""),
                            "conclusion": s.get("conclusion"),
                            "number": s.get("number"),
                        }
                        for s in j.get("steps", [])
                    ],
                }
                for j in data.get("jobs", [])
            ]

    async def get_run_logs(self, run_id: int) -> str:
        """Download run logs (returns URL to zip)."""
        async with self._client() as client:
            r = await client.get(
                f"/repos/{self.repo}/actions/runs/{run_id}/logs",
                follow_redirects=False,
            )
            if r.status_code == 302:
                return r.headers.get("Location", "")
            if r.status_code != 200:
                raise GitHubActionsError(f"Logs fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return r.text[:5000]

    async def get_job_logs(self, job_id: int) -> str:
        """Download logs for a specific job."""
        async with self._client() as client:
            r = await client.get(
                f"/repos/{self.repo}/actions/jobs/{job_id}/logs",
                follow_redirects=False,
            )
            if r.status_code == 302:
                # Redirect to log download URL — fetch the actual logs
                log_r = await client.get(r.headers.get("Location", ""))
                return log_r.text[:10000]
            if r.status_code != 200:
                raise GitHubActionsError(f"Job logs fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            return r.text[:10000]

    # ── Run Actions ──────────────────────────────────────────────────────

    async def retry_run(self, run_id: int) -> dict:
        """Re-run failed jobs in a workflow run."""
        async with self._client() as client:
            r = await client.post(f"/repos/{self.repo}/actions/runs/{run_id}/rerun-failed-jobs")
            if r.status_code not in (201, 204):
                raise GitHubActionsError(f"Retry failed: {r.status_code} {r.text[:200]}", r.status_code)
            return {"status": "retried", "run_id": run_id}

    async def cancel_run(self, run_id: int) -> dict:
        """Cancel a workflow run."""
        async with self._client() as client:
            r = await client.post(f"/repos/{self.repo}/actions/runs/{run_id}/cancel")
            if r.status_code not in (202, 204):
                raise GitHubActionsError(f"Cancel failed: {r.status_code} {r.text[:200]}", r.status_code)
            return {"status": "cancelled", "run_id": run_id}

    # ── Helpers ──────────────────────────────────────────────────────────

    def _format_run(self, run: dict) -> dict:
        return {
            "id": run.get("id"),
            "name": run.get("name", ""),
            "status": run.get("status", ""),
            "conclusion": run.get("conclusion"),
            "branch": run.get("head_branch", ""),
            "event": run.get("event", ""),
            "html_url": run.get("html_url", ""),
            "created_at": run.get("created_at", ""),
            "updated_at": run.get("updated_at", ""),
            "run_number": run.get("run_number"),
            "run_attempt": run.get("run_attempt"),
        }
