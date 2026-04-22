"""Tests for the IntegrationScaffolder module."""

import pytest
from code_agents.knowledge.integration_scaffold import IntegrationScaffolder, ScaffoldResult, format_scaffold


class TestIntegrationScaffolder:
    def test_generate_postgres(self):
        result = IntegrationScaffolder().generate(["postgres"])
        assert len(result.services) == 1
        assert result.services[0].name == "postgres"
        assert "postgres" in result.docker_compose
        assert "5432" in result.docker_compose
        assert "POSTGRES_URL" in result.env_vars

    def test_generate_redis(self):
        result = IntegrationScaffolder().generate(["redis"])
        assert len(result.services) == 1
        assert "redis" in result.docker_compose

    def test_generate_kafka_includes_zookeeper(self):
        result = IntegrationScaffolder().generate(["kafka"])
        service_names = [s.name for s in result.services]
        assert "zookeeper" in service_names
        assert "kafka" in service_names

    def test_generate_multiple(self):
        result = IntegrationScaffolder().generate(["postgres", "redis", "elasticsearch"])
        assert len(result.services) == 3
        assert "POSTGRES_URL" in result.env_vars
        assert "REDIS_URL" in result.env_vars

    def test_docker_compose_valid_yaml(self):
        result = IntegrationScaffolder().generate(["postgres", "redis"])
        assert result.docker_compose.startswith("version:")
        assert "services:" in result.docker_compose
        assert "image:" in result.docker_compose

    def test_conftest_has_fixtures(self):
        result = IntegrationScaffolder().generate(["postgres", "redis"])
        assert "@pytest.fixture" in result.conftest_code
        assert "def postgres_url" in result.conftest_code
        assert "def redis_url" in result.conftest_code

    def test_example_test_generated(self):
        result = IntegrationScaffolder().generate(["postgres"])
        assert "class TestWith" in result.example_test
        assert "def test_postgres_connection" in result.example_test

    def test_unknown_service_ignored(self):
        result = IntegrationScaffolder().generate(["unknown_service"])
        assert len(result.services) == 0

    def test_format_output(self):
        result = ScaffoldResult(summary="Generated for postgres")
        output = format_scaffold(result)
        assert "Scaffold" in output
