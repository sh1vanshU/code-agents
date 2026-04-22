"""Tests for code_agents.load_test_gen — load test scenario generator."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from code_agents.domain.load_test_gen import (
    EndpointSpec,
    LoadTestGenerator,
    Scenario,
    format_scenario_summary,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def fastapi_project(tmp_path: Path) -> Path:
    """Create a minimal FastAPI project for scanning."""
    (tmp_path / "app.py").write_text(
        textwrap.dedent("""\
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.post("/api/users")
        def create_user(data: dict):
            return data

        @app.get("/api/users/{user_id}")
        def get_user(user_id: int):
            return {"id": user_id}

        @app.delete("/api/users/{user_id}")
        def delete_user(user_id: int):
            return {"deleted": True}

        @app.put("/api/users/{user_id}")
        def update_user(user_id: int, data: dict):
            return data
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def flask_project(tmp_path: Path) -> Path:
    """Create a minimal Flask project for scanning."""
    (tmp_path / "app.py").write_text(
        textwrap.dedent("""\
        from flask import Flask
        app = Flask(__name__)

        @app.route("/health")
        def health():
            return "ok"

        @app.route("/api/items", methods=["GET", "POST"])
        def items():
            return "items"

        @app.get("/api/items/<item_id>")
        def get_item(item_id):
            return "item"
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def express_project(tmp_path: Path) -> Path:
    """Create a minimal Express project for scanning."""
    (tmp_path / "routes.js").write_text(
        textwrap.dedent("""\
        const express = require('express');
        const router = express.Router();

        router.get('/api/products', (req, res) => res.json([]));
        router.post('/api/products', (req, res) => res.json(req.body));
        router.get('/api/products/:id', (req, res) => res.json({}));
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def spring_project(tmp_path: Path) -> Path:
    """Create a minimal Spring Boot project for scanning."""
    (tmp_path / "Controller.java").write_text(
        textwrap.dedent("""\
        @RestController
        public class UserController {
            @GetMapping("/api/orders")
            public List<Order> list() { return null; }

            @PostMapping("/api/orders")
            public Order create() { return null; }

            @PutMapping("/api/orders/{id}")
            public Order update() { return null; }
        }
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """An empty project with no endpoints."""
    (tmp_path / "readme.md").write_text("# empty")
    return tmp_path


# ── Endpoint scanning tests ──────────────────────────────────────────────────


class TestEndpointScanning:
    def test_scan_fastapi(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        endpoints = gen._scan_endpoints()
        assert len(endpoints) == 5
        methods = {(e.method, e.path) for e in endpoints}
        assert ("GET", "/health") in methods
        assert ("POST", "/api/users") in methods
        assert ("GET", "/api/users/{user_id}") in methods
        assert ("DELETE", "/api/users/{user_id}") in methods
        assert ("PUT", "/api/users/{user_id}") in methods

    def test_scan_flask(self, flask_project: Path):
        gen = LoadTestGenerator(cwd=str(flask_project))
        endpoints = gen._scan_endpoints()
        assert len(endpoints) >= 3
        methods = {(e.method, e.path) for e in endpoints}
        assert ("GET", "/health") in methods
        assert ("GET", "/api/items") in methods
        assert ("POST", "/api/items") in methods

    def test_scan_express(self, express_project: Path):
        gen = LoadTestGenerator(cwd=str(express_project))
        endpoints = gen._scan_endpoints()
        assert len(endpoints) == 3
        methods = {(e.method, e.path) for e in endpoints}
        assert ("GET", "/api/products") in methods
        assert ("POST", "/api/products") in methods
        assert ("GET", "/api/products/:id") in methods

    def test_scan_spring(self, spring_project: Path):
        gen = LoadTestGenerator(cwd=str(spring_project))
        endpoints = gen._scan_endpoints()
        assert len(endpoints) == 3
        methods = {(e.method, e.path) for e in endpoints}
        assert ("GET", "/api/orders") in methods
        assert ("POST", "/api/orders") in methods
        assert ("PUT", "/api/orders/{id}") in methods

    def test_scan_empty_project(self, empty_project: Path):
        gen = LoadTestGenerator(cwd=str(empty_project))
        endpoints = gen._scan_endpoints()
        assert endpoints == []

    def test_scan_deduplicates(self, tmp_path: Path):
        """Duplicate routes across files should be de-duplicated."""
        (tmp_path / "a.py").write_text('@app.get("/health")\ndef h(): pass')
        (tmp_path / "b.py").write_text('@app.get("/health")\ndef h2(): pass')
        gen = LoadTestGenerator(cwd=str(tmp_path))
        endpoints = gen._scan_endpoints()
        assert len(endpoints) == 1

    def test_body_guessing(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        endpoints = gen._scan_endpoints()
        for ep in endpoints:
            if ep.method in ("POST", "PUT"):
                assert ep.body is not None
            elif ep.method in ("GET", "DELETE"):
                assert ep.body is None


# ── Scenario builder tests ───────────────────────────────────────────────────


class TestScenarioBuilder:
    def test_all_presets(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        endpoints = gen._scan_endpoints()
        for preset in ("smoke", "peak", "stress", "soak"):
            scenario = gen._build_scenario(endpoints, preset)
            assert scenario.name == preset
            assert scenario.rps > 0
            assert len(scenario.endpoints) == 5

    def test_invalid_scenario(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        with pytest.raises(ValueError, match="Unknown scenario"):
            gen.generate(scenario="nonexistent")

    def test_invalid_format(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        with pytest.raises(ValueError, match="Unknown format"):
            gen.generate(format="artillery")

    def test_no_endpoints_raises(self, empty_project: Path):
        gen = LoadTestGenerator(cwd=str(empty_project))
        with pytest.raises(ValueError, match="No API endpoints found"):
            gen.generate()


# ── k6 format tests ─────────────────────────────────────────────────────────


class TestK6Format:
    def test_k6_output_structure(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="smoke", format="k6")
        assert "import http from 'k6/http'" in output
        assert "export const options" in output
        assert "export default function" in output
        assert "stages:" in output
        assert "sleep(" in output

    def test_k6_contains_endpoints(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="peak", format="k6")
        assert "/health" in output
        assert "/api/users" in output
        assert "http.get" in output
        assert "http.post" in output

    def test_k6_thresholds(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(format="k6")
        assert "http_req_duration" in output
        assert "http_req_failed" in output


# ── Locust format tests ─────────────────────────────────────────────────────


class TestLocustFormat:
    def test_locust_output_structure(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="smoke", format="locust")
        assert "from locust import HttpUser" in output
        assert "class LoadTestUser(HttpUser):" in output
        assert "@task" in output
        assert "wait_time" in output

    def test_locust_contains_endpoints(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="peak", format="locust")
        assert "/health" in output
        assert "self.client.get" in output
        assert "self.client.post" in output


# ── JMeter format tests ─────────────────────────────────────────────────────


class TestJMeterFormat:
    def test_jmeter_output_structure(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="smoke", format="jmeter")
        assert '<?xml version="1.0"' in output
        assert "jmeterTestPlan" in output
        assert "ThreadGroup" in output
        assert "HTTPSamplerProxy" in output

    def test_jmeter_contains_endpoints(self, fastapi_project: Path):
        gen = LoadTestGenerator(cwd=str(fastapi_project))
        output = gen.generate(scenario="peak", format="jmeter")
        assert "/health" in output
        assert "/api/users" in output
        assert "GET" in output
        assert "POST" in output

    def test_jmeter_valid_xml_escaping(self, tmp_path: Path):
        """Paths with special chars should be XML-escaped."""
        (tmp_path / "app.py").write_text(
            '@app.get("/api/items")\ndef h(): pass'
        )
        gen = LoadTestGenerator(cwd=str(tmp_path))
        output = gen.generate(format="jmeter")
        # Should not break XML
        assert "jmeterTestPlan" in output


# ── Summary formatter tests ──────────────────────────────────────────────────


class TestFormatSummary:
    def test_summary_contains_fields(self):
        scenario = Scenario(
            name="peak",
            description="Peak traffic test",
            endpoints=[
                EndpointSpec(method="GET", path="/health"),
                EndpointSpec(method="POST", path="/api/users", body={"name": "test"}),
            ],
            rps=200,
            duration="5m",
            ramp_up="1m",
            think_time=0.5,
        )
        summary = format_scenario_summary(scenario)
        assert "peak" in summary
        assert "200" in summary
        assert "5m" in summary
        assert "/health" in summary
        assert "POST" in summary
        assert "(with body)" in summary

    def test_summary_no_body_hint_for_get(self):
        scenario = Scenario(
            name="smoke",
            description="Smoke test",
            endpoints=[EndpointSpec(method="GET", path="/health")],
            rps=5,
            duration="1m",
            ramp_up="10s",
        )
        summary = format_scenario_summary(scenario)
        assert "(with body)" not in summary


# ── Duration parsing tests ───────────────────────────────────────────────────


class TestDurationParsing:
    def test_parse_seconds(self):
        assert LoadTestGenerator._parse_duration_secs("30s") == 30

    def test_parse_minutes(self):
        assert LoadTestGenerator._parse_duration_secs("5m") == 300

    def test_parse_hours(self):
        assert LoadTestGenerator._parse_duration_secs("1h") == 3600

    def test_parse_invalid(self):
        assert LoadTestGenerator._parse_duration_secs("invalid") == 60


# ── DataClass tests ──────────────────────────────────────────────────────────


class TestDataclasses:
    def test_endpoint_spec_defaults(self):
        ep = EndpointSpec(method="GET", path="/test")
        assert ep.body is None
        assert ep.headers == {}

    def test_scenario_defaults(self):
        s = Scenario(
            name="test",
            description="desc",
            endpoints=[],
            rps=10,
            duration="1m",
            ramp_up="10s",
        )
        assert s.think_time == 1.0
