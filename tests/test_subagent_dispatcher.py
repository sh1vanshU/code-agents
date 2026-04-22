"""Tests for code_agents.subagent_dispatcher — SubagentResult + SubagentDispatcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from code_agents.agent_system.subagent_dispatcher import SubagentDispatcher, SubagentResult


# ---------------------------------------------------------------------------
# SubagentResult dataclass
# ---------------------------------------------------------------------------

class TestSubagentResult:
    """SubagentResult field defaults and construction."""

    def test_success_result(self):
        r = SubagentResult(agent="test", response="hi", duration_ms=42, success=True)
        assert r.agent == "test"
        assert r.response == "hi"
        assert r.duration_ms == 42
        assert r.success is True
        assert r.error is None

    def test_error_result(self):
        r = SubagentResult(agent="x", response="", duration_ms=0, success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"

    def test_error_defaults_to_none(self):
        r = SubagentResult(agent="a", response="ok", duration_ms=1, success=True)
        assert r.error is None


# ---------------------------------------------------------------------------
# SubagentDispatcher.__init__
# ---------------------------------------------------------------------------

class TestDispatcherInit:
    def test_default_base_url(self):
        d = SubagentDispatcher()
        assert d.base_url == "http://127.0.0.1:8000"

    def test_custom_base_url_trailing_slash_stripped(self):
        d = SubagentDispatcher("http://localhost:9090/")
        assert d.base_url == "http://localhost:9090"

    def test_custom_base_url_no_trailing_slash(self):
        d = SubagentDispatcher("http://myhost:5000")
        assert d.base_url == "http://myhost:5000"


# ---------------------------------------------------------------------------
# SubagentDispatcher.dispatch — success path
# ---------------------------------------------------------------------------

class TestDispatchSuccess:
    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_success_extracts_content(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}],
        }
        mock_post.return_value = resp

        d = SubagentDispatcher()
        result = d.dispatch("code-gen", "write code")

        assert result.success is True
        assert result.agent == "code-gen"
        assert result.response == "Hello world"
        assert result.duration_ms >= 0
        assert result.error is None

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_success_empty_choices(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("x", "q")
        assert result.success is True
        assert result.response == ""

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_success_no_choices_key(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("x", "q")
        assert result.success is True
        assert result.response == ""

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_success_missing_content_in_message(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {}}]}
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("x", "q")
        assert result.success is True
        assert result.response == ""

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_url_contains_agent_name(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = resp

        SubagentDispatcher("http://h:1").dispatch("my-agent", "q")
        url_called = mock_post.call_args[0][0] if mock_post.call_args[0] else mock_post.call_args[1]["url"]
        # positional arg
        assert "/v1/agents/my-agent/chat/completions" in mock_post.call_args[0][0]

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_payload_includes_session_id(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q", session_id="sid-123")
        payload = mock_post.call_args[1]["json"]
        assert payload["session_id"] == "sid-123"

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_payload_without_session_id(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q")
        payload = mock_post.call_args[1]["json"]
        assert "session_id" not in payload

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_cwd_sets_header(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q", cwd="/my/repo")
        headers = mock_post.call_args[1]["headers"]
        assert headers["X-Repo-Path"] == "/my/repo"

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_no_cwd_no_repo_header(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q")
        headers = mock_post.call_args[1]["headers"]
        assert "X-Repo-Path" not in headers

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_timeout_passed_to_requests(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q", timeout=30)
        assert mock_post.call_args[1]["timeout"] == 30

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_stream_is_false(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        SubagentDispatcher().dispatch("a", "q")
        payload = mock_post.call_args[1]["json"]
        assert payload["stream"] is False


# ---------------------------------------------------------------------------
# SubagentDispatcher.dispatch — HTTP error path
# ---------------------------------------------------------------------------

class TestDispatchHttpError:
    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_non_200_returns_failure(self, mock_post):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("a", "q")
        assert result.success is False
        assert result.response == ""
        assert "HTTP 500" in result.error

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_error_text_truncated_to_500(self, mock_post):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "x" * 1000
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("a", "q")
        # error should contain at most 500 chars of the response text
        assert len(result.error) < 600  # "HTTP 400: " prefix + 500 chars

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post")
    def test_404_error(self, mock_post):
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "Not Found"
        mock_post.return_value = resp

        result = SubagentDispatcher().dispatch("missing", "q")
        assert result.success is False
        assert "404" in result.error
        assert result.agent == "missing"


# ---------------------------------------------------------------------------
# SubagentDispatcher.dispatch — timeout path
# ---------------------------------------------------------------------------

class TestDispatchTimeout:
    @patch("code_agents.agent_system.subagent_dispatcher.requests.post", side_effect=requests.Timeout("timed out"))
    def test_timeout_returns_failure(self, mock_post):
        result = SubagentDispatcher().dispatch("a", "q", timeout=5)
        assert result.success is False
        assert result.response == ""
        assert "Timeout" in result.error
        assert "5" in result.error

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post", side_effect=requests.Timeout)
    def test_timeout_duration_recorded(self, mock_post):
        result = SubagentDispatcher().dispatch("a", "q")
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# SubagentDispatcher.dispatch — generic exception path
# ---------------------------------------------------------------------------

class TestDispatchGenericException:
    @patch("code_agents.agent_system.subagent_dispatcher.requests.post", side_effect=ConnectionError("refused"))
    def test_connection_error(self, mock_post):
        result = SubagentDispatcher().dispatch("a", "q")
        assert result.success is False
        assert "refused" in result.error

    @patch("code_agents.agent_system.subagent_dispatcher.requests.post", side_effect=RuntimeError("unexpected"))
    def test_runtime_error(self, mock_post):
        result = SubagentDispatcher().dispatch("a", "q")
        assert result.success is False
        assert "unexpected" in result.error
        assert result.response == ""
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# SubagentDispatcher.explore — delegates to dispatch
# ---------------------------------------------------------------------------

class TestExplore:
    @patch.object(SubagentDispatcher, "dispatch")
    def test_explore_calls_dispatch_with_explore_agent(self, mock_dispatch):
        mock_dispatch.return_value = SubagentResult(
            agent="explore", response="found it", duration_ms=10, success=True,
        )
        d = SubagentDispatcher()
        result = d.explore("find files")

        mock_dispatch.assert_called_once_with("explore", "find files", cwd=None, timeout=120)
        assert result.agent == "explore"
        assert result.success is True

    @patch.object(SubagentDispatcher, "dispatch")
    def test_explore_passes_cwd_and_timeout(self, mock_dispatch):
        mock_dispatch.return_value = SubagentResult(
            agent="explore", response="", duration_ms=0, success=True,
        )
        d = SubagentDispatcher()
        d.explore("q", cwd="/repo", timeout=60)

        mock_dispatch.assert_called_once_with("explore", "q", cwd="/repo", timeout=60)
