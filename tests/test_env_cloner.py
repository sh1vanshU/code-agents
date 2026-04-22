"""Tests for env_cloner.py — environment config cloning and templating."""

import pytest

from code_agents.devops.env_cloner import (
    EnvCloner,
    CloneReport,
    EnvVariable,
    EnvTemplate,
    format_report,
)


@pytest.fixture
def cloner(tmp_path):
    return EnvCloner(str(tmp_path))


class TestCategorize:
    def test_database_category(self, cloner):
        assert cloner._categorize("DB_HOST") == "database"
        assert cloner._categorize("POSTGRES_PASSWORD") == "database"

    def test_api_category(self, cloner):
        assert cloner._categorize("API_ENDPOINT") == "api"
        assert cloner._categorize("BASE_URL") == "api"

    def test_feature_category(self, cloner):
        assert cloner._categorize("FEATURE_NEW_UI") == "feature"

    def test_other_category(self, cloner):
        assert cloner._categorize("SOME_RANDOM_VAR") == "other"


class TestIsSecret:
    def test_detects_password(self, cloner):
        assert cloner._is_secret("DB_PASSWORD", "mypass") is True

    def test_detects_token(self, cloner):
        assert cloner._is_secret("AUTH_TOKEN", "abc") is True

    def test_detects_long_base64(self, cloner):
        assert cloner._is_secret("SOME_VAR", "aAbBcCdDeEfF123456789012") is True

    def test_normal_var_not_secret(self, cloner):
        assert cloner._is_secret("APP_NAME", "myapp") is False


class TestParseEnvFile:
    def test_parses_env(self, cloner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=localhost\nDB_PORT=5432\n")
        vars = cloner._parse_env_file(str(env_file))
        assert len(vars) == 2
        assert vars[0].key == "DB_HOST"

    def test_skips_comments(self, cloner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nVAR=value\n")
        vars = cloner._parse_env_file(str(env_file))
        assert len(vars) == 1


class TestAnalyze:
    def test_full_analysis(self, cloner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DB_HOST=localhost\nAPI_KEY=secret123\n")
        report = cloner.analyze()
        assert isinstance(report, CloneReport)
        assert report.variables_found >= 2

    def test_format_report(self, cloner, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("VAR=val\n")
        report = cloner.analyze()
        text = format_report(report)
        assert "Clone Report" in text
