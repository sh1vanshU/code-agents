"""Tests for grafana_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.grafana_client import GrafanaClient, GrafanaError


class TestGrafanaClientInit:
    def test_defaults(self):
        c = GrafanaClient()
        assert c.grafana_url == ""
        assert c.username == ""
        assert c.password == ""
        assert c.timeout == 30.0

    def test_custom_init(self):
        c = GrafanaClient(
            grafana_url="https://grafana.example.com/",
            username="viewer",
            password="secret",
            timeout=60.0,
        )
        assert c.grafana_url == "https://grafana.example.com"
        assert c.username == "viewer"
        assert c.password == "secret"
        assert c.timeout == 60.0

    def test_strips_trailing_slash(self):
        c = GrafanaClient(grafana_url="https://grafana.example.com/")
        assert c.grafana_url == "https://grafana.example.com"


class TestGrafanaClientHttpClient:
    def test_client_with_auth(self):
        c = GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")
        client = c._client()
        assert client is not None

    def test_client_without_auth(self):
        c = GrafanaClient(grafana_url="https://grafana.example.com")
        client = c._client()
        assert client is not None


class TestGrafanaHealth:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_health_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"commit": "abc123", "database": "ok", "version": "10.0.0"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.health())
            assert result["version"] == "10.0.0"
            assert result["database"] == "ok"

    def test_health_failure(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Health check failed"):
                asyncio.run(c.health())


class TestGrafanaSearchDashboards:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_search_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uid": "abc", "title": "Payment Service", "url": "/d/abc", "tags": ["prod"], "type": "dash-db"},
            {"uid": "def", "title": "Order Service", "url": "/d/def", "tags": [], "type": "dash-db"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.search_dashboards(query="Payment"))
            assert len(result) == 2
            assert result[0]["uid"] == "abc"
            assert result[0]["title"] == "Payment Service"
            assert result[0]["tags"] == ["prod"]

    def test_search_with_tag(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.search_dashboards(tag="production"))
            assert result == []
            # Verify tag param was passed
            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["tag"] == "production"

    def test_search_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Dashboard search failed"):
                asyncio.run(c.search_dashboards())


class TestGrafanaGetDashboard:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_get_dashboard_with_panels(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "dashboard": {
                "uid": "abc",
                "title": "Payment Service",
                "tags": ["prod"],
                "panels": [
                    {"id": 1, "title": "Error Rate", "type": "graph", "datasource": {"uid": "prom1"}},
                    {"id": 2, "title": "Latency", "type": "timeseries", "datasource": "prometheus"},
                    {
                        "id": 3, "title": "Row", "type": "row",
                        "panels": [
                            {"id": 4, "title": "Throughput", "type": "stat", "datasource": {"uid": "prom1"}},
                        ],
                    },
                ],
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_dashboard("abc"))
            assert result["uid"] == "abc"
            assert result["title"] == "Payment Service"
            assert len(result["panels"]) == 4  # 3 top-level + 1 nested
            assert result["panels"][0]["title"] == "Error Rate"
            assert result["panels"][3]["title"] == "Throughput"

    def test_get_dashboard_not_found(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Dashboard not found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Dashboard fetch failed"):
                asyncio.run(c.get_dashboard("nonexistent"))


class TestGrafanaAlerts:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_get_alerts_unified(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uid": "a1", "title": "High Error Rate", "condition": "C", "folderUID": "f1", "execErrState": "alerting"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_alerts())
            assert len(result) == 1
            assert result[0]["title"] == "High Error Rate"

    def test_get_alerts_legacy_fallback(self):
        c = self._make_client()

        # First call (unified) fails
        resp1 = MagicMock()
        resp1.status_code = 404

        # Second call (legacy) succeeds
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = [
            {"id": 1, "name": "CPU Alert", "state": "alerting", "dashboardUid": "abc", "panelId": 5, "url": "/d/abc"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[resp1, resp2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_alerts())
            assert len(result) == 1
            assert result[0]["name"] == "CPU Alert"
            assert result[0]["state"] == "alerting"

    def test_get_alerts_both_fail(self):
        c = self._make_client()
        resp1 = MagicMock()
        resp1.status_code = 403
        resp2 = MagicMock()
        resp2.status_code = 500
        resp2.text = "Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[resp1, resp2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Alerts fetch failed"):
                asyncio.run(c.get_alerts())

    def test_get_firing_alerts(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_firing_alerts())
            assert result == []


class TestGrafanaAnnotations:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_create_annotation(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42, "message": "Annotation added"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.create_annotation(text="Deploy v1.2.3", tags=["deploy", "payment"]))
            assert result["id"] == 42

    def test_create_annotation_failure(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Annotation create failed"):
                asyncio.run(c.create_annotation(text="Deploy"))

    def test_get_annotations(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 1, "text": "Deploy v1.0", "tags": ["deploy"], "time": 1700000000, "dashboardUID": "abc"},
            {"id": 2, "text": "Deploy v1.1", "tags": ["deploy"], "time": 1700001000, "dashboardUID": "abc"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.get_annotations(tags=["deploy"]))
            assert len(result) == 2
            assert result[0]["text"] == "Deploy v1.0"

    def test_get_annotations_failure(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Annotations fetch failed"):
                asyncio.run(c.get_annotations())


class TestGrafanaDatasources:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_list_datasources(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uid": "prom1", "name": "Prometheus", "type": "prometheus", "url": "http://prom:9090", "isDefault": True},
            {"uid": "inf1", "name": "InfluxDB", "type": "influxdb", "url": "http://influx:8086", "isDefault": False},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.list_datasources())
            assert len(result) == 2
            assert result[0]["name"] == "Prometheus"
            assert result[0]["is_default"] is True
            assert result[1]["type"] == "influxdb"

    def test_list_datasources_error(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Datasources fetch failed"):
                asyncio.run(c.list_datasources())


class TestGrafanaPanelQuery:
    def _make_client(self):
        return GrafanaClient(grafana_url="https://grafana.example.com", username="u", password="p")

    def test_panel_not_found(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "dashboard": {"panels": [{"id": 1, "title": "Other", "targets": []}]}
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Panel 99 not found"):
                asyncio.run(c.query_panel(dashboard_uid="abc", panel_id=99))

    def test_panel_no_queries(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "dashboard": {"panels": [{"id": 1, "title": "Empty Panel", "targets": [], "datasource": {}}]}
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.query_panel(dashboard_uid="abc", panel_id=1))
            assert result["panel"] == "Empty Panel"
            assert result["data"] == []

    def test_panel_query_success(self):
        c = self._make_client()

        # Dashboard fetch
        dash_resp = MagicMock()
        dash_resp.status_code = 200
        dash_resp.json.return_value = {
            "dashboard": {
                "panels": [{
                    "id": 1,
                    "title": "Error Rate",
                    "datasource": {"uid": "prom1"},
                    "targets": [{"expr": "rate(errors[5m])", "refId": "A"}],
                }]
            }
        }

        # Query response
        query_resp = MagicMock()
        query_resp.status_code = 200
        query_resp.json.return_value = {
            "results": {
                "A": {
                    "frames": [{
                        "schema": {"name": "errors", "fields": [{"name": "time"}, {"name": "value"}]},
                        "data": {"values": [[1700000000, 1700001000], [0.1, 0.2]]},
                    }]
                }
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=dash_resp)
        mock_client.post = AsyncMock(return_value=query_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            result = asyncio.run(c.query_panel(dashboard_uid="abc", panel_id=1))
            assert result["panel"] == "Error Rate"
            assert result["datasource"] == "prom1"
            assert len(result["frames"]) == 1
            assert result["frames"][0]["name"] == "errors"

    def test_panel_query_api_error(self):
        c = self._make_client()

        dash_resp = MagicMock()
        dash_resp.status_code = 200
        dash_resp.json.return_value = {
            "dashboard": {
                "panels": [{
                    "id": 1, "title": "P", "datasource": {"uid": "p"},
                    "targets": [{"expr": "up", "refId": "A"}],
                }]
            }
        }

        query_resp = MagicMock()
        query_resp.status_code = 400
        query_resp.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=dash_resp)
        mock_client.post = AsyncMock(return_value=query_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(c, "_client", return_value=mock_client):
            with pytest.raises(GrafanaError, match="Panel query failed"):
                asyncio.run(c.query_panel(dashboard_uid="abc", panel_id=1))


class TestGrafanaError:
    def test_error_attrs(self):
        err = GrafanaError("test error", status_code=500)
        assert str(err) == "test error"
        assert err.status_code == 500

    def test_error_default_status(self):
        err = GrafanaError("oops")
        assert err.status_code == 0
