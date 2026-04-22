"""
Kubernetes API: access EKS pod status, logs, deployments, and events.

Requires kubectl installed and kubeconfig configured for the target cluster.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..cicd.k8s_client import K8sClient, K8sError

logger = logging.getLogger("code_agents.k8s")
router = APIRouter(prefix="/k8s", tags=["kubernetes"])


def _get_client(namespace: Optional[str] = None) -> K8sClient:
    """Build K8sClient from environment variables. Supports SSH remote mode."""
    return K8sClient(
        namespace=namespace or os.getenv("K8S_NAMESPACE", "default"),
        context=os.getenv("K8S_CONTEXT", None),
        kubeconfig=os.getenv("KUBECONFIG", None),
        ssh_host=os.getenv("K8S_SSH_HOST", None),
        ssh_key=os.getenv("K8S_SSH_KEY", None),
        ssh_user=os.getenv("K8S_SSH_USER", "ec2-user"),
        ssh_port=int(os.getenv("K8S_SSH_PORT", "22")),
    )


@router.get("/pods")
async def list_pods(
    namespace: Optional[str] = Query(None, description="Kubernetes namespace"),
    label: Optional[str] = Query(None, description="Label selector (e.g. app=my-service)"),
):
    """List pods with status, ready count, restarts, and images."""
    try:
        client = _get_client(namespace)
        return await client.get_pods(label_selector=label)
    except K8sError as e:
        logger.error("list_pods failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/pods/{pod_name}/logs")
async def get_pod_logs(
    pod_name: str,
    namespace: Optional[str] = Query(None),
    container: Optional[str] = Query(None, description="Container name (for multi-container pods)"),
    tail: int = Query(100, description="Number of lines to tail"),
    previous: bool = Query(False, description="Show logs from previous container instance"),
):
    """Get logs for a specific pod."""
    try:
        client = _get_client(namespace)
        logs = await client.get_pod_logs(pod_name, container=container, tail=tail, previous=previous)
        return {"pod": pod_name, "namespace": namespace or "default", "lines": tail, "logs": logs}
    except K8sError as e:
        logger.error("get_pod_logs failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/pods/{pod_name}/describe")
async def describe_pod(
    pod_name: str,
    namespace: Optional[str] = Query(None),
):
    """Describe a pod — events, conditions, volumes, etc."""
    try:
        client = _get_client(namespace)
        output = await client.get_pod_describe(pod_name)
        return {"pod": pod_name, "describe": output}
    except K8sError as e:
        logger.error("describe_pod failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/deployments")
async def list_deployments(
    namespace: Optional[str] = Query(None),
):
    """List deployments with replica counts and images."""
    try:
        client = _get_client(namespace)
        return await client.get_deployments()
    except K8sError as e:
        logger.error("list_deployments failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/events")
async def list_events(
    namespace: Optional[str] = Query(None),
    limit: int = Query(20, description="Max events to return"),
):
    """Get recent cluster events (sorted by time)."""
    try:
        client = _get_client(namespace)
        return await client.get_events(limit=limit)
    except K8sError as e:
        logger.error("list_events failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/namespaces")
async def list_namespaces():
    """List all available namespaces."""
    try:
        client = _get_client()
        return await client.get_namespaces()
    except K8sError as e:
        logger.error("list_namespaces failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/contexts")
async def list_contexts():
    """List available kubectl contexts (clusters)."""
    try:
        client = _get_client()
        return await client.get_contexts()
    except K8sError as e:
        logger.error("list_contexts failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
