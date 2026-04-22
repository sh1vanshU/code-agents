"""Tests for spec_validator module — requirement extraction, classification, report formatting."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from code_agents.testing.spec_validator import (
    ImplementationEvidence,
    SpecGap,
    SpecReport,
    SpecRequirement,
    SpecValidator,
    format_spec_report,
    _extract_keywords,
    _to_snake,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(tmp_path):
    """Create a tiny fake repo with some Python files."""
    (tmp_path / "app.py").write_text(
        "def login_with_email(email, password):\n"
        "    # authenticate user\n"
        "    return True\n"
    )
    (tmp_path / "auth.py").write_text(
        "def reset_password(email):\n"
        "    # send reset email\n"
        "    pass\n"
        "\n"
        "def rate_limit_check(user_id):\n"
        "    # partial rate limiting\n"
        "    pass\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text(
        "def test_login_with_email():\n"
        "    assert True\n"
        "\n"
        "def test_reset_password():\n"
        "    assert True\n"
    )
    return str(tmp_path)


@pytest.fixture
def validator(tmp_repo):
    return SpecValidator(cwd=tmp_repo)


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    def test_basic_extraction(self):
        kws = _extract_keywords("User login with email and password")
        assert "user" in kws or "User" in [k.capitalize() for k in kws]
        assert "login" in kws
        assert "email" in kws
        assert "password" in kws

    def test_stop_words_removed(self):
        kws = _extract_keywords("The user is a member of the team")
        assert "the" not in kws
        assert "is" not in kws
        assert "of" not in kws

    def test_short_words_removed(self):
        kws = _extract_keywords("I am ok to go do it")
        # all <= 2 chars should be dropped
        for kw in kws:
            assert len(kw) >= 3

    def test_empty_string(self):
        assert _extract_keywords("") == []

    def test_capped_at_twelve(self):
        text = " ".join(f"keyword{i}" for i in range(20))
        assert len(_extract_keywords(text)) <= 12


# ---------------------------------------------------------------------------
# _to_snake
# ---------------------------------------------------------------------------

class TestToSnake:
    def test_basic(self):
        assert _to_snake("User login with email") == "user_login_email"

    def test_strips_punctuation(self):
        result = _to_snake("reset user's password!")
        assert "'" not in result
        assert "!" not in result

    def test_empty(self):
        assert _to_snake("") == ""


# ---------------------------------------------------------------------------
# Requirement extraction
# ---------------------------------------------------------------------------

class TestExtractRequirements:
    def test_user_story(self, validator):
        text = "As a user, I want to login with email so that I can access my account"
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 1
        assert reqs[0].category == "functional"
        assert "REQ-" in reqs[0].id

    def test_given_when_then(self, validator):
        text = (
            "Given the user is on the login page\n"
            "When they enter valid credentials\n"
            "Then they should be redirected to the dashboard"
        )
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 1
        assert "Given" in reqs[0].description or "login" in reqs[0].description.lower()

    def test_numbered_list(self, validator):
        text = (
            "Requirements:\n"
            "1. User should be able to login with email\n"
            "2. User should be able to reset password\n"
            "3. System should enforce rate limiting on API\n"
        )
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 3

    def test_bullet_list(self, validator):
        text = (
            "Acceptance Criteria:\n"
            "- User should be able to login with email\n"
            "- User should be able to reset their password\n"
        )
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 2

    def test_nonfunctional_detection(self, validator):
        text = "1. System performance must handle 1000 requests per second"
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 1
        assert reqs[0].category == "nonfunctional"

    def test_edge_case_detection(self, validator):
        text = "1. Handle invalid email format gracefully with error message"
        reqs = validator._extract_requirements(text)
        assert len(reqs) >= 1
        assert reqs[0].category == "edge_case"

    def test_empty_text(self, validator):
        reqs = validator._extract_requirements("")
        assert reqs == []

    def test_deduplication(self, validator):
        text = (
            "As a user, I want to login with email so that I can access my account\n"
            "1. As a user, I want to login with email so that I can access my account\n"
        )
        reqs = validator._extract_requirements(text)
        # Should deduplicate
        assert len(reqs) == 1

    def test_short_items_skipped(self, validator):
        text = "1. Fix bug\n2. User should be able to reset their password"
        reqs = validator._extract_requirements(text)
        # "Fix bug" is < 10 chars, should be skipped
        assert all("Fix bug" not in r.description for r in reqs)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassifyGap:
    def test_missing_no_evidence(self, validator):
        req = SpecRequirement(id="REQ-1", description="something", category="functional", source="manual")
        gap = validator._classify_gap(req, [])
        assert gap.status == "missing"

    def test_implemented_high_confidence(self, validator):
        req = SpecRequirement(id="REQ-1", description="login with email", category="functional", source="manual")
        evidence = [
            ImplementationEvidence(requirement_id="REQ-1", file="app.py", line=1, code_snippet="def login_with_email(email, password):", confidence=0.85),
            ImplementationEvidence(requirement_id="REQ-1", file="tests/test_auth.py", line=1, code_snippet="def test_login_with_email():", confidence=0.75),
        ]
        gap = validator._classify_gap(req, evidence)
        assert gap.status == "implemented"

    def test_partial_medium_confidence(self, validator):
        req = SpecRequirement(id="REQ-1", description="something", category="functional", source="manual")
        evidence = [
            ImplementationEvidence(requirement_id="REQ-1", file="app.py", line=5, code_snippet="# partial match", confidence=0.45),
        ]
        gap = validator._classify_gap(req, evidence)
        assert gap.status == "partial"

    def test_missing_weak_evidence(self, validator):
        req = SpecRequirement(id="REQ-1", description="something", category="functional", source="manual")
        evidence = [
            ImplementationEvidence(requirement_id="REQ-1", file="app.py", line=5, code_snippet="unrelated", confidence=0.2),
        ]
        gap = validator._classify_gap(req, evidence)
        assert gap.status == "missing"


# ---------------------------------------------------------------------------
# Validation (integration)
# ---------------------------------------------------------------------------

class TestValidate:
    @patch.object(SpecValidator, "_search_implementation")
    def test_full_validate(self, mock_search, validator):
        """Test the full validation pipeline with mocked search."""
        mock_search.return_value = [
            ImplementationEvidence(
                requirement_id="REQ-1", file="app.py", line=1,
                code_snippet="def login_with_email():", confidence=0.85,
            ),
            ImplementationEvidence(
                requirement_id="REQ-1", file="tests/test_auth.py", line=1,
                code_snippet="def test_login_with_email():", confidence=0.75,
            ),
        ]
        report = validator.validate(
            spec_text="1. User should be able to login with email and password"
        )
        assert isinstance(report, SpecReport)
        assert len(report.requirements) >= 1
        assert report.coverage > 0

    def test_empty_spec(self, validator):
        report = validator.validate(spec_text="")
        assert report.requirements == []
        assert report.coverage == 0.0

    def test_prd_file(self, validator, tmp_path):
        prd = tmp_path / "prd.md"
        prd.write_text(
            "# PRD\n"
            "1. User should be able to login with email\n"
            "2. User should be able to reset password\n"
        )
        report = validator.validate(prd_file=str(prd))
        assert len(report.requirements) >= 2

    @patch.object(SpecValidator, "_fetch_jira_spec")
    def test_jira_source(self, mock_jira, validator):
        mock_jira.return_value = "1. User should be able to login with email"
        report = validator.validate(jira_key="PROJ-123")
        assert len(report.requirements) >= 1
        mock_jira.assert_called_once_with("PROJ-123")


# ---------------------------------------------------------------------------
# Jira fetch
# ---------------------------------------------------------------------------

class TestFetchJira:
    def test_missing_env_vars(self, validator):
        """Returns empty string when Jira env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = validator._fetch_jira_spec("PROJ-123")
            assert result == ""

    @patch("urllib.request.urlopen")
    def test_successful_fetch(self, mock_urlopen, validator):
        response_data = json.dumps({
            "fields": {
                "summary": "Add login feature",
                "description": "As a user, I want to login with email",
            }
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_TOKEN": "secret",
        }):
            result = validator._fetch_jira_spec("PROJ-123")
            assert "login" in result.lower()

    @patch("urllib.request.urlopen", side_effect=Exception("Connection error"))
    def test_fetch_failure_graceful(self, mock_urlopen, validator):
        with patch.dict(os.environ, {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_TOKEN": "secret",
        }):
            result = validator._fetch_jira_spec("PROJ-123")
            assert result == ""


# ---------------------------------------------------------------------------
# PRD file reading
# ---------------------------------------------------------------------------

class TestReadPrd:
    def test_read_existing_file(self, validator, tmp_path):
        prd = tmp_path / "spec.md"
        prd.write_text("1. Login feature required")
        result = validator._read_prd(str(prd))
        assert "Login" in result

    def test_read_nonexistent_file(self, validator):
        result = validator._read_prd("/nonexistent/path/prd.md")
        assert result == ""

    def test_relative_path(self, validator, tmp_repo):
        # Write a file relative to the repo
        import pathlib
        (pathlib.Path(tmp_repo) / "spec.md").write_text("1. Some requirement here for testing")
        result = validator._read_prd("spec.md")
        assert "requirement" in result.lower()


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

class TestFormatSpecReport:
    def _make_report(self) -> SpecReport:
        reqs = [
            SpecRequirement(id="REQ-1", description="User login with email", category="functional", source="manual"),
            SpecRequirement(id="REQ-2", description="Password reset flow", category="functional", source="manual"),
            SpecRequirement(id="REQ-3", description="Rate limiting on API", category="nonfunctional", source="manual"),
            SpecRequirement(id="REQ-4", description="Email verification", category="functional", source="manual"),
        ]
        gaps = [
            SpecGap(requirement=reqs[0], status="implemented", evidence=[], notes="3 strong matches (with tests)"),
            SpecGap(requirement=reqs[1], status="implemented", evidence=[], notes="2 strong matches"),
            SpecGap(requirement=reqs[2], status="partial", evidence=[], notes="Some evidence found"),
            SpecGap(requirement=reqs[3], status="missing", evidence=[], notes="No matching code found"),
        ]
        return SpecReport(
            requirements=reqs, gaps=gaps, coverage=50.0,
            missing=["REQ-4"], deviated=[],
        )

    def test_text_format(self):
        report = self._make_report()
        output = format_spec_report(report, fmt="text")
        assert "Spec Validation" in output
        assert "REQ-1" in output
        assert "REQ-4" in output
        assert "missing" in output.lower()

    def test_json_format(self):
        report = self._make_report()
        output = format_spec_report(report, fmt="json")
        data = json.loads(output)
        assert data["coverage"] == 50.0
        assert data["total_requirements"] == 4
        assert "REQ-4" in data["missing"]
        assert len(data["requirements"]) == 4

    def test_empty_report(self):
        report = SpecReport(requirements=[], gaps=[], coverage=0.0, missing=[], deviated=[])
        output = format_spec_report(report, fmt="text")
        assert "No requirements" in output

    def test_json_empty_report(self):
        report = SpecReport(requirements=[], gaps=[], coverage=0.0, missing=[], deviated=[])
        output = format_spec_report(report, fmt="json")
        data = json.loads(output)
        assert data["total_requirements"] == 0


# ---------------------------------------------------------------------------
# CLI wrapper
# ---------------------------------------------------------------------------

class TestCliSpec:
    @patch("code_agents.testing.spec_validator.SpecValidator.validate")
    def test_cmd_spec_validate_with_spec(self, mock_validate, capsys):
        mock_validate.return_value = SpecReport(
            requirements=[], gaps=[], coverage=0.0, missing=[], deviated=[],
        )
        from code_agents.cli.cli_spec import cmd_spec_validate
        cmd_spec_validate(["--spec", "As a user I want login"])
        mock_validate.assert_called_once()

    @patch("code_agents.testing.spec_validator.SpecValidator.validate")
    def test_cmd_spec_validate_with_prd(self, mock_validate, capsys, tmp_path):
        mock_validate.return_value = SpecReport(
            requirements=[], gaps=[], coverage=0.0, missing=[], deviated=[],
        )
        prd = tmp_path / "spec.md"
        prd.write_text("1. Some requirement")
        from code_agents.cli.cli_spec import cmd_spec_validate
        cmd_spec_validate(["--prd", str(prd)])
        mock_validate.assert_called_once()

    def test_cmd_spec_validate_no_args(self, capsys):
        from code_agents.cli.cli_spec import cmd_spec_validate
        cmd_spec_validate([])
        captured = capsys.readouterr()
        assert "No spec source" in captured.out

    def test_cmd_spec_validate_help(self, capsys):
        from code_agents.cli.cli_spec import cmd_spec_validate
        cmd_spec_validate(["--help"])
        captured = capsys.readouterr()
        assert "--spec" in captured.out
        assert "--jira" in captured.out
        assert "--prd" in captured.out
