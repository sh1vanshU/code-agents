"""Tests for the EnvDiffer module."""

import pytest
from code_agents.devops.env_differ import EnvDiffer, EnvDiffConfig, EnvDiffResult, format_env_diff


class TestEnvDiffer:
    def test_diff_identical(self):
        left = {"KEY1": "val1", "KEY2": "val2"}
        right = {"KEY1": "val1", "KEY2": "val2"}
        result = EnvDiffer().diff_dicts(left, right)
        assert result.same == 2
        assert result.different == 0

    def test_diff_different_values(self):
        left = {"DB_HOST": "localhost", "PORT": "8080"}
        right = {"DB_HOST": "prod-db.internal", "PORT": "8080"}
        result = EnvDiffer().diff_dicts(left, right)
        assert result.different == 1
        assert result.same == 1

    def test_diff_missing_keys(self):
        left = {"KEY1": "val1"}
        right = {"KEY1": "val1", "KEY2": "val2"}
        result = EnvDiffer().diff_dicts(left, right)
        assert result.missing_left == 1
        assert result.missing_right == 0

    def test_secret_masking(self):
        left = {"API_KEY": "secret123"}
        right = {"API_KEY": "secret456"}
        result = EnvDiffer(EnvDiffConfig(mask_secrets=True)).diff_dicts(left, right)
        entry = next(e for e in result.entries if e.key == "API_KEY")
        assert entry.is_secret is True
        assert entry.left_value == "***"

    def test_secret_unmasked(self):
        left = {"API_KEY": "secret123"}
        right = {"API_KEY": "secret456"}
        result = EnvDiffer(EnvDiffConfig(mask_secrets=False)).diff_dicts(left, right)
        entry = next(e for e in result.entries if e.key == "API_KEY")
        assert entry.left_value == "secret123"

    def test_critical_key_severity(self):
        left = {"DATABASE_URL": "postgres://local"}
        right = {"DATABASE_URL": "postgres://prod"}
        result = EnvDiffer().diff_dicts(left, right)
        entry = next(e for e in result.entries if e.key == "DATABASE_URL")
        assert entry.severity == "critical"

    def test_suspicious_identical_critical(self):
        left = {"DATABASE_URL": "same_value"}
        right = {"DATABASE_URL": "same_value"}
        result = EnvDiffer().diff_dicts(left, right, "local", "prod")
        assert any("identical" in w for w in result.warnings)

    def test_parse_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2='quoted value'\n# comment\n\nKEY3=value3\n")
        result = EnvDiffer(EnvDiffConfig(cwd=str(tmp_path)))._parse_env_file(str(env_file))
        assert result["KEY1"] == "value1"
        assert result["KEY2"] == "quoted value"
        assert result["KEY3"] == "value3"
        assert "#" not in result

    def test_format_output(self):
        result = EnvDiffResult(left_name="local", right_name="prod", summary="3 keys")
        output = format_env_diff(result)
        assert "local" in output
        assert "prod" in output
