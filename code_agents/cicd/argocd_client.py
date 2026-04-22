"""
ArgoCD REST API client for deployment verification and rollback.

Uses httpx for async HTTP. Authenticates via Bearer token or username/password.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.argocd_client")


def resolve_app_name(
    env_name: str = "",
    app_name: str = "",
    pattern: str = "",
) -> str:
    """
    Resolve ArgoCD application name from pattern.

    Pattern supports {env} and {app} placeholders.
    Example: "{env}-project-bombay-{app}" with env="dev-stable", app="pg-acquiring-biz"
             → "dev-stable-project-bombay-pg-acquiring-biz"

    Falls back to ARGOCD_APP_PATTERN env var, then ARGOCD_APP_NAME.
    """
    import os

    if not pattern:
        pattern = os.getenv("ARGOCD_APP_PATTERN", "").strip()

    if pattern and env_name and app_name:
        resolved = pattern.replace("{env}", env_name).replace("{app}", app_name)
        logger.info("argocd app name resolved: pattern=%s → %s", pattern, resolved)
        return resolved

    # Fallback to static name
    static = os.getenv("ARGOCD_APP_NAME", "").strip()
    if static:
        return static

    # Build from parts if available
    if env_name and app_name:
        return f"{env_name}-project-bombay-{app_name}"

    return app_name or ""


class ArgoCDError(Exception):
    """Raised when an ArgoCD API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class ArgoCDClient:
    """Async client for the ArgoCD REST API."""

    def __init__(
        self,
        base_url: str,
        auth_token: str = "",
        verify_ssl: bool = True,
        timeout: float = 30.0,
        poll_interval: float = 5.0,
        poll_timeout: float = 300.0,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        # Strip UI paths like /applications that users sometimes paste
        import re
        self.base_url = re.sub(r'/(applications|settings|projects)(/.*)?$', '', base_url.rstrip("/"))
        self.auth_token = auth_token
        self._username = username
        self._password = password
        self._logged_in = False
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    async def _login(self, force: bool = False) -> None:
        """Exchange username/password for a session token via POST /api/v1/session."""
        if not force and (self._logged_in or self.auth_token):
            return
        if not self._username or not self._password:
            raise ArgoCDError("No auth_token and no username/password configured")
        async with httpx.AsyncClient(
            base_url=self.base_url, verify=self.verify_ssl, timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            r = await client.post(
                "/api/v1/session",
                json={"username": self._username, "password": self._password},
            )
            if r.status_code != 200:
                raise ArgoCDError(
                    f"ArgoCD login failed: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            token = r.json().get("token")
            if not token:
                raise ArgoCDError("ArgoCD login response missing token")
            self.auth_token = token
            self._logged_in = True
            logger.info("argocd login successful for user=%s", self._username)

    async def _ensure_auth(self) -> None:
        """Ensure we have an auth token, logging in if needed."""
        if not self.auth_token:
            await self._login()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            verify=self.verify_ssl,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an authenticated request with automatic 401 retry.

        On a 401 response, clears the cached token, re-authenticates via
        username/password, and retries the request once.
        """
        await self._ensure_auth()
        async with self._client() as client:
            r = await client.request(method, path, **kwargs)

        if r.status_code == 401 and self._username and self._password:
            logger.info("argocd 401 on %s %s — re-authenticating", method, path)
            self.auth_token = ""
            self._logged_in = False
            await self._login(force=True)
            async with self._client() as client:
                r = await client.request(method, path, **kwargs)

        return r

    async def list_apps(self, project: str = "", selector: str = "") -> list[dict]:
        """List all ArgoCD applications, optionally filtered by project or label selector."""
        params: dict[str, Any] = {}
        if project:
            params["project"] = project
        if selector:
            params["selector"] = selector
        r = await self._request("GET", "/api/v1/applications", params=params)
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to list apps: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        items = r.json().get("items", [])
        return [
            {
                "name": item.get("metadata", {}).get("name", ""),
                "project": item.get("spec", {}).get("project", ""),
                "sync_status": item.get("status", {}).get("sync", {}).get("status", "Unknown"),
                "health_status": item.get("status", {}).get("health", {}).get("status", "Unknown"),
                "repo_url": item.get("spec", {}).get("source", {}).get("repoURL", ""),
                "target_revision": item.get("spec", {}).get("source", {}).get("targetRevision", ""),
                "cluster": item.get("spec", {}).get("destination", {}).get("server", ""),
                "namespace": item.get("spec", {}).get("destination", {}).get("namespace", ""),
            }
            for item in items
        ]

    async def get_app_status(self, app_name: str) -> dict:
        """Get application sync and health status."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get app status: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        status = data.get("status", {})
        sync = status.get("sync", {})
        health = status.get("health", {})

        # Extract images from summary
        images = []
        summary = status.get("summary", {})
        if summary.get("images"):
            images = summary["images"]

        return {
            "app_name": app_name,
            "sync_status": sync.get("status", "Unknown"),
            "health_status": health.get("status", "Unknown"),
            "revision": sync.get("revision", ""),
            "images": images,
            "conditions": status.get("conditions", []),
            "source": data.get("spec", {}).get("source", {}),
        }

    async def list_pods(self, app_name: str) -> list[dict]:
        """List pods for an application from the resource tree."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}/resource-tree")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get resource tree: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        pods = []
        for node in data.get("nodes", []):
            if node.get("kind") == "Pod":
                health = node.get("health", {})
                pods.append({
                    "name": node.get("name", ""),
                    "namespace": node.get("namespace", ""),
                    "status": health.get("status", "Unknown"),
                    "message": health.get("message", ""),
                    "images": node.get("images", []),
                    "ready": health.get("status") == "Healthy",
                })
        return pods

    async def get_pod_logs(
        self,
        app_name: str,
        pod_name: str,
        namespace: str,
        container: Optional[str] = None,
        tail_lines: int = 200,
    ) -> dict:
        """Fetch pod logs via ArgoCD API."""
        params: dict[str, Any] = {
            "podName": pod_name,
            "namespace": namespace,
            "tailLines": tail_lines,
        }
        if container:
            params["container"] = container

        r = await self._request(
            "GET",
            f"/api/v1/applications/{app_name}/logs",
            params=params,
        )
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get pod logs: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )

        logs = r.text

        # Scan for error patterns
        error_patterns = re.compile(
            r"(ERROR|FATAL|Exception|Traceback|panic:|CRITICAL)",
            re.IGNORECASE,
        )
        error_lines = [
            line for line in logs.splitlines()
            if error_patterns.search(line)
        ]

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "logs": logs,
            "error_lines": error_lines[:50],  # Limit
            "has_errors": len(error_lines) > 0,
            "total_lines": len(logs.splitlines()),
        }

    async def sync_app(self, app_name: str, revision: Optional[str] = None) -> dict:
        """Trigger an application sync."""
        body: dict[str, Any] = {}
        if revision:
            body["revision"] = revision

        r = await self._request(
            "POST",
            f"/api/v1/applications/{app_name}/sync",
            json=body,
        )
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to sync app: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return {"app_name": app_name, "status": "sync_triggered", "revision": revision}

    async def rollback(self, app_name: str, revision_id: int) -> dict:
        """Rollback application to a previous deployment revision."""
        body = {"id": revision_id}
        r = await self._request(
            "PUT",
            f"/api/v1/applications/{app_name}/rollback",
            json=body,
        )
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to rollback: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return {
            "app_name": app_name,
            "status": "rollback_triggered",
            "target_revision_id": revision_id,
        }

    async def rollback_to_revision(self, app_name: str, revision: str | int) -> dict:
        """Rollback to a specific revision (git SHA string or deployment revision int).

        If *revision* is a string (git SHA), uses sync_app with the target revision.
        If *revision* is an int, uses the existing rollback API.
        """
        if isinstance(revision, str):
            logger.info("argocd rollback_to_revision: syncing %s to git SHA %s", app_name, revision)
            return await self.sync_app(app_name, revision=revision)
        logger.info("argocd rollback_to_revision: rolling back %s to deployment revision %d", app_name, revision)
        return await self.rollback(app_name, revision_id=revision)

    async def run_smoke_test(self, url: str, expected_status: int = 200, timeout: int = 10) -> dict:
        """Run a simple HTTP smoke test against a URL.

        Returns dict with url, status_code, healthy (bool), and latency_ms.
        """
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                r = await client.get(url)
            latency_ms = (time.monotonic() - start) * 1000
            healthy = r.status_code == expected_status
            logger.info("smoke test %s: status=%d healthy=%s latency=%.0fms", url, r.status_code, healthy, latency_ms)
            return {
                "url": url,
                "status_code": r.status_code,
                "healthy": healthy,
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("smoke test %s failed: %s", url, e)
            return {
                "url": url,
                "status_code": 0,
                "healthy": False,
                "latency_ms": round(latency_ms, 1),
            }

    async def get_history(self, app_name: str) -> list[dict]:
        """Get deployment history for an application."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get app: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        history = data.get("status", {}).get("history", [])
        return [
            {
                "id": entry.get("id"),
                "revision": entry.get("revision", ""),
                "deployed_at": entry.get("deployedAt", ""),
                "source": entry.get("source", {}),
            }
            for entry in history
        ]

    async def wait_for_sync(self, app_name: str) -> dict:
        """Poll until app is synced and healthy."""
        logger.info("argocd wait_for_sync: app=%s (poll_interval=%.0fs timeout=%.0fs)",
                     app_name, self.poll_interval, self.poll_timeout)
        deadline = time.monotonic() + self.poll_timeout
        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            status = await self.get_app_status(app_name)
            if (
                status["sync_status"] == "Synced"
                and status["health_status"] == "Healthy"
            ):
                logger.info("argocd app %s is synced and healthy after %d polls", app_name, poll_count)
                return status
            logger.info(
                "argocd waiting for %s: sync=%s health=%s (poll %d)",
                app_name, status["sync_status"], status["health_status"], poll_count,
            )
            await asyncio.sleep(self.poll_interval)
        logger.error("argocd app %s TIMEOUT after %.0fs (%d polls)", app_name, self.poll_timeout, poll_count)
        raise ArgoCDError(
            f"App {app_name} did not reach Synced/Healthy within {self.poll_timeout}s"
        )

    async def get_events(self, app_name: str) -> list[dict]:
        """Get Kubernetes events for an application."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}/events")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get events: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        items = r.json().get("items", [])
        return [
            {
                "type": ev.get("type", ""),
                "reason": ev.get("reason", ""),
                "message": ev.get("message", ""),
                "first_seen": ev.get("firstTimestamp", ""),
                "last_seen": ev.get("lastTimestamp", ""),
                "count": ev.get("count", 0),
                "source": ev.get("source", {}).get("component", ""),
                "object": ev.get("involvedObject", {}).get("name", ""),
            }
            for ev in items
        ]

    async def get_managed_resources(self, app_name: str) -> list[dict]:
        """List all Kubernetes resources managed by an application."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}/managed-resources")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get managed resources: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        items = r.json().get("items", [])
        return [
            {
                "kind": res.get("kind", ""),
                "name": res.get("name", ""),
                "namespace": res.get("namespace", ""),
                "group": res.get("group", ""),
                "status": res.get("status", ""),
                "health": res.get("health", {}).get("status", "") if res.get("health") else "",
            }
            for res in items
        ]

    async def get_resource(self, app_name: str, name: str, kind: str, namespace: str = "", group: str = "") -> dict:
        """Get details of a single managed resource."""
        params: dict[str, Any] = {"name": name, "kind": kind}
        if namespace:
            params["namespace"] = namespace
        if group:
            params["group"] = group
        r = await self._request("GET", f"/api/v1/applications/{app_name}/resource", params=params)
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get resource: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return r.json()

    async def get_manifests(self, app_name: str) -> dict:
        """Get rendered manifests for an application."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}/manifests")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get manifests: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return r.json()

    async def get_revision_metadata(self, app_name: str, revision: str) -> dict:
        """Get git commit metadata for a specific revision."""
        r = await self._request("GET", f"/api/v1/applications/{app_name}/revisions/{revision}/metadata")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get revision metadata: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        data = r.json()
        return {
            "author": data.get("author", ""),
            "date": data.get("date", ""),
            "message": data.get("message", ""),
            "tags": data.get("tags", []),
        }

    async def cancel_operation(self, app_name: str) -> dict:
        """Cancel a running/stuck sync operation."""
        r = await self._request("DELETE", f"/api/v1/applications/{app_name}/operation")
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to cancel operation: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        logger.info("cancelled operation on %s", app_name)
        return {"app_name": app_name, "status": "operation_cancelled"}

    async def get_resource_actions(self, app_name: str, name: str, kind: str, namespace: str = "", group: str = "") -> list[dict]:
        """List available actions for a resource (e.g. restart)."""
        params: dict[str, Any] = {"name": name, "kind": kind}
        if namespace:
            params["namespace"] = namespace
        if group:
            params["group"] = group
        r = await self._request("GET", f"/api/v1/applications/{app_name}/resource/actions", params=params)
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to get resource actions: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        return r.json().get("actions", [])

    async def run_resource_action(self, app_name: str, name: str, kind: str, action: str, namespace: str = "", group: str = "") -> dict:
        """Execute a resource action (e.g. restart a Deployment)."""
        params: dict[str, Any] = {"name": name, "kind": kind}
        if namespace:
            params["namespace"] = namespace
        if group:
            params["group"] = group
        r = await self._request(
            "POST",
            f"/api/v1/applications/{app_name}/resource/actions",
            params=params,
            json=action,
        )
        if r.status_code != 200:
            raise ArgoCDError(
                f"Failed to run resource action: HTTP {r.status_code}",
                status_code=r.status_code,
                response_text=r.text[:500],
            )
        logger.info("ran action %s on %s/%s in app %s", action, kind, name, app_name)
        return {"app_name": app_name, "resource": name, "kind": kind, "action": action, "status": "executed"}
