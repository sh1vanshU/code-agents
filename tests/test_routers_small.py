"""Tests for small router modules — k8s, completions, testing, redash."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# K8s Router
# ---------------------------------------------------------------------------


class TestK8sRouter:
    @patch("code_agents.routers.k8s._get_client")
    def test_list_pods(self, mock_gc):
        from code_agents.routers.k8s import list_pods
        mock_gc.return_value.get_pods = AsyncMock(return_value=[{"name": "pod1"}])
        result = asyncio.run(list_pods())
        assert result == [{"name": "pod1"}]

    @patch("code_agents.routers.k8s._get_client")
    def test_list_pods_error(self, mock_gc):
        from code_agents.routers.k8s import list_pods
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_pods = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(list_pods())
        assert exc.value.status_code == 502

    @patch("code_agents.routers.k8s._get_client")
    def test_get_pod_logs(self, mock_gc):
        from code_agents.routers.k8s import get_pod_logs
        mock_gc.return_value.get_pod_logs = AsyncMock(return_value="log line 1")
        result = asyncio.run(get_pod_logs("my-pod"))
        assert result["pod"] == "my-pod"
        assert result["logs"] == "log line 1"

    @patch("code_agents.routers.k8s._get_client")
    def test_describe_pod(self, mock_gc):
        from code_agents.routers.k8s import describe_pod
        mock_gc.return_value.get_pod_describe = AsyncMock(return_value="describe output")
        result = asyncio.run(describe_pod("my-pod"))
        assert result["describe"] == "describe output"

    @patch("code_agents.routers.k8s._get_client")
    def test_list_deployments(self, mock_gc):
        from code_agents.routers.k8s import list_deployments
        mock_gc.return_value.get_deployments = AsyncMock(return_value=[{"name": "dep1"}])
        result = asyncio.run(list_deployments())
        assert result == [{"name": "dep1"}]

    @patch("code_agents.routers.k8s._get_client")
    def test_list_events(self, mock_gc):
        from code_agents.routers.k8s import list_events
        mock_gc.return_value.get_events = AsyncMock(return_value=[{"type": "Normal"}])
        result = asyncio.run(list_events())
        assert result == [{"type": "Normal"}]

    @patch("code_agents.routers.k8s._get_client")
    def test_list_namespaces(self, mock_gc):
        from code_agents.routers.k8s import list_namespaces
        mock_gc.return_value.get_namespaces = AsyncMock(return_value=["default", "kube-system"])
        result = asyncio.run(list_namespaces())
        assert "default" in result

    @patch("code_agents.routers.k8s._get_client")
    def test_list_contexts(self, mock_gc):
        from code_agents.routers.k8s import list_contexts
        mock_gc.return_value.get_contexts = AsyncMock(return_value=["ctx1"])
        result = asyncio.run(list_contexts())
        assert result == ["ctx1"]

    def test_get_client_defaults(self):
        from code_agents.routers.k8s import _get_client
        with patch.dict(os.environ, {}, clear=True):
            client = _get_client()
            assert client.namespace == "default"

    def test_get_client_custom(self):
        from code_agents.routers.k8s import _get_client
        with patch.dict(os.environ, {"K8S_NAMESPACE": "prod", "K8S_SSH_HOST": "bastion"}):
            client = _get_client("staging")
            assert client.namespace == "staging"


# ---------------------------------------------------------------------------
# Completions Router
# ---------------------------------------------------------------------------


class TestCompletionsRouter:
    def test_norm_model_label(self):
        from code_agents.routers.completions import _norm_model_label
        assert _norm_model_label("Composer 1.5") == "composer-1.5"
        assert _norm_model_label("Composer 2 Fast") == "composer-2-fast"
        assert _norm_model_label("code_writer") == "code-writer"
        assert _norm_model_label("  hello  ") == "hello"

    def test_resolve_agent_no_model(self):
        from code_agents.routers.completions import _resolve_agent
        mock_agent = MagicMock(name="code-reasoning")
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.default = mock_agent
            result = _resolve_agent(None)
            assert result == mock_agent

    def test_resolve_agent_no_default(self):
        from code_agents.routers.completions import _resolve_agent
        from fastapi import HTTPException
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.default = None
            with pytest.raises(HTTPException) as exc:
                _resolve_agent("")
            assert exc.value.status_code == 400

    def test_resolve_agent_exact_name(self):
        from code_agents.routers.completions import _resolve_agent
        mock_agent = MagicMock()
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.get.return_value = mock_agent
            result = _resolve_agent("code-writer")
            assert result == mock_agent

    def test_resolve_agent_display_name(self):
        from code_agents.routers.completions import _resolve_agent
        mock_agent = MagicMock()
        mock_agent.display_name = "Code Writer Agent"
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.get.return_value = None
            mock_loader.list_agents.return_value = [mock_agent]
            result = _resolve_agent("Code Writer Agent")
            assert result == mock_agent

    def test_resolve_agent_model_match(self):
        from code_agents.routers.completions import _resolve_agent
        mock_agent = MagicMock()
        mock_agent.display_name = None
        mock_agent.model = "Composer 2 Fast"
        mock_agent.name = "code-reasoning"
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.get.return_value = None
            mock_loader.list_agents.return_value = [mock_agent]
            result = _resolve_agent("Composer 2 Fast")
            assert result == mock_agent

    def test_resolve_agent_not_found(self):
        from code_agents.routers.completions import _resolve_agent
        from fastapi import HTTPException
        mock_agent = MagicMock()
        mock_agent.display_name = None
        mock_agent.model = None
        mock_agent.name = "other"
        with patch("code_agents.routers.completions.agent_loader") as mock_loader:
            mock_loader.get.return_value = None
            mock_loader.list_agents.return_value = [mock_agent]
            with pytest.raises(HTTPException) as exc:
                _resolve_agent("nonexistent")
            assert exc.value.status_code == 404

    @patch("code_agents.routers.completions._resolve_agent")
    @patch("code_agents.routers.completions._handle_completions", new_callable=AsyncMock)
    def test_openai_chat_completions(self, mock_handle, mock_resolve):
        from code_agents.routers.completions import openai_chat_completions
        from code_agents.core.models import CompletionRequest, Message
        req = CompletionRequest(model="code-writer", messages=[Message(role="user", content="hi")])
        mock_handle.return_value = {"choices": []}
        asyncio.run(openai_chat_completions(req))
        mock_resolve.assert_called_once()
        mock_handle.assert_called_once()

    @patch("code_agents.routers.completions.agent_loader")
    @patch("code_agents.routers.completions._handle_completions", new_callable=AsyncMock)
    def test_chat_completions_not_found(self, mock_handle, mock_loader):
        from code_agents.routers.completions import chat_completions
        from code_agents.core.models import CompletionRequest, Message
        from fastapi import HTTPException
        mock_loader.get.return_value = None
        mock_loader.list_agents.return_value = []
        req = CompletionRequest(model="x", messages=[Message(role="user", content="hi")])
        with pytest.raises(HTTPException) as exc:
            asyncio.run(chat_completions("nonexistent", req))
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Testing Router
# ---------------------------------------------------------------------------


class TestTestingRouter:
    def test_resolve_repo_path_default(self, tmp_path):
        from code_agents.routers.testing import _resolve_repo_path
        result = _resolve_repo_path(str(tmp_path))
        assert result == str(tmp_path)

    def test_resolve_repo_path_invalid(self):
        from code_agents.routers.testing import _resolve_repo_path
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _resolve_repo_path("/nonexistent/path/xyz123")
        assert exc.value.status_code == 422

    @patch("code_agents.routers.testing._get_client")
    def test_run_tests(self, mock_gc):
        from code_agents.routers.testing import run_tests, RunTestsRequest
        mock_gc.return_value.run_tests = AsyncMock(return_value={
            "passed": True, "total": 10, "passed_count": 10, "failed_count": 0
        })
        req = RunTestsRequest()
        result = asyncio.run(run_tests(req))
        assert result["passed"] is True

    @patch("code_agents.routers.testing._get_client")
    def test_run_tests_error(self, mock_gc):
        from code_agents.routers.testing import run_tests, RunTestsRequest
        from code_agents.cicd.testing_client import TestingError
        from fastapi import HTTPException
        mock_gc.return_value.run_tests = AsyncMock(side_effect=TestingError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(run_tests(RunTestsRequest()))

    @patch("code_agents.routers.testing._get_client")
    def test_get_coverage(self, mock_gc):
        from code_agents.routers.testing import get_coverage
        mock_gc.return_value.get_coverage = AsyncMock(return_value={
            "total_coverage": 85.0, "coverage_threshold": 80.0
        })
        result = asyncio.run(get_coverage())
        assert result["total_coverage"] == 85.0

    @patch("code_agents.routers.testing._get_client")
    def test_get_coverage_gaps(self, mock_gc):
        from code_agents.routers.testing import get_coverage_gaps
        mock_gc.return_value.get_coverage_gaps = AsyncMock(return_value={
            "new_lines_covered": 50, "new_lines_total": 100, "coverage_pct": 50.0
        })
        result = asyncio.run(get_coverage_gaps())
        assert result["coverage_pct"] == 50.0


# ---------------------------------------------------------------------------
# Redash Router
# ---------------------------------------------------------------------------


class TestRedashRouter:
    def test_get_client_no_url(self):
        from code_agents.routers.redash import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert exc.value.status_code == 503

    def test_get_client_no_auth(self):
        from code_agents.routers.redash import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {"REDASH_BASE_URL": "http://redash"}, clear=True):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert "REDASH_API_KEY" in exc.value.detail

    def test_get_client_with_api_key(self):
        from code_agents.routers.redash import _get_client
        with patch.dict(os.environ, {"REDASH_BASE_URL": "http://redash", "REDASH_API_KEY": "key123"}):
            client = _get_client()
            assert client.api_key == "key123"

    @patch("code_agents.routers.redash._get_client")
    def test_run_query(self, mock_gc):
        from code_agents.routers.redash import run_query, RunQueryRequest
        mock_gc.return_value.run_query.return_value = {
            "columns": [{"name": "id"}], "rows": [{"id": 1}],
            "metadata": {"row_count": 1, "runtime": 0.5}
        }
        req = RunQueryRequest(data_source_id=1, query="SELECT 1")
        result = run_query(req)
        assert result["rows"][0]["id"] == 1

    @patch("code_agents.routers.redash._get_client")
    def test_run_query_error(self, mock_gc):
        from code_agents.routers.redash import run_query, RunQueryRequest
        from code_agents.integrations.redash_client import RedashError
        from fastapi import HTTPException
        err = RedashError("bad query")
        err.status_code = 400
        mock_gc.return_value.run_query.side_effect = err
        with pytest.raises(HTTPException) as exc:
            run_query(RunQueryRequest(data_source_id=1, query="BAD"))
        assert exc.value.status_code == 422

    @patch("code_agents.routers.redash._get_client")
    def test_run_saved_query(self, mock_gc):
        from code_agents.routers.redash import run_saved_query, RunSavedQueryRequest
        mock_gc.return_value.run_saved_query.return_value = {"rows": []}
        result = run_saved_query(RunSavedQueryRequest(query_id=42))
        assert result == {"rows": []}

    @patch("code_agents.routers.redash._get_client")
    def test_list_data_sources(self, mock_gc):
        from code_agents.routers.redash import list_data_sources
        mock_gc.return_value.list_data_sources.return_value = [{"id": 1, "name": "prod"}]
        result = list_data_sources()
        assert len(result) == 1

    @patch("code_agents.routers.redash._get_client")
    def test_get_schema(self, mock_gc):
        from code_agents.routers.redash import get_schema
        mock_gc.return_value.get_schema.return_value = [{"table": "users", "columns": ["id", "name"]}]
        result = get_schema(1)
        assert result[0]["table"] == "users"


# ---------------------------------------------------------------------------
# Review Config
# ---------------------------------------------------------------------------


class TestReviewConfig:
    def test_defaults(self):
        from code_agents.cicd.review_config import ReviewConfig
        c = ReviewConfig()
        assert c.strictness == "standard"
        assert c.max_findings == 20

    def test_load_missing(self, tmp_path):
        from code_agents.cicd.review_config import load_review_config
        c = load_review_config(str(tmp_path))
        assert c.strictness == "standard"

    def test_load_valid(self, tmp_path):
        from code_agents.cicd.review_config import load_review_config
        cfg_dir = tmp_path / ".code-agents"
        cfg_dir.mkdir()
        (cfg_dir / "review.yaml").write_text(
            "strictness: strict\nignore_patterns:\n  - '*.md'\nfocus_areas:\n  - security\nmax_findings: 5\nauto_approve:\n  - 'docs/*'\nblock_severity: CRITICAL\n"
        )
        c = load_review_config(str(tmp_path))
        assert c.strictness == "strict"
        assert c.max_findings == 5
        assert "*.md" in c.ignore_patterns
        assert "security" in c.focus_areas

    def test_load_invalid_yaml(self, tmp_path):
        from code_agents.cicd.review_config import load_review_config
        cfg_dir = tmp_path / ".code-agents"
        cfg_dir.mkdir()
        (cfg_dir / "review.yaml").write_text("{{invalid yaml")
        c = load_review_config(str(tmp_path))
        assert c.strictness == "standard"

    def test_should_skip_file(self):
        from code_agents.cicd.review_config import should_skip_file, ReviewConfig
        c = ReviewConfig(ignore_patterns=["*.md", "tests/*"])
        assert should_skip_file("README.md", c) is True
        assert should_skip_file("tests/test_foo.py", c) is True
        assert should_skip_file("src/main.py", c) is False

    def test_is_auto_approve(self):
        from code_agents.cicd.review_config import is_auto_approve, ReviewConfig
        c = ReviewConfig(auto_approve=["docs/*", "*.md"])
        assert is_auto_approve(["docs/readme.md"], c) is True
        assert is_auto_approve(["docs/readme.md", "src/main.py"], c) is False
        assert is_auto_approve([], ReviewConfig()) is False

    def test_format_config_default(self):
        from code_agents.cicd.review_config import format_config_for_prompt, ReviewConfig
        assert format_config_for_prompt(ReviewConfig()) == ""

    def test_format_config_custom(self):
        from code_agents.cicd.review_config import format_config_for_prompt, ReviewConfig
        c = ReviewConfig(strictness="strict", focus_areas=["security"], ignore_patterns=["*.md"])
        result = format_config_for_prompt(c)
        assert "strict" in result
        assert "security" in result


# ---------------------------------------------------------------------------
# Agent Memory
# ---------------------------------------------------------------------------


class TestAgentMemory:
    def test_load_memory_missing(self, tmp_path):
        from code_agents.agent_system.agent_memory import load_memory
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            assert load_memory("test-agent") == ""

    def test_save_and_load(self, tmp_path):
        from code_agents.agent_system.agent_memory import save_memory, load_memory
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            save_memory("test-agent", "learned something")
            assert load_memory("test-agent") == "learned something"

    def test_append_memory(self, tmp_path):
        from code_agents.agent_system.agent_memory import append_memory, load_memory
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            append_memory("test-agent", "first learning")
            append_memory("test-agent", "second learning")
            content = load_memory("test-agent")
            assert "first learning" in content
            assert "second learning" in content

    def test_clear_memory(self, tmp_path):
        from code_agents.agent_system.agent_memory import save_memory, clear_memory, load_memory
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            save_memory("test-agent", "data")
            assert clear_memory("test-agent") is True
            assert load_memory("test-agent") == ""
            assert clear_memory("test-agent") is False

    def test_list_memories(self, tmp_path):
        from code_agents.agent_system.agent_memory import save_memory, list_memories
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            save_memory("agent-a", "line1\nline2")
            save_memory("agent-b", "line1")
            result = list_memories()
            assert result["agent-a"] == 2
            assert result["agent-b"] == 1

    def test_list_memories_empty(self, tmp_path):
        from code_agents.agent_system.agent_memory import list_memories
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path / "nonexistent"):
            assert list_memories() == {}

    def test_load_memory_os_error(self, tmp_path):
        from code_agents.agent_system.agent_memory import load_memory
        (tmp_path / "test-agent.md").write_text("data")
        with patch("code_agents.agent_system.agent_memory.MEMORY_DIR", tmp_path):
            with patch("pathlib.Path.read_text", side_effect=OSError("perm")):
                assert load_memory("test-agent") == ""


# ---------------------------------------------------------------------------
# Chat Welcome
# ---------------------------------------------------------------------------


class TestChatWelcome:
    def test_agent_roles_complete(self):
        from code_agents.chat.chat_welcome import AGENT_ROLES
        assert "code-reasoning" in AGENT_ROLES
        assert "code-writer" in AGENT_ROLES
        assert len(AGENT_ROLES) == 19

    def test_agent_welcome_complete(self):
        from code_agents.chat.chat_welcome import AGENT_WELCOME
        assert "code-reasoning" in AGENT_WELCOME
        for name, (title, caps, examples) in AGENT_WELCOME.items():
            assert isinstance(title, str)
            assert isinstance(caps, list)
            assert isinstance(examples, list)
            assert len(caps) >= 3

    def test_print_welcome(self, capsys):
        from code_agents.chat.chat_welcome import _print_welcome
        with patch("code_agents.chat.chat_welcome._print_welcome_raw"):
            _print_welcome("code-reasoning", "/tmp/my-project")

    def test_print_welcome_gita_error(self, capsys):
        from code_agents.chat.chat_welcome import _print_welcome
        with patch("code_agents.chat.chat_welcome._print_welcome_raw"):
            with patch("code_agents.domain.gita_shlokas.format_shloka_rainbow", side_effect=Exception("fail")):
                _print_welcome("code-reasoning", "/tmp/project")

    def test_select_agent_by_number(self):
        from code_agents.chat.chat_welcome import _select_agent
        agents = {"code-writer": "Code Writer", "code-reasoning": "Code Reasoning"}
        # Force fallback path (no tty)
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", return_value="1"):
                result = _select_agent(agents)
                assert result in agents

    def test_select_agent_by_name(self):
        from code_agents.chat.chat_welcome import _select_agent
        agents = {"code-writer": "Code Writer"}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", return_value="code-writer"):
                result = _select_agent(agents)
                assert result == "code-writer"

    def test_select_agent_cancel(self):
        from code_agents.chat.chat_welcome import _select_agent
        agents = {"code-writer": "Code Writer"}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", return_value="0"):
                result = _select_agent(agents)
                assert result is None

    def test_select_agent_eof(self):
        from code_agents.chat.chat_welcome import _select_agent
        agents = {"code-writer": "Code Writer"}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", side_effect=EOFError):
                result = _select_agent(agents)
                assert result is None
