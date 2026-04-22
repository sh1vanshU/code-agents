"""Coverage completion tests for routers: jira, git_ops, jenkins, completions,
argocd, pipeline, testing, mcp, elasticsearch."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════════
# Jira Router — missing lines: error paths for confluence, transitions
# ═════��═════════════════════════════════════════════════════════════════


class TestJiraRouterMissingCoverage:
    """Cover remaining uncovered lines in jira.py."""

    @patch("code_agents.routers.jira._get_client")
    def test_search_issues_error(self, mock_gc):
        from code_agents.routers.jira import search_issues, JqlSearchRequest
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.search_issues = AsyncMock(side_effect=JiraError("bad jql", status_code=400))
        req = JqlSearchRequest(jql="invalid")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(search_issues(req))
        assert exc.value.status_code == 400

    @patch("code_agents.routers.jira._get_client")
    def test_create_issue_error(self, mock_gc):
        from code_agents.routers.jira import create_issue, CreateIssueRequest
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.create_issue = AsyncMock(side_effect=JiraError("forbidden", status_code=403))
        req = CreateIssueRequest(project="PROJ", summary="Test")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(create_issue(req))
        assert exc.value.status_code == 403

    @patch("code_agents.routers.jira._get_client")
    def test_add_comment_error(self, mock_gc):
        from code_agents.routers.jira import add_comment, CommentRequest
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.add_comment = AsyncMock(side_effect=JiraError("not found", status_code=404))
        req = CommentRequest(body="test comment")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(add_comment("PROJ-999", req))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.jira._get_client")
    def test_get_transitions_error(self, mock_gc):
        from code_agents.routers.jira import get_transitions
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.get_transitions = AsyncMock(side_effect=JiraError("fail"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_transitions("PROJ-1"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jira._get_client")
    def test_transition_issue_error(self, mock_gc):
        from code_agents.routers.jira import transition_issue, TransitionRequest
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.transition_issue = AsyncMock(side_effect=JiraError("transition fail"))
        req = TransitionRequest(transition_id="31")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(transition_issue("PROJ-1", req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jira._get_client")
    def test_transition_issue_with_comment(self, mock_gc):
        from code_agents.routers.jira import transition_issue, TransitionRequest
        mock_gc.return_value.transition_issue = AsyncMock(return_value={"status": "Done"})
        req = TransitionRequest(transition_id="31", comment="Moving to done")
        result = asyncio.run(transition_issue("PROJ-1", req))
        assert result["status"] == "Done"

    @patch("code_agents.routers.jira._get_client")
    def test_get_confluence_page_error(self, mock_gc):
        from code_agents.routers.jira import get_confluence_page
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.get_confluence_page = AsyncMock(side_effect=JiraError("not found", status_code=404))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_confluence_page("12345"))
        assert exc.value.status_code == 404

    @patch("code_agents.routers.jira._get_client")
    def test_search_confluence_error(self, mock_gc):
        from code_agents.routers.jira import search_confluence, CqlSearchRequest
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.search_confluence = AsyncMock(side_effect=JiraError("bad cql"))
        req = CqlSearchRequest(cql="invalid cql")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(search_confluence(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jira._get_client")
    def test_get_issue_no_status_code(self, mock_gc):
        """JiraError with no status_code falls back to 502."""
        from code_agents.routers.jira import get_issue
        from code_agents.cicd.jira_client import JiraError
        mock_gc.return_value.get_issue = AsyncMock(side_effect=JiraError("unknown"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_issue("PROJ-1"))
        assert exc.value.status_code == 502


# ═══════════════════════════════════════════════════════════════════════
# Git Ops Router — missing: push_error, checkout_invalid, log_error, etc.
# ═══════════════════════════════════════════════════════════════════════


class TestGitOpsRouterMissingCoverage:
    @patch("code_agents.routers.git_ops._get_client")
    def test_push_error(self, mock_gc):
        from code_agents.routers.git_ops import push_branch, PushRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.push = AsyncMock(side_effect=GitOpsError("push rejected"))
        req = PushRequest(branch="main")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(push_branch(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_push_invalid_error(self, mock_gc):
        from code_agents.routers.git_ops import push_branch, PushRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.push = AsyncMock(side_effect=GitOpsError("Invalid branch"))
        req = PushRequest(branch="bad;ref")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(push_branch(req))
        assert exc.value.status_code == 422

    @patch("code_agents.routers.git_ops._get_client")
    def test_status_error(self, mock_gc):
        from code_agents.routers.git_ops import get_status
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.status = AsyncMock(side_effect=GitOpsError("git error"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_status())
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_fetch_error(self, mock_gc):
        from code_agents.routers.git_ops import fetch_remote
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.fetch = AsyncMock(side_effect=GitOpsError("fetch failed"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(fetch_remote())
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_log_error_generic(self, mock_gc):
        from code_agents.routers.git_ops import get_log
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.log = AsyncMock(side_effect=GitOpsError("generic error"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_log())
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_log_error_invalid_ref(self, mock_gc):
        from code_agents.routers.git_ops import get_log
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.log = AsyncMock(side_effect=GitOpsError("Invalid ref"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_log("bad ref"))
        assert exc.value.status_code == 422

    @patch("code_agents.routers.git_ops._get_client")
    def test_stash_error(self, mock_gc):
        from code_agents.routers.git_ops import stash_changes, StashRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.stash = AsyncMock(side_effect=GitOpsError("stash failed"))
        req = StashRequest(action="pop")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(stash_changes(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_stage_error(self, mock_gc):
        from code_agents.routers.git_ops import stage_files, AddRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.add = AsyncMock(side_effect=GitOpsError("add failed"))
        req = AddRequest(files=["bad_file"])
        with pytest.raises(HTTPException) as exc:
            asyncio.run(stage_files(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_checkout_generic_error(self, mock_gc):
        from code_agents.routers.git_ops import checkout_branch, CheckoutRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.checkout = AsyncMock(side_effect=GitOpsError("generic error"))
        req = CheckoutRequest(branch="feature")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(checkout_branch(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_checkout_invalid_ref(self, mock_gc):
        from code_agents.routers.git_ops import checkout_branch, CheckoutRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.checkout = AsyncMock(side_effect=GitOpsError("Invalid branch"))
        req = CheckoutRequest(branch="bad;ref")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(checkout_branch(req))
        assert exc.value.status_code == 422

    @patch("code_agents.routers.git_ops._get_client")
    def test_diff_generic_error(self, mock_gc):
        from code_agents.routers.git_ops import get_diff
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.diff = AsyncMock(side_effect=GitOpsError("network error"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_diff("main", "HEAD"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_commit_generic_error(self, mock_gc):
        from code_agents.routers.git_ops import create_commit, CommitRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.commit = AsyncMock(side_effect=GitOpsError("git error"))
        req = CommitRequest(message="test")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(create_commit(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_merge_generic_error(self, mock_gc):
        from code_agents.routers.git_ops import merge_branch, MergeRequest
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.merge = AsyncMock(side_effect=GitOpsError("merge error"))
        req = MergeRequest(branch="feature")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(merge_branch(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.git_ops._get_client")
    def test_current_branch_error(self, mock_gc):
        from code_agents.routers.git_ops import current_branch
        from code_agents.cicd.git_client import GitOpsError
        mock_gc.return_value.current_branch = AsyncMock(side_effect=GitOpsError("detached HEAD"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(current_branch())
        assert exc.value.status_code == 502


# ═══════════════════════════════════════════════════════════════════════
# Jenkins Router — missing: build_and_wait, trigger_build_502 error path,
# queue_lookup_failure, various error handlers
# ═══════════════════════════════════════════════════════════════════════


class TestJenkinsRouterMissingCoverage:
    @patch("code_agents.routers.jenkins._get_client")
    def test_build_and_wait_success(self, mock_gc):
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        from starlette.responses import StreamingResponse
        mock_client = MagicMock()
        mock_client.trigger_and_wait = AsyncMock(return_value={
            "number": 42, "result": "SUCCESS", "build_version": "1.2.3",
        })
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(job_name="my-job", branch="develop")
        result = asyncio.run(trigger_build_and_wait(req))
        # Returns StreamingResponse (newline-delimited JSON)
        assert isinstance(result, StreamingResponse)

    @patch("code_agents.routers.jenkins._get_client")
    def test_build_and_wait_error(self, mock_gc):
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_client = MagicMock()
        mock_client.trigger_and_wait = AsyncMock(side_effect=JenkinsError("build failed"))
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(job_name="my-job")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(trigger_build_and_wait(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_build_and_wait_with_params(self, mock_gc):
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        mock_client = MagicMock()
        mock_client.trigger_and_wait = AsyncMock(return_value={"number": 1, "result": "SUCCESS"})
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(
            job_name="my-job",
            branch="main",
            parameters={"env": "staging"},
        )
        result = asyncio.run(trigger_build_and_wait(req))
        call_kwargs = mock_client.trigger_and_wait.call_args.kwargs
        assert call_kwargs["parameters"]["branch"] == "main"
        assert call_kwargs["parameters"]["env"] == "staging"

    @patch("code_agents.routers.jenkins._get_client")
    def test_build_and_wait_branch_in_params(self, mock_gc):
        """branch param should not override explicit branch in parameters."""
        from code_agents.routers.jenkins import trigger_build_and_wait, TriggerBuildRequest
        mock_client = MagicMock()
        mock_client.trigger_and_wait = AsyncMock(return_value={"number": 1, "result": "SUCCESS"})
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(
            job_name="my-job",
            branch="override-this",
            parameters={"branch": "keep-this"},
        )
        asyncio.run(trigger_build_and_wait(req))
        call_kwargs = mock_client.trigger_and_wait.call_args.kwargs
        assert call_kwargs["parameters"]["branch"] == "keep-this"

    @patch("code_agents.routers.jenkins._get_client")
    def test_trigger_build_queue_lookup_fails(self, mock_gc):
        """Queue lookup failure is silently caught."""
        from code_agents.routers.jenkins import trigger_build, TriggerBuildRequest
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_client = MagicMock()
        mock_client.trigger_build = AsyncMock(return_value={"job_name": "j", "queue_id": 42})
        mock_client.get_build_from_queue = AsyncMock(side_effect=JenkinsError("queue expired"))
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(job_name="j")
        result = asyncio.run(trigger_build(req))
        assert "build_number" not in result

    @patch("code_agents.routers.jenkins._get_client")
    def test_trigger_build_502_error(self, mock_gc):
        from code_agents.routers.jenkins import trigger_build, TriggerBuildRequest
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_client = MagicMock()
        mock_client.trigger_build = AsyncMock(side_effect=JenkinsError("server error", status_code=500))
        mock_gc.return_value = mock_client
        req = TriggerBuildRequest(job_name="j")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(trigger_build(req))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_job_parameters_error(self, mock_gc):
        from code_agents.routers.jenkins import get_job_parameters
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_gc.return_value.get_job_parameters = AsyncMock(side_effect=JenkinsError("not found"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_job_parameters("bad/path"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_build_status_error(self, mock_gc):
        from code_agents.routers.jenkins import get_build_status
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_gc.return_value.get_build_status = AsyncMock(side_effect=JenkinsError("not found"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_build_status("job", 999))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_build_log_error(self, mock_gc):
        from code_agents.routers.jenkins import get_build_log
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_gc.return_value.get_build_log = AsyncMock(side_effect=JenkinsError("not found"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_build_log("job", 999))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_get_last_build_error(self, mock_gc):
        from code_agents.routers.jenkins import get_last_build
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_gc.return_value.get_last_build = AsyncMock(side_effect=JenkinsError("not found"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_last_build("job"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.jenkins._get_client")
    def test_wait_for_build_error(self, mock_gc):
        from code_agents.routers.jenkins import wait_for_build
        from code_agents.cicd.jenkins_client import JenkinsError
        mock_gc.return_value.wait_for_build = AsyncMock(side_effect=JenkinsError("timeout"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(wait_for_build("job", 1))
        assert exc.value.status_code == 502


# ═══════════════════════════════════════════════════════════════════════
# Completions Router — missing: _handle_completions error paths
# ═══════════════════════════════════════════════════════════════════════


class TestCompletionsRouterMissingCoverage:
    def test_handle_completions_empty_messages(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest
        mock_agent = MagicMock()
        mock_agent.name = "test"
        req = CompletionRequest(model="test", messages=[])
        with pytest.raises(HTTPException) as exc:
            asyncio.run(_handle_completions(mock_agent, req))
        assert exc.value.status_code == 400

    def test_handle_completions_non_stream_error_with_process_error(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.backend = "cursor"
        mock_agent.model = "test-model"
        req = CompletionRequest(model="test", messages=[Message(role="user", content="hi")], stream=False)

        # Create a ProcessError-like exception
        pe = MagicMock()
        pe.stderr = "some error output"
        pe.exit_code = 1

        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock, side_effect=Exception("wrapped error")):
            with patch("code_agents.routers.completions.unwrap_process_error", return_value=pe):
                with patch("code_agents.routers.completions.process_error_json_response", return_value={"error": True}) as mock_resp:
                    result = asyncio.run(_handle_completions(mock_agent, req))
        assert result == {"error": True}

    def test_handle_completions_non_stream_error_no_process_error(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.backend = "cursor"
        mock_agent.model = "test-model"
        req = CompletionRequest(model="test", messages=[Message(role="user", content="hi")], stream=False)

        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock, side_effect=RuntimeError("unknown")):
            with patch("code_agents.routers.completions.unwrap_process_error", return_value=None):
                with pytest.raises(RuntimeError, match="unknown"):
                    asyncio.run(_handle_completions(mock_agent, req))

    def test_handle_completions_process_error_empty_stderr(self):
        """ProcessError with empty stderr still logs and returns error response."""
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.backend = "cursor"
        mock_agent.model = "m"
        req = CompletionRequest(model="test", messages=[Message(role="user", content="hi")], stream=False)

        pe = MagicMock()
        pe.stderr = ""
        pe.exit_code = 1

        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock, side_effect=Exception("fail")):
            with patch("code_agents.routers.completions.unwrap_process_error", return_value=pe):
                with patch("code_agents.routers.completions.process_error_json_response", return_value={"err": True}):
                    result = asyncio.run(_handle_completions(mock_agent, req))
        assert result == {"err": True}


# ═══════════════════════════════════════════════════════════════════════
# ArgoCD Router — missing: list_pods error, sync error, wait_for_sync error,
# get_pod_logs with errors
# ═══════════════════════════════════════════════════════════════════════


class TestArgoCDRouterMissingCoverage:
    @patch("code_agents.routers.argocd._get_client")
    def test_list_pods_error(self, mock_gc):
        from code_agents.routers.argocd import list_pods
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.list_pods = AsyncMock(side_effect=ArgoCDError("API error"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(list_pods("my-app"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_get_pod_logs_with_errors(self, mock_gc):
        from code_agents.routers.argocd import get_pod_logs
        mock_gc.return_value.get_pod_logs = AsyncMock(return_value={
            "logs": "ERROR: something failed",
            "has_errors": True,
            "error_lines": ["ERROR: something failed"],
        })
        result = asyncio.run(get_pod_logs("my-app", "pod-1"))
        assert result["has_errors"] is True

    @patch("code_agents.routers.argocd._get_client")
    def test_get_pod_logs_error(self, mock_gc):
        from code_agents.routers.argocd import get_pod_logs
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.get_pod_logs = AsyncMock(side_effect=ArgoCDError("pod not found"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_pod_logs("my-app", "missing-pod"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_sync_app_error(self, mock_gc):
        from code_agents.routers.argocd import sync_app
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.sync_app = AsyncMock(side_effect=ArgoCDError("sync failed"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(sync_app("my-app"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_sync_app_with_revision(self, mock_gc):
        from code_agents.routers.argocd import sync_app, SyncRequest
        mock_gc.return_value.sync_app = AsyncMock(return_value={"status": "syncing"})
        req = SyncRequest(revision="abc123")
        result = asyncio.run(sync_app("my-app", req))
        assert result["status"] == "syncing"

    @patch("code_agents.routers.argocd._get_client")
    def test_get_history_error(self, mock_gc):
        from code_agents.routers.argocd import get_history
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.get_history = AsyncMock(side_effect=ArgoCDError("fail"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_history("my-app"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_wait_for_sync_error(self, mock_gc):
        from code_agents.routers.argocd import wait_for_sync
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.wait_for_sync = AsyncMock(side_effect=ArgoCDError("timeout"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(wait_for_sync("my-app"))
        assert exc.value.status_code == 502

    @patch("code_agents.routers.argocd._get_client")
    def test_rollback_error(self, mock_gc):
        from code_agents.routers.argocd import rollback_app, RollbackRequest
        from code_agents.cicd.argocd_client import ArgoCDError
        mock_gc.return_value.rollback = AsyncMock(side_effect=ArgoCDError("rollback failed"))
        req = RollbackRequest(revision=5)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(rollback_app("my-app", req))
        assert exc.value.status_code == 502


# ═══════════════════════════════════════════════════════════════════════
# Pipeline Router — missing: advance with previous_revision, rollback with no app
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineRouterMissingCoverage:
    @pytest.fixture
    def pipe_client(self):
        from code_agents.routers.pipeline import router as pipeline_router
        app = FastAPI()
        app.include_router(pipeline_router)
        return TestClient(app)

    def test_advance_with_previous_revision(self, pipe_client):
        resp = pipe_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        # Advance step 1 with previous_revision
        resp = pipe_client.post(f"/pipeline/{run_id}/advance", json={
            "details": {"previous_revision": 3}
        })
        assert resp.status_code == 200

    def test_fail_step_before_deploy_no_rollback_recommended(self, pipe_client):
        """Failing before step 4 should not recommend rollback."""
        resp = pipe_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        resp = pipe_client.post(f"/pipeline/{run_id}/fail", json={"error": "test fail"})
        assert resp.status_code == 200
        assert resp.json()["recommended_action"] is None

    def test_fail_not_found(self, pipe_client):
        resp = pipe_client.post("/pipeline/nonexistent/fail", json={"error": "e"})
        assert resp.status_code == 404

    def test_advance_not_found(self, pipe_client):
        resp = pipe_client.post("/pipeline/nonexistent/advance")
        assert resp.status_code == 404

    def test_rollback_not_found(self, pipe_client):
        resp = pipe_client.post("/pipeline/nonexistent/rollback")
        assert resp.status_code == 404

    def test_advance_no_details(self, pipe_client):
        """Advance without details body."""
        resp = pipe_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        resp = pipe_client.post(f"/pipeline/{run_id}/advance")
        assert resp.status_code == 200

    def test_fail_with_details(self, pipe_client):
        resp = pipe_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        resp = pipe_client.post(f"/pipeline/{run_id}/fail", json={
            "error": "boom", "details": {"trace": "stack"}
        })
        assert resp.status_code == 200

    def test_rollback_no_argocd_app(self, pipe_client):
        """Rollback when no ArgoCD app is configured."""
        resp = pipe_client.post("/pipeline/start", json={"branch": "test"})
        run_id = resp.json()["run_id"]
        resp = pipe_client.post(f"/pipeline/{run_id}/rollback")
        assert resp.status_code == 200
        data = resp.json()
        assert "No ArgoCD app" in data["rollback_info"]["instruction"]


# ═══════════════════════════════════════════════════════════════════════
# Testing Router — missing: get_coverage_error, get_coverage_gaps_error,
# run_tests with coverage_threshold
# ═══════════════════════════════════════════════════════════════════════


class TestTestingRouterMissingCoverage:
    @patch("code_agents.routers.testing._get_client")
    def test_get_coverage_error(self, mock_gc):
        from code_agents.routers.testing import get_coverage
        from code_agents.cicd.testing_client import TestingError
        mock_gc.return_value.get_coverage = AsyncMock(side_effect=TestingError("no coverage.xml"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_coverage())
        assert exc.value.status_code == 422

    @patch("code_agents.routers.testing._get_client")
    def test_get_coverage_gaps_error(self, mock_gc):
        from code_agents.routers.testing import get_coverage_gaps
        from code_agents.cicd.testing_client import TestingError
        mock_gc.return_value.get_coverage_gaps = AsyncMock(side_effect=TestingError("diff error"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_coverage_gaps())
        assert exc.value.status_code == 502

    @patch("code_agents.routers.testing._get_client")
    def test_run_tests_with_coverage_threshold(self, mock_gc):
        from code_agents.routers.testing import run_tests, RunTestsRequest
        mock_client = MagicMock()
        mock_client.run_tests = AsyncMock(return_value={
            "passed": True, "total": 5, "passed_count": 5, "failed_count": 0
        })
        mock_gc.return_value = mock_client
        req = RunTestsRequest(coverage_threshold=90.0)
        result = asyncio.run(run_tests(req))
        assert mock_client.coverage_threshold == 90.0

    def test_get_client_uses_env(self, tmp_path):
        from code_agents.routers.testing import _get_client
        with patch.dict(os.environ, {
            "TARGET_REPO_PATH": str(tmp_path),
            "TARGET_TEST_COMMAND": "pytest",
            "TARGET_COVERAGE_THRESHOLD": "85",
        }):
            client = _get_client()
        assert client.repo_path == str(tmp_path)
        assert client.coverage_threshold == 85.0


# ═══════════════════════════════════════════════════════════════════════
# MCP Router — missing: start_server already_running, stop not running
# ═══════════════════════════════════════════════════════════════════════


class TestMcpRouterMissingCoverage:
    @pytest.fixture
    def mcp_client(self):
        from code_agents.routers.mcp import router as mcp_router
        app = FastAPI()
        app.include_router(mcp_router)
        return TestClient(app)

    def test_invoke_tool_sse_server(self, mcp_client):
        """Invoke tool on SSE server (not stdio)."""
        from code_agents.routers.mcp import _active_servers
        from code_agents.integrations.mcp_client import MCPServer
        _active_servers.clear()

        mock_server = MCPServer(name="sse-test", url="http://localhost:3001/sse")
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"sse-test": mock_server}):
            with patch("code_agents.routers.mcp.call_tool", new_callable=AsyncMock, return_value="result"):
                resp = mcp_client.post("/mcp/servers/sse-test/tools/my_tool", json={"arguments": {}})
        assert resp.status_code == 200
        assert resp.json()["result"] == "result"
        _active_servers.clear()

    def test_invoke_tool_null_result(self, mcp_client):
        from code_agents.routers.mcp import _active_servers
        from code_agents.integrations.mcp_client import MCPServer
        _active_servers.clear()

        mock_server = MCPServer(name="test", url="http://localhost:3001/sse")
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test": mock_server}):
            with patch("code_agents.routers.mcp.call_tool", new_callable=AsyncMock, return_value=None):
                resp = mcp_client.post("/mcp/servers/test/tools/bad_tool", json={"arguments": {}})
        assert resp.status_code == 502
        _active_servers.clear()

    def test_start_server_already_running(self, mcp_client):
        from code_agents.routers.mcp import _active_servers
        from code_agents.integrations.mcp_client import MCPServer
        mock_proc = MagicMock()
        mock_proc.pid = 42
        srv = MCPServer(name="test", command="npx")
        srv._process = mock_proc
        _active_servers["test"] = srv

        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"test": srv}):
            resp = mcp_client.post("/mcp/servers/test/start")
        assert resp.status_code == 200
        assert "already running" in resp.json()["message"]
        _active_servers.clear()

    def test_start_server_sse(self, mcp_client):
        from code_agents.routers.mcp import _active_servers
        from code_agents.integrations.mcp_client import MCPServer
        _active_servers.clear()
        srv = MCPServer(name="sse-srv", url="http://localhost/sse")
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"sse-srv": srv}):
            resp = mcp_client.post("/mcp/servers/sse-srv/start")
        assert resp.status_code == 200
        assert "does not need starting" in resp.json()["message"]
        _active_servers.clear()

    def test_start_server_failure(self, mcp_client):
        from code_agents.routers.mcp import _active_servers
        from code_agents.integrations.mcp_client import MCPServer
        _active_servers.clear()
        srv = MCPServer(name="fail", command="bad_cmd")
        with patch("code_agents.routers.mcp.load_mcp_config", return_value={"fail": srv}):
            with patch("code_agents.routers.mcp.start_stdio_server", new_callable=AsyncMock, return_value=None):
                resp = mcp_client.post("/mcp/servers/fail/start")
        assert resp.status_code == 500
        _active_servers.clear()


# ═══════════════════════════════════════════════════════════════════════
# Elasticsearch Router — missing: search error path with status_code
# ═══════════════════════════════════════════════════════════════════════


class TestElasticsearchRouterMissingCoverage:
    @pytest.fixture
    def es_client(self):
        from code_agents.routers.elasticsearch import router as es_router
        app = FastAPI()
        app.include_router(es_router)
        return TestClient(app)

    def test_search_error_with_known_status(self, es_client):
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        with patch("code_agents.routers.elasticsearch._enabled", return_value=True):
            with patch("code_agents.routers.elasticsearch.client_from_env", return_value=MagicMock()):
                with patch("code_agents.routers.elasticsearch.search", side_effect=ElasticsearchConnError("bad request", status_code=400)):
                    resp = es_client.post("/elasticsearch/search", json={"index": "*", "body": {}})
        assert resp.status_code == 400

    def test_search_error_unknown_status(self, es_client):
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        with patch("code_agents.routers.elasticsearch._enabled", return_value=True):
            with patch("code_agents.routers.elasticsearch.client_from_env", return_value=MagicMock()):
                with patch("code_agents.routers.elasticsearch.search", side_effect=ElasticsearchConnError("timeout", status_code=None)):
                    resp = es_client.post("/elasticsearch/search", json={"index": "*", "body": {}})
        assert resp.status_code == 502

    def test_cluster_info_error(self, es_client):
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        with patch("code_agents.routers.elasticsearch._enabled", return_value=True):
            with patch("code_agents.routers.elasticsearch.client_from_env", return_value=MagicMock()):
                with patch("code_agents.routers.elasticsearch.info", side_effect=ElasticsearchConnError("fail", status_code=503)):
                    resp = es_client.get("/elasticsearch/info")
        assert resp.status_code == 503

    def test_cluster_info_error_no_status(self, es_client):
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        with patch("code_agents.routers.elasticsearch._enabled", return_value=True):
            with patch("code_agents.routers.elasticsearch.client_from_env", return_value=MagicMock()):
                with patch("code_agents.routers.elasticsearch.info", side_effect=ElasticsearchConnError("fail")):
                    resp = es_client.get("/elasticsearch/info")
        assert resp.status_code == 502

    def test_search_error_with_server_status(self, es_client):
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        with patch("code_agents.routers.elasticsearch._enabled", return_value=True):
            with patch("code_agents.routers.elasticsearch.client_from_env", return_value=MagicMock()):
                with patch("code_agents.routers.elasticsearch.search", side_effect=ElasticsearchConnError("server error", status_code=500)):
                    resp = es_client.post("/elasticsearch/search", json={"index": "*", "body": {}})
        # 500 is not in (400, 401, 403, 404), so falls back to 502
        assert resp.status_code == 502
