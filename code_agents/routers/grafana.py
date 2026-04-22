"""
Grafana metrics: dashboards, panel data, alerts, annotations.

Queries Grafana HTTP API for monitoring data.
Requires GRAFANA_URL to be set (503 otherwise).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cicd.grafana_client import GrafanaClient, GrafanaError

logger = logging.getLogger("code_agents.routers.grafana")
router = APIRouter(prefix="/grafana", tags=["grafana"])


def _get_client() -> GrafanaClient:
    """Build GrafanaClient from environment variables."""
    grafana_url = os.getenv("GRAFANA_URL")
    if not grafana_url:
        raise HTTPException(
            status_code=503,
            detail="GRAFANA_URL is not set. Configure Grafana connection in environment.",
        )
    return GrafanaClient(
        grafana_url=grafana_url,
        username=os.getenv("GRAFANA_USERNAME", ""),
        password=os.getenv("GRAFANA_PASSWORD", ""),
    )


# ── Models ────────────────────────────────────────────────────────────────


class DashboardSearchRequest(BaseModel):
    query: str = Field(default="", description="Search term for dashboard name")
    tag: str = Field(default="", description="Filter by tag")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")


class PanelQueryRequest(BaseModel):
    dashboard_uid: str = Field(description="Dashboard UID")
    panel_id: int = Field(description="Panel ID within the dashboard")
    time_from: str = Field(default="now-1h", description="Start time (e.g. now-1h, now-6h, now-24h)")
    time_to: str = Field(default="now", description="End time")


class AnnotationCreateRequest(BaseModel):
    text: str = Field(description="Annotation text (e.g. 'Deploy v1.2.3 to qa4')")
    tags: list[str] = Field(default=["deploy"], description="Tags for filtering")
    dashboard_uid: str = Field(default="", description="Optional: attach to specific dashboard")
    panel_id: int = Field(default=0, description="Optional: attach to specific panel")


class AlertsRequest(BaseModel):
    state: str = Field(default="", description="Filter by state: alerting, pending, ok, nodata")
    dashboard_uid: str = Field(default="", description="Filter by dashboard UID")
    limit: int = Field(default=50, ge=1, le=200, description="Max results")


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/health")
async def grafana_health():
    """Check Grafana connectivity and version."""
    client = _get_client()
    try:
        result = await client.health()
        return result
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/dashboards/search")
async def search_dashboards(req: DashboardSearchRequest):
    """Search dashboards by name or tag."""
    client = _get_client()
    try:
        results = await client.search_dashboards(query=req.query, tag=req.tag, limit=req.limit)
        return {"total": len(results), "dashboards": results}
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/dashboards/{uid}")
async def get_dashboard(uid: str):
    """Get dashboard details and panel list by UID."""
    client = _get_client()
    try:
        result = await client.get_dashboard(uid)
        return result
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/panels/query")
async def query_panel(req: PanelQueryRequest):
    """Query a specific panel's metric data."""
    logger.info("Grafana panel query: dashboard=%s, panel=%d, from=%s", req.dashboard_uid, req.panel_id, req.time_from)
    client = _get_client()
    try:
        result = await client.query_panel(
            dashboard_uid=req.dashboard_uid,
            panel_id=req.panel_id,
            time_from=req.time_from,
            time_to=req.time_to,
        )
        return result
    except GrafanaError as exc:
        logger.error("Grafana panel query failed: %s", exc)
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/alerts")
async def list_alerts(req: AlertsRequest):
    """List alert rules, optionally filtered by state or dashboard."""
    client = _get_client()
    try:
        results = await client.get_alerts(state=req.state, dashboard_uid=req.dashboard_uid, limit=req.limit)
        return {"total": len(results), "alerts": results}
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/alerts/firing")
async def firing_alerts():
    """Get currently firing alerts."""
    client = _get_client()
    try:
        results = await client.get_firing_alerts()
        return {"total": len(results), "alerts": results}
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.post("/annotations")
async def create_annotation(req: AnnotationCreateRequest):
    """Create an annotation (e.g. deploy marker on a dashboard)."""
    client = _get_client()
    try:
        result = await client.create_annotation(
            text=req.text,
            tags=req.tags,
            dashboard_uid=req.dashboard_uid,
            panel_id=req.panel_id,
        )
        return result
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/annotations")
async def list_annotations(tags: str = "", limit: int = 20):
    """List recent annotations, optionally filtered by tags (comma-separated)."""
    client = _get_client()
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        results = await client.get_annotations(tags=tag_list, limit=limit)
        return {"total": len(results), "annotations": results}
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))


@router.get("/datasources")
async def list_datasources():
    """List configured datasources (Prometheus, InfluxDB, etc.)."""
    client = _get_client()
    try:
        results = await client.list_datasources()
        return {"total": len(results), "datasources": results}
    except GrafanaError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
