"""
Kubernetes client — access EKS pod status, logs, and cluster info via kubectl.

Uses kubectl subprocess (same pattern as git_client.py).
Requires kubectl installed and kubeconfig configured for the target cluster.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional

logger = logging.getLogger("code_agents.k8s_client")


class K8sError(Exception):
    """Raised when a kubectl command fails."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


class K8sClient:
    """
    Async client for Kubernetes via kubectl subprocess.

    Supports two modes:
    - Local: runs kubectl directly (kubectl must be installed locally)
    - Remote SSH: runs kubectl on a remote server via SSH (for EKS bastion hosts)

    Remote mode activated when ssh_host is set. Requires:
    - K8S_SSH_HOST: server IP or hostname
    - K8S_SSH_KEY: path to RSA private key file
    - K8S_SSH_USER: SSH username (default: ec2-user)
    """

    def __init__(
        self,
        namespace: str = "default",
        context: Optional[str] = None,
        kubeconfig: Optional[str] = None,
        timeout: float = 30.0,
        ssh_host: Optional[str] = None,
        ssh_key: Optional[str] = None,
        ssh_user: str = "ec2-user",
        ssh_port: int = 22,
    ):
        self.namespace = namespace
        self.context = context
        self.kubeconfig = kubeconfig
        self.timeout = timeout
        self.ssh_host = ssh_host
        self.ssh_key = ssh_key
        self.ssh_user = ssh_user
        self.ssh_port = ssh_port

    @property
    def is_remote(self) -> bool:
        return bool(self.ssh_host)

    def _kubectl_args(self, args: list[str]) -> str:
        """Build the kubectl command string (without ssh wrapper)."""
        parts = ["kubectl"]
        if self.kubeconfig:
            parts.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            parts.extend(["--context", self.context])
        parts.extend(["-n", self.namespace])
        parts.extend(args)
        return " ".join(parts)

    def _ssh_cmd(self, remote_cmd: str) -> list[str]:
        """Wrap a command in SSH to run on remote server."""
        ssh = shutil.which("ssh")
        if not ssh:
            raise K8sError("ssh not found")

        cmd = [
            ssh,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-p", str(self.ssh_port),
        ]
        if self.ssh_key:
            cmd.extend(["-i", self.ssh_key])
        cmd.append(f"{self.ssh_user}@{self.ssh_host}")
        cmd.append(remote_cmd)
        return cmd

    def _local_cmd(self, args: list[str]) -> list[str]:
        """Build local kubectl command."""
        kubectl = shutil.which("kubectl")
        if not kubectl:
            raise K8sError("kubectl not found. Install: brew install kubectl")

        cmd = [kubectl]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            cmd.extend(["--context", self.context])
        cmd.extend(["-n", self.namespace])
        cmd.extend(args)
        return cmd

    async def _run(self, args: list[str]) -> str:
        """Run a kubectl command (locally or via SSH) and return stdout."""
        if self.is_remote:
            kubectl_str = self._kubectl_args(args)
            cmd = self._ssh_cmd(kubectl_str)
            logger.info("kubectl (ssh %s@%s): %s", self.ssh_user, self.ssh_host, kubectl_str)
        else:
            cmd = self._local_cmd(args)
            logger.info("kubectl (local): %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=self.timeout
        )

        if proc.returncode != 0:
            error = stderr.decode("utf-8", errors="replace").strip()
            if self.is_remote and ("Connection refused" in error or "Permission denied" in error):
                raise K8sError(
                    f"SSH connection failed to {self.ssh_user}@{self.ssh_host}: {error}. "
                    f"Check K8S_SSH_HOST, K8S_SSH_KEY, K8S_SSH_USER.",
                    returncode=proc.returncode,
                )
            raise K8sError(f"kubectl failed: {error}", returncode=proc.returncode)

        return stdout.decode("utf-8", errors="replace").strip()

    async def get_pods(self, label_selector: Optional[str] = None) -> list[dict]:
        """List pods with status, ready count, restarts, age, and image."""
        args = ["get", "pods", "-o", "json"]
        if label_selector:
            args.extend(["-l", label_selector])

        output = await self._run(args)

        import json
        data = json.loads(output)
        pods = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            status = item.get("status", {})
            spec = item.get("spec", {})

            # Container statuses
            container_statuses = status.get("containerStatuses", [])
            ready_count = sum(1 for cs in container_statuses if cs.get("ready"))
            total_count = len(container_statuses)
            restarts = sum(cs.get("restartCount", 0) for cs in container_statuses)

            # Images
            images = []
            for container in spec.get("containers", []):
                images.append(container.get("image", ""))

            pods.append({
                "name": metadata.get("name", ""),
                "namespace": metadata.get("namespace", self.namespace),
                "status": status.get("phase", "Unknown"),
                "ready": f"{ready_count}/{total_count}",
                "restarts": restarts,
                "node": spec.get("nodeName", ""),
                "images": images,
                "start_time": status.get("startTime", ""),
                "labels": metadata.get("labels", {}),
            })

        return pods

    async def get_pod_logs(
        self,
        pod_name: str,
        container: Optional[str] = None,
        tail: int = 100,
        previous: bool = False,
    ) -> str:
        """Get logs for a specific pod."""
        args = ["logs", pod_name, f"--tail={tail}"]
        if container:
            args.extend(["-c", container])
        if previous:
            args.append("--previous")
        return await self._run(args)

    async def get_pod_describe(self, pod_name: str) -> str:
        """Describe a pod (events, conditions, volumes, etc.)."""
        return await self._run(["describe", "pod", pod_name])

    async def get_deployments(self) -> list[dict]:
        """List deployments with replica counts and images."""
        import json
        output = await self._run(["get", "deployments", "-o", "json"])
        data = json.loads(output)
        deployments = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            images = []
            for container in spec.get("template", {}).get("spec", {}).get("containers", []):
                images.append(container.get("image", ""))

            deployments.append({
                "name": metadata.get("name", ""),
                "namespace": metadata.get("namespace", self.namespace),
                "replicas": f"{status.get('readyReplicas', 0)}/{spec.get('replicas', 0)}",
                "available": status.get("availableReplicas", 0),
                "images": images,
                "strategy": spec.get("strategy", {}).get("type", ""),
            })

        return deployments

    async def get_events(self, field_selector: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Get recent cluster events."""
        import json
        args = ["get", "events", "-o", "json", "--sort-by=.lastTimestamp"]
        if field_selector:
            args.extend(["--field-selector", field_selector])
        output = await self._run(args)
        data = json.loads(output)
        events = []
        for item in data.get("items", [])[-limit:]:
            events.append({
                "type": item.get("type", ""),
                "reason": item.get("reason", ""),
                "message": item.get("message", ""),
                "object": f"{item.get('involvedObject', {}).get('kind', '')}/{item.get('involvedObject', {}).get('name', '')}",
                "count": item.get("count", 1),
                "last_seen": item.get("lastTimestamp", ""),
            })
        return events

    async def get_namespaces(self) -> list[str]:
        """List all namespaces."""
        output = await self._run(["get", "namespaces", "-o", "jsonpath={.items[*].metadata.name}"])
        return output.split() if output else []

    async def get_contexts(self) -> list[dict]:
        """List available kubectl contexts."""
        output = await self._run(["config", "get-contexts", "-o", "name"])
        contexts = []
        current = ""
        try:
            current = await self._run(["config", "current-context"])
        except K8sError as e:
            logger.debug("Could not determine current k8s context: %s", e)
        for name in output.splitlines():
            name = name.strip()
            if name:
                contexts.append({
                    "name": name,
                    "current": name == current.strip(),
                })
        return contexts

    async def exec_command(self, pod_name: str, command: list[str], container: Optional[str] = None) -> str:
        """Execute a command inside a pod."""
        args = ["exec", pod_name]
        if container:
            args.extend(["-c", container])
        args.append("--")
        args.extend(command)
        return await self._run(args)
