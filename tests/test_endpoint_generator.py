"""Tests for code_agents.endpoint_generator."""

import pytest
from code_agents.api.endpoint_generator import EndpointGenerator, EndpointGenConfig, EndpointGenResult, format_endpoint


class TestEndpointGenerator:
    def test_generate_fastapi_crud(self):
        gen = EndpointGenerator(EndpointGenConfig(framework="fastapi"))
        result = gen.generate("User", fields={"name": "str", "email": "str"})
        assert len(result.endpoints) == 5
        assert "GET /users" in result.endpoints
        assert "POST /users" in result.endpoints

    def test_generate_express(self):
        gen = EndpointGenerator(EndpointGenConfig(framework="express"))
        result = gen.generate("Product")
        assert any(f.file_type == "router" for f in result.files)
        assert any("express" in f.content for f in result.files)

    def test_generate_flask(self):
        gen = EndpointGenerator(EndpointGenConfig(framework="flask"))
        result = gen.generate("Item")
        assert any("Blueprint" in f.content for f in result.files)

    def test_generates_pydantic_models(self):
        gen = EndpointGenerator(EndpointGenConfig(framework="fastapi"))
        result = gen.generate("Order", fields={"total": "float", "status": "str"})
        model_file = next((f for f in result.files if f.file_type == "model"), None)
        assert model_file is not None
        assert "OrderBase" in model_file.content
        assert "OrderCreate" in model_file.content

    def test_generates_tests_when_enabled(self):
        gen = EndpointGenerator(EndpointGenConfig(include_tests=True))
        result = gen.generate("User")
        assert any(f.file_type == "test" for f in result.files)

    def test_no_tests_when_disabled(self):
        gen = EndpointGenerator(EndpointGenConfig(include_tests=False))
        result = gen.generate("User")
        assert not any(f.file_type == "test" for f in result.files)

    def test_custom_fields(self):
        gen = EndpointGenerator(EndpointGenConfig())
        result = gen.generate("Payment", fields={"amount": "float", "currency": "str", "status": "str"})
        model_file = next((f for f in result.files if f.file_type == "model"), None)
        assert model_file and "amount" in model_file.content and "currency" in model_file.content

    def test_format_output(self):
        result = EndpointGenResult(resource_name="User", summary="5 endpoints")
        output = format_endpoint(result)
        assert "User" in output
        assert "Endpoint" in output
