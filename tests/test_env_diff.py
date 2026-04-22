"""Tests for the environment diff checker."""

from __future__ import annotations

import pytest
from pathlib import Path

from code_agents.devops.env_diff import EnvDiffChecker, EnvDiffResult


@pytest.fixture
def env_project(tmp_path):
    """Create a temp project with .env files."""
    (tmp_path / ".env.dev").write_text(
        "DB_HOST=localhost\nDB_PORT=5432\nDB_PASSWORD=secret_dev\nDEBUG=true\n"
    )
    (tmp_path / ".env.staging").write_text(
        "DB_HOST=staging-db.internal\nDB_PORT=5432\nDB_PASSWORD=secret_staging\nREDIS_URL=redis://staging\n"
    )
    (tmp_path / ".env.prod").write_text(
        'export DB_HOST="prod-db.internal"\nexport DB_PORT=5432\nDB_PASSWORD=secret_prod\nREDIS_URL=redis://prod\n'
    )
    return tmp_path


class TestEnvDiffCompare:
    def test_compare_basic(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        assert result.env_a == "dev"
        assert result.env_b == "staging"
        assert result.has_differences

    def test_missing_in_b(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        assert "DEBUG" in result.missing_in_b

    def test_missing_in_a(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        assert "REDIS_URL" in result.missing_in_a

    def test_different_values(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        diff_keys = [d["key"] for d in result.different_values]
        assert "DB_HOST" in diff_keys

    def test_secrets_masked(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        password_diff = [d for d in result.different_values if d["key"] == "DB_PASSWORD"]
        assert len(password_diff) == 1
        assert password_diff[0]["value_a"] == "***"
        assert password_diff[0]["value_b"] == "***"

    def test_secrets_differ_list(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "staging")
        assert "DB_PASSWORD" in result.secrets_differ

    def test_same_env_no_diff(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        result = checker.compare("dev", "dev")
        assert not result.has_differences
        assert result.total_diffs == 0

    def test_missing_env_file(self, tmp_path):
        checker = EnvDiffChecker(cwd=str(tmp_path))
        result = checker.compare("dev", "staging")
        assert not result.has_differences


class TestEnvDiffParseFile:
    def test_parse_with_quotes(self, tmp_path):
        (tmp_path / ".env.test").write_text('KEY1="value1"\nKEY2=\'value2\'\n')
        checker = EnvDiffChecker(cwd=str(tmp_path))
        data = checker._load_env("test")
        assert data["KEY1"] == "value1"
        assert data["KEY2"] == "value2"

    def test_parse_export_prefix(self, tmp_path):
        (tmp_path / ".env.test").write_text("export MY_VAR=hello\n")
        checker = EnvDiffChecker(cwd=str(tmp_path))
        data = checker._load_env("test")
        assert data["MY_VAR"] == "hello"

    def test_parse_comments_ignored(self, tmp_path):
        (tmp_path / ".env.test").write_text("# comment\nKEY=val\n# another\n")
        checker = EnvDiffChecker(cwd=str(tmp_path))
        data = checker._load_env("test")
        assert data == {"KEY": "val"}

    def test_parse_empty_lines(self, tmp_path):
        (tmp_path / ".env.test").write_text("\n\nKEY=val\n\n")
        checker = EnvDiffChecker(cwd=str(tmp_path))
        data = checker._load_env("test")
        assert data == {"KEY": "val"}


class TestIsSecretKey:
    @pytest.mark.parametrize("key", [
        "DB_PASSWORD", "API_KEY", "SECRET_TOKEN", "AWS_ACCESS_KEY",
        "JWT_SECRET", "ENCRYPTION_KEY", "AUTH_TOKEN", "PRIVATE_KEY",
    ])
    def test_secret_keys_detected(self, key):
        assert EnvDiffChecker._is_secret_key(key) is True

    @pytest.mark.parametrize("key", [
        "DB_HOST", "DB_PORT", "DEBUG", "LOG_LEVEL", "APP_NAME",
    ])
    def test_non_secret_keys(self, key):
        assert EnvDiffChecker._is_secret_key(key) is False


class TestEnvDiffResult:
    def test_summary_no_diff(self):
        result = EnvDiffResult(env_a="dev", env_b="staging")
        assert result.summary() == "No differences"

    def test_summary_with_diffs(self):
        result = EnvDiffResult(
            env_a="dev", env_b="staging",
            missing_in_b=["KEY1"],
            different_values=[{"key": "K2", "value_a": "a", "value_b": "b"}],
        )
        assert "1 missing in staging" in result.summary()
        assert "1 values differ" in result.summary()

    def test_total_diffs(self):
        result = EnvDiffResult(
            env_a="dev", env_b="staging",
            missing_in_b=["A"], missing_in_a=["B", "C"],
            different_values=[{"key": "D"}],
        )
        assert result.total_diffs == 4


class TestListEnvironments:
    def test_list_env_files(self, env_project):
        checker = EnvDiffChecker(cwd=str(env_project))
        envs = checker.list_environments()
        assert "dev" in envs
        assert "staging" in envs
        assert "prod" in envs

    def test_list_empty(self, tmp_path):
        checker = EnvDiffChecker(cwd=str(tmp_path))
        assert checker.list_environments() == []
