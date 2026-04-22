"""
Grafana metrics client — query dashboards, panels, alerts, and annotations.

Queries Grafana HTTP API for dashboard search, metric data, alert status, and deploy annotations.
Config: GRAFANA_URL, GRAFANA_USERNAME, GRAFANA_PASSWORD (basic auth with read-only service account)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Any
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger("code_agents.grafana_client")


class GrafanaError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class GrafanaClient:
    def __init__(
        self,
        grafana_url: str = "",
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
    ):
        self.grafana_url = grafana_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        auth = None
        if self.username and self.password:
            auth = (self.username, self.password)
        return httpx.AsyncClient(
            base_url=self.grafana_url,
            auth=auth,
            timeout=self.timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

    # ── Dashboards ───────────────────────────────────────────────────────

    async def search_dashboards(self, query: str = "", tag: str = "", limit: int = 20) -> list[dict]:
        """Search dashboards by name or tag."""
        logger.info("Grafana dashboard search: query=%s, tag=%s", query or "*", tag or "*")
        params: dict[str, Any] = {"type": "dash-db", "limit": limit}
        if query:
            params["query"] = query
        if tag:
            params["tag"] = tag

        async with self._client() as client:
            r = await client.get("/api/search", params=params)
            if r.status_code != 200:
                raise GrafanaError(f"Dashboard search failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = r.json()

        return [
            {
                "uid": d.get("uid", ""),
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "tags": d.get("tags", []),
                "type": d.get("type", ""),
            }
            for d in data
        ]

    async def get_dashboard(self, uid: str) -> dict:
        """Get dashboard details by UID — returns panels and metadata."""
        async with self._client() as client:
            r = await client.get(f"/api/dashboards/uid/{uid}")
            if r.status_code != 200:
                raise GrafanaError(f"Dashboard fetch failed: {r.status_code} {r.text[:200]}", r.status_code)
            data = r.json()

        dashboard = data.get("dashboard", {})
        panels = []
        for panel in dashboard.get("panels", []):
            panels.append({
                "id": panel.get("id"),
                "title": panel.get("title", ""),
                "type": panel.get("type", ""),
                "datasource": panel.get("datasource", {}).get("uid", "") if isinstance(panel.get("datasource"), dict) else str(panel.get("datasource", "")),
            })
            # Include nested panels (rows)
            for sub in panel.get("panels", []):
                panels.append({
                    "id": sub.get("id"),
                    "title": sub.get("title", ""),
                    "type": sub.get("type", ""),
                    "datasource": sub.get("datasource", {}).get("uid", "") if isinstance(sub.get("datasource"), dict) else str(sub.get("datasource", "")),
                })

        return {
            "uid": dashboard.get("uid", ""),
            "title": dashboard.get("title", ""),
            "tags": dashboard.get("tags", []),
            "panels": panels,
        }

    # ── Panel Data Query ─────────────────────────────────────────────────

    async def query_panel(
        self,
        dashboard_uid: str,
        panel_id: int,
        time_from: str = "now-1h",
        time_to: str = "now",
    ) -> dict:
        """Query a specific panel's data using Grafana's render/query API."""
        async with self._client() as client:
            # Use the datasource proxy query API via dashboard
            r = await client.get(
                f"/api/dashboards/uid/{dashboard_uid}",
            )
            if r.status_code != 200:
                raise GrafanaError(f"Dashboard fetch failed: {r.status_code}", r.status_code)

            dashboard = r.json().get("dashboard", {})
            target_panel = None
            for panel in dashboard.get("panels", []):
                if panel.get("id") == panel_id:
                    target_panel = panel
                    break
                for sub in panel.get("panels", []):
                    if sub.get("id") == panel_id:
                        target_panel = sub
                        break

            if not target_panel:
                raise GrafanaError(f"Panel {panel_id} not found in dashboard {dashboard_uid}", 404)

            # Extract targets (queries) from the panel
            targets = target_panel.get("targets", [])
            datasource = target_panel.get("datasource", {})

            # Use Grafana's query API to execute the panel's queries
            ds_uid = datasource.get("uid", "") if isinstance(datasource, dict) else str(datasource)

            # Build query payload for /api/ds/query
            queries = []
            for i, target in enumerate(targets):
                q = {**target, "refId": target.get("refId", chr(65 + i))}
                if ds_uid:
                    q["datasource"] = {"uid": ds_uid}
                queries.append(q)

            if not queries:
                return {"panel": target_panel.get("title", ""), "data": [], "message": "No queries defined"}

            payload = {
                "queries": queries,
                "from": time_from,
                "to": time_to,
            }

            r = await client.post("/api/ds/query", json=payload)
            if r.status_code != 200:
                raise GrafanaError(f"Panel query failed: {r.status_code} {r.text[:200]}", r.status_code)

            result = r.json()
            frames = []
            for ref_id, frame_data in result.get("results", {}).items():
                for frame in frame_data.get("frames", []):
                    schema = frame.get("schema", {})
                    data = frame.get("data", {})
                    frames.append({
                        "name": schema.get("name", ref_id),
                        "fields": [f.get("name", "") for f in schema.get("fields", [])],
                        "values": data.get("values", []),
                    })

            return {
                "panel": target_panel.get("title", ""),
                "datasource": ds_uid,
                "frames": frames,
            }

    # ── Alerts ───────────────────────────────────────────────────────────

    async def get_alerts(self, state: str = "", dashboard_uid: str = "", limit: int = 50) -> list[dict]:
        """List alert rules. Filter by state (alerting, pending, ok, nodata) or dashboard."""
        params: dict[str, Any] = {"limit": limit}
        if state:
            params["state"] = state
        if dashboard_uid:
            params["dashboardUID"] = dashboard_uid

        async with self._client() as client:
            # Try unified alerting API first (Grafana 9+)
            r = await client.get("/api/v1/provisioning/alert-rules")
            if r.status_code == 200:
                rules = r.json()
                results = []
                for rule in rules[:limit]:
                    results.append({
                        "uid": rule.get("uid", ""),
                        "title": rule.get("title", ""),
                        "condition": rule.get("condition", ""),
                        "folder": rule.get("folderUID", ""),
                        "state": rule.get("execErrState", ""),
                    })
                return results

            # Fallback: legacy alerting API
            r = await client.get("/api/alerts", params=params)
            if r.status_code != 200:
                raise GrafanaError(f"Alerts fetch failed: {r.status_code} {r.text[:200]}", r.status_code)

            return [
                {
                    "id": a.get("id"),
                    "name": a.get("name", ""),
                    "state": a.get("state", ""),
                    "dashboard_uid": a.get("dashboardUid", ""),
                    "panel_id": a.get("panelId"),
                    "url": a.get("url", ""),
                }
                for a in r.json()
            ]

    async def get_firing_alerts(self) -> list[dict]:
        """Get currently firing alerts — convenience method."""
        return await self.get_alerts(state="alerting")

    # ── Annotations ──────────────────────────────────────────────────────

    async def create_annotation(
        self,
        text: str,
        tags: list[str] | None = None,
        dashboard_uid: str = "",
        panel_id: int = 0,
        time_ms: int = 0,
    ) -> dict:
        """Create an annotation (e.g., deploy marker). Returns annotation ID."""
        payload: dict[str, Any] = {
            "text": text,
            "tags": tags or ["deploy"],
        }
        if dashboard_uid:
            # Need dashboard ID, not UID — fetch it
            async with self._client() as client:
                r = await client.get(f"/api/dashboards/uid/{dashboard_uid}")
                if r.status_code == 200:
                    payload["dashboardId"] = r.json().get("dashboard", {}).get("id")
        if panel_id:
            payload["panelId"] = panel_id
        if time_ms:
            payload["time"] = time_ms

        async with self._client() as client:
            r = await client.post("/api/annotations", json=payload)
            if r.status_code not in (200, 201):
                raise GrafanaError(f"Annotation create failed: {r.status_code} {r.text[:200]}", r.status_code)
            return r.json()

    async def get_annotations(
        self,
        tags: list[str] | None = None,
        time_from: str = "",
        time_to: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """List annotations, optionally filtered by tags and time."""
        params: dict[str, Any] = {"limit": limit}
        if tags:
            for tag in tags:
                params.setdefault("tags", [])
                params["tags"].append(tag)
        if time_from:
            params["from"] = time_from
        if time_to:
            params["to"] = time_to

        async with self._client() as client:
            r = await client.get("/api/annotations", params=params)
            if r.status_code != 200:
                raise GrafanaError(f"Annotations fetch failed: {r.status_code} {r.text[:200]}", r.status_code)

            return [
                {
                    "id": a.get("id"),
                    "text": a.get("text", ""),
                    "tags": a.get("tags", []),
                    "time": a.get("time"),
                    "dashboard_uid": a.get("dashboardUID", ""),
                }
                for a in r.json()
            ]

    # ── Datasources ──────────────────────────────────────────────────────

    async def list_datasources(self) -> list[dict]:
        """List configured datasources (Prometheus, InfluxDB, etc.)."""
        async with self._client() as client:
            r = await client.get("/api/datasources")
            if r.status_code != 200:
                raise GrafanaError(f"Datasources fetch failed: {r.status_code} {r.text[:200]}", r.status_code)

            return [
                {
                    "uid": ds.get("uid", ""),
                    "name": ds.get("name", ""),
                    "type": ds.get("type", ""),
                    "url": ds.get("url", ""),
                    "is_default": ds.get("isDefault", False),
                }
                for ds in r.json()
            ]

    # ── Health Check ─────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Check Grafana health and version."""
        async with self._client() as client:
            r = await client.get("/api/health")
            if r.status_code != 200:
                raise GrafanaError(f"Health check failed: {r.status_code}", r.status_code)
            return r.json()
