"""Integration Scaffold — generate docker-compose + test setup for real dependencies.

Creates test infrastructure for PostgreSQL, Redis, Kafka, Elasticsearch,
RabbitMQ, MongoDB, and other services.

Usage:
    from code_agents.knowledge.integration_scaffold import IntegrationScaffolder
    scaffolder = IntegrationScaffolder()
    result = scaffolder.generate(["postgres", "redis", "kafka"])
    print(format_scaffold(result))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.integration_scaffold")


@dataclass
class IntegrationScaffoldConfig:
    cwd: str = "."
    test_framework: str = "pytest"  # pytest, unittest, jest


@dataclass
class ServiceConfig:
    """Configuration for a single test service."""
    name: str
    image: str
    ports: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    health_check: str = ""
    connection_url: str = ""
    wait_seconds: int = 5


@dataclass
class ScaffoldResult:
    """Generated integration test scaffold."""
    services: list[ServiceConfig] = field(default_factory=list)
    docker_compose: str = ""
    conftest_code: str = ""
    example_test: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    summary: str = ""


# Service templates
SERVICE_TEMPLATES: dict[str, ServiceConfig] = {
    "postgres": ServiceConfig(
        name="postgres", image="postgres:16-alpine",
        ports={"5432": "5432"},
        environment={"POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "testdb"},
        health_check="pg_isready -U test",
        connection_url="postgresql://test:test@localhost:5432/testdb",
    ),
    "redis": ServiceConfig(
        name="redis", image="redis:7-alpine",
        ports={"6379": "6379"},
        health_check="redis-cli ping",
        connection_url="redis://localhost:6379/0",
    ),
    "kafka": ServiceConfig(
        name="kafka", image="confluentinc/cp-kafka:7.5.0",
        ports={"9092": "9092"},
        environment={
            "KAFKA_BROKER_ID": "1",
            "KAFKA_ZOOKEEPER_CONNECT": "zookeeper:2181",
            "KAFKA_ADVERTISED_LISTENERS": "PLAINTEXT://localhost:9092",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        },
        connection_url="localhost:9092",
        wait_seconds=15,
    ),
    "elasticsearch": ServiceConfig(
        name="elasticsearch", image="elasticsearch:8.11.0",
        ports={"9200": "9200"},
        environment={"discovery.type": "single-node", "xpack.security.enabled": "false", "ES_JAVA_OPTS": "-Xms512m -Xmx512m"},
        health_check="curl -f http://localhost:9200/_cluster/health",
        connection_url="http://localhost:9200",
        wait_seconds=20,
    ),
    "mongodb": ServiceConfig(
        name="mongodb", image="mongo:7",
        ports={"27017": "27017"},
        environment={"MONGO_INITDB_ROOT_USERNAME": "test", "MONGO_INITDB_ROOT_PASSWORD": "test"},
        connection_url="mongodb://test:test@localhost:27017",
    ),
    "rabbitmq": ServiceConfig(
        name="rabbitmq", image="rabbitmq:3-management-alpine",
        ports={"5672": "5672", "15672": "15672"},
        environment={"RABBITMQ_DEFAULT_USER": "test", "RABBITMQ_DEFAULT_PASS": "test"},
        connection_url="amqp://test:test@localhost:5672/",
    ),
    "mysql": ServiceConfig(
        name="mysql", image="mysql:8",
        ports={"3306": "3306"},
        environment={"MYSQL_ROOT_PASSWORD": "test", "MYSQL_DATABASE": "testdb"},
        health_check="mysqladmin ping -h localhost",
        connection_url="mysql://root:test@localhost:3306/testdb",
    ),
    "minio": ServiceConfig(
        name="minio", image="minio/minio:latest",
        ports={"9000": "9000"},
        environment={"MINIO_ROOT_USER": "minioadmin", "MINIO_ROOT_PASSWORD": "minioadmin"},
        connection_url="http://localhost:9000",
    ),
}


class IntegrationScaffolder:
    """Generate integration test scaffolding."""

    def __init__(self, config: Optional[IntegrationScaffoldConfig] = None):
        self.config = config or IntegrationScaffoldConfig()

    def generate(self, services: list[str]) -> ScaffoldResult:
        """Generate scaffolding for requested services."""
        logger.info("Generating scaffold for: %s", services)
        result = ScaffoldResult()

        for svc_name in services:
            template = SERVICE_TEMPLATES.get(svc_name.lower())
            if template:
                result.services.append(template)
                result.env_vars[f"{svc_name.upper()}_URL"] = template.connection_url

        # Add zookeeper if kafka is requested
        if "kafka" in [s.lower() for s in services]:
            zk = ServiceConfig(
                name="zookeeper", image="confluentinc/cp-zookeeper:7.5.0",
                ports={"2181": "2181"},
                environment={"ZOOKEEPER_CLIENT_PORT": "2181"},
            )
            result.services.insert(0, zk)

        result.docker_compose = self._generate_docker_compose(result.services)
        result.conftest_code = self._generate_conftest(result.services)
        result.example_test = self._generate_example_test(result.services)
        result.summary = f"Generated scaffold for {len(services)} services: {', '.join(services)}"

        return result

    def _generate_docker_compose(self, services: list[ServiceConfig]) -> str:
        """Generate docker-compose.yml content."""
        lines = ["version: '3.8'", "", "services:"]

        for svc in services:
            lines.append(f"  {svc.name}:")
            lines.append(f"    image: {svc.image}")
            if svc.ports:
                lines.append("    ports:")
                for host, container in svc.ports.items():
                    lines.append(f'      - "{host}:{container}"')
            if svc.environment:
                lines.append("    environment:")
                for key, value in svc.environment.items():
                    lines.append(f"      {key}: \"{value}\"")
            if svc.health_check:
                lines.append("    healthcheck:")
                lines.append(f'      test: ["{svc.health_check}"]')
                lines.append("      interval: 5s")
                lines.append("      timeout: 3s")
                lines.append("      retries: 10")
            lines.append("")

        return "\n".join(lines)

    def _generate_conftest(self, services: list[ServiceConfig]) -> str:
        """Generate conftest.py with fixtures."""
        lines = [
            '"""Integration test fixtures — auto-generated."""',
            "",
            "import os",
            "import time",
            "import pytest",
            "",
        ]

        for svc in services:
            if svc.name == "zookeeper":
                continue
            lines.extend([
                "",
                f"@pytest.fixture(scope='session')",
                f"def {svc.name}_url():",
                f'    """Return {svc.name} connection URL."""',
                f'    url = os.environ.get("{svc.name.upper()}_URL", "{svc.connection_url}")',
                f"    # Wait for service to be ready",
                f"    time.sleep({svc.wait_seconds})",
                f"    return url",
                "",
            ])

        return "\n".join(lines)

    def _generate_example_test(self, services: list[ServiceConfig]) -> str:
        """Generate example integration test."""
        lines = [
            '"""Example integration tests — auto-generated."""',
            "",
            "import pytest",
            "",
        ]

        for svc in services:
            if svc.name in ("zookeeper",):
                continue

            lines.extend([
                f"class TestWith{svc.name.title()}:",
                f"",
                f"    def test_{svc.name}_connection(self, {svc.name}_url):",
                f'        """Verify {svc.name} is reachable."""',
                f"        assert {svc.name}_url is not None",
                f"        # Add actual connection test here",
                f"",
            ])

        return "\n".join(lines)


def format_scaffold(result: ScaffoldResult) -> str:
    """Format scaffold result for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Integration Test Scaffold")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")

    lines.append(f"\n  --- docker-compose.yml ---")
    for line in result.docker_compose.splitlines():
        lines.append(f"  {line}")

    lines.append(f"\n  --- conftest.py ---")
    for line in result.conftest_code.splitlines()[:30]:
        lines.append(f"  {line}")

    lines.append(f"\n  --- example_test.py ---")
    for line in result.example_test.splitlines()[:20]:
        lines.append(f"  {line}")

    if result.env_vars:
        lines.append(f"\n  Environment Variables:")
        for k, v in result.env_vars.items():
            lines.append(f"    {k}={v}")

    lines.append("")
    return "\n".join(lines)
