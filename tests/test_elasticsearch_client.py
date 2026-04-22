"""Tests for elasticsearch_client.py — Elasticsearch client wrapper."""

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.integrations.elasticsearch_client import (
    ElasticsearchConnError,
    client_from_env,
    info,
    search,
)
from code_agents.integrations.elasticsearch_client import (
    _truthy,
    _as_dict,
)


# ---------------------------------------------------------------------------
# ElasticsearchConnError
# ---------------------------------------------------------------------------

class TestElasticsearchConnError:
    def test_basic(self):
        e = ElasticsearchConnError("fail")
        assert str(e) == "fail"
        assert e.status_code is None
        assert e.response is None

    def test_with_status(self):
        e = ElasticsearchConnError("not found", status_code=404, response={"error": "x"})
        assert e.status_code == 404
        assert e.response == {"error": "x"}


# ---------------------------------------------------------------------------
# _truthy
# ---------------------------------------------------------------------------

class TestTruthy:
    def test_true_values(self):
        for v in ("1", "true", "yes", "on", "  TRUE  ", "Yes"):
            assert _truthy(v) is True, f"Failed for {v!r}"

    def test_false_values(self):
        for v in ("0", "false", "no", "off", "random", ""):
            assert _truthy(v) is False, f"Failed for {v!r}"


# ---------------------------------------------------------------------------
# client_from_env
# ---------------------------------------------------------------------------

class TestClientFromEnv:
    def test_no_url_no_cloud_id_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ElasticsearchConnError, match="ELASTICSEARCH_URL"):
                client_from_env()

    def test_both_auth_methods_raises(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_API_KEY": "mykey",
            "ELASTICSEARCH_USERNAME": "user",
            "ELASTICSEARCH_PASSWORD": "pass",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ElasticsearchConnError, match="not both"):
                client_from_env()

    def test_url_with_api_key(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_API_KEY": "base64key",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                MockES.assert_called_once()
                call_kwargs = MockES.call_args
                assert call_kwargs.kwargs.get("api_key") == "base64key"

    def test_url_with_basic_auth(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_USERNAME": "user",
            "ELASTICSEARCH_PASSWORD": "pass",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args
                assert call_kwargs.kwargs.get("basic_auth") == ("user", "pass")

    def test_cloud_id(self):
        env = {
            "ELASTICSEARCH_CLOUD_ID": "my-cloud:abc123",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args
                assert call_kwargs.kwargs.get("cloud_id") == "my-cloud:abc123"

    def test_verify_ssl_false(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_VERIFY_SSL": "false",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args
                assert call_kwargs.kwargs.get("verify_certs") is False

    def test_ca_certs(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_CA_CERTS": "/path/to/ca.pem",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args
                assert call_kwargs.kwargs.get("ca_certs") == "/path/to/ca.pem"

    def test_multiple_urls(self):
        env = {
            "ELASTICSEARCH_URL": "http://host1:9200, http://host2:9200",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_args = MockES.call_args
                hosts = call_args.args[0]
                assert len(hosts) == 2

    def test_empty_url_after_parsing_raises(self):
        env = {
            "ELASTICSEARCH_URL": "  ,  , ",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ElasticsearchConnError, match="empty after parsing"):
                client_from_env()


# ---------------------------------------------------------------------------
# _as_dict
# ---------------------------------------------------------------------------

class TestAsDict:
    def test_dict_input(self):
        assert _as_dict({"a": 1}) == {"a": 1}

    def test_object_with_body(self):
        obj = MagicMock()
        obj.body = {"cluster": "test"}
        assert _as_dict(obj) == {"cluster": "test"}

    def test_non_dict_body(self):
        obj = MagicMock()
        obj.body = "not a dict"
        # Falls through to dict(resp) or {"raw": str(resp)}
        result = _as_dict(obj)
        assert isinstance(result, dict)

    def test_unconvertible(self):
        result = _as_dict(42)
        assert "raw" in result


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

class TestInfo:
    def test_success(self):
        es = MagicMock()
        es.info.return_value = {"cluster_name": "test"}
        result = info(es)
        assert result == {"cluster_name": "test"}

    def test_api_error(self):
        from elasticsearch.exceptions import ApiError
        es = MagicMock()
        meta = MagicMock()
        meta.status = 401
        es.info.side_effect = ApiError(message="unauthorized", meta=meta, body={})
        with pytest.raises(ElasticsearchConnError):
            info(es)

    def test_generic_error(self):
        es = MagicMock()
        es.info.side_effect = RuntimeError("connection refused")
        with pytest.raises(ElasticsearchConnError):
            info(es)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_with_body(self):
        es = MagicMock()
        es.search.return_value = {"hits": {"total": 5}}
        result = search(es, "my-index", {"query": {"match_all": {}}})
        assert "hits" in result
        es.search.assert_called_once_with(index="my-index", body={"query": {"match_all": {}}})

    def test_empty_body_uses_match_all(self):
        es = MagicMock()
        es.search.return_value = {"hits": {}}
        search(es, "idx", {})
        es.search.assert_called_once_with(index="idx", query={"match_all": {}})

    def test_api_error(self):
        from elasticsearch.exceptions import ApiError
        es = MagicMock()
        meta = MagicMock()
        meta.status = 400
        es.search.side_effect = ApiError(message="bad query", meta=meta, body={})
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {"invalid": True}})

    def test_generic_error(self):
        es = MagicMock()
        es.search.side_effect = Exception("timeout")
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {}})
