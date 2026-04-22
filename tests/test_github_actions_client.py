"""Tests for github_actions_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.github_actions_client import GitHubActionsClient, GitHubActionsError


class TestGitHubActionsClientInit:
    def test_defaults(self):
        c = GitHubActionsClient()
        assert c.token == ""
        assert c.repo == ""
        assert c.api_url == "https://api.github.com"
        assert c.timeout == 30.0

    def test_custom_init(self):
        c = GitHubActionsClient(token="ghp_test", repo="owner/repo", timeout=60.0)
        assert c.token == "ghp_test"
        assert c.repo == "owner/repo"
        assert c.timeout == 60.0

    def test_strips_trailing_slash(self):
        c = GitHubActionsClient(api_url="https://api.github.com/")
        assert c.api_url == "https://api.github.com"


class TestGitHubActionsClientHttpClient:
    def test_client_with_token(self):
        c = GitHubActionsClient(token="ghp_test", repo="owner/repo")
        client = c._client()
        assert client is not None

    def test_client_without_token(self):
        c = GitHubActionsClient(repo="owner/repo")
        client = c._client()
        assert client is not None


def _mock_client(mock_resp):
    mock_c = AsyncMock()
    mock_c.get = AsyncMock(return_value=mock_resp)
    mock_c.post = AsyncMock(return_value=mock_resp)
    mock_c.__aenter__ = AsyncMock(return_value=mock_c)
    mock_c.__aexit__ = AsyncMock(return_value=False)
    return mock_c


class TestGetRepo:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "full_name": "owner/repo",
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/owner/repo",
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_repo())
            assert result["full_name"] == "owner/repo"
            assert result["default_branch"] == "main"

    def test_failure(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            with pytest.raises(GitHubActionsError):
                asyncio.run(c.get_repo())


class TestListWorkflows:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "workflows": [
                {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active", "html_url": ""},
                {"id": 2, "name": "Deploy", "path": ".github/workflows/deploy.yml", "state": "active", "html_url": ""},
            ]
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.list_workflows())
            assert len(result) == 2
            assert result[0]["name"] == "CI"

    def test_failure(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            with pytest.raises(GitHubActionsError):
                asyncio.run(c.list_workflows())


class TestGetWorkflowRuns:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "workflow_runs": [
                {
                    "id": 100, "name": "CI", "status": "completed", "conclusion": "success",
                    "head_branch": "main", "event": "push", "html_url": "", "created_at": "",
                    "updated_at": "", "run_number": 42, "run_attempt": 1,
                }
            ]
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_workflow_runs(1))
            assert len(result) == 1
            assert result[0]["status"] == "completed"
            assert result[0]["conclusion"] == "success"


class TestDispatchWorkflow:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.dispatch_workflow(1, ref="main"))
            assert result["status"] == "dispatched"

    def test_failure(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable"
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            with pytest.raises(GitHubActionsError):
                asyncio.run(c.dispatch_workflow(1, ref="main"))


class TestGetRun:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 100, "name": "CI", "status": "completed", "conclusion": "failure",
            "head_branch": "fix-bug", "event": "push", "html_url": "", "created_at": "",
            "updated_at": "", "run_number": 43, "run_attempt": 1,
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_run(100))
            assert result["id"] == 100
            assert result["conclusion"] == "failure"


class TestGetRunJobs:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobs": [
                {
                    "id": 200, "name": "build", "status": "completed", "conclusion": "success",
                    "started_at": "", "completed_at": "",
                    "steps": [{"name": "Checkout", "status": "completed", "conclusion": "success", "number": 1}],
                }
            ]
        }
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.get_run_jobs(100))
            assert len(result) == 1
            assert result[0]["name"] == "build"
            assert len(result[0]["steps"]) == 1


class TestRetryRun:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.retry_run(100))
            assert result["status"] == "retried"


class TestCancelRun:
    def test_success(self):
        c = GitHubActionsClient(token="t", repo="owner/repo")
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch.object(c, "_client", return_value=_mock_client(mock_resp)):
            result = asyncio.run(c.cancel_run(100))
            assert result["status"] == "cancelled"


class TestFormatRun:
    def test_format(self):
        c = GitHubActionsClient()
        run = {
            "id": 1, "name": "CI", "status": "completed", "conclusion": "success",
            "head_branch": "main", "event": "push", "html_url": "https://example.com",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:01:00Z",
            "run_number": 10, "run_attempt": 1,
        }
        result = c._format_run(run)
        assert result["id"] == 1
        assert result["branch"] == "main"
        assert result["run_number"] == 10
