"""Full coverage tests for redash_client.py — covers remaining uncovered lines."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from code_agents.integrations.redash_client import RedashClient, RedashError


class TestRedashClientCache:
    """Cover cache hit/miss/expiry paths."""

    def test_cache_hit(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        c._cache_set("key1", {"data": "cached"}, ttl=300)
        result = c._cache_get("key1")
        assert result == {"data": "cached"}

    def test_cache_miss(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        result = c._cache_get("nonexistent_key")
        assert result is None

    def test_cache_expired(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        # Set with negative TTL so it's already expired
        c._query_cache["expired_key"] = (time.monotonic() - 1, "old_data")
        result = c._cache_get("expired_key")
        assert result is None
        assert "expired_key" not in c._query_cache

    def test_run_query_cache_hit(self):
        """When cache has fresh data, skip HTTP call."""
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        cached_result = {"columns": [], "rows": [{"id": 1}], "metadata": {"runtime": 0.1}}
        cache_key = "run_query:1:SELECT 1:None"
        c._cache_set(cache_key, cached_result, ttl=300)

        # Should NOT call _request
        with patch.object(c, "_request") as mock_req:
            result = c.run_query(1, "SELECT 1")
        mock_req.assert_not_called()
        assert result == cached_result


class TestRedashClientRequest:
    def test_request_method(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        mock_resp = MagicMock()
        with patch.object(c._session, "request", return_value=mock_resp) as mock_req:
            c._request("GET", "/api/data_sources", timeout=5)
        mock_req.assert_called_once_with(
            "GET", "https://redash.example.com/api/data_sources", json=None, timeout=5
        )


class TestRedashClientRunQueryParameters:
    def test_run_query_with_parameters(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=1.0)

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 3, "query_result_id": 10}}

        result_resp = MagicMock()
        result_resp.status_code = 200
        result_resp.json.return_value = {
            "query_result": {
                "data": {"columns": [{"name": "x"}], "rows": [{"x": 1}]},
                "runtime": 0.2,
            }
        }

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            result = c.run_query(1, "SELECT * WHERE id = :id", parameters={"id": 42})
        assert result["rows"] == [{"x": 1}]

    def test_run_query_job_failure_no_error_message(self):
        """Job fails with no 'error' key — uses default message."""
        c = RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=1.0)

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 4}}  # failure, no error key

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp]):
            with pytest.raises(RedashError, match="Query execution failed"):
                c.run_query(1, "BAD SQL")


class TestRedashClientSavedQueryParameters:
    def test_run_saved_query_with_parameters(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=1.0)

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 3, "query_result_id": 10}}

        result_resp = MagicMock()
        result_resp.status_code = 200
        result_resp.json.return_value = {
            "query_result": {
                "data": {"columns": [{"name": "a"}], "rows": [{"a": 1}]},
                "runtime": 0.5,
            }
        }

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            result = c.run_saved_query(42, parameters={"env": "prod"})
        assert result["rows"] == [{"a": 1}]

    def test_run_saved_query_no_job_in_response(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        resp.text = "{}"
        with patch.object(c, "_request", return_value=resp):
            with pytest.raises(RedashError, match="no job"):
                c.run_saved_query(1)

    def test_run_saved_query_job_failure(self):
        c = RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=1.0)

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1, "error": "bad query"}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 4, "error": "bad query"}}

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp]):
            with pytest.raises(RedashError, match="bad query"):
                c.run_saved_query(42)


class TestRedashClientGetSchemaEdgeCases:
    def test_schema_with_non_dict_columns(self):
        """Column entries that are neither string nor dict."""
        c = RedashClient(base_url="https://redash.example.com", api_key="k")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "schema": [
                {"name": "table1", "columns": [42, True]},
            ]
        }
        with patch.object(c, "_request", return_value=mock_resp):
            result = c.get_schema(1)
        assert result[0]["columns"] == ["42", "True"]


class TestRedashClientLoginEdgeCases:
    def test_login_restores_content_type(self):
        """Content-Type header is restored after login."""
        c = RedashClient.__new__(RedashClient)
        c.base_url = "https://redash.example.com"
        c.username = "user"
        c.password = "pass"
        c.timeout = 30.0

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://redash.example.com/"
        mock_session.post.return_value = mock_resp
        mock_session.headers = {"Content-Type": "application/json"}
        c._session = mock_session

        c._login()
        assert "Content-Type" in c._session.headers


class TestRedashClientRunQuery201:
    def test_run_query_201_status(self):
        """201 status is also accepted for query_results POST."""
        c = RedashClient(base_url="https://redash.example.com", api_key="k", poll_interval=0.01, poll_timeout=1.0)

        post_resp = MagicMock()
        post_resp.status_code = 201
        post_resp.json.return_value = {"job": {"id": "j1", "status": 1}}
        post_resp.text = '{"job": {"id": "j1"}}'

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"job": {"id": "j1", "status": 3, "query_result_id": 5}}

        result_resp = MagicMock()
        result_resp.status_code = 200
        result_resp.json.return_value = {
            "query_result": {
                "data": {"columns": [], "rows": []},
                "runtime": 0.0,
            }
        }

        with patch.object(c, "_request", side_effect=[post_resp, poll_resp, result_resp]):
            result = c.run_query(1, "SELECT 1")
        assert result["rows"] == []
