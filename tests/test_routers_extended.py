"""Extended tests for routers — git_ops.py and jenkins.py."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.routers.git_ops import (
    _resolve_repo_path,
    _get_client,
    router as git_router,
    list_branches,
    current_branch,
    get_diff,
    get_log,
    push_branch,
    get_status,
    fetch_remote,
    checkout_branch,
    stash_changes,
    merge_branch,
    stage_files,
    create_commit,
    PushRequest,
    CheckoutRequest,
    StashRequest,
    MergeRequest,
    AddRequest,
    CommitRequest,
)
from code_agents.routers.jenkins import (
    _get_client as _get_jenkins_client,
    router as jenkins_router,
    list_jobs,
    get_job_parameters,
    trigger_build,
    get_build_status as router_get_build_status,
    get_build_log as router_get_build_log,
    get_last_build as router_get_last_build,
    wait_for_build as router_wait_for_build,
    TriggerBuildRequest,
    WaitForBuildRequest,
)


# ═══════════════════════════════════════════════════════════════════════
# git_ops router tests
# ═══════════════════════════════════════════════════════════════════════


class TestResolveRepoPath:
    def test_from_param(self, tmp_path):
        path = _resolve_repo_path(str(tmp_path))
        assert path == str(tmp_path)

    def test_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TARGET_REPO_PATH", str(tmp_path))
        path = _resolve_repo_path(None)
        assert path == str(tmp_path)

    def test_nonexistent_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _resolve_repo_path("/nonexistent/path/12345")
        assert exc_info.value.status_code == 422


class TestGitOpsRouterEndpoints:
    """Test git_ops router handler functions with mocked GitClient."""

    @patch("code_agents.routers.git_ops._get_client")
    def test_list_branches(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.list_branches = AsyncMock(return_value=["main", "develop"])
        mock_get_client.return_value = mock_client

        result = asyncio.run(list_branches(str(tmp_path)))
        assert result["branches"] == ["main", "develop"]
        assert result["repo_path"] == str(tmp_path)

    @patch("code_agents.routers.git_ops._get_client")
    def test_list_branches_error(self, mock_get_client):
        from code_agents.cicd.git_client import GitOpsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.list_branches = AsyncMock(side_effect=GitOpsError("git failed"))
        mock_get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(list_branches(None))
        assert exc_info.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_current_branch(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.current_branch = AsyncMock(return_value="main")
        mock_get_client.return_value = mock_client

        result = asyncio.run(current_branch(str(tmp_path)))
        assert result["branch"] == "main"

    @patch("code_agents.routers.git_ops._get_client")
    def test_get_diff(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.diff = AsyncMock(return_value={
            "files_changed": 3, "insertions": 50, "deletions": 10, "diff": "...",
        })
        mock_get_client.return_value = mock_client

        result = asyncio.run(get_diff("main", "HEAD", str(tmp_path)))
        assert result["files_changed"] == 3
        assert result["repo_path"] == str(tmp_path)

    @patch("code_agents.routers.git_ops._get_client")
    def test_get_diff_invalid_ref(self, mock_get_client):
        from code_agents.cicd.git_client import GitOpsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.diff = AsyncMock(side_effect=GitOpsError("Invalid ref"))
        mock_get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_diff("bad", "HEAD"))
        assert exc_info.value.status_code == 422

    @patch("code_agents.routers.git_ops._get_client")
    def test_get_log(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.log = AsyncMock(return_value=[
            {"hash": "abc", "message": "initial"},
        ])
        mock_get_client.return_value = mock_client

        result = asyncio.run(get_log("HEAD", 10, str(tmp_path)))
        assert result["count"] == 1

    @patch("code_agents.routers.git_ops._get_client")
    def test_push_branch(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.push = AsyncMock(return_value={"status": "pushed"})
        mock_get_client.return_value = mock_client

        req = PushRequest(branch="main", remote="origin", repo_path=str(tmp_path))
        result = asyncio.run(push_branch(req))
        assert result["status"] == "pushed"

    @patch("code_agents.routers.git_ops._get_client")
    def test_get_status(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.status = AsyncMock(return_value={"clean": True})
        mock_get_client.return_value = mock_client

        result = asyncio.run(get_status(str(tmp_path)))
        assert result["clean"] is True

    @patch("code_agents.routers.git_ops._get_client")
    def test_fetch_remote(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.fetch = AsyncMock(return_value="fetched")
        mock_get_client.return_value = mock_client

        result = asyncio.run(fetch_remote("origin", str(tmp_path)))
        assert result["remote"] == "origin"

    @patch("code_agents.routers.git_ops._get_client")
    def test_checkout_branch(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.checkout = AsyncMock(return_value={"branch": "feature"})
        mock_get_client.return_value = mock_client

        req = CheckoutRequest(branch="feature", create=True, repo_path=str(tmp_path))
        result = asyncio.run(checkout_branch(req))
        assert result["branch"] == "feature"

    @patch("code_agents.routers.git_ops._get_client")
    def test_checkout_dirty_tree(self, mock_get_client):
        from code_agents.cicd.git_client import GitOpsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.checkout = AsyncMock(side_effect=GitOpsError("dirty working tree"))
        mock_get_client.return_value = mock_client

        req = CheckoutRequest(branch="feature")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(checkout_branch(req))
        assert exc_info.value.status_code == 409

    @patch("code_agents.routers.git_ops._get_client")
    def test_stash_changes(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.stash = AsyncMock(return_value={"action": "push"})
        mock_get_client.return_value = mock_client

        req = StashRequest(action="push", message="wip", repo_path=str(tmp_path))
        result = asyncio.run(stash_changes(req))
        assert result["action"] == "push"

    @patch("code_agents.routers.git_ops._get_client")
    def test_merge_branch(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.merge = AsyncMock(return_value={"merged": True})
        mock_get_client.return_value = mock_client

        req = MergeRequest(branch="feature", no_ff=True, repo_path=str(tmp_path))
        result = asyncio.run(merge_branch(req))
        assert result["merged"] is True

    @patch("code_agents.routers.git_ops._get_client")
    def test_merge_conflict(self, mock_get_client):
        from code_agents.cicd.git_client import GitOpsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.merge = AsyncMock(side_effect=GitOpsError("merge conflict"))
        mock_get_client.return_value = mock_client

        req = MergeRequest(branch="feature")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(merge_branch(req))
        assert exc_info.value.status_code == 409

    @patch("code_agents.routers.git_ops._get_client")
    def test_stage_files(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.add = AsyncMock(return_value={"staged": ["a.py"]})
        mock_get_client.return_value = mock_client

        req = AddRequest(files=["a.py"], repo_path=str(tmp_path))
        result = asyncio.run(stage_files(req))
        assert result["staged"] == ["a.py"]

    @patch("code_agents.routers.git_ops._get_client")
    def test_create_commit(self, mock_get_client, tmp_path):
        mock_client = MagicMock()
        mock_client.repo_path = str(tmp_path)
        mock_client.commit = AsyncMock(return_value={"hash": "abc123"})
        mock_get_client.return_value = mock_client

        req = CommitRequest(message="feat: add login", repo_path=str(tmp_path))
        result = asyncio.run(create_commit(req))
        assert result["hash"] == "abc123"

    @patch("code_agents.routers.git_ops._get_client")
    def test_create_commit_empty(self, mock_get_client):
        from code_agents.cicd.git_client import GitOpsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.commit = AsyncMock(side_effect=GitOpsError("nothing to commit, working tree is empty"))
        mock_get_client.return_value = mock_client

        req = CommitRequest(message="test")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_commit(req))
        assert exc_info.value.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# jenkins router tests
# ═══════════════════════════════════════════════════════════════════════


class TestJenkinsGetClient:
    def test_missing_url(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.delenv("JENKINS_URL", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            _get_jenkins_client()
        assert exc_info.value.status_code == 503
        assert "JENKINS_URL" in exc_info.value.detail

    def test_missing_credentials(self, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setenv("JENKINS_URL", "https://jenkins.test")
        monkeypatch.delenv("JENKINS_USERNAME", raising=False)
        monkeypatch.delenv("JENKINS_API_TOKEN", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            _get_jenkins_client()
        assert exc_info.value.status_code == 503

    def test_success(self, monkeypatch):
        monkeypatch.setenv("JENKINS_URL", "https://jenkins.test")
        monkeypatch.setenv("JENKINS_USERNAME", "admin")
        monkeypatch.setenv("JENKINS_API_TOKEN", "tok123")
        client = _get_jenkins_client()
        assert client.base_url == "https://jenkins.test"


class TestJenkinsRouterEndpoints:
    """Test jenkins router handler functions with mocked JenkinsClient."""

    @patch("code_agents.routers.jenkins._get_client")
    def test_list_jobs(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.list_jobs = AsyncMock(return_value=[
            {"name": "build-job", "type": "job"},
        ])
        mock_get_client.return_value = mock_client

        result = asyncio.run(list_jobs(folder="my-folder"))
        assert result["count"] == 1
        assert result["folder"] == "my-folder"

    @patch("code_agents.routers.jenkins._get_client")
    def test_list_jobs_root(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.list_jobs = AsyncMock(return_value=[])
        mock_get_client.return_value = mock_client

        result = asyncio.run(list_jobs(folder=None))
        assert result["folder"] == "(root)"

    @patch("code_agents.routers.jenkins._get_client")
    def test_list_jobs_error(self, mock_get_client):
        from code_agents.cicd.jenkins_client import JenkinsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.list_jobs = AsyncMock(side_effect=JenkinsError("failed"))
        mock_get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(list_jobs())
        assert exc_info.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_job_parameters(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_job_parameters = AsyncMock(return_value=[
            {"name": "branch", "type": "String", "default": "main"},
        ])
        mock_get_client.return_value = mock_client

        result = asyncio.run(get_job_parameters("my-folder/my-job"))
        assert result["job_name"] == "my-folder/my-job"
        assert len(result["parameters"]) == 1

    @patch("code_agents.routers.jenkins._get_client")
    def test_trigger_build_with_branch(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.trigger_build = AsyncMock(return_value={
            "job_name": "my-job", "queue_id": 42, "status": "queued",
        })
        mock_client.get_build_from_queue = AsyncMock(return_value=7)
        mock_get_client.return_value = mock_client

        req = TriggerBuildRequest(job_name="my-job", branch="feature/test")
        result = asyncio.run(trigger_build(req))
        assert result["build_number"] == 7
        assert result["status"] == "started"

    @patch("code_agents.routers.jenkins._get_client")
    def test_trigger_build_no_queue(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.trigger_build = AsyncMock(return_value={
            "job_name": "my-job", "queue_id": None, "status": "queued",
        })
        mock_get_client.return_value = mock_client

        req = TriggerBuildRequest(job_name="my-job")
        result = asyncio.run(trigger_build(req))
        assert "build_number" not in result

    @patch("code_agents.routers.jenkins._get_client")
    def test_trigger_build_error(self, mock_get_client):
        from code_agents.cicd.jenkins_client import JenkinsError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.trigger_build = AsyncMock(
            side_effect=JenkinsError("Forbidden", status_code=403)
        )
        mock_get_client.return_value = mock_client

        req = TriggerBuildRequest(job_name="my-job")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(trigger_build(req))
        assert exc_info.value.status_code == 422

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_build_status(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_build_status = AsyncMock(return_value={
            "result": "SUCCESS", "building": False,
        })
        mock_get_client.return_value = mock_client

        result = asyncio.run(router_get_build_status("my-job", 1))
        assert result["result"] == "SUCCESS"

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_build_log(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_build_log = AsyncMock(return_value="Build started...\nDone.")
        mock_get_client.return_value = mock_client

        result = asyncio.run(router_get_build_log("my-job", 1))
        assert result["log"] == "Build started...\nDone."

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_last_build(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_last_build = AsyncMock(return_value={
            "number": 42, "result": "SUCCESS",
        })
        mock_get_client.return_value = mock_client

        result = asyncio.run(router_get_last_build("my-job"))
        assert result["number"] == 42

    @patch("code_agents.routers.jenkins._get_client")
    def test_wait_for_build(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.wait_for_build = AsyncMock(return_value={
            "result": "SUCCESS", "building": False,
        })
        mock_get_client.return_value = mock_client

        result = asyncio.run(router_wait_for_build("my-job", 1, None))
        assert result["result"] == "SUCCESS"

    @patch("code_agents.routers.jenkins._get_client")
    def test_wait_for_build_custom_timeout(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.wait_for_build = AsyncMock(return_value={"result": "SUCCESS"})
        mock_get_client.return_value = mock_client

        req = WaitForBuildRequest(timeout=120.0)
        result = asyncio.run(router_wait_for_build("my-job", 1, req))
        assert mock_client.poll_timeout == 120.0


class TestPydanticModels:
    def test_push_request_defaults(self):
        req = PushRequest(branch="main")
        assert req.remote == "origin"
        assert req.repo_path is None

    def test_checkout_request_defaults(self):
        req = CheckoutRequest(branch="feature")
        assert req.create is False

    def test_stash_request_defaults(self):
        req = StashRequest()
        assert req.action == "push"
        assert req.message == ""

    def test_merge_request_defaults(self):
        req = MergeRequest(branch="feature")
        assert req.no_ff is False

    def test_trigger_build_request(self):
        req = TriggerBuildRequest(job_name="my-job", branch="develop")
        assert req.branch == "develop"
        assert req.parameters is None


# ═══════════════════════════════════════════════════════════════════════
# ArgoCD router tests
# ═══════════════════════════════════════════════════════════════════════


class TestArgoCDGetClient:
    """Test ArgoCD _get_client env resolution."""

    def test_missing_url_raises(self):
        from code_agents.routers.argocd import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {"ARGOCD_URL": "", "ARGOCD_USERNAME": "a", "ARGOCD_PASSWORD": "b"}, clear=False):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert exc.value.status_code == 503
            assert "ARGOCD_URL" in exc.value.detail

    def test_missing_credentials_raises(self):
        from code_agents.routers.argocd import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {
            "ARGOCD_URL": "https://argocd.example.com",
            "ARGOCD_USERNAME": "",
            "ARGOCD_PASSWORD": "",
        }):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert exc.value.status_code == 503

    def test_client_created_with_username_password(self):
        from code_agents.routers.argocd import _get_client
        with patch.dict(os.environ, {
            "ARGOCD_URL": "https://argocd.example.com",
            "ARGOCD_USERNAME": "admin",
            "ARGOCD_PASSWORD": "secret",
        }):
            client = _get_client()
            assert client._username == "admin"
            assert client._password == "secret"
            assert client.auth_token == ""

    def test_client_verify_ssl_false(self):
        from code_agents.routers.argocd import _get_client
        with patch.dict(os.environ, {
            "ARGOCD_URL": "https://argocd.example.com",
            "ARGOCD_USERNAME": "admin",
            "ARGOCD_PASSWORD": "secret",
            "ARGOCD_VERIFY_SSL": "false",
        }):
            client = _get_client()
            assert client.base_url == "https://argocd.example.com"
            assert client.verify_ssl is False


class TestArgoCDRouterEndpoints:
    """Test ArgoCD router endpoint handlers."""

    @patch("code_agents.routers.argocd._get_client")
    def test_get_app_status(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_app_status = AsyncMock(return_value={
            "sync_status": "Synced",
            "health_status": "Healthy",
        })
        mock_get_client.return_value = mock_client
        result = asyncio.run(
            __import__("code_agents.routers.argocd", fromlist=["get_app_status"]).get_app_status("my-app")
        )
        assert result["sync_status"] == "Synced"

    @patch("code_agents.routers.argocd._get_client")
    def test_get_app_status_error(self, mock_get_client):
        from code_agents.cicd.argocd_client import ArgoCDError
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.get_app_status = AsyncMock(side_effect=ArgoCDError("API error"))
        mock_get_client.return_value = mock_client
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                __import__("code_agents.routers.argocd", fromlist=["get_app_status"]).get_app_status("my-app")
            )
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_list_pods(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.list_pods = AsyncMock(return_value=[
            {"name": "pod-1", "status": "Running"},
        ])
        mock_get_client.return_value = mock_client
        from code_agents.routers.argocd import list_pods
        result = asyncio.run(list_pods("my-app"))
        assert result["count"] == 1
        assert result["app_name"] == "my-app"

    @patch("code_agents.routers.argocd._get_client")
    def test_get_pod_logs(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_pod_logs = AsyncMock(return_value={
            "logs": "some output",
            "has_errors": False,
            "error_lines": [],
        })
        mock_get_client.return_value = mock_client
        from code_agents.routers.argocd import get_pod_logs
        result = asyncio.run(get_pod_logs("my-app", "pod-1"))
        assert result["has_errors"] is False

    @patch("code_agents.routers.argocd._get_client")
    def test_sync_app(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.sync_app = AsyncMock(return_value={"status": "triggered"})
        mock_get_client.return_value = mock_client
        from code_agents.routers.argocd import sync_app
        result = asyncio.run(sync_app("my-app"))
        assert result["status"] == "triggered"

    @patch("code_agents.routers.argocd._get_client")
    def test_get_history(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_history = AsyncMock(return_value=[
            {"id": 1, "revision": "abc123"},
            {"id": 2, "revision": "def456"},
        ])
        mock_get_client.return_value = mock_client
        from code_agents.routers.argocd import get_history
        result = asyncio.run(get_history("my-app"))
        assert result["count"] == 2

    @patch("code_agents.routers.argocd._get_client")
    def test_rollback_with_previous(self, mock_get_client):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        mock_client = MagicMock()
        mock_client.get_history = AsyncMock(return_value=[
            {"id": 1, "revision": "old"},
            {"id": 2, "revision": "current"},
        ])
        mock_client.rollback = AsyncMock(return_value={"status": "rolled_back"})
        mock_get_client.return_value = mock_client
        req = RollbackRequest(revision="previous")
        result = asyncio.run(rollback_app("my-app", req))
        assert result["status"] == "rolled_back"
        mock_client.rollback.assert_called_once_with(app_name="my-app", revision_id=1)

    @patch("code_agents.routers.argocd._get_client")
    def test_rollback_no_previous_history(self, mock_get_client):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        from fastapi import HTTPException
        mock_client = MagicMock()
        mock_client.get_history = AsyncMock(return_value=[{"id": 1}])
        mock_get_client.return_value = mock_client
        req = RollbackRequest(revision="previous")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(rollback_app("my-app", req))
        assert exc.value.status_code == 422

    @patch("code_agents.routers.argocd._get_client")
    def test_rollback_with_int_revision(self, mock_get_client):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        mock_client = MagicMock()
        mock_client.rollback = AsyncMock(return_value={"status": "ok"})
        mock_get_client.return_value = mock_client
        req = RollbackRequest(revision=5)
        result = asyncio.run(rollback_app("my-app", req))
        mock_client.rollback.assert_called_once_with(app_name="my-app", revision_id=5)

    @patch("code_agents.routers.argocd._get_client")
    def test_wait_for_sync(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.wait_for_sync = AsyncMock(return_value={"synced": True})
        mock_get_client.return_value = mock_client
        from code_agents.routers.argocd import wait_for_sync
        result = asyncio.run(wait_for_sync("my-app"))
        assert result["synced"] is True


class TestArgoCDPydanticModels:
    """Test ArgoCD request models."""

    def test_sync_request_defaults(self):
        from code_agents.routers.argocd import SyncRequest
        req = SyncRequest()
        assert req.revision is None

    def test_rollback_request_required(self):
        from code_agents.routers.argocd import RollbackRequest
        req = RollbackRequest(revision=3)
        assert req.revision == 3

    def test_rollback_request_string(self):
        from code_agents.routers.argocd import RollbackRequest
        req = RollbackRequest(revision="previous")
        assert req.revision == "previous"


# ═══════════════════════════════════════════════════════════════════════
# Jira router tests
# ═══════════════════════════════════════════════════════════════════════


class TestJiraGetClient:
    """Test Jira _get_client env resolution."""

    def test_missing_url_raises(self):
        from code_agents.routers.jira import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {"JIRA_URL": ""}):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert exc.value.status_code == 503

    def test_client_created(self):
        from code_agents.routers.jira import _get_client
        with patch.dict(os.environ, {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "api-token-123",
        }):
            client = _get_client()
            assert client.base_url == "https://jira.example.com"


class TestJiraRouterEndpoints:
    """Test Jira router endpoint handlers."""

    @patch("code_agents.routers.jira._get_client")
    def test_get_issue(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value={
            "key": "PROJ-123",
            "summary": "Test issue",
        })
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import get_issue
        result = asyncio.run(get_issue("PROJ-123"))
        assert result["key"] == "PROJ-123"

    @patch("code_agents.routers.jira._get_client")
    def test_get_issue_error(self, mock_get_client):
        from code_agents.cicd.jira_client import JiraError
        from fastapi import HTTPException
        mock_client = MagicMock()
        err = JiraError("Not found", status_code=404)
        mock_client.get_issue = AsyncMock(side_effect=err)
        mock_get_client.return_value = mock_client
        from code_agents.routers import jira as jira_router
        # Re-bind JiraError so the except clause catches our mock's exception
        jira_router.JiraError = JiraError
        with pytest.raises(HTTPException) as exc:
            asyncio.run(jira_router.get_issue("PROJ-999"))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.jira._get_client")
    def test_search_issues(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(return_value=[{"key": "PROJ-1"}])
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import search_issues, JqlSearchRequest
        req = JqlSearchRequest(jql="project = PROJ", max_results=10)
        result = asyncio.run(search_issues(req))
        assert len(result) == 1

    @patch("code_agents.routers.jira._get_client")
    def test_create_issue(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.create_issue = AsyncMock(return_value={"key": "PROJ-NEW"})
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import create_issue, CreateIssueRequest
        req = CreateIssueRequest(project="PROJ", summary="New task")
        result = asyncio.run(create_issue(req))
        assert result["key"] == "PROJ-NEW"

    @patch("code_agents.routers.jira._get_client")
    def test_add_comment(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.add_comment = AsyncMock(return_value={"id": "12345"})
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import add_comment, CommentRequest
        req = CommentRequest(body="This is a comment")
        result = asyncio.run(add_comment("PROJ-123", req))
        assert result["id"] == "12345"

    @patch("code_agents.routers.jira._get_client")
    def test_get_transitions(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_transitions = AsyncMock(return_value=[
            {"id": "31", "name": "In Progress"},
        ])
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import get_transitions
        result = asyncio.run(get_transitions("PROJ-123"))
        assert len(result) == 1

    @patch("code_agents.routers.jira._get_client")
    def test_transition_issue(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.transition_issue = AsyncMock(return_value={"status": "done"})
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import transition_issue, TransitionRequest
        req = TransitionRequest(transition_id="31", comment="Moving to done")
        result = asyncio.run(transition_issue("PROJ-123", req))
        assert result["status"] == "done"

    @patch("code_agents.routers.jira._get_client")
    def test_get_confluence_page(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_confluence_page = AsyncMock(return_value={
            "id": "page-1",
            "title": "Test Page",
        })
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import get_confluence_page
        result = asyncio.run(get_confluence_page("page-1"))
        assert result["title"] == "Test Page"

    @patch("code_agents.routers.jira._get_client")
    def test_search_confluence(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.search_confluence = AsyncMock(return_value=[{"title": "HLD"}])
        mock_get_client.return_value = mock_client
        from code_agents.routers.jira import search_confluence, CqlSearchRequest
        req = CqlSearchRequest(cql="space = 'TEAM' and title ~ 'HLD'")
        result = asyncio.run(search_confluence(req))
        assert len(result) == 1


class TestJiraPydanticModels:
    """Test Jira request models."""

    def test_jql_search_defaults(self):
        from code_agents.routers.jira import JqlSearchRequest
        req = JqlSearchRequest(jql="project = PROJ")
        assert req.max_results == 50

    def test_create_issue_defaults(self):
        from code_agents.routers.jira import CreateIssueRequest
        req = CreateIssueRequest(project="PROJ", summary="Test")
        assert req.issue_type == "Task"
        assert req.description == ""

    def test_transition_request(self):
        from code_agents.routers.jira import TransitionRequest
        req = TransitionRequest(transition_id="31")
        assert req.comment is None


# ═══════════════════════════════════════════════════════════════════════
# MCP router tests
# ═══════════════════════════════════════════════════════════════════════


class TestMCPRouterEndpoints:
    """Test MCP router endpoint handlers."""

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_list_servers(self, mock_load_config):
        mock_server = MagicMock()
        mock_server.name = "test-server"
        mock_server.is_stdio = True
        mock_server.command = "npx server"
        mock_server.url = ""
        mock_server.agents = ["code-writer"]
        mock_load_config.return_value = {"test-server": mock_server}
        from code_agents.routers.mcp import list_servers, _active_servers
        _active_servers.clear()
        result = asyncio.run(list_servers())
        assert len(result) == 1
        assert result[0].name == "test-server"
        assert result[0].running is False

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_list_servers_marks_active(self, mock_load_config):
        mock_server = MagicMock()
        mock_server.name = "active-server"
        mock_server.is_stdio = True
        mock_server.command = "npx server"
        mock_server.url = ""
        mock_server.agents = []
        mock_load_config.return_value = {"active-server": mock_server}
        from code_agents.routers.mcp import list_servers, _active_servers
        _active_servers["active-server"] = mock_server
        result = asyncio.run(list_servers())
        assert result[0].running is True
        _active_servers.clear()

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_get_server_tools_not_found(self, mock_load_config):
        from fastapi import HTTPException
        mock_load_config.return_value = {}
        from code_agents.routers.mcp import get_server_tools
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_server_tools("nonexistent"))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_invoke_tool_not_found(self, mock_load_config):
        from fastapi import HTTPException
        mock_load_config.return_value = {}
        from code_agents.routers.mcp import invoke_tool, ToolCallRequest, _active_servers
        _active_servers.clear()
        req = ToolCallRequest(arguments={"key": "value"})
        with pytest.raises(HTTPException) as exc:
            asyncio.run(invoke_tool("nonexistent", "tool", req))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_start_server_not_found(self, mock_load_config):
        from fastapi import HTTPException
        mock_load_config.return_value = {}
        from code_agents.routers.mcp import start_server
        with pytest.raises(HTTPException) as exc:
            asyncio.run(start_server("nonexistent"))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.mcp.load_mcp_config")
    def test_start_server_sse_noop(self, mock_load_config):
        mock_server = MagicMock()
        mock_server.name = "sse-server"
        mock_server.is_stdio = False
        mock_load_config.return_value = {"sse-server": mock_server}
        from code_agents.routers.mcp import start_server
        result = asyncio.run(start_server("sse-server"))
        assert result["status"] == "ok"
        assert "does not need starting" in result["message"]

    def test_stop_server_not_running(self):
        from fastapi import HTTPException
        from code_agents.routers.mcp import stop_server_endpoint, _active_servers
        _active_servers.clear()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(stop_server_endpoint("nonexistent"))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.mcp.stop_server")
    def test_stop_server_running(self, mock_stop):
        from code_agents.routers.mcp import stop_server_endpoint, _active_servers
        mock_server = MagicMock()
        _active_servers["test-server"] = mock_server
        result = asyncio.run(stop_server_endpoint("test-server"))
        assert result["status"] == "ok"
        mock_stop.assert_called_once_with(mock_server)
        assert "test-server" not in _active_servers


class TestMCPPydanticModels:
    """Test MCP request/response models."""

    def test_tool_call_request_defaults(self):
        from code_agents.routers.mcp import ToolCallRequest
        req = ToolCallRequest()
        assert req.arguments == {}

    def test_server_info_defaults(self):
        from code_agents.routers.mcp import ServerInfo
        info = ServerInfo(name="test", transport="stdio")
        assert info.running is False
        assert info.agents == []
        assert info.command == ""

    def test_tool_info_defaults(self):
        from code_agents.routers.mcp import ToolInfo
        info = ToolInfo(name="read_file")
        assert info.description == ""
        assert info.input_schema == {}


# ═══════════════════════════════════════════════════════════════════════
# Atlassian OAuth web router tests
# ═══════════════════════════════════════════════════════════════════════


class TestAtlassianOAuthHelpers:
    """Test Atlassian OAuth web router helper functions."""

    def test_cleanup_states(self):
        from code_agents.routers.atlassian_oauth_web import _cleanup_states, _pending_state
        import time
        # Add an expired state
        _pending_state["expired_state"] = (time.time() - 10, "http://localhost/cb")
        _pending_state["valid_state"] = (time.time() + 600, "http://localhost/cb")
        _cleanup_states()
        assert "expired_state" not in _pending_state
        assert "valid_state" in _pending_state
        # Cleanup
        _pending_state.pop("valid_state", None)

    def test_public_base_from_env(self):
        from code_agents.routers.atlassian_oauth_web import _public_base
        mock_request = MagicMock()
        mock_request.base_url = "http://localhost:8000/"
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "https://api.example.com"}):
            result = _public_base(mock_request)
            assert result == "https://api.example.com"

    def test_public_base_from_request(self):
        from code_agents.routers.atlassian_oauth_web import _public_base
        mock_request = MagicMock()
        mock_request.base_url = "http://localhost:8000/"
        with patch.dict(os.environ, {
            "CODE_AGENTS_PUBLIC_BASE_URL": "",
            "ATLASSIAN_OAUTH_PUBLIC_BASE_URL": "",
        }):
            result = _public_base(mock_request)
            assert result == "http://localhost:8000"

    def test_require_oauth_config_missing_client(self):
        from code_agents.routers.atlassian_oauth_web import _require_oauth_config
        from fastapi import HTTPException
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "secret",
        }):
            with pytest.raises(HTTPException) as exc:
                _require_oauth_config()
            assert exc.value.status_code == 500

    def test_require_oauth_config_missing_scopes(self):
        from code_agents.routers.atlassian_oauth_web import _require_oauth_config
        from fastapi import HTTPException
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "secret",
            "ATLASSIAN_OAUTH_SCOPES": "",
        }):
            with pytest.raises(HTTPException) as exc:
                _require_oauth_config()
            assert exc.value.status_code == 500

    def test_require_oauth_config_success(self):
        from code_agents.routers.atlassian_oauth_web import _require_oauth_config
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_CLIENT_ID": "client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "secret",
            "ATLASSIAN_OAUTH_SCOPES": "read:jira-work offline_access",
        }):
            cid, sec, scopes = _require_oauth_config()
            assert cid == "client-id"
            assert sec == "secret"
            assert "read:jira-work" in scopes

    def test_success_redirect_url_empty(self):
        from code_agents.routers.atlassian_oauth_web import _success_redirect_url
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_SUCCESS_REDIRECT": ""}):
            assert _success_redirect_url() is None

    def test_success_redirect_url_set(self):
        from code_agents.routers.atlassian_oauth_web import _success_redirect_url
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_SUCCESS_REDIRECT": "https://chat.example.com"}):
            assert _success_redirect_url() == "https://chat.example.com"

    def test_open_webui_public_url_empty(self):
        from code_agents.routers.atlassian_oauth_web import _open_webui_public_url
        with patch.dict(os.environ, {"OPEN_WEBUI_PUBLIC_URL": "", "OPEN_WEBUI_URL": ""}):
            assert _open_webui_public_url() is None

    def test_open_webui_public_url_set(self):
        from code_agents.routers.atlassian_oauth_web import _open_webui_public_url
        with patch.dict(os.environ, {"OPEN_WEBUI_PUBLIC_URL": "http://localhost:8080"}):
            assert _open_webui_public_url() == "http://localhost:8080"

    def test_oauth_callback_with_error(self):
        from code_agents.routers.atlassian_oauth_web import oauth_callback
        mock_request = MagicMock()
        result = oauth_callback(mock_request, error="access_denied", error_description="User denied")
        assert result.status_code == 400
        assert "User denied" in result.body.decode()

    def test_oauth_callback_missing_code(self):
        from code_agents.routers.atlassian_oauth_web import oauth_callback
        from fastapi import HTTPException
        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc:
            oauth_callback(mock_request, code=None, state=None)
        assert exc.value.status_code == 400

    def test_oauth_callback_invalid_state(self):
        from code_agents.routers.atlassian_oauth_web import oauth_callback, _pending_state
        from fastapi import HTTPException
        mock_request = MagicMock()
        _pending_state.clear()
        with pytest.raises(HTTPException) as exc:
            oauth_callback(mock_request, code="test-code", state="invalid-state")
        assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Atlassian OAuth module tests
# ═══════════════════════════════════════════════════════════════════════


class TestAtlassianOAuth:
    """Test atlassian_oauth.py helper functions."""

    def test_httpx_verify_default(self):
        from code_agents.domain.atlassian_oauth import _httpx_verify
        with patch.dict(os.environ, {
            "ATLASSIAN_OAUTH_HTTPS_VERIFY": "",
            "CODE_AGENTS_HTTPS_VERIFY": "",
            "SSL_CERT_FILE": "",
            "REQUESTS_CA_BUNDLE": "",
        }):
            result = _httpx_verify()
            # Should return certifi path
            assert isinstance(result, str) and result.endswith(".pem")

    def test_httpx_verify_disabled(self):
        from code_agents.domain.atlassian_oauth import _httpx_verify
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_HTTPS_VERIFY": "false"}):
            assert _httpx_verify() is False

    def test_httpx_verify_disabled_zero(self):
        from code_agents.domain.atlassian_oauth import _httpx_verify
        with patch.dict(os.environ, {"CODE_AGENTS_HTTPS_VERIFY": "0"}):
            assert _httpx_verify() is False

    def test_cache_path_default(self):
        from code_agents.domain.atlassian_oauth import _cache_path
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_TOKEN_CACHE": ""}):
            path = _cache_path()
            assert path.name == ".code-agents-atlassian-oauth.json"

    def test_cache_path_custom(self):
        from code_agents.domain.atlassian_oauth import _cache_path
        with patch.dict(os.environ, {"ATLASSIAN_OAUTH_TOKEN_CACHE": "/tmp/custom-cache.json"}):
            path = _cache_path()
            assert str(path) == "/tmp/custom-cache.json"

    def test_token_expired_none(self):
        from code_agents.domain.atlassian_oauth import _token_expired
        assert _token_expired(None) is True

    def test_token_expired_future(self):
        from code_agents.domain.atlassian_oauth import _token_expired
        import time
        assert _token_expired(time.time() + 3600) is False

    def test_token_expired_past(self):
        from code_agents.domain.atlassian_oauth import _token_expired
        import time
        assert _token_expired(time.time() - 60) is True

    def test_token_expired_within_skew(self):
        from code_agents.domain.atlassian_oauth import _token_expired
        import time
        assert _token_expired(time.time() + 30, skew_seconds=60) is True

    def test_save_and_load_cache(self, tmp_path):
        from code_agents.domain.atlassian_oauth import _save_cache, _load_cache
        cache_file = tmp_path / "cache.json"
        with patch("code_agents.domain.atlassian_oauth._cache_path", return_value=cache_file):
            _save_cache({"access_token": "test-token", "client_id": "cid"})
            loaded = _load_cache()
            assert loaded["access_token"] == "test-token"

    def test_load_cache_missing(self, tmp_path):
        from code_agents.domain.atlassian_oauth import _load_cache
        cache_file = tmp_path / "nonexistent.json"
        with patch("code_agents.domain.atlassian_oauth._cache_path", return_value=cache_file):
            assert _load_cache() is None

    def test_clear_token_cache(self, tmp_path):
        from code_agents.domain.atlassian_oauth import _save_cache, clear_token_cache
        cache_file = tmp_path / "cache.json"
        with patch("code_agents.domain.atlassian_oauth._cache_path", return_value=cache_file):
            _save_cache({"access_token": "tok"})
            assert cache_file.is_file()
            clear_token_cache()
            assert not cache_file.is_file()

    def test_build_authorize_url(self):
        from code_agents.domain.atlassian_oauth import build_authorize_url
        url = build_authorize_url(
            client_id="test-client",
            redirect_uri="http://localhost:8766/callback",
            scope="read:jira-work offline_access",
            state="random-state",
        )
        assert "auth.atlassian.com" in url
        assert "test-client" in url
        assert "random-state" in url

    def test_parse_redirect_uri_valid(self):
        from code_agents.domain.atlassian_oauth import _parse_redirect_uri
        full, host, port, path = _parse_redirect_uri("http://127.0.0.1:8766/callback")
        assert host == "127.0.0.1"
        assert port == 8766
        assert path == "/callback"

    def test_parse_redirect_uri_invalid_scheme(self):
        from code_agents.domain.atlassian_oauth import _parse_redirect_uri
        with pytest.raises(ValueError, match="http"):
            _parse_redirect_uri("ftp://localhost:8766/callback")

    def test_parse_redirect_uri_local_no_port(self):
        from code_agents.domain.atlassian_oauth import _parse_redirect_uri
        with pytest.raises(ValueError, match="explicit port"):
            _parse_redirect_uri("http://127.0.0.1/callback")

    def test_persist_tokens(self, tmp_path):
        from code_agents.domain.atlassian_oauth import _persist_tokens
        cache_file = tmp_path / "cache.json"
        with patch("code_agents.domain.atlassian_oauth._cache_path", return_value=cache_file):
            result = _persist_tokens("cid", {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "scope": "read:jira-work",
            }, previous_refresh=None)
            assert result["access_token"] == "at"
            assert result["refresh_token"] == "rt"
            assert result["expires_at"] is not None

    def test_persist_tokens_preserves_previous_refresh(self, tmp_path):
        from code_agents.domain.atlassian_oauth import _persist_tokens
        cache_file = tmp_path / "cache.json"
        with patch("code_agents.domain.atlassian_oauth._cache_path", return_value=cache_file):
            result = _persist_tokens("cid", {
                "access_token": "at2",
            }, previous_refresh="old-refresh")
            assert result["refresh_token"] == "old-refresh"
