"""Coverage tests for chat_slash_ops.py — covers missing lines from coverage_run.json.

Missing lines: 119-120,175-177,221-260,271-274,282-283,306-318,390-391,
413-414,419-422,431-432,536-552
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from code_agents.chat.chat_slash_ops import _handle_operations


# ---------------------------------------------------------------------------
# Lines 119-120: /repo — not a git repo, add_repo raises ValueError
# ---------------------------------------------------------------------------


class TestRepoNotGitRepo:
    def test_repo_current_path_not_git(self, capsys):
        """Lines 119-120: current repo_path raises ValueError on add_repo."""
        rm = MagicMock()
        rm.repos = {}  # empty → triggers add_repo
        rm.add_repo.side_effect = ValueError("Not a git repo")
        rm.list_repos.return_value = []
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "", {"repo_path": "/bad/path"}, "http://localhost:8000")
        # Should not crash; shows "No repos" message
        output = capsys.readouterr().out
        assert "No repos" in output


# ---------------------------------------------------------------------------
# Lines 175-177: /repo remove — not found but other repos available
# ---------------------------------------------------------------------------


class TestRepoRemoveNotFoundWithAvailable:
    def test_remove_not_found_shows_available(self, capsys):
        """Lines 175-177: remove non-existent shows available repos."""
        rm = MagicMock()
        rm.repos = {"my-app": True}
        rm.remove_repo.return_value = False
        ctx = MagicMock()
        ctx.name = "my-app"
        rm.list_repos.return_value = [ctx]
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "remove nonexistent", {"repo_path": "/r"}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "not found" in output
        assert "my-app" in output

    def test_remove_raises_value_error(self, capsys):
        """Line 177: remove_repo raises ValueError."""
        rm = MagicMock()
        rm.repos = {"x": True}
        rm.remove_repo.side_effect = ValueError("Cannot remove active repo")
        with patch("code_agents.domain.repo_manager.get_repo_manager", return_value=rm):
            _handle_operations("/repo", "remove x", {"repo_path": "/r"}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Cannot remove" in output


# ---------------------------------------------------------------------------
# Lines 221-260: /endpoints run — full path with cached data and failures
# ---------------------------------------------------------------------------


class TestEndpointsRun:
    def test_endpoints_run_all_with_cache(self, capsys):
        """Lines 221-260: /endpoints run with cached endpoints."""
        cached = {
            "repo_name": "my-app",
            "rest_endpoints": [{"method": "GET", "path": "/health", "controller": "HC"}],
            "grpc_services": [],
            "kafka_listeners": [],
        }
        ep_config = {"base_url": "http://localhost:8080", "auth_header": "", "timeout": 5}
        run_results = [{"endpoint": "/health", "passed": True, "status": 200}]

        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=cached), \
             patch("code_agents.cicd.endpoint_scanner.load_endpoint_config", return_value=ep_config), \
             patch("code_agents.cicd.endpoint_scanner.ScanResult") as MockSR, \
             patch("code_agents.cicd.endpoint_scanner.RestEndpoint"), \
             patch("code_agents.cicd.endpoint_scanner.GrpcService"), \
             patch("code_agents.cicd.endpoint_scanner.KafkaListener"), \
             patch("code_agents.cicd.endpoint_scanner.run_all_endpoints", return_value=run_results), \
             patch("code_agents.cicd.endpoint_scanner.format_run_report", return_value="All passed"):
            mock_sr = MagicMock()
            mock_sr.total = 1
            MockSR.return_value = mock_sr
            _handle_operations("/endpoints", "run", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "All passed" in output

    def test_endpoints_run_with_failures(self, capsys):
        """Lines 255-271: /endpoints run with failures feeds report to agent."""
        cached = {
            "repo_name": "my-app",
            "rest_endpoints": [{"method": "GET", "path": "/api", "controller": "C"}],
            "grpc_services": [],
            "kafka_listeners": [],
        }
        ep_config = {"base_url": "http://localhost:8080", "auth_header": "", "timeout": 5}
        run_results = [
            {"endpoint": "/api", "passed": False, "status": 500},
        ]

        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=cached), \
             patch("code_agents.cicd.endpoint_scanner.load_endpoint_config", return_value=ep_config), \
             patch("code_agents.cicd.endpoint_scanner.ScanResult") as MockSR, \
             patch("code_agents.cicd.endpoint_scanner.RestEndpoint"), \
             patch("code_agents.cicd.endpoint_scanner.GrpcService"), \
             patch("code_agents.cicd.endpoint_scanner.KafkaListener"), \
             patch("code_agents.cicd.endpoint_scanner.run_all_endpoints", return_value=run_results), \
             patch("code_agents.cicd.endpoint_scanner.format_run_report", return_value="1 failed"):
            mock_sr = MagicMock()
            mock_sr.total = 1
            MockSR.return_value = mock_sr
            result = _handle_operations("/endpoints", "run", state, "http://localhost:8000")
        assert result == "exec_feedback"
        assert "failed" in state["_exec_feedback"]["output"]

    def test_endpoints_run_no_cache_scans_first(self, capsys):
        """Lines 239-242: /endpoints run with no cache → scan first."""
        ep_config = {"base_url": "http://localhost:8080", "auth_header": "", "timeout": 5}
        mock_result = MagicMock()
        mock_result.total = 0

        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=None), \
             patch("code_agents.cicd.endpoint_scanner.load_endpoint_config", return_value=ep_config), \
             patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result):
            _handle_operations("/endpoints", "run rest", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No endpoints" in output or "No cached" in output

    def test_endpoints_run_no_cache_scan_finds(self, capsys):
        """Lines 241-242: scan finds endpoints then runs them."""
        ep_config = {"base_url": "http://localhost:8080", "auth_header": "", "timeout": 5}
        mock_result = MagicMock()
        mock_result.total = 1
        run_results = [{"endpoint": "/api", "passed": True, "status": 200}]

        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=None), \
             patch("code_agents.cicd.endpoint_scanner.load_endpoint_config", return_value=ep_config), \
             patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result), \
             patch("code_agents.cicd.endpoint_scanner.save_cache"), \
             patch("code_agents.cicd.endpoint_scanner.run_all_endpoints", return_value=run_results), \
             patch("code_agents.cicd.endpoint_scanner.format_run_report", return_value="All passed"):
            _handle_operations("/endpoints", "run all", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "All passed" in output


# ---------------------------------------------------------------------------
# Lines 282-283: /endpoints list — no cache, scan finds some
# ---------------------------------------------------------------------------


class TestEndpointsListScanFinds:
    def test_endpoints_list_no_cache_scan_finds(self, capsys):
        """Lines 282-283: no cache → scan finds endpoints → reload cache."""
        mock_result = MagicMock()
        mock_result.total = 2
        cached = {
            "repo_name": "my-app",
            "summary": "2 REST",
            "rest_endpoints": [{"method": "GET", "path": "/api", "controller": "C"}],
            "grpc_services": [],
            "kafka_listeners": [],
        }

        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", side_effect=[None, cached]), \
             patch("code_agents.cicd.endpoint_scanner.scan_all", return_value=mock_result), \
             patch("code_agents.cicd.endpoint_scanner.save_cache"):
            _handle_operations("/endpoints", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "my-app" in output


# ---------------------------------------------------------------------------
# Lines 306-318: /endpoints list — grpc and kafka sections
# ---------------------------------------------------------------------------


class TestEndpointsListSections:
    def test_endpoints_list_grpc(self, capsys):
        """Lines 306-311: /endpoints grpc section."""
        cached = {
            "repo_name": "my-app",
            "summary": "1 gRPC",
            "rest_endpoints": [],
            "grpc_services": [{"service_name": "PaymentService", "methods": [
                {"name": "ProcessPayment", "request_type": "PayReq", "response_type": "PayResp"}
            ]}],
            "kafka_listeners": [],
        }
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=cached):
            _handle_operations("/endpoints", "grpc", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "PaymentService" in output
        assert "ProcessPayment" in output

    def test_endpoints_list_kafka(self, capsys):
        """Lines 314-318: /endpoints kafka section."""
        cached = {
            "repo_name": "my-app",
            "summary": "1 Kafka",
            "rest_endpoints": [],
            "grpc_services": [],
            "kafka_listeners": [{"topic": "payment-events", "group": "consumer-1", "file": "PaymentListener.java"}],
        }
        state = {"repo_path": "/repo"}
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=cached):
            _handle_operations("/endpoints", "kafka", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "payment-events" in output
        assert "consumer-1" in output


# ---------------------------------------------------------------------------
# Lines 390-391: /voice — edit mode EOFError
# ---------------------------------------------------------------------------


class TestVoiceEditEOF:
    def test_voice_edit_eof(self, capsys):
        """Lines 390-391: EOFError during voice edit."""
        state = {}
        with patch("code_agents.ui.voice_input.is_available", return_value=True), \
             patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="hello world"), \
             patch("builtins.input", side_effect=["edit", EOFError]):
            result = _handle_operations("/voice", "", state, "http://localhost:8000")
        assert result is None


# ---------------------------------------------------------------------------
# Lines 413-414, 419-422: /plan proposed — auto_edit_after_plan flow
# ---------------------------------------------------------------------------


class TestPlanAutoEditAfterPlan:
    def test_plan_approve_with_auto_edit(self, capsys):
        """Lines 419-422: approve plan with _auto_edit_after_plan → switch to edit mode."""
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        active.title = "My plan"
        pm = MagicMock()
        pm.active_plan = active
        pm.format_plan.return_value = "Plan display"
        pm.build_plan_approval_questionnaire.return_value = "Choose:"

        state = {"_auto_edit_after_plan": True}
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm), \
             patch("builtins.input", return_value="1"), \
             patch("code_agents.chat.chat_input.set_mode") as mock_set_mode:
            _handle_operations("/plan", "", state, "http://localhost:8000")
        pm.approve.assert_called_once_with(ApprovalMode.AUTO_ACCEPT)
        mock_set_mode.assert_called_once_with("edit")
        assert "_auto_edit_after_plan" not in state

    def test_plan_approve_eof(self, capsys):
        """Lines 413-414: EOFError during plan approval input."""
        from code_agents.agent_system.plan_manager import PlanStatus, ApprovalMode
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = MagicMock()
        pm.active_plan = active
        pm.format_plan.return_value = "Plan"
        pm.build_plan_approval_questionnaire.return_value = "Choose:"

        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm), \
             patch("builtins.input", side_effect=EOFError):
            _handle_operations("/plan", "", {}, "http://localhost:8000")
        # Empty choice defaults to "1" (auto accept)
        pm.approve.assert_called_once_with(ApprovalMode.AUTO_ACCEPT)

    def test_plan_proposed_feedback_eof(self, capsys):
        """Lines 431-432: EOFError during feedback input."""
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.PROPOSED
        pm = MagicMock()
        pm.active_plan = active
        pm.format_plan.return_value = "Plan"
        pm.build_plan_approval_questionnaire.return_value = "Choose:"

        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm), \
             patch("builtins.input", side_effect=["3", EOFError]):
            _handle_operations("/plan", "", {}, "http://localhost:8000")
        # Empty feedback → no edit_plan call
        pm.edit_plan.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 536-552: /plan edit — legacy file edit paths
# ---------------------------------------------------------------------------


class TestPlanEditLegacy:
    def test_plan_edit_no_feedback_active_plan_legacy(self, capsys):
        """Lines 536-543: active plan + empty feedback → legacy file edit."""
        from code_agents.agent_system.plan_manager import PlanStatus
        active = MagicMock()
        active.status = PlanStatus.EXECUTING
        pm = MagicMock()
        pm.active_plan = active

        plan_data = {"title": "Plan", "path": "/tmp/plan.yaml"}
        state = {"_last_plan_id": "p1"}

        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm), \
             patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data), \
             patch.dict(os.environ, {"EDITOR": "echo"}), \
             patch("subprocess.run") as mock_sp:
            _handle_operations("/plan", "edit", state, "http://localhost:8000")
        mock_sp.assert_called_once_with(["echo", "/tmp/plan.yaml"])

    def test_plan_edit_no_feedback_no_active_no_plan_id(self, capsys):
        """Lines 543-544: no active plan + empty feedback + no plan_id."""
        pm = MagicMock()
        pm.active_plan = MagicMock()
        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "edit", {}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "edit" in output.lower() or "Usage" in output or "feedback" in output.lower()

    def test_plan_edit_no_active_plan_legacy_file(self, capsys):
        """Lines 546-552: no active_plan → legacy file edit with plan_active."""
        pm = MagicMock()
        pm.active_plan = None

        plan_data = {"title": "Legacy Plan", "path": "/tmp/legacy.yaml"}
        state = {"plan_active": "p2"}

        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm), \
             patch("code_agents.agent_system.plan_manager.load_plan", return_value=plan_data), \
             patch.dict(os.environ, {"EDITOR": "echo"}), \
             patch("subprocess.run") as mock_sp:
            _handle_operations("/plan", "edit", state, "http://localhost:8000")
        mock_sp.assert_called_once_with(["echo", "/tmp/legacy.yaml"])

    def test_plan_edit_no_active_plan_no_id(self, capsys):
        """Lines 553-554: no active plan, no plan_id → "No plan to edit"."""
        pm = MagicMock()
        pm.active_plan = None

        with patch("code_agents.agent_system.plan_manager.get_plan_manager", return_value=pm):
            _handle_operations("/plan", "edit", {}, "http://localhost:8000")
        assert "No plan" in capsys.readouterr().out


class TestPermissions:
    """Tests for /permissions command."""

    def test_permissions_shows_mode(self, capsys):
        """/permissions shows auto-run and superpower status."""
        state = {"agent": "code-writer", "superpower": False}
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config", return_value={"allow": [], "block": []}), \
             patch("code_agents.chat.chat_commands._load_global_autorun_config", return_value={"allow": ["ls "], "block": ["rm "]}), \
             patch.dict(os.environ, {"CODE_AGENTS_AUTO_RUN": "true"}):
            _handle_operations("/permissions", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Permissions" in output
        assert "Auto-run" in output
        assert "Superpower" in output

    def test_permissions_with_agent_rules(self, capsys):
        """/permissions shows agent-specific allow/block rules."""
        state = {"agent": "jenkins-cicd", "superpower": True}
        with patch("code_agents.chat.chat_commands._load_agent_autorun_config",
                    return_value={"allow": ["ls ", "curl "], "block": ["rm ", "git push"]}), \
             patch("code_agents.chat.chat_commands._load_global_autorun_config",
                    return_value={"allow": ["ls "], "block": ["rm "]}):
            _handle_operations("/permissions", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "jenkins-cicd" in output
        assert "curl" in output

    def test_permissions_no_agent(self, capsys):
        """/permissions with no agent selected."""
        state = {}
        _handle_operations("/permissions", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "No agent selected" in output
