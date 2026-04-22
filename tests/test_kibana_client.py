"""Tests for kibana_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.kibana_client import KibanaClient, KibanaError


class TestKibanaClientInit:
    def test_defaults(self):
        c = KibanaClient()
        assert c.kibana_url == ""
        assert c.username == ""
        assert c.password == ""
        assert c.timeout == 30.0

    def test_custom_init(self):
        c = KibanaClient(
            kibana_url="https://kibana.example.com/",
            username="admin",
            password="secret",
            timeout=60.0,
        )
        assert c.kibana_url == "https://kibana.example.com"
        assert c.username == "admin"
        assert c.password == "secret"
        assert c.timeout == 60.0

    def test_strips_trailing_slash(self):
        c = KibanaClient(kibana_url="https://kibana.example.com/")
        assert c.kibana_url == "https://kibana.example.com"


class TestKibanaClientHttpClient:
    def test_client_with_auth(self):
        c = KibanaClient(kibana_url="https://kibana.example.com", username="u", password="p")
        client = c._client()
        # httpx.AsyncClient with auth set
        assert client is not None

    def test_client_without_auth(self):
        c = KibanaClient(kibana_url="https://kibana.example.com")
        client = c._client()
        assert client is not None


class TestKibanaGetIndices:
    def _make_client(self):
        return KibanaClient(kibana_url="https://kibana.example.com", username="u", password="p")

    def test_get_indices_from_saved_objects(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "saved_objects": [
                {"attributes": {"title": "logs-*"}},
                {"attributes": {"title": "metrics-*"}},
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_indices())
            assert result == ["logs-*", "metrics-*"]

    def test_get_indices_fallback_to_cat_indices(self):
        c = self._make_client()

        # First call returns non-200
        resp1 = MagicMock()
        resp1.status_code = 404

        # Second call (fallback) returns indices
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.text = "green open logs-2025.01 abc 1 1 100 0 1mb 500kb\ngreen open metrics-2025.01 def 1 1 50 0 500kb 250kb"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[resp1, resp2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_indices())
            assert result == ["logs-2025.01", "metrics-2025.01"]

    def test_get_indices_both_fail(self):
        c = self._make_client()

        resp1 = MagicMock()
        resp1.status_code = 500
        resp2 = MagicMock()
        resp2.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[resp1, resp2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_indices())
            assert result == []


class TestKibanaSearchLogs:
    def _make_client(self):
        return KibanaClient(kibana_url="https://kibana.example.com", username="u", password="p")

    def test_search_logs_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "@timestamp": "2025-01-01T00:00:00Z",
                            "level": "ERROR",
                            "message": "NullPointerException at line 42",
                            "kubernetes": {"labels": {"app": "payment-service"}},
                            "logger_name": "com.example.PaymentService",
                            "stack_trace": "java.lang.NullPointerException...",
                        }
                    },
                    {
                        "_source": {
                            "@timestamp": "2025-01-01T00:01:00Z",
                            "level": "INFO",
                            "message": "Request processed",
                            "kubernetes": {"labels": {"app": "payment-service"}},
                            "logger_name": "com.example.Handler",
                        }
                    },
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(
                c.search_logs(service="payment-service", log_level="ERROR", time_range="1h")
            )
            assert len(result) == 2
            assert result[0]["level"] == "ERROR"
            assert result[0]["service"] == "payment-service"
            assert result[0]["stack_trace"] is not None
            assert result[1]["stack_trace"] is None

    def test_search_logs_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(KibanaError, match="Search failed"):
                asyncio.run(c.search_logs())

    def test_search_logs_time_ranges(self):
        """Verify different time ranges are accepted."""
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": {"hits": []}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            for tr in ["5m", "15m", "30m", "1h", "3h", "6h", "12h", "24h"]:
                result = asyncio.run(
                    c.search_logs(time_range=tr)
                )
                assert result == []

    def test_search_logs_with_query(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": {"hits": []}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            asyncio.run(
                c.search_logs(query="OutOfMemoryError")
            )
            # Verify query_string was included in the request body
            call_args = mock_client.post.call_args
            body = call_args[1]["json"]
            must = body["query"]["bool"]["must"]
            assert any("query_string" in m for m in must)

    @patch.dict(os.environ, {"KIBANA_SERVICE_FIELD": "service.name"})
    def test_search_logs_custom_service_field(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": {"hits": []}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            asyncio.run(
                c.search_logs(service="my-svc")
            )
            call_args = mock_client.post.call_args
            body = call_args[1]["json"]
            filters = body["query"]["bool"]["filter"]
            service_filter = [f for f in filters if "term" in f and "service.name" in f.get("term", {})]
            assert len(service_filter) == 1


class TestKibanaErrorSummary:
    def _make_client(self):
        return KibanaClient(kibana_url="https://kibana.example.com", username="u", password="p")

    def test_error_summary_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "aggregations": {
                "error_patterns": {
                    "buckets": [
                        {"key": "NullPointerException", "doc_count": 150},
                        {"key": "ConnectionTimeoutException", "doc_count": 50},
                    ]
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(
                c.error_summary(service="payment-service", time_range="1h")
            )
            assert len(result) == 2
            assert result[0]["pattern"] == "NullPointerException"
            assert result[0]["count"] == 150

    def test_error_summary_api_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(KibanaError, match="Aggregation failed"):
                asyncio.run(c.error_summary())

    def test_error_summary_empty_buckets(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"aggregations": {"error_patterns": {"buckets": []}}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.error_summary())
            assert result == []


class TestKibanaError:
    def test_error_attrs(self):
        err = KibanaError("test error", status_code=500)
        assert str(err) == "test error"
        assert err.status_code == 500

    def test_error_default_status(self):
        err = KibanaError("oops")
        assert err.status_code == 0
