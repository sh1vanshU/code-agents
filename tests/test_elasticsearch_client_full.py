"""Full coverage tests for elasticsearch_client.py — covers remaining uncovered lines."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from code_agents.integrations.elasticsearch_client import (
    ElasticsearchConnError,
    _truthy,
    client_from_env,
    _as_dict,
    info,
    search,
)


class TestClientFromEnvEdgeCases:
    def test_url_no_auth(self):
        """URL without any auth method should create client with no auth."""
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args.kwargs
                assert "api_key" not in call_kwargs
                assert "basic_auth" not in call_kwargs

    def test_cloud_id_with_api_key(self):
        """Cloud ID with API key auth."""
        env = {
            "ELASTICSEARCH_CLOUD_ID": "my-cloud:abc",
            "ELASTICSEARCH_API_KEY": "base64key",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args.kwargs
                assert call_kwargs["cloud_id"] == "my-cloud:abc"
                assert call_kwargs["api_key"] == "base64key"

    def test_verify_ssl_true_by_default(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                call_kwargs = MockES.call_args.kwargs
                assert call_kwargs["verify_certs"] is True

    def test_single_url(self):
        env = {
            "ELASTICSEARCH_URL": "http://localhost:9200",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("code_agents.integrations.elasticsearch_client.Elasticsearch") as MockES:
                client_from_env()
                hosts = MockES.call_args.args[0]
                assert hosts == ["http://localhost:9200"]


class TestAsDictEdgeCases:
    def test_dict_like_object(self):
        """Object that can be converted to dict via dict()."""
        obj = MagicMock()
        obj.body = [1, 2]  # Not a dict body
        obj.__iter__ = MagicMock(return_value=iter([("key", "val")]))
        result = _as_dict(obj)
        assert isinstance(result, dict)

    def test_body_is_none(self):
        """Object with body=None falls through to dict() or raw."""
        obj = MagicMock()
        obj.body = None
        # MagicMock is dict-able (via __iter__), so should produce something
        result = _as_dict(obj)
        assert isinstance(result, dict)


class TestSearchEdgeCases:
    def test_search_with_transport_error(self):
        from elasticsearch.exceptions import TransportError
        es = MagicMock()
        err = TransportError("Connection timeout")
        # TransportError may not have .meta
        es.search.side_effect = err
        with pytest.raises(ElasticsearchConnError):
            search(es, "idx", {"query": {"match_all": {}}})

    def test_info_with_transport_error(self):
        from elasticsearch.exceptions import TransportError
        es = MagicMock()
        es.info.side_effect = TransportError("timeout")
        with pytest.raises(ElasticsearchConnError):
            info(es)

    def test_info_with_api_error_no_status_in_meta(self):
        from elasticsearch.exceptions import ApiError
        es = MagicMock()
        meta = MagicMock()
        meta.status = None
        err = ApiError(message="fail", meta=meta, body={})
        es.info.side_effect = err
        with pytest.raises(ElasticsearchConnError) as exc:
            info(es)
        assert exc.value.status_code is None

    def test_search_with_api_error_no_status_in_meta(self):
        from elasticsearch.exceptions import ApiError
        es = MagicMock()
        meta = MagicMock()
        meta.status = None
        err = ApiError(message="fail", meta=meta, body={})
        es.search.side_effect = err
        with pytest.raises(ElasticsearchConnError) as exc:
            search(es, "idx", {"query": {}})
        assert exc.value.status_code is None
