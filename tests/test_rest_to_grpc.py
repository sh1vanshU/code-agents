"""Tests for code_agents.rest_to_grpc."""

import pytest
from code_agents.api.rest_to_grpc import RestToGrpcConverter, RestToGrpcConfig, GrpcConvertResult, format_grpc_output


class TestRestToGrpcConverter:
    def test_make_rpc_name_get(self):
        converter = RestToGrpcConverter(RestToGrpcConfig())
        assert converter._make_rpc_name("GET", "/users") == "ListUsers"
        assert converter._make_rpc_name("GET", "/users/{id}") == "GetUsers"

    def test_make_rpc_name_post(self):
        converter = RestToGrpcConverter(RestToGrpcConfig())
        assert converter._make_rpc_name("POST", "/users") == "CreateUsers"

    def test_make_rpc_name_delete(self):
        converter = RestToGrpcConverter(RestToGrpcConfig())
        assert converter._make_rpc_name("DELETE", "/users/{id}") == "DeleteUsers"

    def test_extract_resource(self):
        converter = RestToGrpcConverter(RestToGrpcConfig())
        assert converter._extract_resource("/users") == "users"
        assert converter._extract_resource("/api/v1/orders") == "api"

    def test_generate_proto_has_syntax(self):
        result = GrpcConvertResult()
        result.services = []
        result.messages = []
        converter = RestToGrpcConverter(RestToGrpcConfig())
        proto = converter._generate_proto(result)
        assert 'syntax = "proto3"' in proto

    def test_convert_empty_codebase(self, tmp_path):
        converter = RestToGrpcConverter(RestToGrpcConfig(cwd=str(tmp_path)))
        result = converter.convert()
        assert result.endpoints_converted == 0

    def test_format_output(self):
        result = GrpcConvertResult(summary="Converted 3 endpoints")
        output = format_grpc_output(result)
        assert "REST to gRPC" in output
