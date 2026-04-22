"""Tests for verbal_architect.py — NL description to architecture design."""

import pytest

from code_agents.knowledge.verbal_architect import (
    VerbalArchitect,
    ArchitectReport,
    ArchitectureDesign,
    Component,
    format_report,
)


@pytest.fixture
def architect():
    return VerbalArchitect()


class TestExtractComponents:
    def test_finds_service(self, architect):
        components = architect._extract_components(
            "we need a microservice for user management",
            "We need a microservice for user management"
        )
        types = [c.component_type for c in components]
        assert "service" in types

    def test_finds_database(self, architect):
        components = architect._extract_components(
            "store user data in a database",
            "Store user data in a database"
        )
        types = [c.component_type for c in components]
        assert "database" in types

    def test_fallback_monolith(self, architect):
        components = architect._extract_components("just build something", "Just build something")
        assert len(components) >= 1


class TestDetectPatterns:
    def test_microservices(self, architect):
        patterns = architect._detect_patterns("build as microservices with independent deployment")
        assert "microservices" in patterns

    def test_event_driven(self, architect):
        patterns = architect._detect_patterns("use event-driven async communication")
        assert "event_driven" in patterns

    def test_default_monolith(self, architect):
        patterns = architect._detect_patterns("simple web app")
        assert "monolith" in patterns


class TestAnalyze:
    def test_full_analysis(self, architect):
        report = architect.analyze(
            "Build a scalable API service with a database backend and message queue for async processing"
        )
        assert isinstance(report, ArchitectReport)
        assert len(report.design.components) >= 2

    def test_connections_inferred(self, architect):
        report = architect.analyze("API service communicating with database and queue via REST")
        if len(report.design.components) >= 2:
            assert len(report.design.connections) >= 1

    def test_nf_requirements(self, architect):
        report = architect.analyze("Build a secure, scalable, highly available payment service")
        assert "security" in report.design.non_functional or "scalability" in report.design.non_functional

    def test_format_report(self, architect):
        report = architect.analyze("Build a simple web service")
        text = format_report(report)
        assert "Architecture" in text

    def test_ambiguities_detected(self, architect):
        report = architect.analyze("Build something somehow")
        assert len(report.ambiguities) >= 1
