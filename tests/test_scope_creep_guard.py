"""Tests for scope_creep_guard.py — coding session scope monitoring."""

import pytest

from code_agents.agent_system.scope_creep_guard import (
    ScopeCreepGuard,
    ScopeReport,
    ScopeViolation,
    format_report,
)


@pytest.fixture
def guard():
    return ScopeCreepGuard()


TICKET = {
    "title": "Fix authentication login flow",
    "description": "Fix the login endpoint that returns 500 for valid credentials",
    "components": ["auth"],
    "labels": ["bug"],
}


class TestInScope:
    def test_related_file_in_scope(self, guard):
        guard.scope_items = guard._extract_scope(TICKET)
        assert guard._is_in_scope("src/auth/login.py", TICKET["description"])

    def test_test_file_in_scope(self, guard):
        guard.scope_items = guard._extract_scope(TICKET)
        assert guard._is_in_scope("tests/test_auth.py", TICKET["description"])

    def test_unrelated_file_out_of_scope(self, guard):
        guard.scope_items = guard._extract_scope(TICKET)
        assert not guard._is_in_scope("src/billing/invoice.py", TICKET["description"])


class TestAnalyze:
    def test_detects_in_scope(self, guard):
        report = guard.analyze(TICKET, ["src/auth/login.py", "tests/test_auth.py"])
        assert len(report.in_scope_files) >= 1

    def test_detects_out_of_scope(self, guard):
        report = guard.analyze(TICKET, ["src/auth/login.py", "src/billing/invoice.py"])
        assert len(report.out_of_scope_files) >= 1
        assert len(report.violations) >= 1

    def test_drift_score(self, guard):
        report = guard.analyze(TICKET, ["src/auth/login.py", "src/billing/x.py", "src/email/y.py"])
        assert 0.0 <= report.drift_score <= 1.0

    def test_warns_on_high_drift(self, guard):
        files = [f"src/unrelated/{i}.py" for i in range(5)]
        report = guard.analyze(TICKET, files)
        assert len(report.warnings) >= 1

    def test_format_report(self, guard):
        report = guard.analyze(TICKET, ["src/auth/login.py"])
        text = format_report(report)
        assert "Scope Creep" in text

    def test_empty_files(self, guard):
        report = guard.analyze(TICKET, [])
        assert report.drift_score == 0.0
