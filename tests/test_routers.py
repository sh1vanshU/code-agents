"""Tests for FastAPI routers — git, testing, jenkins, argocd, pipeline."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from code_agents.core.app import app

client = TestClient(app)


# --- Git Router Tests ---


class TestGitRouter:
    def test_branches_defaults_to_cwd(self):
        """When no repo_path is set, should use cwd (which is a git repo)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TARGET_REPO_PATH", None)
            resp = client.get("/git/branches")
            # cwd is the code-agents repo, so this should work
            assert resp.status_code == 200
            assert "branches" in resp.json()

    def test_branches_with_explicit_repo_path(self):
        """Can pass repo_path as query param to target any repo."""
        resp = client.get(f"/git/branches?repo_path={os.getcwd()}")
        assert resp.status_code == 200

    def test_branches_invalid_repo_path(self):
        """Should 422 when repo_path doesn't exist."""
        resp = client.get("/git/branches?repo_path=/tmp/nonexistent-repo-xyz")
        assert resp.status_code == 422

    def test_diff_invalid_ref(self):
        """Should reject invalid git refs."""
        resp = client.get(f"/git/diff?base=main&head=bad%3Bref&repo_path={os.getcwd()}")
        assert resp.status_code == 422


# --- Jenkins Router Tests ---


class TestJenkinsRouter:
    def test_build_no_jenkins_configured(self):
        """Should return 503 when JENKINS_URL is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JENKINS_URL", None)
            resp = client.post("/jenkins/build", json={"job_name": "test"})
            assert resp.status_code == 503


# --- ArgoCD Router Tests ---


class TestArgoCDRouter:
    def test_status_no_argocd_configured(self):
        """Should return 503 when ARGOCD_URL is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARGOCD_URL", None)
            resp = client.get("/argocd/apps/my-app/status")
            assert resp.status_code == 503


# --- Pipeline Router Tests ---


class TestPipelineRouter:
    """Test pipeline router using a dedicated FastAPI app with the router explicitly included."""

    @pytest.fixture
    def pipeline_client(self):
        """Create a test client with pipeline router always registered."""
        from fastapi import FastAPI
        from code_agents.routers.pipeline import router as pipeline_router

        test_app = FastAPI()
        test_app.include_router(pipeline_router)
        return TestClient(test_app)

    def test_pipeline_lifecycle(self, pipeline_client):
        """Test the pipeline start -> status -> advance -> rollback flow."""
        # Start — repo_path falls back to cwd dynamically
        resp = pipeline_client.post("/pipeline/start", json={"branch": "feature-123"})
        assert resp.status_code == 200
        data = resp.json()
        run_id = data["run_id"]
        assert data["branch"] == "feature-123"
        assert data["current_step"] == 1
        assert data["current_step_name"] == "connect"

        # Status
        resp = pipeline_client.get(f"/pipeline/{run_id}/status")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

        # Advance to step 2
        resp = pipeline_client.post(f"/pipeline/{run_id}/advance", json={
            "details": {"connected": True}
        })
        assert resp.status_code == 200
        assert resp.json()["current_step"] == 2

        # Advance to step 3
        resp = pipeline_client.post(f"/pipeline/{run_id}/advance", json={
            "details": {"tests_passed": True, "coverage": 100}
        })
        assert resp.status_code == 200
        assert resp.json()["current_step"] == 3

        # Advance to step 4 with build number
        resp = pipeline_client.post(f"/pipeline/{run_id}/advance", json={
            "details": {"build_number": 42}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_step"] == 4
        assert data["build_number"] == 42

        # Fail step 4
        resp = pipeline_client.post(f"/pipeline/{run_id}/fail", json={
            "error": "Deploy job failed"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"]["4"]["status"] == "failed"
        assert data["recommended_action"] == "rollback"

        # Rollback
        resp = pipeline_client.post(f"/pipeline/{run_id}/rollback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_step"] == 7
        assert data["steps"]["5"]["status"] == "skipped"
        assert data["steps"]["6"]["status"] == "skipped"

    def test_pipeline_not_found(self, pipeline_client):
        resp = pipeline_client.get("/pipeline/nonexistent/status")
        assert resp.status_code == 404

    def test_list_runs(self, pipeline_client):
        resp = pipeline_client.get("/pipeline/runs")
        assert resp.status_code == 200
        assert "runs" in resp.json()

    def test_start_with_invalid_repo_path(self, pipeline_client):
        """Should 422 when repo_path doesn't exist."""
        resp = pipeline_client.post("/pipeline/start", json={
            "branch": "test",
            "repo_path": "/tmp/nonexistent-repo-xyz",
        })
        assert resp.status_code == 422

    def test_start_with_dynamic_repo_path(self, pipeline_client):
        """Can pass repo_path in request body to target any repo."""
        resp = pipeline_client.post("/pipeline/start", json={
            "branch": "test",
            "repo_path": os.getcwd(),
        })
        assert resp.status_code == 200
        assert resp.json()["repo_path"] == os.getcwd()

    def test_advance_failed_step_blocked(self, pipeline_client):
        """Cannot advance a failed step."""
        resp = pipeline_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        # Fail current step
        pipeline_client.post(f"/pipeline/{run_id}/fail", json={"error": "broken"})
        # Try to advance — should be blocked
        resp = pipeline_client.post(f"/pipeline/{run_id}/advance")
        assert resp.status_code == 422


# --- Health & Diagnostics ---


class TestHealthDiagnostics:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_diagnostics(self):
        resp = client.get("/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "target_repo_configured" in data
        assert "jenkins_configured" in data
        assert "argocd_configured" in data
        assert "pipeline_enabled" in data
