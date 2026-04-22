"""Tests for GitHub Actions, Terraform, DB, and PR Review routers — integration tests with mocked clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from code_agents.core.app import app


client = TestClient(app)


class TestGitHubActionsRouter:
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test", "GITHUB_REPO": "owner/repo"})
    @patch("code_agents.routers.github_actions.GitHubActionsClient")
    def test_list_workflows(self, MockClient):
        mock = MockClient.return_value
        mock.list_workflows = AsyncMock(return_value=[{"id": 1, "name": "CI"}])
        resp = client.get("/github-actions/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test", "GITHUB_REPO": "owner/repo"})
    @patch("code_agents.routers.github_actions.GitHubActionsClient")
    def test_get_run(self, MockClient):
        mock = MockClient.return_value
        mock.get_run = AsyncMock(return_value={"id": 100, "status": "completed"})
        resp = client.get("/github-actions/runs/100")
        assert resp.status_code == 200

    def test_no_token_returns_503(self):
        with patch.dict("os.environ", {}, clear=True):
            resp = client.get("/github-actions/workflows")
            assert resp.status_code == 503


class TestTerraformRouter:
    @patch("code_agents.routers.terraform.TerraformClient")
    def test_state_list(self, MockClient):
        mock = MockClient.return_value
        mock.state_list = AsyncMock(return_value=["aws_s3_bucket.logs"])
        resp = client.get("/terraform/state?working_dir=.")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @patch("code_agents.routers.terraform.TerraformClient")
    def test_validate(self, MockClient):
        mock = MockClient.return_value
        mock.validate = AsyncMock(return_value={"valid": True})
        resp = client.post("/terraform/validate", json={"working_dir": "."})
        assert resp.status_code == 200


class TestDBRouter:
    def test_no_config_returns_503(self):
        with patch.dict("os.environ", {}, clear=True):
            resp = client.get("/db/databases")
            assert resp.status_code == 503


class TestPRReviewRouter:
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test", "GITHUB_REPO": "owner/repo"})
    @patch("code_agents.routers.pr_review.PRReviewClient")
    def test_list_pulls(self, MockClient):
        mock = MockClient.return_value
        mock.list_pulls = AsyncMock(return_value=[{"number": 1, "title": "Fix"}])
        resp = client.get("/pr-review/pulls")
        assert resp.status_code == 200

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test", "GITHUB_REPO": "owner/repo"})
    @patch("code_agents.routers.pr_review.PRReviewClient")
    def test_checklist(self, MockClient):
        resp = client.get("/pr-review/checklist")
        assert resp.status_code == 200
        data = resp.json()
        assert "checklist" in data

    def test_no_token_returns_503(self):
        with patch.dict("os.environ", {}, clear=True):
            resp = client.get("/pr-review/pulls")
            assert resp.status_code == 503
