"""Coverage gap tests for CICD modules — endpoint_scanner, argocd_client, git_client,
pipeline_state, jira_client, jenkins_client, sanity_checker, testing_client, jacoco_parser."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

# ---------------------------------------------------------------------------
# endpoint_scanner.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.endpoint_scanner import (
    RestEndpoint,
    GrpcService,
    KafkaListener,
    ScanResult,
    scan_rest_endpoints,
    scan_grpc_services,
    scan_kafka_listeners,
    scan_db_queries,
    scan_all,
    generate_curls,
    generate_grpc_cmds,
    generate_kafka_cmds,
    save_cache,
    load_cache,
    background_scan,
    run_single_endpoint,
    run_all_endpoints,
    format_run_report,
    load_endpoint_config,
    _extract_dto_fields,
    _load_openapi_schemas,
    _generate_sample_body,
)


class TestEndpointScannerCoverage:
    """Cover missing lines in endpoint_scanner.py."""

    def test_scan_rest_endpoints_oserror(self, tmp_path):
        """Line 121-122: OSError when reading a java file."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "Controller.java"
        java_file.write_text("@RestController\n@GetMapping(\"/health\")\npublic class Controller {}")
        # Make file unreadable
        java_file.chmod(0o000)
        try:
            result = scan_rest_endpoints(str(tmp_path))
            # Should not crash, just skip the file
            assert isinstance(result, list)
        finally:
            java_file.chmod(0o644)

    def test_scan_grpc_services_oserror(self, tmp_path):
        """Lines 173-174: OSError reading proto file."""
        proto_file = tmp_path / "service.proto"
        proto_file.write_text("syntax = \"proto3\";")
        proto_file.chmod(0o000)
        try:
            result = scan_grpc_services(str(tmp_path))
            assert isinstance(result, list)
        finally:
            proto_file.chmod(0o644)

    def test_scan_grpc_nested_braces(self, tmp_path):
        """Lines 185+: gRPC service with nested braces."""
        proto_file = tmp_path / "service.proto"
        proto_file.write_text("""
service PaymentService {
  rpc Pay(PayRequest) returns (PayResponse);
  rpc Refund(RefundRequest) returns (RefundResponse);
}
""")
        result = scan_grpc_services(str(tmp_path))
        assert len(result) == 1
        assert len(result[0].methods) == 2

    def test_scan_kafka_listeners_multiline(self, tmp_path):
        """Lines 218-252: multi-line @KafkaListener with array topics."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "Consumer.java"
        java_file.write_text('''
@KafkaListener(
    topics = {"topic1", "topic2"},
    groupId = "my-group"
)
public void consume(String msg) {}
''')
        result = scan_kafka_listeners(str(tmp_path))
        assert len(result) == 2
        assert any(k.topic == "topic1" for k in result)
        assert result[0].group == "my-group"

    def test_scan_kafka_no_topic_parsed(self, tmp_path):
        """Line 252: fallback when no topic pattern matches."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "Consumer.java"
        java_file.write_text('''
@KafkaListener()
public void consume(String msg) {}
''')
        result = scan_kafka_listeners(str(tmp_path))
        assert len(result) == 1
        assert "unparsed" in result[0].topic

    def test_scan_kafka_oserror(self, tmp_path):
        """Lines 221-222: OSError reading kafka java file."""
        java_file = tmp_path / "Consumer.java"
        java_file.write_text("@KafkaListener(topics=\"test\")")
        java_file.chmod(0o000)
        try:
            result = scan_kafka_listeners(str(tmp_path))
            assert isinstance(result, list)
        finally:
            java_file.chmod(0o644)

    def test_scan_db_queries_oserror(self, tmp_path):
        """Lines 283-287: OSError reading java file for DB queries."""
        java_file = tmp_path / "Repo.java"
        java_file.write_text("@Repository\n@Query(\"SELECT 1\")")
        java_file.chmod(0o000)
        try:
            result = scan_db_queries(str(tmp_path))
            assert isinstance(result, list)
        finally:
            java_file.chmod(0o644)

    def test_extract_dto_fields_empty_class(self, tmp_path):
        """Lines 358-387: DTO extraction — class found but no fields."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "EmptyDto.java"
        java_file.write_text("public class EmptyDto { }")
        result = _extract_dto_fields(str(tmp_path), "EmptyDto")
        assert result is None

    def test_extract_dto_fields_with_fields(self, tmp_path):
        """Lines 358-387: DTO extraction — class with fields."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "PaymentRequest.java"
        java_file.write_text("""
public class PaymentRequest {
    private String name;
    private int amount;
    private boolean active;
}
""")
        result = _extract_dto_fields(str(tmp_path), "PaymentRequest")
        assert result is not None
        data = json.loads(result)
        assert "name" in data
        assert "amount" in data

    def test_extract_dto_fields_not_found(self, tmp_path):
        """DTO class not found."""
        result = _extract_dto_fields(str(tmp_path), "NonExistent")
        assert result is None

    def test_extract_dto_fields_empty_inputs(self):
        """Empty class_name or repo_path."""
        assert _extract_dto_fields("", "Foo") is None
        assert _extract_dto_fields("/tmp", "") is None

    def test_load_openapi_schemas_yaml(self, tmp_path):
        """Lines 417-418, 433-477: OpenAPI YAML loading."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/payment": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "amount": {"type": "integer"},
                                            "currency": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "get": {},
                }
            }
        }
        import yaml
        spec_file = tmp_path / "openapi.yaml"
        spec_file.write_text(yaml.dump(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/payment" in result

    def test_load_openapi_schemas_json(self, tmp_path):
        """OpenAPI JSON loading."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/users": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/users" in result

    def test_load_openapi_schemas_swagger2(self, tmp_path):
        """Swagger 2.0 with body parameters."""
        spec = {
            "swagger": "2.0",
            "paths": {
                "/api/items": {
                    "post": {
                        "parameters": [
                            {
                                "in": "body",
                                "name": "body",
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"}
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        spec_file = tmp_path / "swagger.json"
        spec_file.write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/items" in result

    def test_load_openapi_schemas_with_ref(self, tmp_path):
        """Schema with $ref."""
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "MyDto": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}}
                    }
                }
            },
            "paths": {
                "/api/test": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/MyDto"}
                                }
                            }
                        }
                    }
                }
            }
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/test" in result

    def test_load_openapi_schemas_none(self, tmp_path):
        """No spec file found."""
        result = _load_openapi_schemas(str(tmp_path))
        assert result == {}

    def test_load_openapi_schema_types(self, tmp_path):
        """Cover various schema types: string formats, number, boolean, array."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/all-types": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "d": {"type": "string", "format": "date"},
                                            "dt": {"type": "string", "format": "date-time"},
                                            "uid": {"type": "string", "format": "uuid"},
                                            "email": {"type": "string", "format": "email"},
                                            "num": {"type": "number"},
                                            "flag": {"type": "boolean"},
                                            "items": {"type": "array", "items": {"type": "string"}},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/all-types" in result

    def test_load_openapi_non_dict_path_methods(self, tmp_path):
        """Lines 471-477: non-dict values in paths/methods."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/test": "invalid",
                "/api/test2": {
                    "post": "not_a_dict"
                }
            }
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert result == {}

    def test_generate_sample_body_payment(self):
        """Lines 505-522: heuristic body generation."""
        result = _generate_sample_body("CreatePaymentRequest")
        data = json.loads(result)
        assert "amount" in data or "currency" in data

    def test_generate_sample_body_user(self):
        result = _generate_sample_body("UserRequest")
        data = json.loads(result)
        assert "name" in data or "email" in data

    def test_generate_sample_body_empty(self):
        result = _generate_sample_body("")
        assert result == '{"field1": "value1"}'

    def test_generate_sample_body_unknown(self):
        result = _generate_sample_body("XyzDto")
        data = json.loads(result)
        assert len(data) > 0

    def test_generate_curls_with_openapi(self, tmp_path):
        """Lines 540-541: curls with OpenAPI body."""
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/test": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "integer"}}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))

        eps = [RestEndpoint(method="POST", path="/api/test")]
        curls = generate_curls(eps, repo_path=str(tmp_path))
        assert len(curls) == 1
        assert "POST" in curls[0]

    def test_generate_curls_with_dto(self, tmp_path):
        """Lines 552: curls with DTO body fallback."""
        java_dir = tmp_path / "src"
        java_dir.mkdir()
        java_file = java_dir / "MyDto.java"
        java_file.write_text("public class MyDto { private String name; }")

        eps = [RestEndpoint(method="POST", path="/api/data", request_body="MyDto")]
        curls = generate_curls(eps, repo_path=str(tmp_path))
        assert len(curls) == 1

    def test_run_all_endpoints_types(self, tmp_path):
        """Lines 658-710: run_all_endpoints with different types."""
        result = ScanResult(repo_name="test")
        result.rest_endpoints = [RestEndpoint(method="GET", path="/health")]
        result.grpc_services = [GrpcService(service_name="Svc", methods=[{"name": "Rpc", "request_type": "Req"}])]
        result.kafka_listeners = [KafkaListener(topic="test-topic")]

        with patch("code_agents.cicd.endpoint_scanner.run_single_endpoint", return_value={"passed": True, "command": "curl", "status_code": 200, "body": "", "stderr": "", "exit_code": 0, "duration_ms": 10}):
            # Test rest only
            results = run_all_endpoints(result, endpoint_type="rest")
            assert len(results) >= 1

            # Test grpc only
            results = run_all_endpoints(result, endpoint_type="grpc")
            assert len(results) >= 1

            # Test kafka only
            results = run_all_endpoints(result, endpoint_type="kafka")
            assert len(results) >= 1

            # Test all with auth header
            results = run_all_endpoints(result, auth_header="Bearer token123")
            assert len(results) >= 3

    def test_run_single_endpoint_timeout(self):
        """Lines 658-659: timeout in run_single_endpoint."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            result = run_single_endpoint("curl http://localhost", timeout=1)
            assert result["passed"] is False
            assert "Timed out" in result["stderr"]

    def test_run_single_endpoint_exception(self):
        """General exception in run_single_endpoint."""
        with patch("subprocess.run", side_effect=Exception("boom")):
            result = run_single_endpoint("curl http://localhost")
            assert result["passed"] is False
            assert "boom" in result["stderr"]

    def test_format_run_report_empty(self):
        assert format_run_report([]) == "No endpoints to run."

    def test_format_run_report_results(self):
        results = [
            {"passed": True, "command": "curl /a", "type": "rest", "duration_ms": 50, "stderr": ""},
            {"passed": False, "command": "curl /b", "type": "rest", "duration_ms": 100, "stderr": "Connection refused"},
        ]
        output = format_run_report(results)
        assert "1 passed" in output
        assert "1 failed" in output
        assert "Connection refused" in output

    def test_load_endpoint_config(self, tmp_path):
        """load_endpoint_config returns empty dict when no file."""
        result = load_endpoint_config(str(tmp_path))
        assert result == {}

    def test_load_endpoint_config_with_file(self, tmp_path):
        """load_endpoint_config loads YAML."""
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        config_file = config_dir / "endpoints.yaml"
        config_file.write_text("base_url: http://localhost:8080\n")
        result = load_endpoint_config(str(tmp_path))
        assert result["base_url"] == "http://localhost:8080"

    def test_scan_kafka_constant_topic(self, tmp_path):
        """Kafka listener with constant topic name."""
        java_file = tmp_path / "Consumer.java"
        java_file.write_text('''
@KafkaListener(topics = PAYMENT_TOPIC, groupId = "group1")
public void consume(String msg) {}
''')
        result = scan_kafka_listeners(str(tmp_path))
        assert len(result) == 1
        assert result[0].topic == "PAYMENT_TOPIC"

    def test_scan_kafka_spel_topic(self, tmp_path):
        """Kafka listener with SpEL topic."""
        java_file = tmp_path / "Consumer.java"
        java_file.write_text('''
@KafkaListener(topics = '${kafka.topic.name}')
public void consume(String msg) {}
''')
        result = scan_kafka_listeners(str(tmp_path))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# argocd_client.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.argocd_client import ArgoCDClient, ArgoCDError


class TestArgoCDClientCoverage:
    """Cover missing lines in argocd_client.py."""

    @pytest.fixture
    def client(self):
        return ArgoCDClient(
            base_url="https://argocd.example.com",
            auth_token="test-token",
            poll_interval=0.01,
            poll_timeout=0.1,
        )

    @pytest.fixture
    def client_with_creds(self):
        return ArgoCDClient(
            base_url="https://argocd.example.com",
            username="admin",
            password="secret",
            poll_interval=0.01,
            poll_timeout=0.1,
        )

    def test_login_no_creds(self):
        """Line 85: _login raises when no credentials."""
        client = ArgoCDClient(base_url="https://argocd.example.com")
        with pytest.raises(ArgoCDError, match="No auth_token"):
            asyncio.run(client._login())

    def test_login_success(self, client_with_creds):
        """Line 129: successful login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "new-token"}

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                instance.post = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance
                await client_with_creds._login()

        asyncio.run(run())
        assert client_with_creds.auth_token == "new-token"

    def test_login_failed(self, client_with_creds):
        """Login with bad credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                instance.post = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance
                with pytest.raises(ArgoCDError, match="login failed"):
                    await client_with_creds._login(force=True)

        asyncio.run(run())

    def test_login_missing_token(self, client_with_creds):
        """Login response without token field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                instance.post = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance
                with pytest.raises(ArgoCDError, match="missing token"):
                    await client_with_creds._login(force=True)

        asyncio.run(run())

    def test_get_app_status_images(self, client):
        """Line 165, 172: extract images from status summary."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": {
                "sync": {"status": "Synced", "revision": "abc123"},
                "health": {"status": "Healthy"},
                "summary": {"images": ["registry/app:v1.0"]},
                "conditions": [],
            },
            "spec": {"source": {}},
        }

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                result = await client.get_app_status("my-app")
            assert result["images"] == ["registry/app:v1.0"]

        asyncio.run(run())

    def test_get_pod_logs(self, client):
        """Lines 227-262: pod log retrieval with error scanning."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "INFO starting\nERROR NullPointerException\nINFO done"

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                result = await client.get_pod_logs("app", "pod-1", "default", container="main")
            assert result["has_errors"] is True
            assert len(result["error_lines"]) == 1

        asyncio.run(run())

    def test_get_pod_logs_failed(self, client):
        """Pod logs 404."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                with pytest.raises(ArgoCDError):
                    await client.get_pod_logs("app", "pod-1", "default")

        asyncio.run(run())

    def test_sync_app(self, client):
        """Lines 255-262: sync with revision."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                result = await client.sync_app("my-app", revision="abc123")
            assert result["status"] == "sync_triggered"
            assert result["revision"] == "abc123"

        asyncio.run(run())

    def test_sync_app_failed(self, client):
        """Sync failure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Error"

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                with pytest.raises(ArgoCDError):
                    await client.sync_app("my-app")

        asyncio.run(run())

    def test_rollback(self, client):
        """Lines 268-271: rollback."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                result = await client.rollback("my-app", 5)
            assert result["target_revision_id"] == 5

        asyncio.run(run())

    def test_rollback_failed(self, client):
        """Rollback failure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"

        async def run():
            with patch.object(client, "_request", return_value=mock_resp):
                with pytest.raises(ArgoCDError):
                    await client.rollback("my-app", 5)

        asyncio.run(run())

    def test_rollback_to_revision_string(self, client):
        """Line 283: rollback_to_revision with string (git SHA)."""
        async def run():
            with patch.object(client, "sync_app", return_value={"status": "sync_triggered"}) as mock_sync:
                result = await client.rollback_to_revision("my-app", "abc123")
            mock_sync.assert_called_once_with("my-app", revision="abc123")

        asyncio.run(run())

    def test_rollback_to_revision_int(self, client):
        """rollback_to_revision with int (deployment revision)."""
        async def run():
            with patch.object(client, "rollback", return_value={"status": "rollback_triggered"}) as mock_rb:
                result = await client.rollback_to_revision("my-app", 3)
            mock_rb.assert_called_once_with("my-app", revision_id=3)

        asyncio.run(run())

    def test_request_401_retry(self, client_with_creds):
        """Line 129: 401 retry with re-auth."""
        mock_401 = MagicMock()
        mock_401.status_code = 401

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"status": {}}

        call_count = [0]

        async def mock_request(method, path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_401
            return mock_200

        async def run():
            client_with_creds.auth_token = "old-token"
            with patch.object(client_with_creds, "_login", new_callable=AsyncMock):
                with patch("httpx.AsyncClient") as MockClient:
                    instance = AsyncMock()
                    instance.__aenter__ = AsyncMock(return_value=instance)
                    instance.__aexit__ = AsyncMock(return_value=False)
                    instance.request = AsyncMock(side_effect=[mock_401, mock_200])
                    MockClient.return_value = instance
                    result = await client_with_creds._request("GET", "/api/v1/applications/test")
                assert result.status_code == 200

        asyncio.run(run())


# ---------------------------------------------------------------------------
# git_client.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.git_client import GitClient, GitOpsError, _validate_ref


class TestGitClientCoverage:
    """Cover missing lines in git_client.py."""

    def test_validate_ref_invalid(self):
        """Lines 62-63: invalid ref raises error."""
        with pytest.raises(GitOpsError, match="Invalid"):
            _validate_ref("", "branch")
        with pytest.raises(GitOpsError, match="Invalid"):
            _validate_ref("bad branch!", "branch")

    def test_run_check_failure(self, tmp_path):
        """Lines 62-63: _run with check=True on bad command."""
        client = GitClient(str(tmp_path))

        async def run():
            with pytest.raises(GitOpsError):
                await client._run("log", "--bad-flag-that-does-not-exist")

        asyncio.run(run())

    def test_diff_large(self, tmp_path):
        """Lines 123-127: diff with > 100 files."""
        client = GitClient(str(tmp_path))

        async def run():
            stat_out = "100 files changed"
            # Generate 101 numstat lines
            numstat_lines = "\n".join(f"10\t5\tfile{i}.py" for i in range(101))
            diff_out = "some diff"

            with patch.object(client, "_run", new_callable=AsyncMock) as mock_run:
                mock_run.side_effect = [
                    (stat_out, ""),
                    (numstat_lines, ""),
                ]
                result = await client.diff("main", "feature")

            assert result["truncated"] is True
            assert result["files_changed"] == 101
            assert len(result["changed_files"]) <= 50

        asyncio.run(run())

    def test_diff_truncated_output(self, tmp_path):
        """Lines 133-134: diff with very long output."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run", new_callable=AsyncMock) as mock_run:
                mock_run.side_effect = [
                    ("stat", ""),
                    ("10\t5\tfile.py", ""),
                    ("x" * 40000, ""),  # very long diff
                ]
                result = await client.diff("main", "feature")

            assert result["truncated"] is True
            assert "truncated" in result["diff"]

        asyncio.run(run())

    def test_push(self, tmp_path):
        """Lines 169-172: push operation."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run", new_callable=AsyncMock, return_value=("", "pushed")):
                result = await client.push("main")
            assert result["success"] is True
            assert result["branch"] == "main"

        asyncio.run(run())

    def test_fetch(self, tmp_path):
        """Lines 181-183: fetch operation."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run", new_callable=AsyncMock, return_value=("", "")):
                result = await client.fetch()
            assert "fetch complete" in result

        asyncio.run(run())

    def test_checkout_dirty_tree(self, tmp_path):
        """Lines 226-229: checkout with dirty working tree."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "status", new_callable=AsyncMock, return_value={"clean": False, "files": [{"status": "M", "file": "a.py"}]}):
                with pytest.raises(GitOpsError, match="uncommitted"):
                    await client.checkout("feature")

        asyncio.run(run())

    def test_create_branch_with_start_point(self, tmp_path):
        """Line 226-229: create_branch with start_point."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "checkout", new_callable=AsyncMock, return_value={"success": True}):
                result = await client.create_branch("feature", start_point="main")
            assert result["success"] is True

        asyncio.run(run())

    def test_list_branches_empty_line(self, tmp_path):
        """Line 83: empty line in branch list."""
        client = GitClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run", new_callable=AsyncMock, return_value=("main abc123\n\nfeature def456 origin/feature", "")):
                result = await client.list_branches()
            assert len(result) == 2

        asyncio.run(run())


# ---------------------------------------------------------------------------
# pipeline_state.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.pipeline_state import PipelineStateManager, PipelineRun, StepStatus, STEP_NAMES


class TestPipelineStateCoverage:
    """Cover missing lines in pipeline_state.py."""

    @pytest.fixture
    def mgr(self):
        return PipelineStateManager()

    def test_start_step_not_found(self, mgr):
        """Line 143: start_step KeyError."""
        with pytest.raises(KeyError):
            mgr.start_step("nonexistent")

    def test_fail_step(self, mgr):
        """Lines 151-155: fail_step with details."""
        run = mgr.create_run("main", "/repo")
        updated = mgr.fail_step(run.run_id, "Build failed", details={"exit_code": 1})
        assert updated.step_status[1] == StepStatus.FAILED
        assert updated.error == "Build failed"
        assert updated.step_details[1] == {"exit_code": 1}

    def test_fail_step_not_found(self, mgr):
        """Line 151: fail_step KeyError."""
        with pytest.raises(KeyError):
            mgr.fail_step("nonexistent", "error")

    def test_set_step_details_not_found(self, mgr):
        """Line 166: set_step_details KeyError."""
        with pytest.raises(KeyError):
            mgr.set_step_details("nonexistent", 1, {})

    def test_trigger_rollback_not_found(self, mgr):
        """Line 174: trigger_rollback KeyError."""
        with pytest.raises(KeyError):
            mgr.trigger_rollback("nonexistent")

    def test_store_previous_revision(self, mgr):
        """Lines 188-192: store_previous_revision."""
        run = mgr.create_run("main", "/repo")
        mgr.store_previous_revision(run.run_id, "abc123")
        assert run.previous_revision == "abc123"

    def test_store_previous_revision_not_found(self, mgr):
        """Lines 188-192: KeyError."""
        with pytest.raises(KeyError):
            mgr.store_previous_revision("nonexistent", "abc")

    def test_auto_rollback_on_verify_failure(self, mgr):
        """Lines 199-208: auto rollback when verify step (6) fails."""
        run = mgr.create_run("main", "/repo")
        # Advance to step 6 (verify) — 5 advances from step 1
        for _ in range(5):
            mgr.advance(run.run_id)
        assert run.current_step == 6
        # Fail step 6 (verify)
        mgr.fail_step(run.run_id, "Smoke test failed")
        # Auto rollback
        result = mgr.auto_rollback_on_verify_failure(run.run_id)
        assert result is not None
        assert result.current_step == 7
        assert result.step_status[7] == StepStatus.IN_PROGRESS

    def test_auto_rollback_not_step5(self, mgr):
        """Lines 199-208: auto rollback returns None when not on step 5."""
        run = mgr.create_run("main", "/repo")
        result = mgr.auto_rollback_on_verify_failure(run.run_id)
        assert result is None

    def test_auto_rollback_not_found(self, mgr):
        """KeyError for auto_rollback."""
        with pytest.raises(KeyError):
            mgr.auto_rollback_on_verify_failure("nonexistent")

    def test_trigger_rollback_skips_remaining(self, mgr):
        """Line 174: trigger_rollback skips steps between current and 7."""
        run = mgr.create_run("main", "/repo")
        mgr.advance(run.run_id)  # step 2
        mgr.trigger_rollback(run.run_id)
        assert run.current_step == 7
        for i in range(3, 7):
            assert run.step_status[i] == StepStatus.SKIPPED

    def test_fail_step_no_details(self, mgr):
        """Line 155: fail_step without details dict."""
        run = mgr.create_run("main", "/repo")
        updated = mgr.fail_step(run.run_id, "failed")
        assert 1 not in updated.step_details


# ---------------------------------------------------------------------------
# jira_client.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.jira_client import JiraClient, JiraError


class TestJiraClientCoverage:
    """Cover missing lines in jira_client.py."""

    @pytest.fixture
    def client(self):
        return JiraClient(
            base_url="https://jira.example.com",
            email="user@example.com",
            api_token="token123",
        )

    def test_client_creates_with_follow_redirects(self, client):
        """Line 47: _client creates httpx.AsyncClient."""
        c = client._client()
        assert c is not None

    def test_bulk_transition(self, client):
        """Lines 247-268: bulk_transition."""

        async def run():
            with patch.object(client, "get_transitions", return_value=[
                {"id": "31", "name": "Done", "to": "Done"},
            ]):
                with patch.object(client, "transition_issue", return_value={}):
                    results = await client.bulk_transition(["PROJ-1", "PROJ-2"], "Done")
            assert len(results) == 2
            assert all(r["status"] == "ok" for r in results)

        asyncio.run(run())

    def test_bulk_transition_no_match(self, client):
        """Lines 257-258: transition name not found."""

        async def run():
            with patch.object(client, "get_transitions", return_value=[
                {"id": "31", "name": "In Progress", "to": "In Progress"},
            ]):
                results = await client.bulk_transition(["PROJ-1"], "Done")
            assert results[0]["status"] == "error"
            assert "not found" in results[0]["message"]

        asyncio.run(run())

    def test_bulk_transition_exception(self, client):
        """Lines 266-268: exception during transition."""

        async def run():
            with patch.object(client, "get_transitions", side_effect=Exception("network error")):
                results = await client.bulk_transition(["PROJ-1"], "Done")
            assert results[0]["status"] == "error"
            assert "network error" in results[0]["message"]

        asyncio.run(run())


# ---------------------------------------------------------------------------
# jenkins_client.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.jenkins_client import JenkinsClient, JenkinsError


class TestJenkinsClientCoverage:
    """Cover missing lines in jenkins_client.py."""

    @pytest.fixture
    def client(self):
        return JenkinsClient(
            base_url="https://jenkins.example.com",
            username="admin",
            api_token="token",
            poll_interval=0.01,
            poll_timeout=0.1,
        )

    def test_client_method(self, client):
        """Line 50: _client creation."""
        c = client._client()
        assert c is not None

    def test_get_crumb_failure(self, client):
        """Lines 67-68: crumb fetch fails."""

        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await client._get_crumb(mock_client)
            assert result == {}

        asyncio.run(run())

    def test_job_path_with_job_prefix(self, client):
        """Line 91: job path with 'job/' prefix already."""
        path = client._job_path("job/pg2/job/builds/my-job")
        assert path == "/job/pg2/job/builds/job/my-job"

    def test_list_jobs_error(self, client):
        """Line 104: list_jobs HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.text = "Error"
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.list_jobs()

        asyncio.run(run())

    def test_trigger_build_error(self, client):
        """Lines 202: trigger_build HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                instance.get = AsyncMock(return_value=MagicMock(status_code=200, json=MagicMock(return_value={"crumbRequestField": "Jenkins-Crumb", "crumb": "abc"})))
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.text = "Error"
                mock_resp.headers = {}
                instance.post = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                client._crumb = None
                with pytest.raises(JenkinsError):
                    await client.trigger_build("my-job")

        asyncio.run(run())

    def test_trigger_build_with_params_and_queue(self, client):
        """Lines 214-215: trigger_build with parameters and queue location."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                instance.get = AsyncMock(return_value=MagicMock(status_code=200, json=MagicMock(return_value={"crumbRequestField": "Jenkins-Crumb", "crumb": "abc"})))
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_resp.text = ""
                mock_resp.headers = {"Location": "https://jenkins.example.com/queue/item/42/"}
                instance.post = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                client._crumb = None
                result = await client.trigger_build("my-job", parameters={"BRANCH": "main"})
                assert result["queue_id"] == 42

        asyncio.run(run())

    def test_get_build_from_queue_cancelled(self, client):
        """Lines 241-242: build cancelled in queue."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"cancelled": True}
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                result = await client.get_build_from_queue(42)
                assert result is None

        asyncio.run(run())

    def test_get_build_status_error(self, client):
        """Line 250: get_build_status HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 404
                mock_resp.text = "Not Found"
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.get_build_status("my-job", 1)

        asyncio.run(run())

    def test_get_build_log_error(self, client):
        """Line 274: get_build_log HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                mock_resp.text = "Error"
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.get_build_log("my-job", 1)

        asyncio.run(run())

    def test_get_last_build(self, client):
        """Lines 288-320: get_last_build with version extraction."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                build_resp = MagicMock()
                build_resp.status_code = 200
                build_resp.json.return_value = {
                    "number": 42, "result": "SUCCESS", "building": False, "url": "http://j/42",
                }
                log_resp = MagicMock()
                log_resp.status_code = 200
                log_resp.text = "BUILD_VERSION=1.2.3\nFinished: SUCCESS"
                instance.get = AsyncMock(side_effect=[build_resp, log_resp])
                MockClient.return_value = instance
                result = await client.get_last_build("my-job")
                assert result["build_version"] == "1.2.3"

        asyncio.run(run())

    def test_get_last_build_error(self, client):
        """Lines 288-292: get_last_build HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 404
                mock_resp.text = "Not Found"
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.get_last_build("my-job")

        asyncio.run(run())

    def test_get_last_build_log_fetch_error(self, client):
        """Lines 317-318: console log fetch fails during get_last_build."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                build_resp = MagicMock()
                build_resp.status_code = 200
                build_resp.json.return_value = {"number": 42, "result": "SUCCESS", "building": False, "url": "http://j/42"}
                log_resp = MagicMock()
                log_resp.status_code = 500
                log_resp.text = "Error"
                instance.get = AsyncMock(side_effect=[build_resp, log_resp])
                MockClient.return_value = instance
                # Should not crash, just have no version
                result = await client.get_last_build("my-job")
                assert result["build_version"] is None

        asyncio.run(run())

    def test_get_build_artifacts_error(self, client):
        """Lines 393-403: get_build_artifacts HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 404
                mock_resp.text = "Not Found"
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.get_build_artifacts("my-job", 1)

        asyncio.run(run())

    def test_trigger_and_wait_no_build_number(self, client):
        """Lines 417-431: trigger_and_wait when no build number obtained."""

        async def run():
            with patch.object(client, "trigger_build", return_value={"queue_id": None, "build_number": None}):
                result = await client.trigger_and_wait("my-job")
            assert result["status"] == "failed"

        asyncio.run(run())

    def test_trigger_and_wait_with_queue(self, client):
        """Lines 421-452: trigger_and_wait with queue polling."""

        async def run():
            with patch.object(client, "trigger_build", return_value={"queue_id": 42, "build_number": None}):
                with patch.object(client, "get_build_from_queue", return_value=10):
                    with patch.object(client, "wait_for_build", return_value={"result": "SUCCESS", "building": False, "duration": 1000}):
                        with patch.object(client, "get_build_log", return_value="BUILD_VERSION=2.0\nDone"):
                            result = await client.trigger_and_wait("my-job")
            assert result["build_version"] == "2.0"

        asyncio.run(run())

    def test_trigger_and_wait_log_error(self, client):
        """Lines 449-450: trigger_and_wait when log fetch fails."""

        async def run():
            with patch.object(client, "trigger_build", return_value={"queue_id": 42, "build_number": None}):
                with patch.object(client, "get_build_from_queue", return_value=10):
                    with patch.object(client, "wait_for_build", return_value={"result": "SUCCESS", "building": False}):
                        with patch.object(client, "get_build_log", side_effect=Exception("log error")):
                            result = await client.trigger_and_wait("my-job")
            assert result["build_version"] is None

        asyncio.run(run())

    def test_get_build_from_queue_build_error(self, client):
        """Line 231: get_build_from_queue HTTP error."""

        async def run():
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 500
                instance.get = AsyncMock(return_value=mock_resp)
                MockClient.return_value = instance
                with pytest.raises(JenkinsError):
                    await client.get_build_from_queue(42)

        asyncio.run(run())

    def test_extract_build_version_docker_push(self):
        """Line 393-397: docker push manifest pattern."""
        log = "pushing manifest for registry.example.com/service:1.2.3-42@sha256:abc"
        result = JenkinsClient.extract_build_version(log)
        assert result == "1.2.3-42"


# ---------------------------------------------------------------------------
# sanity_checker.py — missing lines 210-211
# ---------------------------------------------------------------------------
from code_agents.cicd.sanity_checker import discover_health_endpoints, EndpointCheck


class TestSanityCheckerCoverage:
    """Cover missing lines 210-211 in sanity_checker.py."""

    def test_discover_default_when_no_cache(self, tmp_path):
        """Lines 210-211: no endpoint cache returns default actuator health."""
        result = discover_health_endpoints(str(tmp_path))
        assert len(result) >= 1
        assert "actuator/health" in result[0].url


# ---------------------------------------------------------------------------
# testing_client.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.cicd.testing_client import TestingClient, TestingError


class TestTestingClientCoverage:
    """Cover missing lines in testing_client.py."""

    def test_detect_test_command_node(self, tmp_path):
        """Line 68: Node.js detection."""
        (tmp_path / "package.json").write_text("{}")
        client = TestingClient(str(tmp_path))
        cmd = client._detect_test_command()
        assert "npm test" in cmd

    def test_detect_test_command_maven(self, tmp_path):
        """Maven detection."""
        (tmp_path / "pom.xml").write_text("<project/>")
        client = TestingClient(str(tmp_path))
        cmd = client._detect_test_command()
        assert "mvn test" in cmd

    def test_detect_test_command_gradle(self, tmp_path):
        """Gradle detection."""
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        client = TestingClient(str(tmp_path))
        cmd = client._detect_test_command()
        assert "gradlew" in cmd or "gradle" in cmd

    def test_detect_test_command_go(self, tmp_path):
        """Go detection."""
        (tmp_path / "go.mod").write_text("module example")
        client = TestingClient(str(tmp_path))
        cmd = client._detect_test_command()
        assert "go test" in cmd

    def test_detect_test_command_default(self, tmp_path):
        """Default fallback."""
        client = TestingClient(str(tmp_path))
        cmd = client._detect_test_command()
        assert "pytest" in cmd

    def test_run_tests_with_branch(self, tmp_path):
        """Lines 102-104: run_tests with branch checkout failure."""
        client = TestingClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run_command", return_value=(1, "", "error: branch not found")):
                with pytest.raises(TestingError, match="Failed to checkout"):
                    await client.run_tests(branch="nonexistent")

        asyncio.run(run())

    def test_run_tests_parses_output(self, tmp_path):
        """Lines 131-137: test output parsing and truncation."""
        client = TestingClient(str(tmp_path))

        async def run():
            with patch.object(client, "_run_command", return_value=(0, "10 passed, 2 failed, 1 error\n" + "x" * 25000, "")):
                result = await client.run_tests(test_command="pytest")
            assert result["passed_count"] == 10
            assert result["failed_count"] == 2
            assert result["error_count"] == 1
            assert "truncated" in result["output"]

        asyncio.run(run())

    def test_get_coverage_no_file(self, tmp_path):
        """Lines 165-166: no coverage.xml."""
        client = TestingClient(str(tmp_path))

        async def run():
            with pytest.raises(TestingError, match="No coverage.xml"):
                await client.get_coverage()

        asyncio.run(run())

    def test_get_coverage_parse_error(self, tmp_path):
        """Lines 165-166: malformed coverage.xml."""
        (tmp_path / "coverage.xml").write_text("not xml at all <<<")
        client = TestingClient(str(tmp_path))

        async def run():
            with pytest.raises(TestingError, match="Failed to parse"):
                await client.get_coverage()

        asyncio.run(run())

    def test_get_coverage_gaps(self, tmp_path):
        """Lines 215-267: coverage gaps analysis."""
        # Create a coverage.xml
        coverage_xml = '''<?xml version="1.0" ?>
<coverage line-rate="0.8">
    <packages>
        <package>
            <classes>
                <class filename="app.py" line-rate="0.7">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="0"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>'''
        (tmp_path / "coverage.xml").write_text(coverage_xml)
        client = TestingClient(str(tmp_path))

        async def run():
            mock_diff = {
                "changed_files": [
                    {"file": "app.py", "insertions": 10},
                    {"file": "other.py", "insertions": 5},
                ]
            }
            with patch("code_agents.cicd.git_client.GitClient") as MockGit:
                git_instance = AsyncMock()
                git_instance.diff = AsyncMock(return_value=mock_diff)
                MockGit.return_value = git_instance
                result = await client.get_coverage_gaps("main", "feature")

            assert "gaps" in result
            assert result["new_lines_total"] == 15

        asyncio.run(run())

    def test_get_coverage_gaps_no_coverage(self, tmp_path):
        """Lines 226-229: no coverage data available."""
        client = TestingClient(str(tmp_path))

        async def run():
            with patch("code_agents.cicd.git_client.GitClient") as MockGit:
                git_instance = AsyncMock()
                git_instance.diff = AsyncMock(return_value={"changed_files": []})
                MockGit.return_value = git_instance
                result = await client.get_coverage_gaps("main", "feature")
            assert "error" in result

        asyncio.run(run())

    def test_get_coverage_gaps_diff_error(self, tmp_path):
        """Lines 220-223: diff fails."""
        from code_agents.cicd.git_client import GitOpsError
        client = TestingClient(str(tmp_path))

        async def run():
            with patch("code_agents.cicd.git_client.GitClient") as MockGit:
                git_instance = AsyncMock()
                git_instance.diff = AsyncMock(side_effect=GitOpsError("bad diff"))
                MockGit.return_value = git_instance
                with pytest.raises(TestingError, match="Failed to get diff"):
                    await client.get_coverage_gaps("main", "feature")

        asyncio.run(run())


# ---------------------------------------------------------------------------
# jacoco_parser.py — missing line 177
# ---------------------------------------------------------------------------
from code_agents.cicd.jacoco_parser import format_coverage_report, CoverageReport, ClassCoverage


class TestJacocoParserCoverage:
    """Cover missing line 177 in jacoco_parser.py."""

    def test_format_coverage_report_skips_zero_total(self):
        """Line 177: classes with line_total == 0 are skipped."""
        report = CoverageReport(
            classes=[
                ClassCoverage(
                    name="Empty",
                    package="com.example",
                    line_covered=0,
                    line_missed=0,
                    branch_covered=0,
                    branch_missed=0,
                ),
                ClassCoverage(
                    name="Real",
                    package="com.example",
                    line_covered=9,
                    line_missed=1,
                    branch_covered=8,
                    branch_missed=2,
                ),
            ],
            total_line_covered=9,
            total_line_missed=1,
        )
        output = format_coverage_report(report)
        assert "com.example.Real" in output
        # Empty class should be skipped (line_total == 0)
        assert "com.example.Empty" not in output
