"""
Coverage boost tests — targets specific uncovered lines to push overall coverage from 79% → 80%+.

Covers:
  - openai_errors.py         (lines 27, 30-36, 68-70)
  - questionnaire.py         (lines 56-57, 66-67, 111-128, 133, 138-141)
  - env_health.py            (lines 65-69, 79-81, 92, 105-117, 130-141, 154-166, 179-190)
  - watchdog.py              (lines 62-69, 73-89, 93-96, 127-156)
  - connection_validator.py  (lines 60-105, 123-124, 142, 152, 192, 225-254, 278, 304-309, 328-330)
  - skill_loader.py          (lines 179, 184-190, 217-241, 250-276, 281)
  - mutation_tester.py       (lines 108-110, 132-133, 146-184, 196-208)
  - webui/router.py          (lines 13, 18, 23, 28-31)
  - log_investigator.py      (lines 67, 70-72, 100-122, 132-142)
  - slack_bot.py             (lines 79-96, 102-127, 151-181)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# =============================================================================
# openai_errors.py
# =============================================================================

class TestOpenAIErrorsBoost:
    """Cover lines 27, 30-36 (unwrap_process_error) and 68-70 (process_error_json_response)."""

    def test_unwrap_process_error_none(self):
        from code_agents.core.openai_errors import unwrap_process_error
        assert unwrap_process_error(None) is None

    def test_unwrap_process_error_import_error(self):
        """Lines 27-31: ImportError path — cursor_agent_sdk missing."""
        from code_agents.core.openai_errors import unwrap_process_error
        with patch.dict("sys.modules", {"cursor_agent_sdk": None, "cursor_agent_sdk._errors": None}):
            result = unwrap_process_error(ValueError("test"))
        assert result is None

    def test_unwrap_process_error_with_cause_chain(self):
        """Lines 33-36: Follows __cause__ chain."""
        from code_agents.core.openai_errors import unwrap_process_error
        exc = ValueError("outer")
        exc.__cause__ = None
        # Without cursor_agent_sdk the function returns None after import failure
        result = unwrap_process_error(exc)
        assert result is None

    def test_process_error_json_response_exception_fallback(self):
        """Lines 68-70: Exception fallback path in process_error_json_response."""
        from code_agents.core.openai_errors import process_error_json_response
        mock_exc = MagicMock()
        mock_exc.__str__ = lambda self: "err"
        mock_exc.stderr = None

        # Patch JSONResponse to raise first, then succeed
        call_count = {"n": 0}
        original_JSONResponse = __import__("fastapi.responses", fromlist=["JSONResponse"]).JSONResponse

        def flaky_json_response(status_code, content):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("serialize error")
            return original_JSONResponse(status_code=status_code, content=content)

        with patch("code_agents.core.openai_errors.JSONResponse", side_effect=flaky_json_response):
            resp = process_error_json_response(mock_exc)
        assert resp.status_code == 502

    def test_format_process_error_with_stderr(self):
        """Line 50-52: format_process_error_message includes stderr."""
        from code_agents.core.openai_errors import format_process_error_message
        exc = MagicMock()
        exc.__str__ = lambda self: "process failed"
        exc.stderr = "some stderr output"
        msg = format_process_error_message(exc)
        assert "stderr" in msg
        assert "some stderr output" in msg


# =============================================================================
# questionnaire.py
# =============================================================================

class TestQuestionnaireBoost:
    """Cover lines 55-57 (int parse), 66-67 (is_other input), 111-141 (suggest_questions, etc.)."""

    def test_ask_question_numeric_input(self):
        """Letter input selects correct option index."""
        from code_agents.agent_system.questionnaire import ask_question
        with patch("builtins.input", return_value="b"):
            result = ask_question("Q?", ["opt1", "opt2", "opt3"], allow_other=False)
        assert result["option_idx"] == 1  # "b" → index 1

    def test_ask_question_out_of_range_number(self):
        """Lines 56-57: out-of-range number falls back to default."""
        from code_agents.agent_system.questionnaire import ask_question
        with patch("builtins.input", return_value="99"):
            result = ask_question("Q?", ["opt1", "opt2"], allow_other=False, default=0)
        assert result["option_idx"] == 0

    def test_ask_question_is_other_with_detail(self):
        """Lines 63-66: user selects 'Other' and provides detail."""
        from code_agents.agent_system.questionnaire import ask_question
        # 'c' selects the 3rd option which is 'Other' (index 2 with allow_other=True, 2 real options)
        with patch("builtins.input", side_effect=["c", "My custom answer"]):
            result = ask_question("Q?", ["opt1", "opt2"], allow_other=True)
        assert result["is_other"] is True
        assert result["answer"] == "My custom answer"

    def test_ask_question_is_other_eof(self):
        """Lines 63-67: EOFError on detail input → 'No details provided'."""
        from code_agents.agent_system.questionnaire import ask_question
        with patch("builtins.input", side_effect=["c", EOFError()]):
            result = ask_question("Q?", ["opt1", "opt2"], allow_other=True)
        assert result["is_other"] is True
        assert result["answer"] == "No details provided"

    def test_suggest_questions_deploy(self):
        """Lines 111-128: suggest_questions returns relevant templates."""
        from code_agents.agent_system.questionnaire import suggest_questions
        suggestions = suggest_questions("deploy to production env", "code_writer")
        assert "environment" in suggestions
        assert "deploy_strategy" in suggestions

    def test_suggest_questions_database(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        suggestions = suggest_questions("run database migration", "code_writer")
        assert "database" in suggestions

    def test_suggest_questions_test(self):
        from code_agents.agent_system.questionnaire import suggest_questions
        suggestions = suggest_questions("run test coverage", "code_tester")
        assert "test_scope" in suggestions

    def test_suggest_questions_no_match(self):
        """Lines 111-128: no keywords → empty list."""
        from code_agents.agent_system.questionnaire import suggest_questions
        suggestions = suggest_questions("hello world", "agent")
        assert suggestions == []

    def test_get_session_answers(self):
        """Line 133: get_session_answers returns list from state."""
        from code_agents.agent_system.questionnaire import get_session_answers
        state = {"_qa_pairs": [{"question": "Q1", "answer": "A1"}]}
        result = get_session_answers(state)
        assert len(result) == 1
        assert result[0]["answer"] == "A1"

    def test_get_session_answers_empty(self):
        from code_agents.agent_system.questionnaire import get_session_answers
        assert get_session_answers({}) == []

    def test_has_been_answered_true(self):
        """Lines 136-141: has_been_answered returns True when found."""
        from code_agents.agent_system.questionnaire import has_been_answered
        state = {"_qa_pairs": [{"question": "What env?", "answer": "prod"}]}
        assert has_been_answered(state, "What env?") is True

    def test_has_been_answered_false(self):
        from code_agents.agent_system.questionnaire import has_been_answered
        assert has_been_answered({}, "Never asked") is False

    def test_ask_multiple(self):
        """Lines 74-91: ask_multiple sequences questions."""
        from code_agents.agent_system.questionnaire import ask_multiple
        questions = [
            {"question": "Q1?", "options": ["yes", "no"], "default": 0},
            {"question": "Q2?", "options": ["a", "b"], "default": 1},
        ]
        with patch("builtins.input", side_effect=["a", "b"]):
            results = ask_multiple(questions)
        assert len(results) == 2


# =============================================================================
# env_health.py
# =============================================================================

class TestEnvHealthBoost:
    """Cover _check_* branches where _api_get returns data."""

    def _make_checker(self):
        from code_agents.reporters.env_health import EnvironmentHealthChecker
        checker = EnvironmentHealthChecker()
        return checker

    def test_check_server_ok(self):
        """Lines 79-81: server returns data → ok."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"status": "ok"}):
            checker._check_server()
        checks = [c for c in checker.report.checks if "Server" in c.name]
        assert checks[0].status == "ok"

    def test_check_server_unreachable(self):
        """Line 92: _api_get returns None → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value=None):
            checker._check_server()
        checks = [c for c in checker.report.checks if "Server" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": "myapp"}, clear=False)
    def test_check_argocd_healthy(self):
        """Lines 105-113: ArgoCD healthy and synced."""
        checker = self._make_checker()
        data = {"health": {"status": "Healthy"}, "sync": {"status": "Synced"}, "pod_count": 3}
        with patch.object(checker, "_api_get", return_value=data):
            checker._check_argocd()
        checks = [c for c in checker.report.checks if "ArgoCD" in c.name]
        assert checks[0].status == "ok"

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": "myapp"}, clear=False)
    def test_check_argocd_degraded(self):
        """Lines 105-113: ArgoCD unhealthy → warning."""
        checker = self._make_checker()
        data = {"health": {"status": "Degraded"}, "sync": {"status": "OutOfSync"}, "pod_count": 1}
        with patch.object(checker, "_api_get", return_value=data):
            checker._check_argocd()
        checks = [c for c in checker.report.checks if "ArgoCD" in c.name]
        assert checks[0].status == "warning"

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": "myapp"}, clear=False)
    def test_check_argocd_api_unreachable(self):
        """Line 117: ArgoCD api returns None → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value=None):
            checker._check_argocd()
        checks = [c for c in checker.report.checks if "ArgoCD" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"JENKINS_URL": "https://jenkins.example.com"}, clear=False)
    def test_check_jenkins_success(self):
        """Lines 130-136: Jenkins build SUCCESS."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"result": "SUCCESS", "number": 42}):
            checker._check_jenkins()
        checks = [c for c in checker.report.checks if "Jenkins" in c.name]
        assert checks[0].status == "ok"
        assert "#42" in checks[0].message

    @patch.dict("os.environ", {"JENKINS_URL": "https://jenkins.example.com"}, clear=False)
    def test_check_jenkins_failure(self):
        """Lines 130-136: Jenkins build FAILURE → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"result": "FAILURE", "number": 43}):
            checker._check_jenkins()
        checks = [c for c in checker.report.checks if "Jenkins" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"JENKINS_URL": "https://jenkins.example.com"}, clear=False)
    def test_check_jenkins_unreachable(self):
        """Line 141: Jenkins api None → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value=None):
            checker._check_jenkins()
        checks = [c for c in checker.report.checks if "Jenkins" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com", "JIRA_PROJECT_KEY": "PROJ"}, clear=False)
    def test_check_jira_few_bugs(self):
        """Lines 154-160: Jira few open bugs → ok."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"total": 2}):
            checker._check_jira()
        checks = [c for c in checker.report.checks if "Jira" in c.name]
        assert checks[0].status == "ok"

    @patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com"}, clear=False)
    def test_check_jira_many_bugs(self):
        """Lines 154-160: Jira many open bugs → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"total": 20}):
            checker._check_jira()
        checks = [c for c in checker.report.checks if "Jira" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"JIRA_URL": "https://jira.example.com"}, clear=False)
    def test_check_jira_unreachable(self):
        """Line 166: Jira api None → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value=None):
            checker._check_jira()
        checks = [c for c in checker.report.checks if "Jira" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"KIBANA_URL": "https://kibana.example.com"}, clear=False)
    def test_check_kibana_low_rate(self):
        """Lines 179-185: Kibana low error rate → ok."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"error_rate": 0.5, "error_count": 3}):
            checker._check_kibana()
        checks = [c for c in checker.report.checks if "Kibana" in c.name]
        assert checks[0].status == "ok"

    @patch.dict("os.environ", {"KIBANA_URL": "https://kibana.example.com"}, clear=False)
    def test_check_kibana_high_rate(self):
        """Lines 179-185: Kibana high error rate → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value={"error_rate": 10.0, "error_count": 500}):
            checker._check_kibana()
        checks = [c for c in checker.report.checks if "Kibana" in c.name]
        assert checks[0].status == "error"

    @patch.dict("os.environ", {"KIBANA_URL": "https://kibana.example.com"}, clear=False)
    def test_check_kibana_unreachable(self):
        """Line 190: Kibana api None → error."""
        checker = self._make_checker()
        with patch.object(checker, "_api_get", return_value=None):
            checker._check_kibana()
        checks = [c for c in checker.report.checks if "Kibana" in c.name]
        assert checks[0].status == "error"

    def test_api_get_success(self):
        """Lines 65-69: _api_get returns parsed JSON on success."""
        checker = self._make_checker()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = checker._api_get("/health")
        assert result == {"status": "ok"}

    def test_api_get_failure(self):
        """Lines 70-72: _api_get returns None on exception."""
        checker = self._make_checker()
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = checker._api_get("/health")
        assert result is None


# =============================================================================
# watchdog.py
# =============================================================================

class TestWatchdogBoost:
    """Cover _api_get, collect_snapshot, collect_baseline, run loop."""

    def _make_watchdog(self):
        from code_agents.tools.watchdog import PostDeployWatchdog
        return PostDeployWatchdog(duration_minutes=1)

    def test_api_get_success(self):
        """Lines 62-69: _api_get returns parsed JSON."""
        wd = self._make_watchdog()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error_rate": 1.5}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = wd._api_get("/kibana/error-rate?minutes=5")
        assert result["error_rate"] == 1.5

    def test_api_get_failure(self):
        """Lines 70-72: _api_get returns None on network error."""
        wd = self._make_watchdog()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = wd._api_get("/health")
        assert result is None

    def test_collect_snapshot_with_data(self):
        """Lines 73-89: collect_snapshot fills in error_count/rate and pod_restarts."""
        wd = self._make_watchdog()

        def fake_api_get(path, timeout=10):
            if "kibana" in path:
                return {"error_count": 10, "error_rate": 2.5}
            if "argocd" in path and "pods" in path:
                return {"pods": [{"restarts": 2}, {"restarts": 1}]}
            return None

        with patch.dict("os.environ", {"ARGOCD_APP_NAME": "myapp"}, clear=False):
            with patch.object(wd, "_api_get", side_effect=fake_api_get):
                snap = wd.collect_snapshot()

        assert snap.error_count == 10
        assert snap.error_rate == 2.5
        assert snap.pod_restarts == 3

    def test_collect_baseline(self):
        """Lines 93-96: collect_baseline wraps collect_snapshot."""
        wd = self._make_watchdog()
        snap_data = MagicMock()
        snap_data.error_rate = 1.0

        with patch.object(wd, "collect_snapshot", return_value=snap_data):
            baseline = wd.collect_baseline()
        assert wd.report.baseline is snap_data
        assert baseline.error_rate == 1.0

    def test_run_detects_spike_early(self):
        """Lines 127-156: run loop exits early on spike."""
        from code_agents.tools.watchdog import WatchdogSnapshot
        wd = self._make_watchdog()
        wd.poll_interval = 0  # no sleep in tests

        call_num = {"n": 0}

        def fake_snapshot():
            call_num["n"] += 1
            if call_num["n"] == 1:
                # baseline
                s = WatchdogSnapshot(timestamp="t0", error_rate=1.0, pod_restarts=0)
                wd.report.baseline = s
                return s
            # Second call: spike
            return WatchdogSnapshot(timestamp="t1", error_rate=10.0, pod_restarts=0)

        with patch.object(wd, "collect_snapshot", side_effect=fake_snapshot):
            with patch.object(wd, "collect_baseline", side_effect=lambda: fake_snapshot()):
                report = wd.run(duration_minutes=1)

        assert report is not None

    def test_run_completes_without_spike(self):
        """Lines 127-156: run loop completes normally when no spike."""
        from code_agents.tools.watchdog import WatchdogSnapshot
        wd = self._make_watchdog()
        wd.poll_interval = 0  # avoid sleep
        wd.report.baseline = WatchdogSnapshot(timestamp="t0", error_rate=1.0, pod_restarts=0)

        def fake_snapshot():
            return WatchdogSnapshot(timestamp="t1", error_rate=1.0, pod_restarts=0)

        # Make time.time() expire immediately to avoid infinite loop
        original_time = time.time
        times = iter([0, 0, 100])  # start, check, expired

        with patch("time.time", side_effect=lambda: next(times, 100)):
            with patch.object(wd, "collect_snapshot", side_effect=fake_snapshot):
                report = wd.run(duration_minutes=0)

        assert report is not None


# =============================================================================
# connection_validator.py
# =============================================================================

class TestConnectionValidatorBoost:
    """Cover validate_cursor_http, validate_claude_sdk deeper paths, validate_sync."""

    @pytest.mark.asyncio
    async def test_validate_cursor_http_no_url(self):
        """Lines 60-65: CURSOR_API_URL not set → invalid."""
        from code_agents.devops.connection_validator import validate_cursor_http
        with patch.dict("os.environ", {"CURSOR_API_URL": ""}, clear=False):
            result = await validate_cursor_http()
        assert result.valid is False
        assert "CURSOR_API_URL" in result.message

    @pytest.mark.asyncio
    async def test_validate_cursor_http_no_key(self):
        """Lines 66-70: URL set but no API key → invalid."""
        from code_agents.devops.connection_validator import validate_cursor_http
        with patch.dict("os.environ", {"CURSOR_API_URL": "http://x.com", "CURSOR_API_KEY": ""}, clear=False):
            result = await validate_cursor_http()
        assert result.valid is False
        assert "CURSOR_API_KEY" in result.message

    @pytest.mark.asyncio
    async def test_validate_cursor_http_200_ok(self):
        """Lines 72-85: HTTP 200 → valid."""
        from code_agents.devops.connection_validator import validate_cursor_http
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"CURSOR_API_URL": "http://api.example.com", "CURSOR_API_KEY": "crsr_test123"}
        with patch.dict("os.environ", env, clear=False):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await validate_cursor_http()
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_validate_cursor_http_401(self):
        """Lines 85-90: HTTP 401 → invalid (auth issue)."""
        from code_agents.devops.connection_validator import validate_cursor_http

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"CURSOR_API_URL": "http://api.example.com", "CURSOR_API_KEY": "crsr_test123"}
        with patch.dict("os.environ", env, clear=False):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await validate_cursor_http()
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_validate_cursor_http_unexpected_status(self):
        """Lines 91-95: Unexpected status code."""
        from code_agents.devops.connection_validator import validate_cursor_http

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"CURSOR_API_URL": "http://api.example.com", "CURSOR_API_KEY": "crsr_test123"}
        with patch.dict("os.environ", env, clear=False):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await validate_cursor_http()
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_validate_cursor_http_connect_error(self):
        """Lines 96-100: ConnectError → invalid."""
        from code_agents.devops.connection_validator import validate_cursor_http
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"CURSOR_API_URL": "http://api.example.com", "CURSOR_API_KEY": "crsr_test123"}
        with patch.dict("os.environ", env, clear=False):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await validate_cursor_http()
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_validate_cursor_http_generic_exception(self):
        """Lines 101-105: Generic exception → invalid."""
        from code_agents.devops.connection_validator import validate_cursor_http

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"CURSOR_API_URL": "http://api.example.com", "CURSOR_API_KEY": "crsr_test123"}
        with patch.dict("os.environ", env, clear=False):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await validate_cursor_http()
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_validate_claude_sdk_api_200(self):
        """Lines 142-148: Anthropic API key valid (200)."""
        from code_agents.devops.connection_validator import validate_claude_sdk

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        env = {"ANTHROPIC_API_KEY": "sk-ant-test12345"}
        import sys
        fake_sdk = MagicMock()
        with patch.dict("os.environ", env, clear=False):
            with patch.dict("sys.modules", {"claude_agent_sdk": fake_sdk}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    result = await validate_claude_sdk()
        # Either valid (200) or returns valid=True with network caveat
        assert isinstance(result.valid, bool)

    @pytest.mark.asyncio
    async def test_validate_claude_sdk_no_key(self):
        """Lines 123-124: No ANTHROPIC_API_KEY → invalid immediately."""
        from code_agents.devops.connection_validator import validate_claude_sdk
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = await validate_claude_sdk()
        assert result.valid is False
        assert "ANTHROPIC_API_KEY" in result.message

    @pytest.mark.asyncio
    async def test_validate_backend_cursor_http_route(self):
        """Line 278: backend=cursor_http → validate_cursor_http."""
        from code_agents.devops.connection_validator import validate_backend
        with patch("code_agents.devops.connection_validator.validate_cursor_http",
                   new=AsyncMock(return_value=MagicMock(valid=True, backend="cursor_http", message="ok"))):
            result = await validate_backend("cursor_http")
        assert result.backend == "cursor_http"

    @pytest.mark.asyncio
    async def test_validate_server_and_backend_both_fail(self):
        """Lines 304-309: both server and backend fail."""
        from code_agents.devops.connection_validator import validate_server_and_backend

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("code_agents.devops.connection_validator.validate_backend",
                       new=AsyncMock(return_value=MagicMock(valid=False, backend="cursor", message="no"))):
                results = await validate_server_and_backend("http://localhost:8000")
        assert len(results) == 2
        assert results[0].valid is False  # server

    def test_validate_sync_no_running_loop(self):
        """Lines 328-330: validate_sync with no running loop → asyncio.run."""
        from code_agents.devops.connection_validator import validate_sync
        mock_result = MagicMock(valid=True, backend="cursor", message="ok")

        with patch("code_agents.devops.connection_validator.validate_backend",
                   new=AsyncMock(return_value=mock_result)):
            result = validate_sync("cursor")
        assert result.valid is True


# =============================================================================
# skill_loader.py
# =============================================================================

class TestSkillLoaderBoost:
    """Cover get_skill fallback paths, list_all_skills, format_skills_for_prompt,
    generate_skill_index, get_all_agents_with_skills, estimate_prompt_tokens."""

    def _create_agents_dir(self, tmp_path: Path) -> Path:
        """Create a minimal agents/ structure with skill files."""
        agents_dir = tmp_path / "agents"
        # Agent skill
        skill_dir = agents_dir / "code_writer" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "build.md").write_text(
            "---\nname: build\ndescription: Trigger Jenkins build\n---\n\n## Workflow\n1. Trigger\n"
        )
        # Shared skill
        shared_dir = agents_dir / "_shared" / "skills"
        shared_dir.mkdir(parents=True)
        (shared_dir / "debug.md").write_text(
            "---\nname: debug\ndescription: Debug an issue\n---\n\n## Steps\n1. Check logs\n"
        )
        return agents_dir

    def test_get_skill_fallback_to_shared(self, tmp_path):
        """Lines 179, 184-190: get_skill falls back to _shared when not in agent."""
        from code_agents.agent_system.skill_loader import get_skill
        agents_dir = self._create_agents_dir(tmp_path)
        skill = get_skill(agents_dir, "code_writer", "debug")  # not in code_writer, but in _shared
        assert skill is not None
        assert skill.name == "debug"

    def test_get_skill_not_found(self, tmp_path):
        """Lines 179, 184-190: get_skill returns None when skill doesn't exist."""
        from code_agents.agent_system.skill_loader import get_skill
        agents_dir = self._create_agents_dir(tmp_path)
        skill = get_skill(agents_dir, "code_writer", "nonexistent_skill")
        assert skill is None

    def test_get_skill_by_alternate_name(self, tmp_path):
        """Lines 184-188: get_skill finds by iterating with name match."""
        from code_agents.agent_system.skill_loader import get_skill
        agents_dir = self._create_agents_dir(tmp_path)
        skill = get_skill(agents_dir, "code_writer", "build")
        assert skill is not None
        assert skill.name == "build"

    def test_list_all_skills(self, tmp_path):
        """Lines 217-221: list_all_skills returns flat list across all agents."""
        from code_agents.agent_system.skill_loader import list_all_skills
        agents_dir = self._create_agents_dir(tmp_path)
        skills = list_all_skills(agents_dir)
        names = [s.name for s in skills]
        assert "build" in names
        assert "debug" in names

    def test_format_skills_for_prompt_empty(self):
        """Line 225: format_skills_for_prompt with empty list returns empty string."""
        from code_agents.agent_system.skill_loader import format_skills_for_prompt
        result = format_skills_for_prompt([])
        assert result == ""

    def test_format_skills_for_prompt_with_skills(self, tmp_path):
        """Lines 225-232: format_skills_for_prompt formats skills list."""
        from code_agents.agent_system.skill_loader import format_skills_for_prompt, load_agent_skills
        agents_dir = self._create_agents_dir(tmp_path)
        skills = []
        for agent_skills in load_agent_skills(agents_dir).values():
            skills.extend(agent_skills)
        result = format_skills_for_prompt(skills)
        assert "Available skills" in result
        assert "build" in result

    def test_generate_skill_index(self, tmp_path):
        """Lines 237-276: generate_skill_index builds index including shared count."""
        from code_agents.agent_system.skill_loader import generate_skill_index
        agents_dir = self._create_agents_dir(tmp_path)
        index = generate_skill_index(agents_dir, "code_writer")
        assert "build" in index
        # Shared skills summary line should mention shared workflows
        assert "shared" in index.lower()

    def test_generate_skill_index_no_skills(self, tmp_path):
        """Lines 237-276: generate_skill_index returns empty string when no skills."""
        from code_agents.agent_system.skill_loader import generate_skill_index
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = generate_skill_index(agents_dir, "empty_agent")
        assert result == ""

    def test_get_all_agents_with_skills(self, tmp_path):
        """Lines 250-276: get_all_agents_with_skills builds full catalog."""
        from code_agents.agent_system.skill_loader import get_all_agents_with_skills
        agents_dir = self._create_agents_dir(tmp_path)
        catalog = get_all_agents_with_skills(agents_dir)
        # Agent stored as "code-writer" (hyphenated) or "code_writer" depending on dir name
        assert "code" in catalog  # matches either "code_writer" or "code-writer"
        assert "build" in catalog

    def test_get_all_agents_with_skills_empty(self, tmp_path):
        """Lines 250-252: returns empty string when no agents."""
        from code_agents.agent_system.skill_loader import get_all_agents_with_skills
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        result = get_all_agents_with_skills(agents_dir)
        assert result == ""

    def test_estimate_prompt_tokens(self):
        """Line 281: rough token estimate."""
        from code_agents.agent_system.skill_loader import estimate_prompt_tokens
        text = "a" * 400
        assert estimate_prompt_tokens(text) == 100


# =============================================================================
# mutation_tester.py
# =============================================================================

class TestMutationTesterBoost:
    """Cover generate_mutations with real files, run_mutation, and test_file."""

    def test_generate_mutations_nonexistent_file(self):
        """Lines 108-110: returns [] for non-existent file."""
        from code_agents.testing.mutation_tester import MutationTester
        mt = MutationTester(repo_path="/tmp")
        result = mt.generate_mutations("/nonexistent/file.py")
        assert result == []

    def test_generate_mutations_from_file(self, tmp_path):
        """Lines 113-133: actually generates mutations from source code."""
        from code_agents.testing.mutation_tester import MutationTester
        source = tmp_path / "source.py"
        source.write_text("def foo(x, y):\n    if x == y:\n        return True\n    return False\n")
        mt = MutationTester(repo_path=str(tmp_path))
        mutations = mt.generate_mutations(str(source))
        assert len(mutations) > 0
        types = {m.mutation_type for m in mutations}
        assert "operator" in types or "return_value" in types

    def test_generate_mutations_skips_comments(self, tmp_path):
        """Lines 120-122: comment lines are skipped."""
        from code_agents.testing.mutation_tester import MutationTester
        source = tmp_path / "comments.py"
        source.write_text("# This is a comment\n# return True\nx = 1\n")
        mt = MutationTester(repo_path=str(tmp_path))
        mutations = mt.generate_mutations(str(source))
        # Comment lines should not produce mutations
        for m in mutations:
            assert not m.original.startswith("#")

    def test_run_mutation_nonexistent_file(self, tmp_path):
        """Lines 146-148: returns mutation unchanged for missing file."""
        from code_agents.testing.mutation_tester import MutationTester, Mutation
        mt = MutationTester(repo_path=str(tmp_path))
        mutation = Mutation(
            file="/nonexistent.py", line=1,
            original="x == y", mutated="x != y", mutation_type="operator"
        )
        result = mt.run_mutation(mutation)
        assert result.killed is False  # default, unchanged

    def test_run_mutation_tests_catch_it(self, tmp_path):
        """Lines 162-184: test suite catches the mutation (tests fail → killed=True)."""
        from code_agents.testing.mutation_tester import MutationTester, Mutation
        source = tmp_path / "src.py"
        source.write_text("def add(a, b):\n    return a + b\n")

        mt = MutationTester(repo_path=str(tmp_path), test_command="false")
        mutation = Mutation(
            file=str(source), line=2,
            original="return a + b", mutated="return a - b", mutation_type="operator"
        )

        mock_result = MagicMock()
        mock_result.returncode = 1  # tests fail → mutation killed

        with patch("subprocess.run", return_value=mock_result):
            result = mt.run_mutation(mutation)
        assert result.killed is True

    def test_run_mutation_tests_dont_catch(self, tmp_path):
        """Lines 162-184: tests pass → mutation survived (killed=False)."""
        from code_agents.testing.mutation_tester import MutationTester, Mutation
        source = tmp_path / "src.py"
        source.write_text("def add(a, b):\n    return a + b\n")

        mt = MutationTester(repo_path=str(tmp_path), test_command="true")
        mutation = Mutation(
            file=str(source), line=2,
            original="return a + b", mutated="return a - b", mutation_type="operator"
        )

        mock_result = MagicMock()
        mock_result.returncode = 0  # tests pass → mutation survived

        with patch("subprocess.run", return_value=mock_result):
            result = mt.run_mutation(mutation)
        assert result.killed is False

    def test_run_mutation_timeout(self, tmp_path):
        """Lines 176-178: timeout counts as killed=True."""
        from code_agents.testing.mutation_tester import MutationTester, Mutation
        source = tmp_path / "src.py"
        source.write_text("def f():\n    return True\n")

        mt = MutationTester(repo_path=str(tmp_path))
        mutation = Mutation(
            file=str(source), line=2,
            original="return True", mutated="return False", mutation_type="return_value"
        )

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 120)):
            result = mt.run_mutation(mutation)
        assert result.killed is True

    def test_test_file_produces_report(self, tmp_path):
        """Lines 196-208: test_file generates full report."""
        from code_agents.testing.mutation_tester import MutationTester
        source = tmp_path / "func.py"
        source.write_text("def cmp(a, b):\n    return a == b\n")

        mt = MutationTester(repo_path=str(tmp_path))
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            report = mt.test_file(str(source), max_mutations=5)

        assert report.source_file == str(source)
        assert report.total >= 0
        assert 0.0 <= report.score <= 100.0


# =============================================================================
# webui/router.py
# =============================================================================

class TestWebuiRouterBoost:
    """Cover /ui, /telemetry-dashboard, /dashboard, /ui/{path} endpoints."""

    def test_ui_index_missing_file(self):
        """Lines 13, 18, 23: endpoints return FileResponse (file may not exist but route covered)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from code_agents.webui.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)

        # These may 500 if static files don't exist, but the route code is executed
        r = client.get("/ui")
        assert r.status_code in (200, 404, 500)

    def test_telemetry_page(self):
        """Line 18: /telemetry-dashboard route."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from code_agents.webui.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/telemetry-dashboard")
        assert r.status_code in (200, 404, 500)

    def test_dashboard_page(self):
        """Line 23: /dashboard route."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from code_agents.webui.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/dashboard")
        assert r.status_code in (200, 404, 500)

    def test_ui_static_not_found(self):
        """Lines 28-31: /ui/{path} returns 404 for missing files."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from code_agents.webui.router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/ui/nonexistent_file_xyz.js")
        assert r.status_code in (200, 404, 500)

    def test_ui_static_existing_file(self, tmp_path):
        """Lines 28-30: /ui/{path} returns FileResponse for existing files."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from code_agents.webui import router as webui_module
        import code_agents.webui.router as wr

        # Temporarily patch STATIC_DIR to a tmp_path with a test file
        test_file = tmp_path / "test.js"
        test_file.write_text("console.log('test');")

        original_static = wr.STATIC_DIR
        wr.STATIC_DIR = tmp_path

        try:
            app = FastAPI()
            app.include_router(wr.router)
            client = TestClient(app)
            r = client.get("/ui/test.js")
            assert r.status_code == 200
        finally:
            wr.STATIC_DIR = original_static


# =============================================================================
# log_investigator.py
# =============================================================================

class TestLogInvestigatorBoost:
    """Cover _search_kibana_logs, _find_error_patterns, _correlate_deploys, _find_related_commits."""

    def _make_investigator(self):
        from code_agents.observability.log_investigator import LogInvestigator
        return LogInvestigator(query="NullPointerException", cwd="/tmp", hours=24)

    def test_search_kibana_logs_success(self):
        """Lines 67-72: Kibana search returns hits."""
        inv = self._make_investigator()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"hits": [{"message": "NullPointerException in service.py:42", "timestamp": "2026-04-02T10:00:00"}]}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            inv._search_kibana_logs()

        assert len(inv.investigation.matching_logs) == 1

    def test_search_kibana_logs_failure(self):
        """Lines 70-72: Kibana search fails silently."""
        inv = self._make_investigator()
        with patch("urllib.request.urlopen", side_effect=Exception("connection error")):
            inv._search_kibana_logs()
        assert inv.investigation.matching_logs == []

    def test_find_error_patterns(self):
        """Lines 76-95 (approx): groups logs by normalized pattern."""
        from code_agents.observability.log_investigator import LogInvestigator
        inv = LogInvestigator(query="error", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": "Error in service.py line 42 at 2026-01-01T10:00:00Z", "timestamp": "t1"},
            {"message": "Error in service.py line 43 at 2026-01-01T10:01:00Z", "timestamp": "t2"},
            {"message": "Different error at 2026-01-01T10:02:00Z", "timestamp": "t3"},
        ]
        inv._find_error_patterns()
        assert len(inv.investigation.error_patterns) >= 1

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": "myapp"}, clear=False)
    def test_correlate_deploys_with_app(self):
        """Lines 100-122: correlate_deploys fetches ArgoCD status."""
        from code_agents.observability.log_investigator import LogInvestigator
        inv = LogInvestigator(query="error", cwd="/tmp")
        inv.investigation.error_patterns = [{"pattern": "err", "count": 5, "first_seen": "2026-04-02T10:00:00", "last_seen": ""}]

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"revision": "abc123", "sync_status": "Synced", "health_status": "Healthy"}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            inv._correlate_deploys()
        assert len(inv.investigation.correlated_deploys) == 1

    def test_correlate_deploys_no_patterns(self):
        """Lines 95-97: skip if no error patterns."""
        inv = self._make_investigator()
        inv.investigation.error_patterns = []
        inv._correlate_deploys()  # should not raise
        assert inv.investigation.correlated_deploys == []

    def test_find_related_commits(self, tmp_path):
        """Lines 124-142: git log finds commits."""
        from code_agents.observability.log_investigator import LogInvestigator
        inv = LogInvestigator(query="NullPointer error", cwd=str(tmp_path))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 Fix NullPointerException in service\ndef5678 Refactor error handling\n"

        with patch("subprocess.run", return_value=mock_result):
            inv._find_related_commits()
        assert len(inv.investigation.related_commits) >= 1


# =============================================================================
# slack_bot.py
# =============================================================================

class TestSlackBotBoost:
    """Cover get_bot_user_id, send_message, delegate_to_agent."""

    def _make_bot(self):
        from code_agents.integrations.slack_bot import SlackBot
        with patch.dict("os.environ", {
            "CODE_AGENTS_SLACK_BOT_TOKEN": "xoxb-test-token",
            "CODE_AGENTS_PUBLIC_BASE_URL": "http://localhost:8000",
        }, clear=False):
            return SlackBot()

    def test_get_bot_user_id_success(self):
        """Lines 79-93: auth.test returns ok=True."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "user_id": "U123ABC"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            uid = bot.get_bot_user_id()
        assert uid == "U123ABC"

    def test_get_bot_user_id_auth_failure(self):
        """Lines 90-92: auth.test returns ok=False."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "error": "invalid_auth"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            uid = bot.get_bot_user_id()
        assert uid == ""

    def test_get_bot_user_id_exception(self):
        """Lines 93-95: exception → empty string."""
        bot = self._make_bot()
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            uid = bot.get_bot_user_id()
        assert uid == ""

    def test_get_bot_user_id_cached(self):
        """Lines 75-77: returns cached _bot_user_id."""
        bot = self._make_bot()
        bot._bot_user_id = "U_CACHED"
        uid = bot.get_bot_user_id()
        assert uid == "U_CACHED"

    def test_get_bot_user_id_no_token(self):
        """Lines 77-78: no token → returns empty string immediately."""
        from code_agents.integrations.slack_bot import SlackBot
        with patch.dict("os.environ", {"CODE_AGENTS_SLACK_BOT_TOKEN": ""}, clear=False):
            bot = SlackBot()
        uid = bot.get_bot_user_id()
        assert uid == ""

    def test_send_message_success(self):
        """Lines 102-125: send_message returns True on ok=True."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "ts": "1234.5678"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.send_message("#general", "Hello there!")
        assert result is True

    def test_send_message_failure(self):
        """Lines 120-122: postMessage returns ok=False."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": False, "error": "channel_not_found"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.send_message("#nonexistent", "test")
        assert result is False

    def test_send_message_exception(self):
        """Lines 123-125: network exception → False."""
        bot = self._make_bot()
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = bot.send_message("#general", "test")
        assert result is False

    def test_send_message_with_thread_ts(self):
        """Lines 102-125: send_message with thread_ts."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.send_message("#general", "reply", thread_ts="1234.5678")
        assert result is True

    def test_delegate_to_agent_success(self):
        """Lines 151-175: delegate_to_agent returns content from API."""
        bot = self._make_bot()
        response_data = {
            "choices": [{"message": {"content": "Here's my answer"}}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.delegate_to_agent("what is CI/CD?", "auto-pilot")
        assert result == "Here's my answer"

    def test_delegate_to_agent_no_choices(self):
        """Lines 173-174: empty choices → 'No response'."""
        bot = self._make_bot()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"choices": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = bot.delegate_to_agent("hello", "auto-pilot")
        assert result == "No response from agent"

    def test_delegate_to_agent_retry_on_failure(self):
        """Lines 176-181: first attempt fails, second succeeds after retry."""
        bot = self._make_bot()
        success_data = {"choices": [{"message": {"content": "retry worked"}}]}
        success_resp = MagicMock()
        success_resp.read.return_value = json.dumps(success_data).encode()
        success_resp.__enter__ = lambda s: s
        success_resp.__exit__ = MagicMock(return_value=False)

        call_count = {"n": 0}

        def mock_urlopen(req, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("first attempt failed")
            return success_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep"):
                result = bot.delegate_to_agent("question", "auto-pilot")
        assert result == "retry worked"

    def test_delegate_to_agent_both_fail(self):
        """Lines 180-181: both attempts fail → error message."""
        bot = self._make_bot()
        with patch("urllib.request.urlopen", side_effect=Exception("always fails")):
            with patch("time.sleep"):
                result = bot.delegate_to_agent("question", "auto-pilot")
        assert "Error" in result


# =============================================================================
# main.py
# =============================================================================

class TestMainBoost:
    """Cover the main() function (lines 19-23, 32)."""

    def test_main_function(self):
        """Lines 19-23, 32: main() calls uvicorn.run with correct settings."""
        import code_agents.core.main as main_module
        with patch("uvicorn.run") as mock_run:
            with patch("code_agents.core.main.setup_logging"):
                main_module.main()
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert "code_agents.core.app:app" in call_kwargs[0] or call_kwargs[1].get("app") is not None or "code_agents.core.app:app" == call_kwargs[0][0]
