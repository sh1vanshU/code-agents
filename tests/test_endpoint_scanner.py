"""Tests for endpoint_scanner.py — endpoint & contract auto-discovery."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

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
)


# ── Dataclass tests ──────────────────────────────────────────────────


class TestDataclasses:
    def test_rest_endpoint_defaults(self):
        ep = RestEndpoint(method="GET", path="/api/v1/users")
        assert ep.controller == ""
        assert ep.request_body == ""
        assert ep.file == ""
        assert ep.line == 0

    def test_grpc_service_defaults(self):
        svc = GrpcService(service_name="UserService")
        assert svc.methods == []
        assert svc.file == ""

    def test_kafka_listener_defaults(self):
        kl = KafkaListener(topic="my-topic")
        assert kl.group == ""
        assert kl.method == ""
        assert kl.file == ""
        assert kl.line == 0

    def test_scan_result_total_empty(self):
        sr = ScanResult(repo_name="test")
        assert sr.total == 0

    def test_scan_result_total_mixed(self):
        sr = ScanResult(
            repo_name="test",
            rest_endpoints=[RestEndpoint(method="GET", path="/a")],
            grpc_services=[GrpcService(service_name="Svc", methods=[{"name": "Foo"}, {"name": "Bar"}])],
            kafka_listeners=[KafkaListener(topic="t1")],
            db_queries=[{"query": "SELECT 1"}],
        )
        assert sr.total == 5  # 1 REST + 2 gRPC + 1 Kafka + 1 DB

    def test_scan_result_summary_empty(self):
        sr = ScanResult(repo_name="test")
        assert sr.summary() == "0 endpoints"

    def test_scan_result_summary_with_data(self):
        sr = ScanResult(
            repo_name="test",
            rest_endpoints=[RestEndpoint(method="GET", path="/a"), RestEndpoint(method="POST", path="/b")],
            kafka_listeners=[KafkaListener(topic="t1")],
        )
        s = sr.summary()
        assert "3 endpoints" in s
        assert "2 REST" in s
        assert "1 Kafka" in s


# ── REST endpoint scanning ───────────────────────────────────────────


class TestScanRestEndpoints:
    def test_spring_controller(self, tmp_path):
        java = tmp_path / "src" / "UserController.java"
        java.parent.mkdir(parents=True)
        java.write_text(
            '@RestController\n'
            '@RequestMapping("/api/users")\n'
            'public class UserController {\n'
            '    @GetMapping("/list")\n'
            '    public List<User> getUsers() { return null; }\n'
            '    @PostMapping("/create")\n'
            '    public User create(@RequestBody UserDto body) { return null; }\n'
            '}\n'
        )
        eps = scan_rest_endpoints(str(tmp_path))
        # 3 endpoints: class-level @RequestMapping + 2 method-level mappings
        assert len(eps) >= 2
        # Find the GetMapping and PostMapping results
        get_eps = [e for e in eps if e.path.endswith("/list")]
        post_eps = [e for e in eps if e.path.endswith("/create")]
        assert len(get_eps) == 1
        assert get_eps[0].method == "GET"
        assert get_eps[0].controller == "UserController"
        assert len(post_eps) == 1
        assert post_eps[0].method == "POST"
        assert post_eps[0].request_body == "UserDto"

    def test_request_mapping_defaults_to_get(self, tmp_path):
        java = tmp_path / "Ctrl.java"
        java.write_text(
            '@Controller\n'
            'public class Ctrl {\n'
            '    @RequestMapping("/health")\n'
            '    public String health() { return "ok"; }\n'
            '}\n'
        )
        eps = scan_rest_endpoints(str(tmp_path))
        assert len(eps) == 1
        assert eps[0].method == "GET"

    def test_no_controller_skipped(self, tmp_path):
        java = tmp_path / "Service.java"
        java.write_text(
            '@Service\n'
            'public class Service {\n'
            '    @GetMapping("/nope")\n'
            '    public void nope() {}\n'
            '}\n'
        )
        eps = scan_rest_endpoints(str(tmp_path))
        assert len(eps) == 0

    def test_skips_target_dir(self, tmp_path):
        target = tmp_path / "target" / "classes"
        target.mkdir(parents=True)
        java = target / "Ctrl.java"
        java.write_text('@RestController\n@GetMapping("/x")\n')
        eps = scan_rest_endpoints(str(tmp_path))
        assert len(eps) == 0

    def test_empty_repo(self, tmp_path):
        eps = scan_rest_endpoints(str(tmp_path))
        assert eps == []


# ── gRPC scanning ────────────────────────────────────────────────────


class TestScanGrpcServices:
    def test_proto_file(self, tmp_path):
        proto = tmp_path / "user.proto"
        proto.write_text(
            'syntax = "proto3";\n'
            'service UserService {\n'
            '  rpc GetUser (GetUserRequest) returns (UserResponse);\n'
            '  rpc ListUsers (ListRequest) returns (ListResponse);\n'
            '}\n'
        )
        services = scan_grpc_services(str(tmp_path))
        assert len(services) == 1
        assert services[0].service_name == "UserService"
        assert len(services[0].methods) == 2
        assert services[0].methods[0]["name"] == "GetUser"
        assert services[0].methods[0]["request_type"] == "GetUserRequest"

    def test_no_proto_files(self, tmp_path):
        services = scan_grpc_services(str(tmp_path))
        assert services == []

    def test_skips_build_dir(self, tmp_path):
        build = tmp_path / "build" / "gen"
        build.mkdir(parents=True)
        proto = build / "service.proto"
        proto.write_text('service Foo { rpc Bar (Req) returns (Resp); }')
        services = scan_grpc_services(str(tmp_path))
        assert services == []


# ── Kafka scanning ───────────────────────────────────────────────────


class TestScanKafkaListeners:
    def test_simple_listener(self, tmp_path):
        java = tmp_path / "Consumer.java"
        java.write_text(
            'public class Consumer {\n'
            '    @KafkaListener(topics = "payment-events", groupId = "payment-group")\n'
            '    public void listen(String msg) {}\n'
            '}\n'
        )
        listeners = scan_kafka_listeners(str(tmp_path))
        assert len(listeners) == 1
        assert listeners[0].topic == "payment-events"
        assert listeners[0].group == "payment-group"

    def test_multiline_annotation(self, tmp_path):
        java = tmp_path / "Consumer.java"
        java.write_text(
            'public class Consumer {\n'
            '    @KafkaListener(\n'
            '        topics = "order-events",\n'
            '        groupId = "order-group"\n'
            '    )\n'
            '    public void listen(String msg) {}\n'
            '}\n'
        )
        listeners = scan_kafka_listeners(str(tmp_path))
        assert len(listeners) == 1
        assert listeners[0].topic == "order-events"

    def test_array_topics(self, tmp_path):
        java = tmp_path / "Consumer.java"
        java.write_text(
            'public class Consumer {\n'
            '    @KafkaListener(topics = {"topic-a", "topic-b"})\n'
            '    public void listen(String msg) {}\n'
            '}\n'
        )
        listeners = scan_kafka_listeners(str(tmp_path))
        assert len(listeners) == 2
        topics = {l.topic for l in listeners}
        assert "topic-a" in topics
        assert "topic-b" in topics

    def test_no_listeners(self, tmp_path):
        java = tmp_path / "Service.java"
        java.write_text('public class Service { }')
        listeners = scan_kafka_listeners(str(tmp_path))
        assert listeners == []


# ── DB query scanning ────────────────────────────────────────────────


class TestScanDbQueries:
    def test_jpa_query(self, tmp_path):
        java = tmp_path / "UserRepo.java"
        java.write_text(
            '@Repository\n'
            'public interface UserRepo {\n'
            '    @Query("SELECT u FROM User u WHERE u.active = true")\n'
            '    List<User> findActive();\n'
            '}\n'
        )
        queries = scan_db_queries(str(tmp_path))
        assert len(queries) == 1
        assert "SELECT u FROM User u" in queries[0]["query"]
        assert queries[0]["repository"] is True

    def test_native_query(self, tmp_path):
        java = tmp_path / "Repo.java"
        java.write_text(
            '@Repository\n'
            'public interface Repo {\n'
            '    @Query(value = "SELECT * FROM users", nativeQuery = true)\n'
            '    List<User> findAll();\n'
            '}\n'
        )
        queries = scan_db_queries(str(tmp_path))
        assert len(queries) == 1
        assert queries[0]["native"] is True

    def test_no_queries(self, tmp_path):
        assert scan_db_queries(str(tmp_path)) == []


# ── scan_all ─────────────────────────────────────────────────────────


class TestScanAll:
    def test_scan_all_empty(self, tmp_path):
        result = scan_all(str(tmp_path))
        assert result.repo_name == tmp_path.name
        assert result.total == 0

    def test_scan_all_with_rest(self, tmp_path):
        java = tmp_path / "Ctrl.java"
        java.write_text(
            '@RestController\npublic class Ctrl {\n'
            '    @GetMapping("/api/health")\n'
            '    public String health() { return "ok"; }\n}\n'
        )
        result = scan_all(str(tmp_path))
        assert result.total == 1
        assert len(result.rest_endpoints) == 1


# ── Command generation ───────────────────────────────────────────────


class TestGenerateCommands:
    def test_generate_curls_get(self):
        eps = [RestEndpoint(method="GET", path="/api/users")]
        curls = generate_curls(eps)
        assert len(curls) == 1
        assert "-w" in curls[0]
        assert "http://localhost:8080/api/users" in curls[0]

    def test_generate_curls_post(self):
        eps = [RestEndpoint(method="POST", path="/api/users", request_body="UserDto")]
        curls = generate_curls(eps)
        assert len(curls) == 1
        assert "-X POST" in curls[0]
        # Sample body generated from CamelCase class name instead of TODO placeholder
        assert "TODO" not in curls[0]

    def test_generate_curls_custom_base(self):
        eps = [RestEndpoint(method="GET", path="/health")]
        curls = generate_curls(eps, base_url="http://myhost:9090")
        assert "http://myhost:9090/health" in curls[0]

    def test_generate_grpc_cmds(self):
        services = [GrpcService(service_name="UserSvc", methods=[{"name": "Get"}])]
        cmds = generate_grpc_cmds(services)
        assert len(cmds) == 1
        assert "UserSvc/Get" in cmds[0]

    def test_generate_kafka_cmds(self):
        listeners = [KafkaListener(topic="my-topic")]
        cmds = generate_kafka_cmds(listeners)
        assert len(cmds) == 1
        assert "--topic my-topic" in cmds[0]


# ── Cache management ─────────────────────────────────────────────────


class TestCache:
    def test_save_and_load_cache(self, tmp_path):
        result = ScanResult(
            repo_name=tmp_path.name,
            rest_endpoints=[RestEndpoint(method="GET", path="/api/v1")],
        )
        save_cache(str(tmp_path), result)
        loaded = load_cache(str(tmp_path))
        assert loaded is not None
        assert loaded["repo_name"] == tmp_path.name
        assert len(loaded["rest_endpoints"]) == 1

    def test_load_cache_missing(self, tmp_path):
        assert load_cache(str(tmp_path)) is None

    def test_load_cache_corrupt(self, tmp_path):
        cache_dir = tmp_path / ".code-agents"
        cache_dir.mkdir()
        cache_file = cache_dir / f"{tmp_path.name}.endpoints.cache.json"
        cache_file.write_text("not json {{{")
        assert load_cache(str(tmp_path)) is None


# ── background_scan ──────────────────────────────────────────────────


class TestBackgroundScan:
    def test_background_scan_with_endpoints(self, tmp_path):
        java = tmp_path / "Ctrl.java"
        java.write_text(
            '@RestController\npublic class Ctrl {\n'
            '    @GetMapping("/api/health")\n'
            '    public String health() { return "ok"; }\n}\n'
        )
        background_scan(str(tmp_path))
        loaded = load_cache(str(tmp_path))
        assert loaded is not None
        assert loaded["total"] == 1

    def test_background_scan_empty(self, tmp_path):
        background_scan(str(tmp_path))
        # No cache saved when 0 endpoints
        assert load_cache(str(tmp_path)) is None

    def test_background_scan_error(self, tmp_path):
        with patch("code_agents.cicd.endpoint_scanner.scan_all", side_effect=Exception("boom")):
            background_scan(str(tmp_path))  # should not raise


# ── run_single_endpoint ──────────────────────────────────────────────


class TestRunSingleEndpoint:
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"ok": true}', stderr=""
        )
        result = run_single_endpoint('curl -sS "http://localhost/health"')
        assert result["passed"] is True
        assert result["status_code"] == 200
        assert result["exit_code"] == 0

    @patch("subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=7, stdout="", stderr="Connection refused"
        )
        result = run_single_endpoint('curl -sS "http://localhost/bad"')
        assert result["passed"] is False
        assert result["exit_code"] == 7

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("curl", 10))
    def test_timeout(self, mock_run):
        result = run_single_endpoint('curl -sS "http://slow"', timeout=10)
        assert result["passed"] is False
        assert "Timed out" in result["stderr"]

    @patch("subprocess.run", side_effect=OSError("no curl"))
    def test_exception(self, mock_run):
        result = run_single_endpoint("curl http://x")
        assert result["passed"] is False
        assert "no curl" in result["stderr"]


# ── run_all_endpoints ────────────────────────────────────────────────


class TestRunAllEndpoints:
    @patch("code_agents.cicd.endpoint_scanner.run_single_endpoint")
    def test_rest_only(self, mock_run):
        mock_run.return_value = {"passed": True, "status_code": 200, "exit_code": 0,
                                  "duration_ms": 50, "body": "", "stderr": "", "command": "c"}
        result_data = ScanResult(
            repo_name="test",
            rest_endpoints=[RestEndpoint(method="GET", path="/api/v1")],
        )
        results = run_all_endpoints(result_data, endpoint_type="rest")
        assert len(results) == 1
        assert results[0]["type"] == "rest"

    @patch("code_agents.cicd.endpoint_scanner.run_single_endpoint")
    def test_with_auth_header(self, mock_run):
        mock_run.return_value = {"passed": True, "status_code": 200, "exit_code": 0,
                                  "duration_ms": 50, "body": "", "stderr": "", "command": "c"}
        result_data = ScanResult(
            repo_name="test",
            rest_endpoints=[RestEndpoint(method="GET", path="/api/v1")],
        )
        run_all_endpoints(result_data, auth_header="Bearer tok123", endpoint_type="rest")
        call_args = mock_run.call_args[0][0]
        assert "Authorization: Bearer tok123" in call_args


# ── format_run_report ────────────────────────────────────────────────


class TestFormatRunReport:
    def test_empty_results(self):
        assert format_run_report([]) == "No endpoints to run."

    def test_with_results(self):
        results = [
            {"passed": True, "type": "rest", "command": "curl /health", "duration_ms": 42, "stderr": ""},
            {"passed": False, "type": "rest", "command": "curl /bad", "duration_ms": 100, "stderr": "404 Not Found"},
        ]
        output = format_run_report(results)
        assert "1 passed" in output
        assert "1 failed" in output
        assert "PASS" in output
        assert "FAIL" in output
        assert "404 Not Found" in output


# ── load_endpoint_config ─────────────────────────────────────────────


class TestLoadEndpointConfig:
    def test_load_existing(self, tmp_path):
        cfg_dir = tmp_path / ".code-agents"
        cfg_dir.mkdir()
        cfg = cfg_dir / "endpoints.yaml"
        cfg.write_text("base_url: http://localhost:9090\nauth_header: Bearer tok\n")
        config = load_endpoint_config(str(tmp_path))
        assert config["base_url"] == "http://localhost:9090"

    def test_load_missing(self, tmp_path):
        config = load_endpoint_config(str(tmp_path))
        assert config == {}

    def test_load_corrupt(self, tmp_path):
        cfg_dir = tmp_path / ".code-agents"
        cfg_dir.mkdir()
        cfg = cfg_dir / "endpoints.yaml"
        cfg.write_text(": invalid yaml {{{\n")
        config = load_endpoint_config(str(tmp_path))
        assert config == {}


# ---------------------------------------------------------------------------
# DTO field extraction
# ---------------------------------------------------------------------------


class TestExtractDtoFields:
    def test_extracts_java_fields(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "ChargeRequest.java").write_text("""
package com.example;

public class ChargeRequest {
    private String merchantId;
    private long amount;
    private BigDecimal price;
    private boolean active;
    private List<String> tags;
    private LocalDate createdDate;
}
""")
        result = _extract_dto_fields(str(tmp_path), "ChargeRequest")
        assert result is not None
        data = json.loads(result)
        assert data["merchantId"] == "string"
        assert data["amount"] == 0
        assert data["price"] == 0.0
        assert data["active"] is False
        assert data["tags"] == []
        assert data["createdDate"] == "2026-01-01"

    def test_returns_none_for_missing_class(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        result = _extract_dto_fields(str(tmp_path), "NonExistentClass")
        assert result is None

    def test_returns_none_for_empty_inputs(self):
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        assert _extract_dto_fields("", "Foo") is None
        assert _extract_dto_fields("/tmp", "") is None

    def test_skips_test_and_build_dirs(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        test_dir = tmp_path / "src" / "test" / "java"
        test_dir.mkdir(parents=True)
        (test_dir / "MyDto.java").write_text("public class MyDto { private String name; }")
        result = _extract_dto_fields(str(tmp_path), "MyDto")
        assert result is None  # test dir is skipped


class TestLoadOpenapiSchemas:
    def test_loads_openapi_yaml(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/api/orders": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "orderId": {"type": "string"},
                                            "amount": {"type": "integer"},
                                            "active": {"type": "boolean"},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        import yaml
        (tmp_path / "openapi.yaml").write_text(yaml.dump(spec))
        schemas = _load_openapi_schemas(str(tmp_path))
        assert "POST /api/orders" in schemas
        data = json.loads(schemas["POST /api/orders"])
        assert data["orderId"] == "string"
        assert data["amount"] == 0
        assert data["active"] is False

    def test_returns_empty_when_no_spec(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        assert _load_openapi_schemas(str(tmp_path)) == {}

    def test_loads_swagger_json(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        spec = {
            "swagger": "2.0",
            "definitions": {
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    }
                }
            },
            "paths": {
                "/users": {
                    "post": {
                        "parameters": [{
                            "in": "body",
                            "name": "body",
                            "schema": {"$ref": "#/definitions/User"}
                        }]
                    }
                }
            }
        }
        (tmp_path / "swagger.json").write_text(json.dumps(spec))
        schemas = _load_openapi_schemas(str(tmp_path))
        assert "POST /users" in schemas
        data = json.loads(schemas["POST /users"])
        assert data["name"] == "string"
        assert data["age"] == 0


class TestGenerateCurlsWithRepo:
    def test_uses_dto_fields(self, tmp_path):
        from code_agents.cicd.endpoint_scanner import generate_curls, RestEndpoint
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "OrderRequest.java").write_text(
            "public class OrderRequest { private String orderId; private int quantity; }"
        )
        eps = [RestEndpoint(method="POST", path="/api/orders", controller="OrderCtrl",
                            request_body="OrderRequest", file="x.java", line=1)]
        curls = generate_curls(eps, "http://localhost:8080", repo_path=str(tmp_path))
        assert len(curls) == 1
        assert '"orderId"' in curls[0]
        assert '"quantity"' in curls[0]


# ---------------------------------------------------------------------------
# gRPC nested braces (line 185)
# ---------------------------------------------------------------------------


class TestGrpcNestedBraces:
    def test_grpc_service_with_nested_braces(self, tmp_path):
        """gRPC parser handles nested braces in service blocks (line 185)."""
        from code_agents.cicd.endpoint_scanner import scan_grpc_services
        proto_dir = tmp_path / "proto"
        proto_dir.mkdir()
        (proto_dir / "service.proto").write_text("""
syntax = "proto3";

service UserService {
    rpc GetUser (GetUserRequest) returns (GetUserResponse) {
        option (google.api.http) = {
            get: "/api/users/{id}"
        };
    }
    rpc CreateUser (CreateUserRequest) returns (CreateUserResponse);
}
""")
        services = scan_grpc_services(str(tmp_path))
        assert len(services) >= 1
        methods = services[0].methods
        assert any(m["name"] == "GetUser" for m in methods)


# ---------------------------------------------------------------------------
# Kafka listener skip build dir (line 218)
# ---------------------------------------------------------------------------


class TestKafkaSkipBuildDir:
    def test_kafka_skips_build_dir(self, tmp_path):
        """Kafka scanner skips files in /build/ directory (line 218)."""
        from code_agents.cicd.endpoint_scanner import scan_kafka_listeners
        build_dir = tmp_path / "build" / "classes"
        build_dir.mkdir(parents=True)
        (build_dir / "Listener.java").write_text(
            '@KafkaListener(topics = "test-topic")\npublic void listen() {}\n'
        )
        result = scan_kafka_listeners(str(tmp_path))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# JPA skip build dir (line 283)
# ---------------------------------------------------------------------------


class TestJpaSkipBuildDir:
    def test_jpa_skips_build_dir(self, tmp_path):
        """JPA/DB query scanner skips files in /build/ directory (line 283)."""
        from code_agents.cicd.endpoint_scanner import scan_db_queries
        build_dir = tmp_path / "build" / "classes"
        build_dir.mkdir(parents=True)
        (build_dir / "UserRepo.java").write_text(
            '@Repository\npublic interface UserRepo extends JpaRepository<User, Long> {\n'
            '    @Query("SELECT u FROM User u")\n'
            '    List<User> findAll();\n'
            '}\n'
        )
        result = scan_db_queries(str(tmp_path))
        assert len(result) == 0


# ---------------------------------------------------------------------------
# DTO extraction paths (lines 358-359, 378, 385-387)
# ---------------------------------------------------------------------------


class TestExtractDtoFields:
    def test_dto_skip_test_dir(self, tmp_path):
        """DTO search skips test directories (lines 352-353)."""
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        test_dir = tmp_path / "src" / "test" / "java"
        test_dir.mkdir(parents=True)
        (test_dir / "MyDto.java").write_text(
            "public class MyDto { private String name; }"
        )
        result = _extract_dto_fields(str(tmp_path), "MyDto")
        assert result is None  # not found in non-test dirs

    def test_dto_skip_common_fields(self, tmp_path):
        """DTO skips serialVersionUID, log, logger fields (line 378)."""
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "MyDto.java").write_text(
            "public class MyDto { private long serialVersionUID = 1L; private Logger logger; private String name; }"
        )
        result = _extract_dto_fields(str(tmp_path), "MyDto")
        assert result is not None
        data = json.loads(result)
        assert "serialVersionUID" not in data
        assert "logger" not in data
        assert "name" in data

    def test_dto_extraction_exception(self, tmp_path):
        """DTO extraction returns None on exception (lines 385-387)."""
        from code_agents.cicd.endpoint_scanner import _extract_dto_fields
        # Cause an exception by providing invalid repo path
        result = _extract_dto_fields("/nonexistent/path/that/does/not/exist", "SomeDto")
        assert result is None


# ---------------------------------------------------------------------------
# OpenAPI schema loading (lines 417-418, 433, 440, 466-468)
# ---------------------------------------------------------------------------


class TestLoadOpenAPISchemas:
    def test_yaml_parse_exception(self, tmp_path):
        """Invalid YAML spec is skipped (lines 417-418)."""
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        (tmp_path / "openapi.yaml").write_text("invalid: yaml: {{{}}")
        result = _load_openapi_schemas(str(tmp_path))
        assert result == {}

    def test_schema_ref_not_found(self, tmp_path):
        """$ref pointing to missing schema returns fallback (line 440)."""
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/MissingSchema"}
                                }
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}}
        }
        (tmp_path / "openapi.json").write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /users" in result

    def test_schema_array_type(self, tmp_path):
        """Array type schema generates list sample (line 466)."""
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/items": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}}
        }
        (tmp_path / "openapi.json").write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /items" in result
        data = json.loads(result["POST /items"])
        assert isinstance(data, list)

    def test_schema_object_type(self, tmp_path):
        """Object type schema generates dict sample (line 467)."""
        from code_agents.cicd.endpoint_scanner import _load_openapi_schemas
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/data": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "age": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}}
        }
        (tmp_path / "openapi.json").write_text(json.dumps(spec))
        result = _load_openapi_schemas(str(tmp_path))
        assert "POST /data" in result


# ---------------------------------------------------------------------------
# _generate_sample_body no fields (line 522)
# ---------------------------------------------------------------------------


class TestGenerateSampleBodyNoFields:
    def test_all_words_are_verbs_fallback(self):
        """When all CamelCase words are verbs/generic, uses fallback (line 522)."""
        from code_agents.cicd.endpoint_scanner import _generate_sample_body
        result = _generate_sample_body("CreateNew")
        data = json.loads(result)
        assert "id" in data
        assert "data" in data

    def test_empty_class_name_fallback(self):
        """Empty class name returns generic body (line 504-505)."""
        from code_agents.cicd.endpoint_scanner import _generate_sample_body
        result = _generate_sample_body("")
        data = json.loads(result)
        assert "field1" in data


# ---------------------------------------------------------------------------
# generate_curls openapi exception (lines 540-541)
# ---------------------------------------------------------------------------


class TestGenerateCurlsOpenAPIException:
    def test_openapi_load_exception_handled(self, tmp_path):
        """Exception loading OpenAPI schemas is silently caught (lines 540-541)."""
        from code_agents.cicd.endpoint_scanner import generate_curls, RestEndpoint
        eps = [RestEndpoint(method="POST", path="/api/test", controller="TestCtrl",
                            request_body="TestRequest", file="x.java", line=1)]
        with patch("code_agents.cicd.endpoint_scanner._load_openapi_schemas", side_effect=Exception("fail")):
            curls = generate_curls(eps, "http://localhost:8080", repo_path=str(tmp_path))
        assert len(curls) == 1


# ---------------------------------------------------------------------------
# run_curl timeout (lines 658-659)
# ---------------------------------------------------------------------------


class TestRunSingleEndpointTimeout:
    def test_timeout(self):
        """run_single_endpoint handles subprocess timeout (line 658-659)."""
        from code_agents.cicd.endpoint_scanner import run_single_endpoint
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("curl", 10)):
            result = run_single_endpoint("curl http://localhost:8080/test", timeout=10)
        assert result["passed"] is False
        assert "Timed out" in result["stderr"]

    def test_general_exception(self):
        """run_single_endpoint handles general exception."""
        from code_agents.cicd.endpoint_scanner import run_single_endpoint
        with patch("subprocess.run", side_effect=Exception("unexpected")):
            result = run_single_endpoint("curl http://localhost:8080/test")
        assert result["passed"] is False
        assert "unexpected" in result["stderr"]
