"""Final coverage push — tests for small remaining gaps to reach 80%."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Elasticsearch Router
# ---------------------------------------------------------------------------


class TestElasticsearchRouter:
    def test_enabled_with_url(self):
        from code_agents.routers.elasticsearch import _enabled
        with patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://es:9200"}):
            assert _enabled() is True

    def test_enabled_with_cloud_id(self):
        from code_agents.routers.elasticsearch import _enabled
        with patch.dict(os.environ, {"ELASTICSEARCH_CLOUD_ID": "cloud:abc"}, clear=True):
            assert _enabled() is True

    def test_not_enabled(self):
        from code_agents.routers.elasticsearch import _enabled
        with patch.dict(os.environ, {}, clear=True):
            assert _enabled() is False

    def test_client_or_503_disabled(self):
        from code_agents.routers.elasticsearch import _client_or_503
        from fastapi import HTTPException
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc:
                _client_or_503()
            assert exc.value.status_code == 503

    def test_client_or_503_conn_error(self):
        from code_agents.routers.elasticsearch import _client_or_503
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        from fastapi import HTTPException
        with patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://es:9200"}):
            with patch("code_agents.routers.elasticsearch.client_from_env",
                       side_effect=ElasticsearchConnError("conn refused")):
                with pytest.raises(HTTPException) as exc:
                    _client_or_503()
                assert exc.value.status_code == 503

    def test_cluster_info(self):
        from code_agents.routers.elasticsearch import cluster_info
        with patch("code_agents.routers.elasticsearch._client_or_503") as mock_client:
            with patch("code_agents.routers.elasticsearch.info",
                       return_value={"cluster_name": "test"}):
                result = cluster_info()
                assert result["cluster_name"] == "test"

    def test_cluster_info_error(self):
        from code_agents.routers.elasticsearch import cluster_info
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        from fastapi import HTTPException
        with patch("code_agents.routers.elasticsearch._client_or_503"):
            err = ElasticsearchConnError("timeout")
            err.status_code = None
            with patch("code_agents.routers.elasticsearch.info", side_effect=err):
                with pytest.raises(HTTPException) as exc:
                    cluster_info()
                assert exc.value.status_code == 502

    def test_run_search(self):
        from code_agents.routers.elasticsearch import run_search, SearchRequest
        with patch("code_agents.routers.elasticsearch._client_or_503"):
            with patch("code_agents.routers.elasticsearch.search",
                       return_value={"hits": {"total": 5}}):
                result = run_search(SearchRequest(index="logs-*", body={"query": {"match_all": {}}}))
                assert result["hits"]["total"] == 5

    def test_run_search_error(self):
        from code_agents.routers.elasticsearch import run_search, SearchRequest
        from code_agents.integrations.elasticsearch_client import ElasticsearchConnError
        from fastapi import HTTPException
        with patch("code_agents.routers.elasticsearch._client_or_503"):
            err = ElasticsearchConnError("bad query")
            err.status_code = 400
            with patch("code_agents.routers.elasticsearch.search", side_effect=err):
                with pytest.raises(HTTPException) as exc:
                    run_search(SearchRequest())
                assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Kibana Router
# ---------------------------------------------------------------------------


class TestKibanaRouter:
    def test_get_client_no_url(self):
        from code_agents.routers.kibana import _get_client
        from fastapi import HTTPException
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc:
                _get_client()
            assert exc.value.status_code == 503

    def test_get_client_with_url(self):
        from code_agents.routers.kibana import _get_client
        with patch.dict(os.environ, {"KIBANA_URL": "http://kibana:5601"}):
            client = _get_client()
            assert client.kibana_url == "http://kibana:5601"

    @patch("code_agents.routers.kibana._get_client")
    def test_list_indices(self, mock_gc):
        from code_agents.routers.kibana import list_indices
        mock_gc.return_value.get_indices = AsyncMock(return_value=["logs-*", "metrics-*"])
        result = asyncio.run(list_indices())
        assert result["indices"] == ["logs-*", "metrics-*"]

    @patch("code_agents.routers.kibana._get_client")
    def test_list_indices_error(self, mock_gc):
        from code_agents.routers.kibana import list_indices
        from code_agents.cicd.kibana_client import KibanaError
        from fastapi import HTTPException
        mock_gc.return_value.get_indices = AsyncMock(side_effect=KibanaError("fail", status_code=502))
        with pytest.raises(HTTPException):
            asyncio.run(list_indices())

    @patch("code_agents.routers.kibana._get_client")
    def test_search_logs(self, mock_gc):
        from code_agents.routers.kibana import search_logs, SearchRequest
        mock_gc.return_value.search_logs = AsyncMock(return_value=[{"msg": "error"}])
        result = asyncio.run(search_logs(SearchRequest()))
        assert result["total"] == 1

    @patch("code_agents.routers.kibana._get_client")
    def test_search_logs_error(self, mock_gc):
        from code_agents.routers.kibana import search_logs, SearchRequest
        from code_agents.cicd.kibana_client import KibanaError
        from fastapi import HTTPException
        mock_gc.return_value.search_logs = AsyncMock(side_effect=KibanaError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(search_logs(SearchRequest()))

    @patch("code_agents.routers.kibana._get_client")
    def test_error_summary(self, mock_gc):
        from code_agents.routers.kibana import error_summary, ErrorSummaryRequest
        mock_gc.return_value.error_summary = AsyncMock(return_value=[{"pattern": "NPE", "count": 5}])
        result = asyncio.run(error_summary(ErrorSummaryRequest()))
        assert result["total_patterns"] == 1

    @patch("code_agents.routers.kibana._get_client")
    def test_error_summary_error(self, mock_gc):
        from code_agents.routers.kibana import error_summary, ErrorSummaryRequest
        from code_agents.cicd.kibana_client import KibanaError
        from fastapi import HTTPException
        mock_gc.return_value.error_summary = AsyncMock(side_effect=KibanaError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(error_summary(ErrorSummaryRequest()))


# ---------------------------------------------------------------------------
# CLI Helpers
# ---------------------------------------------------------------------------


class TestCliHelpers:
    def test_find_code_agents_home(self):
        from code_agents.cli.cli_helpers import _find_code_agents_home
        home = _find_code_agents_home()
        assert home.is_dir()

    def test_user_cwd_env(self):
        from code_agents.cli.cli_helpers import _user_cwd
        with patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/custom"}):
            assert _user_cwd() == "/tmp/custom"

    def test_user_cwd_default(self):
        from code_agents.cli.cli_helpers import _user_cwd
        with patch.dict(os.environ, {}, clear=True):
            result = _user_cwd()
            assert os.path.isdir(result)

    def test_load_env(self):
        from code_agents.cli.cli_helpers import _load_env
        with patch("code_agents.core.env_loader.load_all_env"):
            _load_env()

    def test_colors(self):
        from code_agents.cli.cli_helpers import _colors
        bold, green, yellow, red, cyan, dim = _colors()
        assert callable(bold)
        assert callable(red)

    def test_api_get_success(self):
        from code_agents.cli.cli_helpers import _api_get
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        with patch("httpx.get", return_value=mock_resp):
            result = _api_get("/health")
            assert result == {"status": "ok"}

    def test_api_get_error(self):
        from code_agents.cli.cli_helpers import _api_get
        with patch("httpx.get", side_effect=Exception("conn refused")):
            assert _api_get("/health") is None

    def test_api_post_success(self):
        from code_agents.cli.cli_helpers import _api_post
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "ok"}
        with patch("httpx.post", return_value=mock_resp):
            result = _api_post("/api/run", {"data": 1})
            assert result == {"result": "ok"}

    def test_api_post_error(self, capsys):
        from code_agents.cli.cli_helpers import _api_post
        with patch("httpx.post", side_effect=Exception("timeout")):
            result = _api_post("/api/run")
            assert result is None

    def test_prompt_yes_no_default_yes(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value=""):
            assert prompt_yes_no("continue?") is True

    def test_prompt_yes_no_no(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value="n"):
            assert prompt_yes_no("continue?") is False

    def test_prompt_yes_no_eof(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", side_effect=EOFError):
            assert prompt_yes_no("continue?", default=False) is False

    def test_check_workspace_trust(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        assert _check_workspace_trust("/tmp/repo") is True

    def test_check_workspace_trust_claude_cli(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}):
            assert _check_workspace_trust("/tmp/repo") is True


# ---------------------------------------------------------------------------
# Bug Patterns — boost from 63% to higher
# ---------------------------------------------------------------------------


class TestBugPatternsExtra:
    def test_detector_init(self, tmp_path):
        from code_agents.analysis.bug_patterns import BugPatternDetector
        store = tmp_path / "bugs.json"
        d = BugPatternDetector(repo_path=str(tmp_path), store_path=store)
        assert d.patterns == []

    def test_detector_check_diff(self, tmp_path):
        from code_agents.analysis.bug_patterns import BugPatternDetector
        store = tmp_path / "bugs.json"
        d = BugPatternDetector(repo_path=str(tmp_path), store_path=store)
        diff = "+    result = None\n+    result.strip()\n"
        findings = d.check_diff(diff)
        assert isinstance(findings, list)

    def test_detector_add_pattern(self, tmp_path):
        from code_agents.analysis.bug_patterns import BugPatternDetector
        store = tmp_path / "bugs.json"
        d = BugPatternDetector(repo_path=str(tmp_path), store_path=store)
        p = d.add_pattern("null_check", "Missing null check")
        assert p.pattern == "null_check"
        assert len(d.patterns) == 1

    def test_format_bug_warnings_empty(self):
        from code_agents.analysis.bug_patterns import format_bug_warnings
        output = format_bug_warnings([])
        assert "No" in output or output == "" or "bug" in output.lower()

    def test_format_bug_warnings_with_items(self):
        from code_agents.analysis.bug_patterns import format_bug_warnings, BugPattern
        patterns = [
            BugPattern(pattern="null_deref", description="NPE risk", occurrences=3),
        ]
        output = format_bug_warnings(patterns)
        assert "NPE risk" in output


# ---------------------------------------------------------------------------
# Telemetry Router
# ---------------------------------------------------------------------------


class TestTelemetryRouter:
    @patch("code_agents.routers.telemetry.is_enabled", return_value=False)
    def test_summary_disabled(self, mock_en):
        from code_agents.routers.telemetry import summary
        result = asyncio.run(summary())
        assert result == {"enabled": False}

    @patch("code_agents.routers.telemetry.is_enabled", return_value=True)
    @patch("code_agents.routers.telemetry.get_summary", return_value={"total": 100})
    def test_summary_enabled(self, mock_sum, mock_en):
        from code_agents.routers.telemetry import summary
        result = asyncio.run(summary(days=7))
        assert result["total"] == 100

    @patch("code_agents.routers.telemetry.is_enabled", return_value=False)
    def test_agents_disabled(self, mock_en):
        from code_agents.routers.telemetry import agents
        result = asyncio.run(agents())
        assert result == {"enabled": False}

    @patch("code_agents.routers.telemetry.is_enabled", return_value=True)
    @patch("code_agents.routers.telemetry.get_agent_usage", return_value={"code-writer": 50})
    def test_agents_enabled(self, mock_usage, mock_en):
        from code_agents.routers.telemetry import agents
        result = asyncio.run(agents())
        assert "code-writer" in result

    @patch("code_agents.routers.telemetry.is_enabled", return_value=False)
    def test_commands_disabled(self, mock_en):
        from code_agents.routers.telemetry import commands
        result = asyncio.run(commands())
        assert result == {"enabled": False}

    @patch("code_agents.routers.telemetry.is_enabled", return_value=True)
    @patch("code_agents.routers.telemetry.get_top_commands", return_value=["/help"])
    def test_commands_enabled(self, mock_cmds, mock_en):
        from code_agents.routers.telemetry import commands
        result = asyncio.run(commands())
        assert "/help" in result

    @patch("code_agents.routers.telemetry.is_enabled", return_value=False)
    def test_errors_disabled(self, mock_en):
        from code_agents.routers.telemetry import errors
        result = asyncio.run(errors())
        assert result == {"enabled": False}

    @patch("code_agents.routers.telemetry.is_enabled", return_value=True)
    @patch("code_agents.routers.telemetry.get_error_summary", return_value={"count": 3})
    def test_errors_enabled(self, mock_errs, mock_en):
        from code_agents.routers.telemetry import errors
        result = asyncio.run(errors())
        assert result["count"] == 3


# ---------------------------------------------------------------------------
# Agents List Router
# ---------------------------------------------------------------------------


class TestAgentsListRouter:
    def test_model_entry(self):
        from code_agents.routers.agents_list import _model_entry
        mock_agent = MagicMock()
        mock_agent.name = "code-writer"
        mock_agent.backend = "cursor"
        entry = _model_entry(mock_agent, 1000)
        assert entry["id"] == "code-writer"
        assert entry["owned_by"] == "cursor"

    @patch("code_agents.routers.agents_list.agent_loader")
    def test_list_agents(self, mock_loader):
        from code_agents.routers.agents_list import list_agents
        mock_agent = MagicMock()
        mock_agent.name = "code-writer"
        mock_agent.display_name = "Code Writer"
        mock_agent.backend = "cursor"
        mock_agent.model = "Composer 2 Fast"
        mock_loader.list_agents.return_value = [mock_agent]
        result = list_agents()
        assert result["object"] == "list"
        assert len(result["data"]) == 1

    @patch("code_agents.routers.agents_list.agent_loader")
    def test_list_models(self, mock_loader):
        from code_agents.routers.agents_list import list_models
        mock_agent = MagicMock()
        mock_agent.name = "code-reasoning"
        mock_agent.backend = "cursor"
        mock_loader.list_agents.return_value = [mock_agent]
        result = list_models()
        assert result["object"] == "list"

    @patch("code_agents.routers.agents_list.agent_loader")
    def test_list_agent_models_found(self, mock_loader):
        from code_agents.routers.agents_list import list_agent_models
        mock_agent = MagicMock()
        mock_agent.name = "code-writer"
        mock_agent.backend = "cursor"
        mock_loader.get.return_value = mock_agent
        result = list_agent_models("code-writer")
        assert result["data"][0]["id"] == "code-writer"

    @patch("code_agents.routers.agents_list.agent_loader")
    def test_list_agent_models_not_found(self, mock_loader):
        from code_agents.routers.agents_list import list_agent_models
        from fastapi import HTTPException
        mock_loader.get.return_value = None
        mock_loader.list_agents.return_value = []
        with pytest.raises(HTTPException) as exc:
            list_agent_models("nonexistent")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Public URLs
# ---------------------------------------------------------------------------


class TestPublicUrls:
    def test_default_url(self):
        from code_agents.core.public_urls import code_agents_public_base_url
        with patch.dict(os.environ, {}, clear=True):
            result = code_agents_public_base_url()
            assert "127.0.0.1" in result

    def test_custom_url(self):
        from code_agents.core.public_urls import code_agents_public_base_url
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "https://myserver.com/"}):
            result = code_agents_public_base_url()
            assert result == "https://myserver.com"

    def test_atlassian_site_url(self):
        from code_agents.core.public_urls import atlassian_cloud_site_url
        with patch.dict(os.environ, {"ATLASSIAN_CLOUD_SITE_URL": "https://company.atlassian.net/"}):
            result = atlassian_cloud_site_url()
            assert result == "https://company.atlassian.net"

    def test_atlassian_site_url_empty(self):
        from code_agents.core.public_urls import atlassian_cloud_site_url
        with patch.dict(os.environ, {}, clear=True):
            assert atlassian_cloud_site_url() is None


# ---------------------------------------------------------------------------
# Completions _handle_completions
# ---------------------------------------------------------------------------


class TestHandleCompletions:
    def test_no_messages(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest
        from fastapi import HTTPException
        agent = MagicMock()
        req = CompletionRequest(model="x", messages=[])
        with pytest.raises(HTTPException) as exc:
            asyncio.run(_handle_completions(agent, req))
        assert exc.value.status_code == 400

    def test_stream_mode(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        from fastapi.responses import StreamingResponse
        agent = MagicMock(name="code-writer", backend="cursor", model="m")
        req = CompletionRequest(model="x", messages=[Message(role="user", content="hi")], stream=True)
        with patch("code_agents.routers.completions.stream_response"):
            result = asyncio.run(_handle_completions(agent, req))
            assert isinstance(result, StreamingResponse)

    def test_non_stream_success(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        agent = MagicMock(name="code-writer", backend="cursor", model="m")
        req = CompletionRequest(model="x", messages=[Message(role="user", content="hi")], stream=False)
        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock,
                   return_value={"choices": [{"text": "hello"}]}):
            result = asyncio.run(_handle_completions(agent, req))
            assert result["choices"][0]["text"] == "hello"

    def test_non_stream_error(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        agent = MagicMock(name="code-writer", backend="cursor", model="m")
        req = CompletionRequest(model="x", messages=[Message(role="user", content="hi")], stream=False)
        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock,
                   side_effect=RuntimeError("backend down")):
            with patch("code_agents.routers.completions.unwrap_process_error", return_value=None):
                with pytest.raises(RuntimeError):
                    asyncio.run(_handle_completions(agent, req))

    def test_long_prompt_preview(self):
        from code_agents.routers.completions import _handle_completions
        from code_agents.core.models import CompletionRequest, Message
        agent = MagicMock(name="code-writer", backend="cursor", model="m")
        long_msg = "x" * 200
        req = CompletionRequest(model="x", messages=[Message(role="user", content=long_msg)], stream=False)
        with patch("code_agents.routers.completions.collect_response", new_callable=AsyncMock,
                   return_value={"choices": []}):
            result = asyncio.run(_handle_completions(agent, req))
            assert result is not None


# ---------------------------------------------------------------------------
# More Router error paths
# ---------------------------------------------------------------------------


class TestRouterErrorPaths:
    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_pod_logs_error(self, mock_gc):
        from code_agents.routers.k8s import get_pod_logs
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_pod_logs = AsyncMock(side_effect=K8sError("pod not found"))
        with pytest.raises(HTTPException):
            asyncio.run(get_pod_logs("missing-pod"))

    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_describe_error(self, mock_gc):
        from code_agents.routers.k8s import describe_pod
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_pod_describe = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(describe_pod("pod"))

    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_deployments_error(self, mock_gc):
        from code_agents.routers.k8s import list_deployments
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_deployments = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(list_deployments())

    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_events_error(self, mock_gc):
        from code_agents.routers.k8s import list_events
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_events = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(list_events())

    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_namespaces_error(self, mock_gc):
        from code_agents.routers.k8s import list_namespaces
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_namespaces = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(list_namespaces())

    @patch("code_agents.routers.k8s._get_client")
    def test_k8s_contexts_error(self, mock_gc):
        from code_agents.routers.k8s import list_contexts
        from code_agents.cicd.k8s_client import K8sError
        from fastapi import HTTPException
        mock_gc.return_value.get_contexts = AsyncMock(side_effect=K8sError("fail"))
        with pytest.raises(HTTPException):
            asyncio.run(list_contexts())

    @patch("code_agents.routers.testing._get_client")
    def test_testing_coverage_error(self, mock_gc):
        from code_agents.routers.testing import get_coverage
        from code_agents.cicd.testing_client import TestingError
        from fastapi import HTTPException
        mock_gc.return_value.get_coverage = AsyncMock(side_effect=TestingError("no xml"))
        with pytest.raises(HTTPException):
            asyncio.run(get_coverage())

    @patch("code_agents.routers.testing._get_client")
    def test_testing_gaps_error(self, mock_gc):
        from code_agents.routers.testing import get_coverage_gaps
        from code_agents.cicd.testing_client import TestingError
        from fastapi import HTTPException
        mock_gc.return_value.get_coverage_gaps = AsyncMock(side_effect=TestingError("no data"))
        with pytest.raises(HTTPException):
            asyncio.run(get_coverage_gaps())

    @patch("code_agents.routers.redash._get_client")
    def test_redash_saved_query_error(self, mock_gc):
        from code_agents.routers.redash import run_saved_query, RunSavedQueryRequest
        from code_agents.integrations.redash_client import RedashError
        from fastapi import HTTPException
        err = RedashError("not found")
        err.status_code = 404
        mock_gc.return_value.run_saved_query.side_effect = err
        with pytest.raises(HTTPException):
            run_saved_query(RunSavedQueryRequest(query_id=999))

    @patch("code_agents.routers.redash._get_client")
    def test_redash_list_ds_error(self, mock_gc):
        from code_agents.routers.redash import list_data_sources
        from code_agents.integrations.redash_client import RedashError
        from fastapi import HTTPException
        err = RedashError("fail")
        err.status_code = 500
        mock_gc.return_value.list_data_sources.side_effect = err
        with pytest.raises(HTTPException):
            list_data_sources()

    @patch("code_agents.routers.redash._get_client")
    def test_redash_schema_error(self, mock_gc):
        from code_agents.routers.redash import get_schema
        from code_agents.integrations.redash_client import RedashError
        from fastapi import HTTPException
        err = RedashError("fail")
        err.status_code = 500
        mock_gc.return_value.get_schema.side_effect = err
        with pytest.raises(HTTPException):
            get_schema(1)


