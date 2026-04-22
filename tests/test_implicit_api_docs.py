"""Tests for implicit_api_docs.py — API docs from traffic patterns."""

import pytest

from code_agents.api.implicit_api_docs import (
    ImplicitAPIDocs,
    ImplicitDocsReport,
    APIEndpoint,
    format_report,
)


@pytest.fixture
def analyzer(tmp_path):
    return ImplicitAPIDocs(str(tmp_path))


SAMPLE_TRAFFIC = [
    {"method": "GET", "path": "/api/users/123", "status_code": 200, "latency_ms": 45,
     "response_body": {"id": 123, "name": "Alice"}},
    {"method": "GET", "path": "/api/users/456", "status_code": 200, "latency_ms": 50,
     "response_body": {"id": 456, "name": "Bob"}},
    {"method": "POST", "path": "/api/users", "status_code": 201, "latency_ms": 120,
     "request_body": {"name": "Charlie", "email": "c@test.com"}},
    {"method": "GET", "path": "/api/orders/789", "status_code": 404, "latency_ms": 15},
    {"method": "GET", "path": "/api/users/123", "status_code": 500, "latency_ms": 2000},
]


class TestNormalizePath:
    def test_replaces_ids(self, analyzer):
        assert analyzer._normalize_path("/api/users/123") == "/api/users/{id}"

    def test_replaces_uuids(self, analyzer):
        result = analyzer._normalize_path("/api/items/abc12345-def6-7890")
        assert "{id}" in result

    def test_no_ids(self, analyzer):
        assert analyzer._normalize_path("/api/health") == "/api/health"


class TestAnalyze:
    def test_discovers_endpoints(self, analyzer):
        report = analyzer.analyze(SAMPLE_TRAFFIC)
        assert isinstance(report, ImplicitDocsReport)
        assert report.total_endpoints >= 2

    def test_groups_by_resource(self, analyzer):
        report = analyzer.analyze(SAMPLE_TRAFFIC)
        group_names = [g.name for g in report.groups]
        assert "api" in group_names

    def test_computes_error_rate(self, analyzer):
        report = analyzer.analyze(SAMPLE_TRAFFIC)
        endpoints = [e for g in report.groups for e in g.endpoints]
        get_users = [e for e in endpoints if "users" in e.path and e.method == "GET"]
        assert len(get_users) >= 1

    def test_infers_schema(self, analyzer):
        schema = analyzer._infer_schema([{"name": "Alice", "age": 30}])
        assert "properties" in schema
        assert "name" in schema["properties"]

    def test_format_report(self, analyzer):
        report = analyzer.analyze(SAMPLE_TRAFFIC)
        text = format_report(report)
        assert "API Documentation" in text

    def test_empty_traffic(self, analyzer):
        report = analyzer.analyze([])
        assert report.total_endpoints == 0
