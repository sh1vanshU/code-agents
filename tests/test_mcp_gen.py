"""Tests for the MCP server code generator."""

from __future__ import annotations

import json
import os
import pytest

from code_agents.generators.mcp_gen import (
    MCPGenerator, MCPGeneratorResult, EndpointInfo, generate_mcp,
)


class TestMCPGenerator:
    """Test MCPGenerator methods."""

    def test_init(self, tmp_path):
        gen = MCPGenerator(cwd=str(tmp_path))
        assert gen.cwd == str(tmp_path)

    def test_generate_no_spec(self, tmp_path):
        gen = MCPGenerator(cwd=str(tmp_path))
        result = gen.generate()
        assert isinstance(result, MCPGeneratorResult)
        assert len(result.warnings) > 0
        assert result.endpoints_parsed == 0

    def test_generate_openapi_json(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "summary": "List all users",
                        "parameters": [
                            {"name": "limit", "in": "query", "required": False}
                        ],
                        "responses": {"200": {"description": "OK"}},
                    },
                    "post": {
                        "operationId": "createUser",
                        "summary": "Create a user",
                        "responses": {"201": {"description": "Created"}},
                    },
                },
            },
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))

        gen = MCPGenerator(cwd=str(tmp_path))
        result = gen.generate(spec_path=str(spec_file), api_title="UserAPI")
        assert result.endpoints_parsed == 2
        assert result.resource_count >= 1  # GET -> resource
        assert result.tool_count >= 1  # POST -> tool
        assert "UserAPI" in result.server_code

    def test_generate_proto(self, tmp_path):
        proto_content = """
syntax = "proto3";
service UserService {
    rpc GetUser (GetUserRequest) returns (User);
    rpc CreateUser (CreateUserRequest) returns (User);
}
"""
        proto_file = tmp_path / "service.proto"
        proto_file.write_text(proto_content)

        gen = MCPGenerator(cwd=str(tmp_path))
        result = gen.generate(spec_path=str(proto_file))
        assert result.endpoints_parsed == 2

    def test_generate_with_output(self, tmp_path):
        spec = {"openapi": "3.0.0", "paths": {
            "/items": {"get": {"operationId": "listItems", "summary": "List items",
                               "parameters": [], "responses": {}}},
        }}
        spec_file = tmp_path / "api.json"
        spec_file.write_text(json.dumps(spec))
        out_dir = tmp_path / "mcp_out"

        gen = MCPGenerator(cwd=str(tmp_path))
        result = gen.generate(spec_path=str(spec_file), output_dir=str(out_dir))
        assert len(result.output_files) == 1
        assert os.path.exists(result.output_files[0])

    def test_auto_detect_spec(self, tmp_path):
        (tmp_path / "openapi.yaml").write_text("openapi: '3.0.0'\npaths: {}")
        gen = MCPGenerator(cwd=str(tmp_path))
        detected = gen._auto_detect_spec()
        assert detected is not None
        assert "openapi.yaml" in detected

    def test_convenience_function(self, tmp_path):
        result = generate_mcp(cwd=str(tmp_path))
        assert isinstance(result, dict)
        assert "warnings" in result
        assert "server_code" in result
