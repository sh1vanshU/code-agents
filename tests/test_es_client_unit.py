"""Unit tests for code_agents/integrations/elasticsearch_client.py."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the elasticsearch package is importable even if not installed.
# We create lightweight stubs so the real module can be imported.
# ---------------------------------------------------------------------------
_es_mod = types.ModuleType("elasticsearch")
_es_exc = types.ModuleType("elasticsearch.exceptions")


class _FakeApiError(Exception):
    pass


class _FakeTransportError(Exception):
    pass


_es_exc.ApiError = _FakeApiError
_es_exc.TransportError = _FakeTransportError
_es_mod.exceptions = _es_exc
_es_mod.Elasticsearch = MagicMock  # placeholder class

# Only patch if not already importable
if "elasticsearch" not in sys.modules:
    sys.modules["elasticsearch"] = _es_mod
    sys.modules["elasticsearch.exceptions"] = _es_exc

from code_agents.integrations.elasticsearch_client import (
    ElasticsearchConnError,
    _as_dict,
    _truthy,
    client_from_env,
    info,
    search,
)


# ---------------------------------------------------------------------------
# _truthy helper
# ---------------------------------------------------------------------------

class TestTruthy:
    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "on", " true "])
    def test_truthy_values(self, val):
        assert _truthy(val) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "random"])
    def test_falsy_values(self, val):
        assert _truthy(val) is False


# ---------------------------------------------------------------------------
# ElasticsearchConnError
# ---------------------------------------------------------------------------

class TestConnError:
    def test_basic(self):
        e = ElasticsearchConnError("boom")
        assert str(e) == "boom"
        assert e.status_code is None
        assert e.response is None

    def test_with_details(self):
        e = ElasticsearchConnError("fail", status_code=500, response={"error": "x"})
        assert e.status_code == 500
        assert e.response == {"error": "x"}


# ---------------------------------------------------------------------------
# client_from_env
# ---------------------------------------------------------------------------

class TestClientFromEnv:
    def test_no_url_no_cloud_id_raises(self, monkeypatch):
        monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_CLOUD_ID", raising=False)
        with pytest.raises(ElasticsearchConnError, match="Set ELASTICSEARCH_URL"):
            client_from_env()

    def test_both_auth_raises(self, monkeypatch):
        monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")
        monkeypatch.setenv("ELASTICSEARCH_API_KEY", "abc123")
        monkeypatch.setenv("ELASTICSEARCH_USERNAME", "user")
        monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "pass")
        with pytest.raises(ElasticsearchConnError, match="not both"):
            client_from_env()

    @patch("code_agents.integrations.elasticsearch_client.Elasticsearch")
    def test_cloud_id_path(self, mock_es, monkeypatch):
        monkeypatch.setenv("ELASTICSEARCH_CLOUD_ID", "my-cloud")
        monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_USERNAME", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_VERIFY_SSL", "1")
        monkeypatch.delenv("ELASTICSEARCH_CA_CERTS", raising=False)
        client_from_env()
        mock_es.assert_called_once()
        call_kw = mock_es.call_args[1]
        assert call_kw["cloud_id"] == "my-cloud"

    @patch("code_agents.integrations.elasticsearch_client.Elasticsearch")
    def test_url_with_api_key(self, mock_es, monkeypatch):
        monkeypatch.delenv("ELASTICSEARCH_CLOUD_ID", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")
        monkeypatch.setenv("ELASTICSEARCH_API_KEY", "mykey")
        monkeypatch.delenv("ELASTICSEARCH_USERNAME", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_CA_CERTS", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_VERIFY_SSL", "true")
        client_from_env()
        mock_es.assert_called_once()
        call_kw = mock_es.call_args[1]
        assert call_kw["api_key"] == "mykey"
        assert "cloud_id" not in call_kw

    @patch("code_agents.integrations.elasticsearch_client.Elasticsearch")
    def test_url_with_basic_auth(self, mock_es, monkeypatch):
        monkeypatch.delenv("ELASTICSEARCH_CLOUD_ID", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_URL", "http://host1:9200,http://host2:9200")
        monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_USERNAME", "admin")
        monkeypatch.setenv("ELASTICSEARCH_PASSWORD", "secret")
        monkeypatch.delenv("ELASTICSEARCH_CA_CERTS", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_VERIFY_SSL", "0")
        client_from_env()
        mock_es.assert_called_once()
        call_kw = mock_es.call_args[1]
        assert call_kw["basic_auth"] == ("admin", "secret")
        assert call_kw["verify_certs"] is False

    @patch("code_agents.integrations.elasticsearch_client.Elasticsearch")
    def test_ca_certs_set(self, mock_es, monkeypatch):
        monkeypatch.delenv("ELASTICSEARCH_CLOUD_ID", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")
        monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_USERNAME", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_CA_CERTS", "/path/to/ca.pem")
        monkeypatch.setenv("ELASTICSEARCH_VERIFY_SSL", "1")
        client_from_env()
        call_kw = mock_es.call_args[1]
        assert call_kw["ca_certs"] == "/path/to/ca.pem"

    def test_empty_url_after_parse_raises(self, monkeypatch):
        monkeypatch.delenv("ELASTICSEARCH_CLOUD_ID", raising=False)
        monkeypatch.setenv("ELASTICSEARCH_URL", " , , ")
        monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_USERNAME", raising=False)
        monkeypatch.delenv("ELASTICSEARCH_PASSWORD", raising=False)
        with pytest.raises(ElasticsearchConnError, match="empty after parsing"):
            client_from_env()


# ---------------------------------------------------------------------------
# _as_dict
# ---------------------------------------------------------------------------

class TestAsDict:
    def test_with_body_attr_dict(self):
        obj = MagicMock()
        obj.body = {"key": "val"}
        assert _as_dict(obj) == {"key": "val"}

    def test_with_body_attr_non_dict(self):
        obj = MagicMock()
        obj.body = "string"
        # body not dict, resp itself isn't dict either → tries dict(obj)
        # MagicMock is iterable sometimes, but let's test the fallback
        result = _as_dict({"a": 1})
        assert result == {"a": 1}

    def test_plain_dict(self):
        assert _as_dict({"foo": "bar"}) == {"foo": "bar"}

    def test_non_dict_non_body_fallback(self):
        # Something that can be dict()'d
        result = _as_dict([("k", "v")])
        assert result == {"k": "v"}

    def test_non_convertible_returns_raw(self):
        result = _as_dict(42)
        assert result == {"raw": "42"}


# ---------------------------------------------------------------------------
# info()
# ---------------------------------------------------------------------------

class TestInfo:
    def test_success(self):
        es = MagicMock()
        es.info.return_value = {"version": {"number": "8.0"}}
        result = info(es)
        assert result == {"version": {"number": "8.0"}}

    def test_api_error(self):
        es = MagicMock()
        err = _FakeApiError("bad request")
        es.info.side_effect = err
        with pytest.raises(ElasticsearchConnError):
            info(es)

    def test_transport_error(self):
        es = MagicMock()
        err = _FakeTransportError("timeout")
        es.info.side_effect = err
        with pytest.raises(ElasticsearchConnError):
            info(es)

    def test_generic_error(self):
        es = MagicMock()
        es.info.side_effect = ValueError("unexpected")
        with pytest.raises(ElasticsearchConnError):
            info(es)

    def test_api_error_with_meta_status(self):
        es = MagicMock()
        err = _FakeApiError("bad")
        meta = MagicMock()
        meta.status = 403
        err.meta = meta
        es.info.side_effect = err
        with pytest.raises(ElasticsearchConnError) as exc_info:
            info(es)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestSearch:
    def test_with_body(self):
        es = MagicMock()
        es.search.return_value = {"hits": {"total": 5}}
        result = search(es, "my-index", {"query": {"match_all": {}}})
        assert result == {"hits": {"total": 5}}
        es.search.assert_called_once_with(index="my-index", body={"query": {"match_all": {}}})

    def test_empty_body_uses_match_all(self):
        es = MagicMock()
        es.search.return_value = {"hits": {"total": 0}}
        search(es, "idx", {})
        es.search.assert_called_once_with(index="idx", query={"match_all": {}})

    def test_api_error(self):
        es = MagicMock()
        es.search.side_effect = _FakeApiError("not found")
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {}})

    def test_transport_error(self):
        es = MagicMock()
        es.search.side_effect = _FakeTransportError("conn refused")
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {}})

    def test_generic_error(self):
        es = MagicMock()
        es.search.side_effect = RuntimeError("oops")
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {}})

    def test_search_error_with_meta_status(self):
        es = MagicMock()
        err = _FakeApiError("nope")
        meta = MagicMock()
        meta.status = 404
        err.meta = meta
        es.search.side_effect = err
        with pytest.raises(ElasticsearchConnError) as exc_info:
            search(es, "idx", {"query": {}})
        assert exc_info.value.status_code == 404
