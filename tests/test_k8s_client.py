"""Tests for k8s_client.py — unit tests with mocked subprocess."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from code_agents.cicd.k8s_client import K8sClient, K8sError


class TestK8sClientInit:
    def test_defaults(self):
        c = K8sClient()
        assert c.namespace == "default"
        assert c.context is None
        assert c.kubeconfig is None
        assert c.timeout == 30.0
        assert c.ssh_host is None
        assert c.is_remote is False

    def test_custom_init(self):
        c = K8sClient(
            namespace="prod",
            context="eks-prod",
            kubeconfig="/home/user/.kube/prod",
            timeout=60.0,
            ssh_host="bastion.example.com",
            ssh_key="/home/user/.ssh/id_rsa",
            ssh_user="ubuntu",
            ssh_port=2222,
        )
        assert c.namespace == "prod"
        assert c.context == "eks-prod"
        assert c.kubeconfig == "/home/user/.kube/prod"
        assert c.timeout == 60.0
        assert c.ssh_host == "bastion.example.com"
        assert c.ssh_key == "/home/user/.ssh/id_rsa"
        assert c.ssh_user == "ubuntu"
        assert c.ssh_port == 2222
        assert c.is_remote is True

    def test_is_remote_false_when_no_ssh_host(self):
        c = K8sClient(ssh_host="")
        assert c.is_remote is False

    def test_is_remote_true_when_ssh_host_set(self):
        c = K8sClient(ssh_host="10.0.0.1")
        assert c.is_remote is True


class TestK8sClientKubectlArgs:
    def test_basic_args(self):
        c = K8sClient(namespace="staging")
        result = c._kubectl_args(["get", "pods"])
        assert result == "kubectl -n staging get pods"

    def test_with_kubeconfig(self):
        c = K8sClient(namespace="default", kubeconfig="/tmp/kube")
        result = c._kubectl_args(["get", "pods"])
        assert "--kubeconfig /tmp/kube" in result

    def test_with_context(self):
        c = K8sClient(namespace="default", context="my-ctx")
        result = c._kubectl_args(["get", "pods"])
        assert "--context my-ctx" in result


class TestK8sClientLocalCmd:
    @patch("shutil.which", return_value="/usr/local/bin/kubectl")
    def test_local_cmd_basic(self, mock_which):
        c = K8sClient(namespace="default")
        cmd = c._local_cmd(["get", "pods"])
        assert cmd[0] == "/usr/local/bin/kubectl"
        assert "-n" in cmd
        assert "default" in cmd
        assert "get" in cmd
        assert "pods" in cmd

    @patch("shutil.which", return_value="/usr/local/bin/kubectl")
    def test_local_cmd_with_kubeconfig_and_context(self, mock_which):
        c = K8sClient(namespace="prod", kubeconfig="/tmp/kube", context="prod-ctx")
        cmd = c._local_cmd(["get", "deployments"])
        assert "--kubeconfig" in cmd
        assert "/tmp/kube" in cmd
        assert "--context" in cmd
        assert "prod-ctx" in cmd

    @patch("shutil.which", return_value=None)
    def test_local_cmd_no_kubectl(self, mock_which):
        c = K8sClient()
        with pytest.raises(K8sError, match="kubectl not found"):
            c._local_cmd(["get", "pods"])


class TestK8sClientSSHCmd:
    @patch("shutil.which", return_value="/usr/bin/ssh")
    def test_ssh_cmd_basic(self, mock_which):
        c = K8sClient(ssh_host="bastion.example.com", ssh_key="/tmp/key", ssh_user="ec2-user", ssh_port=22)
        cmd = c._ssh_cmd("kubectl -n default get pods")
        assert cmd[0] == "/usr/bin/ssh"
        assert "-o" in cmd
        assert "StrictHostKeyChecking=no" in cmd
        assert "-i" in cmd
        assert "/tmp/key" in cmd
        assert "ec2-user@bastion.example.com" in cmd
        assert "kubectl -n default get pods" in cmd

    @patch("shutil.which", return_value="/usr/bin/ssh")
    def test_ssh_cmd_custom_port(self, mock_which):
        c = K8sClient(ssh_host="bastion.example.com", ssh_port=2222)
        cmd = c._ssh_cmd("kubectl get pods")
        assert "-p" in cmd
        assert "2222" in cmd

    @patch("shutil.which", return_value="/usr/bin/ssh")
    def test_ssh_cmd_no_key(self, mock_which):
        c = K8sClient(ssh_host="bastion.example.com")
        cmd = c._ssh_cmd("kubectl get pods")
        assert "-i" not in cmd

    @patch("shutil.which", return_value=None)
    def test_ssh_cmd_no_ssh(self, mock_which):
        c = K8sClient(ssh_host="bastion.example.com")
        with pytest.raises(K8sError, match="ssh not found"):
            c._ssh_cmd("kubectl get pods")


class TestK8sClientRun:
    """Test _run with mocked subprocess."""

    @patch("shutil.which", return_value="/usr/local/bin/kubectl")
    def test_run_local_success(self, mock_which):
        c = K8sClient(namespace="default")
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"pod1\npod2", b""))

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"pod1\npod2", b"")):
                mock_proc.communicate = AsyncMock(return_value=(b"pod1\npod2", b""))
                result = asyncio.run(c._run(["get", "pods"]))
                assert result == "pod1\npod2"

    @patch("shutil.which", return_value="/usr/local/bin/kubectl")
    def test_run_local_failure(self, mock_which):
        c = K8sClient(namespace="default")
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error: not found"))

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"", b"error: not found")):
                with pytest.raises(K8sError, match="kubectl failed"):
                    asyncio.run(c._run(["get", "pods"]))

    @patch("shutil.which", return_value="/usr/bin/ssh")
    def test_run_remote_ssh_connection_refused(self, mock_which):
        c = K8sClient(namespace="default", ssh_host="bastion.example.com")
        mock_proc = MagicMock()
        mock_proc.returncode = 255
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Connection refused"))

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"", b"Connection refused")):
                with pytest.raises(K8sError, match="SSH connection failed"):
                    asyncio.run(c._run(["get", "pods"]))

    @patch("shutil.which", return_value="/usr/bin/ssh")
    def test_run_remote_permission_denied(self, mock_which):
        c = K8sClient(namespace="default", ssh_host="bastion.example.com")
        mock_proc = MagicMock()
        mock_proc.returncode = 255
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Permission denied"))

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(b"", b"Permission denied")):
                with pytest.raises(K8sError, match="SSH connection failed"):
                    asyncio.run(c._run(["get", "pods"]))


class TestK8sClientGetPods:
    def _make_pods_json(self) -> str:
        return json.dumps({
            "items": [
                {
                    "metadata": {"name": "web-abc123", "namespace": "prod", "labels": {"app": "web"}},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {"ready": True, "restartCount": 0},
                            {"ready": True, "restartCount": 2},
                        ],
                        "startTime": "2025-01-01T00:00:00Z",
                    },
                    "spec": {
                        "nodeName": "node-1",
                        "containers": [
                            {"image": "web:1.0"},
                            {"image": "sidecar:2.0"},
                        ],
                    },
                },
                {
                    "metadata": {"name": "api-def456", "namespace": "prod", "labels": {}},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [{"ready": False, "restartCount": 5}],
                        "startTime": "2025-01-02T00:00:00Z",
                    },
                    "spec": {"containers": [{"image": "api:3.0"}]},
                },
            ]
        })

    def test_get_pods(self):
        c = K8sClient(namespace="prod")
        pods_json = self._make_pods_json()

        with patch.object(c, "_run", new_callable=AsyncMock, return_value=pods_json):
            pods = asyncio.run(c.get_pods())
            assert len(pods) == 2
            assert pods[0]["name"] == "web-abc123"
            assert pods[0]["status"] == "Running"
            assert pods[0]["ready"] == "2/2"
            assert pods[0]["restarts"] == 2
            assert pods[0]["node"] == "node-1"
            assert pods[0]["images"] == ["web:1.0", "sidecar:2.0"]
            assert pods[1]["name"] == "api-def456"
            assert pods[1]["status"] == "Pending"
            assert pods[1]["ready"] == "0/1"
            assert pods[1]["restarts"] == 5

    def test_get_pods_with_label_selector(self):
        c = K8sClient(namespace="prod")
        pods_json = json.dumps({"items": []})

        with patch.object(c, "_run", new_callable=AsyncMock, return_value=pods_json) as mock_run:
            pods = asyncio.run(c.get_pods(label_selector="app=web"))
            assert pods == []
            call_args = mock_run.call_args[0][0]
            assert "-l" in call_args
            assert "app=web" in call_args


class TestK8sClientGetPodLogs:
    def test_get_pod_logs_basic(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="log line 1\nlog line 2") as mock_run:
            result = asyncio.run(c.get_pod_logs("my-pod"))
            assert result == "log line 1\nlog line 2"
            call_args = mock_run.call_args[0][0]
            assert "logs" in call_args
            assert "my-pod" in call_args
            assert "--tail=100" in call_args

    def test_get_pod_logs_with_container_and_previous(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="old logs") as mock_run:
            result = asyncio.run(
                c.get_pod_logs("my-pod", container="web", tail=50, previous=True)
            )
            call_args = mock_run.call_args[0][0]
            assert "-c" in call_args
            assert "web" in call_args
            assert "--tail=50" in call_args
            assert "--previous" in call_args


class TestK8sClientGetDeployments:
    def test_get_deployments(self):
        c = K8sClient()
        deploy_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "web", "namespace": "prod"},
                    "spec": {
                        "replicas": 3,
                        "strategy": {"type": "RollingUpdate"},
                        "template": {"spec": {"containers": [{"image": "web:1.0"}]}},
                    },
                    "status": {"readyReplicas": 3, "availableReplicas": 3},
                }
            ]
        })
        with patch.object(c, "_run", new_callable=AsyncMock, return_value=deploy_json):
            deploys = asyncio.run(c.get_deployments())
            assert len(deploys) == 1
            assert deploys[0]["name"] == "web"
            assert deploys[0]["replicas"] == "3/3"
            assert deploys[0]["available"] == 3
            assert deploys[0]["images"] == ["web:1.0"]
            assert deploys[0]["strategy"] == "RollingUpdate"


class TestK8sClientGetEvents:
    def test_get_events(self):
        c = K8sClient()
        events_json = json.dumps({
            "items": [
                {
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": "Back-off restarting",
                    "involvedObject": {"kind": "Pod", "name": "web-abc123"},
                    "count": 5,
                    "lastTimestamp": "2025-01-01T00:00:00Z",
                },
            ]
        })
        with patch.object(c, "_run", new_callable=AsyncMock, return_value=events_json):
            events = asyncio.run(c.get_events())
            assert len(events) == 1
            assert events[0]["type"] == "Warning"
            assert events[0]["reason"] == "BackOff"
            assert events[0]["object"] == "Pod/web-abc123"
            assert events[0]["count"] == 5

    def test_get_events_with_field_selector(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value='{"items": []}') as mock_run:
            asyncio.run(c.get_events(field_selector="type=Warning"))
            call_args = mock_run.call_args[0][0]
            assert "--field-selector" in call_args
            assert "type=Warning" in call_args

    def test_get_events_limit(self):
        c = K8sClient()
        items = [{"type": "Normal", "reason": "Pulled", "message": f"msg{i}",
                   "involvedObject": {"kind": "Pod", "name": f"pod{i}"},
                   "count": 1, "lastTimestamp": f"2025-01-0{i+1}T00:00:00Z"}
                 for i in range(30)]
        with patch.object(c, "_run", new_callable=AsyncMock, return_value=json.dumps({"items": items})):
            events = asyncio.run(c.get_events(limit=5))
            assert len(events) == 5


class TestK8sClientGetNamespaces:
    def test_get_namespaces(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="default kube-system prod"):
            ns = asyncio.run(c.get_namespaces())
            assert ns == ["default", "kube-system", "prod"]

    def test_get_namespaces_empty(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value=""):
            ns = asyncio.run(c.get_namespaces())
            assert ns == []


class TestK8sClientGetContexts:
    def test_get_contexts(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = ["eks-prod\neks-staging\n", "eks-prod"]
            contexts = asyncio.run(c.get_contexts())
            assert len(contexts) == 2
            assert contexts[0] == {"name": "eks-prod", "current": True}
            assert contexts[1] == {"name": "eks-staging", "current": False}

    def test_get_contexts_no_current(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = ["eks-prod\n", K8sError("no context")]
            contexts = asyncio.run(c.get_contexts())
            assert len(contexts) == 1
            assert contexts[0]["current"] is False


class TestK8sClientPodDescribe:
    def test_get_pod_describe(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="Name: web-abc\nStatus: Running") as mock_run:
            result = asyncio.run(c.get_pod_describe("web-abc"))
            assert "Name: web-abc" in result
            call_args = mock_run.call_args[0][0]
            assert call_args == ["describe", "pod", "web-abc"]


class TestK8sClientExecCommand:
    def test_exec_command(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="hello") as mock_run:
            result = asyncio.run(
                c.exec_command("web-abc", ["echo", "hello"])
            )
            assert result == "hello"
            call_args = mock_run.call_args[0][0]
            assert call_args == ["exec", "web-abc", "--", "echo", "hello"]

    def test_exec_command_with_container(self):
        c = K8sClient()
        with patch.object(c, "_run", new_callable=AsyncMock, return_value="ok") as mock_run:
            asyncio.run(
                c.exec_command("web-abc", ["ls"], container="sidecar")
            )
            call_args = mock_run.call_args[0][0]
            assert "-c" in call_args
            assert "sidecar" in call_args


class TestK8sError:
    def test_error_message(self):
        err = K8sError("something went wrong", returncode=2)
        assert str(err) == "something went wrong"
        assert err.returncode == 2

    def test_error_defaults(self):
        err = K8sError("oops")
        assert err.returncode == 1
