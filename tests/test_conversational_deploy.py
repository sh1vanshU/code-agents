"""Tests for conversational_deploy.py — NL deploy commands to plans."""

import pytest

from code_agents.devops.conversational_deploy import (
    ConversationalDeploy,
    ConversationalDeployReport,
    DeployIntent,
    format_report,
)


@pytest.fixture
def deployer(tmp_path):
    return ConversationalDeploy(str(tmp_path))


GIT_LOG = [
    {"sha": "abc1234", "date": "today", "message": "Fix auth bug"},
    {"sha": "def5678", "date": "yesterday", "message": "Add feature X"},
    {"sha": "ghi9012", "date": "2 days ago", "message": "Refactor DB"},
]


class TestParseIntent:
    def test_detects_deploy(self, deployer):
        intent = deployer._parse_intent("deploy the latest to staging", [])
        assert intent.action == "deploy"
        assert intent.target_env == "staging"

    def test_detects_rollback(self, deployer):
        intent = deployer._parse_intent("rollback production", [])
        assert intent.action == "rollback"
        assert intent.target_env == "production"

    def test_detects_service(self, deployer):
        intent = deployer._parse_intent("deploy auth-service to staging", ["auth-service"])
        assert intent.service == "auth-service"

    def test_detects_sha(self, deployer):
        intent = deployer._parse_intent("deploy abc1234 to staging", [])
        assert intent.version == "abc1234"

    def test_detects_semver(self, deployer):
        intent = deployer._parse_intent("deploy v2.3.1 to production", [])
        assert intent.version == "v2.3.1"


class TestResolveReferences:
    def test_resolves_latest(self, deployer):
        resolved = deployer._resolve_references("deploy latest to staging", GIT_LOG)
        assert "latest" in resolved

    def test_resolves_yesterday(self, deployer):
        resolved = deployer._resolve_references("deploy yesterday's fix to staging", GIT_LOG)
        assert "yesterday" in resolved


class TestAnalyze:
    def test_generates_plan(self, deployer):
        report = deployer.analyze(
            "deploy abc1234 to staging",
            git_log=GIT_LOG,
        )
        assert isinstance(report, ConversationalDeployReport)
        assert report.success is True
        assert report.plan is not None
        assert len(report.plan.steps) >= 1

    def test_detects_ambiguity(self, deployer):
        report = deployer.analyze("just push it somewhere")
        assert len(report.ambiguities) >= 1

    def test_production_warning(self, deployer):
        report = deployer.analyze("deploy abc1234 to production")
        if report.plan:
            assert report.plan.requires_approval is True

    def test_format_report(self, deployer):
        report = deployer.analyze("deploy v1.0 to staging")
        text = format_report(report)
        assert "Deploy" in text
