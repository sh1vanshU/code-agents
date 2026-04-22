"""Tests for the API Contract Testing module."""

from __future__ import annotations

import os

import pytest

from code_agents.testing.contract_testing import (
    ContractTest,
    ContractTestGenerator,
    RouteInfo,
    VerificationResult,
    format_tests_summary,
)


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project with FastAPI routes."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    (app_dir / "main.py").write_text('''
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/v1/users", response_model=UserResponse, status_code=201)
async def create_user(body: CreateUserRequest):
    return {"id": 1, "name": "test"}

@app.get("/api/v1/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}

@app.put("/api/v1/users/{user_id}")
def update_user(user_id: int, data: UpdateUserRequest):
    return {"id": user_id}

@app.delete("/api/v1/users/{user_id}")
def delete_user(user_id: int):
    return {"deleted": True}
''')

    return tmp_path


@pytest.fixture
def flask_project(tmp_path):
    """Create a sample project with Flask routes."""
    (tmp_path / "app.py").write_text('''
from flask import Flask

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return {"status": "ok"}

@app.route("/api/items", methods=["GET", "POST"])
def items():
    return {"items": []}
''')
    return tmp_path


@pytest.fixture
def generator(sample_project):
    return ContractTestGenerator(cwd=str(sample_project))


class TestRouteInfo:
    """Test RouteInfo dataclass."""

    def test_to_dict(self):
        route = RouteInfo(
            path="/api/users", method="GET",
            function_name="get_users", file_path="app.py",
        )
        d = route.to_dict()
        assert d["path"] == "/api/users"
        assert d["method"] == "GET"

    def test_default_status(self):
        route = RouteInfo(path="/", method="GET", function_name="root", file_path="app.py")
        assert route.status_code == 200


class TestContractTestGenerator:
    """Test ContractTestGenerator methods."""

    def test_scan_fastapi_routes(self, generator):
        routes = generator._scan_api_routes("app")
        assert len(routes) >= 4  # health, create, get, update, delete
        methods = {r.method for r in routes}
        assert "GET" in methods
        assert "POST" in methods

    def test_scan_route_paths(self, generator):
        routes = generator._scan_api_routes("app")
        paths = {r.path for r in routes}
        assert "/health" in paths
        assert "/api/v1/users" in paths

    def test_scan_path_params(self, generator):
        routes = generator._scan_api_routes("app")
        user_routes = [r for r in routes if "{user_id}" in r.path]
        assert len(user_routes) >= 2
        for r in user_routes:
            assert "user_id" in r.params

    def test_scan_response_model(self, generator):
        routes = generator._scan_api_routes("app")
        create_routes = [r for r in routes if r.method == "POST" and "users" in r.path]
        assert len(create_routes) >= 1
        assert create_routes[0].response_model == "UserResponse"

    def test_scan_flask_routes(self, flask_project):
        gen = ContractTestGenerator(cwd=str(flask_project))
        routes = gen._scan_api_routes()
        assert len(routes) >= 2  # index GET + items GET + items POST

    def test_scan_empty_dir(self, tmp_path):
        gen = ContractTestGenerator(cwd=str(tmp_path))
        routes = gen._scan_api_routes()
        assert routes == []

    def test_scan_nonexistent_target(self, generator):
        routes = generator._scan_api_routes("nonexistent")
        assert routes == []

    def test_generate_pact_tests(self, generator):
        tests = generator.generate(target="app", fmt="pact")
        assert len(tests) >= 4
        assert all(t.test_type == "pact" for t in tests)
        for t in tests:
            assert "def test_" in t.test_code
            assert t.test_name.startswith("test_pact_")

    def test_generate_schema_tests(self, generator):
        tests = generator.generate(target="app", fmt="schema")
        assert len(tests) >= 4
        assert all(t.test_type == "schema" for t in tests)
        for t in tests:
            assert "EXPECTED_SCHEMA" in t.test_code

    def test_generate_both(self, generator):
        tests = generator.generate(target="app", fmt="both")
        pact_count = sum(1 for t in tests if t.test_type == "pact")
        schema_count = sum(1 for t in tests if t.test_type == "schema")
        assert pact_count >= 4
        assert schema_count >= 4

    def test_generate_no_routes(self, tmp_path):
        gen = ContractTestGenerator(cwd=str(tmp_path))
        tests = gen.generate()
        assert tests == []

    def test_pact_test_has_status_check(self, generator):
        tests = generator.generate(target="app", fmt="pact")
        for t in tests:
            assert "status_code" in t.test_code

    def test_pact_test_post_has_body(self, generator):
        tests = generator.generate(target="app", fmt="pact")
        post_tests = [t for t in tests if t.route.method == "POST"]
        for t in post_tests:
            assert "request_body" in t.test_code

    def test_extract_path_params(self, generator):
        assert generator._extract_path_params("/api/users/{id}") == ["id"]
        assert generator._extract_path_params("/api/{org}/repos/{repo_id}") == ["org", "repo_id"]
        assert generator._extract_path_params("/simple") == []


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_to_dict(self):
        vr = VerificationResult(total=10, passed=8, failed=2, errors=["FAILED test_x"])
        d = vr.to_dict()
        assert d["total"] == 10
        assert d["passed"] == 8
        assert len(d["errors"]) == 1


class TestFormatTestsSummary:
    """Test formatting of test summaries."""

    def test_no_tests(self):
        output = format_tests_summary([])
        assert "No contract tests" in output

    def test_with_tests(self, generator):
        tests = generator.generate(target="app", fmt="both")
        output = format_tests_summary(tests)
        assert "Contract Tests Generated" in output
        assert "Pact Tests" in output
        assert "Schema Tests" in output
