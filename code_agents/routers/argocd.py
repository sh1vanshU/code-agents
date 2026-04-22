"""
ArgoCD API: check deployment status, verify pods, fetch logs, and rollback.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..cicd.argocd_client import ArgoCDClient, ArgoCDError

logger = logging.getLogger("code_agents.argocd")
router = APIRouter(prefix="/argocd", tags=["argocd"])

# Alias: /argocd/app/* → /argocd/apps/* (LLMs sometimes drop the trailing 's')
app_alias_router = APIRouter(prefix="/argocd", tags=["argocd"])


@app_alias_router.api_route("/app/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def app_singular_redirect(path: str, request: Request):
    """Redirect /argocd/app/* to /argocd/apps/* for LLM typo tolerance."""
    query = f"?{request.query_params}" if request.query_params else ""
    target = f"/argocd/apps/{path}{query}"
    logger.warning("redirecting %s → %s (singular 'app' alias)", request.url.path, target)
    return RedirectResponse(url=target, status_code=307)


@app_alias_router.api_route("/applications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def applications_redirect(path: str, request: Request):
    """Redirect /argocd/applications/* to /argocd/apps/* for LLM hallucination tolerance."""
    query = f"?{request.query_params}" if request.query_params else ""
    target = f"/argocd/apps/{path}{query}"
    logger.warning("redirecting %s → %s ('applications' alias)", request.url.path, target)
    return RedirectResponse(url=target, status_code=307)


def _get_client() -> ArgoCDClient:
    """Build ArgoCDClient from environment variables."""
    base_url = os.getenv("ARGOCD_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="ARGOCD_URL is not set. Configure ArgoCD connection in environment.",
        )
    username = os.getenv("ARGOCD_USERNAME", "")
    password = os.getenv("ARGOCD_PASSWORD", "")
    if not (username and password):
        raise HTTPException(
            status_code=503,
            detail="ArgoCD auth not configured. Set both ARGOCD_USERNAME and ARGOCD_PASSWORD.",
        )
    verify_ssl = os.getenv("ARGOCD_VERIFY_SSL", "1").strip().lower() not in ("0", "false", "no")
    return ArgoCDClient(
        base_url=base_url,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
    )


class SyncRequest(BaseModel):
    """Request to sync an ArgoCD application."""
    revision: Optional[str] = Field(None, description="Target revision (default: latest)")


class RollbackRequest(BaseModel):
    """Request to rollback an ArgoCD application."""
    revision: Union[int, str] = Field(
        ...,
        description="Deployment history revision ID (int) or 'previous' for the last revision",
    )


@router.get("/apps")
async def list_apps(project: str = "", selector: str = ""):
    """List all ArgoCD applications, optionally filtered by project or label selector."""
    try:
        client = _get_client()
        apps = await client.list_apps(project=project, selector=selector)
        return {"apps": apps, "count": len(apps)}
    except ArgoCDError as e:
        logger.error("list_apps failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/status")
async def get_app_status(app_name: str):
    """Get ArgoCD application sync and health status."""
    try:
        client = _get_client()
        result = await client.get_app_status(app_name)
        logger.info("app_status %s: sync=%s health=%s",
                     app_name, result["sync_status"], result["health_status"])
        return result
    except ArgoCDError as e:
        logger.error("get_app_status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/pods")
async def list_pods(app_name: str):
    """List pods for an ArgoCD application with image tags and health."""
    try:
        client = _get_client()
        pods = await client.list_pods(app_name)
        return {"app_name": app_name, "pods": pods, "count": len(pods)}
    except ArgoCDError as e:
        logger.error("list_pods failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/pods/{pod_name}/logs")
async def get_pod_logs(
    app_name: str,
    pod_name: str,
    namespace: str = "default",
    container: Optional[str] = None,
    tail: int = 200,
):
    """Fetch pod logs and scan for error patterns (ERROR, FATAL, Exception, panic)."""
    try:
        client = _get_client()
        result = await client.get_pod_logs(
            app_name=app_name,
            pod_name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail,
        )
        if result["has_errors"]:
            logger.warning("Pod %s has %d error lines", pod_name, len(result["error_lines"]))
        return result
    except ArgoCDError as e:
        logger.error("get_pod_logs failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/sync")
async def sync_app(app_name: str, req: Optional[SyncRequest] = None):
    """Trigger an ArgoCD application sync."""
    try:
        client = _get_client()
        result = await client.sync_app(
            app_name=app_name,
            revision=req.revision if req else None,
        )
        logger.info("sync_app %s: triggered", app_name)
        return result
    except ArgoCDError as e:
        logger.error("sync_app failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/rollback")
async def rollback_app(app_name: str, req: RollbackRequest):
    """
    Rollback an ArgoCD application to a previous deployment revision.

    Pass revision as an integer (history ID) or "previous" to rollback to the last deployment.
    """
    try:
        client = _get_client()

        # Resolve "previous" to actual revision ID
        revision_id: int
        if isinstance(req.revision, str) and req.revision.lower() == "previous":
            history = await client.get_history(app_name)
            if len(history) < 2:
                raise HTTPException(
                    status_code=422,
                    detail="No previous revision available in deployment history.",
                )
            revision_id = history[-2]["id"]  # Second-to-last is the previous deployment
        else:
            revision_id = int(req.revision)

        result = await client.rollback(app_name=app_name, revision_id=revision_id)
        logger.info("rollback %s to revision %d", app_name, revision_id)
        return result
    except ArgoCDError as e:
        logger.error("rollback failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/history")
async def get_history(app_name: str):
    """Get deployment history for an ArgoCD application."""
    try:
        client = _get_client()
        history = await client.get_history(app_name)
        return {"app_name": app_name, "history": history, "count": len(history)}
    except ArgoCDError as e:
        logger.error("get_history failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/wait-sync")
async def wait_for_sync(app_name: str):
    """Wait until application is synced and healthy (long-poll)."""
    try:
        client = _get_client()
        result = await client.wait_for_sync(app_name)
        return result
    except ArgoCDError as e:
        logger.error("wait_for_sync failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/events")
async def get_events(app_name: str):
    """Get Kubernetes events for an ArgoCD application (deploy errors, scheduling failures)."""
    try:
        client = _get_client()
        events = await client.get_events(app_name)
        return {"app_name": app_name, "events": events, "count": len(events)}
    except ArgoCDError as e:
        logger.error("get_events failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/managed-resources")
async def get_managed_resources(app_name: str):
    """List all K8s resources managed by this ArgoCD application."""
    try:
        client = _get_client()
        resources = await client.get_managed_resources(app_name)
        return {"app_name": app_name, "resources": resources, "count": len(resources)}
    except ArgoCDError as e:
        logger.error("get_managed_resources failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/resource")
async def get_resource(app_name: str, name: str, kind: str, namespace: str = "", group: str = ""):
    """Get details of a single managed resource."""
    try:
        client = _get_client()
        resource = await client.get_resource(app_name, name=name, kind=kind, namespace=namespace, group=group)
        return resource
    except ArgoCDError as e:
        logger.error("get_resource failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/manifests")
async def get_manifests(app_name: str):
    """Get rendered manifests for an ArgoCD application."""
    try:
        client = _get_client()
        manifests = await client.get_manifests(app_name)
        return manifests
    except ArgoCDError as e:
        logger.error("get_manifests failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/revisions/{revision}/metadata")
async def get_revision_metadata(app_name: str, revision: str):
    """Get git commit metadata for a specific revision."""
    try:
        client = _get_client()
        metadata = await client.get_revision_metadata(app_name, revision)
        return {"app_name": app_name, "revision": revision, **metadata}
    except ArgoCDError as e:
        logger.error("get_revision_metadata failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/apps/{app_name}/operation")
async def cancel_operation(app_name: str):
    """Cancel a stuck/running sync operation."""
    try:
        client = _get_client()
        result = await client.cancel_operation(app_name)
        logger.info("cancel_operation %s: done", app_name)
        return result
    except ArgoCDError as e:
        logger.error("cancel_operation failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/resource/actions")
async def get_resource_actions(app_name: str, name: str, kind: str, namespace: str = "", group: str = ""):
    """List available actions for a resource (e.g. restart)."""
    try:
        client = _get_client()
        actions = await client.get_resource_actions(app_name, name=name, kind=kind, namespace=namespace, group=group)
        return {"app_name": app_name, "resource": name, "kind": kind, "actions": actions}
    except ArgoCDError as e:
        logger.error("get_resource_actions failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/resource/actions")
async def run_resource_action(app_name: str, name: str, kind: str, action: str, namespace: str = "", group: str = ""):
    """Execute a resource action (e.g. restart a Deployment)."""
    try:
        client = _get_client()
        result = await client.run_resource_action(app_name, name=name, kind=kind, action=action, namespace=namespace, group=group)
        logger.info("run_resource_action %s/%s: %s", kind, name, action)
        return result
    except ArgoCDError as e:
        logger.error("run_resource_action failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
