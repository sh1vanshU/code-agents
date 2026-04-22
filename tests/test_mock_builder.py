"""Tests for the MockBuilder module."""

import textwrap
import pytest
from code_agents.testing.mock_builder import MockBuilder, MockBuilderConfig, MockBuildResult, format_mock


class TestMockBuilder:
    def test_build_mock_for_class(self, tmp_path):
        source = textwrap.dedent('''\
            class ApiClient:
                """HTTP API client."""
                def __init__(self, base_url: str):
                    self.base_url = base_url
                def get_user(self, user_id: int) -> dict:
                    pass
                def create_user(self, data: dict) -> dict:
                    pass
                def delete_user(self, user_id: int) -> bool:
                    pass
        ''')
        (tmp_path / "client.py").write_text(source)
        result = MockBuilder(MockBuilderConfig(cwd=str(tmp_path))).build("client.py:ApiClient")

        assert len(result.mocks) == 1
        mock_def = result.mocks[0]
        assert mock_def.class_name == "MockApiClient"
        method_names = [m.name for m in mock_def.methods]
        assert "get_user" in method_names
        assert "create_user" in method_names

    def test_generate_return_values(self):
        builder = MockBuilder(MockBuilderConfig())
        assert builder._generate_return_value("str", "get_name") == '"mock_value"'
        assert builder._generate_return_value("int", "count") == "42"
        assert builder._generate_return_value("bool", "is_active") == "True"
        assert builder._generate_return_value("", "get_user") == '{"id": 1, "name": "mock"}'
        assert builder._generate_return_value("", "list_items") == '[{"id": 1}, {"id": 2}]'
        assert builder._generate_return_value("", "is_valid") == "True"
        assert builder._generate_return_value("", "delete_item") == "True"

    def test_generate_error_scenarios(self):
        builder = MockBuilder(MockBuilderConfig())
        scenarios = builder._generate_error_scenarios("connect")
        assert any("ConnectionError" in s for s in scenarios)
        scenarios = builder._generate_error_scenarios("get_user")
        assert any("KeyError" in s for s in scenarios)

    def test_generated_code_is_valid_python(self, tmp_path):
        source = textwrap.dedent('''\
            class Service:
                def process(self, data: dict) -> dict:
                    pass
        ''')
        (tmp_path / "svc.py").write_text(source)
        result = MockBuilder(MockBuilderConfig(cwd=str(tmp_path))).build("svc.py:Service")
        mock_code = result.mocks[0].code
        # Should be valid Python
        compile(mock_code, "<mock>", "exec")

    def test_class_not_found(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1\n")
        result = MockBuilder(MockBuilderConfig(cwd=str(tmp_path))).build("empty.py:NonExistent")
        assert "not found" in result.summary.lower()

    def test_format_output(self):
        result = MockBuildResult(target="client.py:Client", summary="Generated MockClient")
        output = format_mock(result)
        assert "Mock Builder" in output
