"""Tests for config_drift.py — config drift detection across environments."""

import os
import json
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.config_drift import (
    ConfigDiff,
    ConfigDriftDetector,
    DriftReport,
    format_drift_report,
)


@pytest.fixture
def detector(tmp_path):
    """Create a ConfigDriftDetector with a temp working directory."""
    return ConfigDriftDetector(str(tmp_path))


# ---------------------------------------------------------------------------
# _flatten_dict
# ---------------------------------------------------------------------------

class TestFlattenDict:
    def test_flat(self, detector):
        result = detector._flatten_dict({"a": "1", "b": "2"})
        assert result == {"a": "1", "b": "2"}

    def test_nested(self, detector):
        result = detector._flatten_dict({"server": {"port": 8080, "host": "localhost"}})
        assert result == {"server.port": "8080", "server.host": "localhost"}

    def test_deeply_nested(self, detector):
        result = detector._flatten_dict({"a": {"b": {"c": "deep"}}})
        assert result == {"a.b.c": "deep"}

    def test_none_value(self, detector):
        result = detector._flatten_dict({"key": None})
        assert result == {"key": ""}

    def test_empty_dict(self, detector):
        result = detector._flatten_dict({})
        assert result == {}


# ---------------------------------------------------------------------------
# _parse_properties
# ---------------------------------------------------------------------------

class TestParseProperties:
    def test_basic(self, detector, tmp_path):
        props = tmp_path / "test.properties"
        props.write_text("db.host=localhost\ndb.port=5432\n")
        result = detector._parse_properties(str(props))
        assert result == {"db.host": "localhost", "db.port": "5432"}

    def test_comments_and_blanks(self, detector, tmp_path):
        props = tmp_path / "test.properties"
        props.write_text("# comment\n\ndb.host=localhost\n! another comment\n")
        result = detector._parse_properties(str(props))
        assert result == {"db.host": "localhost"}

    def test_colon_separator(self, detector, tmp_path):
        props = tmp_path / "test.properties"
        props.write_text("db.host: localhost\n")
        result = detector._parse_properties(str(props))
        assert result == {"db.host": "localhost"}


# ---------------------------------------------------------------------------
# _parse_env_file
# ---------------------------------------------------------------------------

class TestParseEnvFile:
    def test_basic(self, detector, tmp_path):
        env = tmp_path / ".env.dev"
        env.write_text("DB_HOST=localhost\nDB_PORT=5432\n")
        result = detector._parse_env_file(str(env))
        assert result == {"DB_HOST": "localhost", "DB_PORT": "5432"}

    def test_quoted_values(self, detector, tmp_path):
        env = tmp_path / ".env.dev"
        env.write_text('DB_HOST="localhost"\nDB_PASS=\'secret\'\n')
        result = detector._parse_env_file(str(env))
        assert result == {"DB_HOST": "localhost", "DB_PASS": "secret"}

    def test_comments_and_blanks(self, detector, tmp_path):
        env = tmp_path / ".env.dev"
        env.write_text("# comment\n\nDB_HOST=localhost\n")
        result = detector._parse_env_file(str(env))
        assert result == {"DB_HOST": "localhost"}


# ---------------------------------------------------------------------------
# _mask_sensitive
# ---------------------------------------------------------------------------

class TestMaskSensitive:
    def test_masks_password(self, detector):
        assert detector._mask_sensitive("db_password", "supersecret") == "sup***"

    def test_masks_token(self, detector):
        assert detector._mask_sensitive("API_TOKEN", "abc123def") == "abc***"

    def test_masks_key(self, detector):
        assert detector._mask_sensitive("SECRET_KEY", "mysecretkey") == "mys***"

    def test_masks_short_value(self, detector):
        assert detector._mask_sensitive("auth_token", "abc") == "***"

    def test_does_not_mask_normal(self, detector):
        assert detector._mask_sensitive("db_host", "localhost") == "localhost"

    def test_does_not_mask_port(self, detector):
        assert detector._mask_sensitive("server_port", "8080") == "8080"


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

class TestCompare:
    def test_identical(self, detector):
        detector.configs = {
            "dev": {"host": "localhost", "port": "8080"},
            "staging": {"host": "localhost", "port": "8080"},
        }
        diff = detector.compare("dev", "staging")
        assert diff.same_values == 2
        assert diff.different_values == []
        assert diff.only_in_a == []
        assert diff.only_in_b == []

    def test_different_values(self, detector):
        detector.configs = {
            "dev": {"host": "localhost", "port": "8080"},
            "prod": {"host": "prod-server", "port": "80"},
        }
        diff = detector.compare("dev", "prod")
        assert diff.same_values == 0
        assert len(diff.different_values) == 2
        keys = {d["key"] for d in diff.different_values}
        assert keys == {"host", "port"}

    def test_missing_keys(self, detector):
        detector.configs = {
            "dev": {"host": "localhost", "debug": "true"},
            "prod": {"host": "prod-server", "replicas": "3"},
        }
        diff = detector.compare("dev", "prod")
        assert diff.same_values == 0
        assert len(diff.different_values) == 1  # host
        assert len(diff.only_in_a) == 1  # debug
        assert diff.only_in_a[0]["key"] == "debug"
        assert len(diff.only_in_b) == 1  # replicas
        assert diff.only_in_b[0]["key"] == "replicas"

    def test_empty_env(self, detector):
        detector.configs = {"dev": {"host": "localhost"}}
        diff = detector.compare("dev", "missing")
        assert len(diff.only_in_a) == 1
        assert diff.only_in_b == []
        assert diff.same_values == 0

    def test_sensitive_values_masked_in_diff(self, detector):
        detector.configs = {
            "dev": {"db_password": "devsecret123"},
            "prod": {"db_password": "prodsecret456"},
        }
        diff = detector.compare("dev", "prod")
        assert len(diff.different_values) == 1
        assert diff.different_values[0]["value_a"] == "dev***"
        assert diff.different_values[0]["value_b"] == "pro***"


# ---------------------------------------------------------------------------
# compare_all
# ---------------------------------------------------------------------------

class TestCompareAll:
    def test_three_environments(self, detector):
        detector.configs = {
            "dev": {"host": "localhost", "port": "8080"},
            "staging": {"host": "staging-server", "port": "8080"},
            "prod": {"host": "prod-server", "port": "80"},
        }
        report = detector.compare_all()
        assert set(report.environments) == {"dev", "prod", "staging"}
        # 3 environments => 3 pairwise comparisons
        assert len(report.diffs) == 3

    def test_warnings_for_missing_keys(self, detector):
        detector.configs = {
            "dev": {"host": "localhost", "debug": "true"},
            "prod": {"host": "prod-server"},
        }
        report = detector.compare_all()
        assert len(report.warnings) >= 1
        assert any("only in dev" in w for w in report.warnings)

    def test_empty_configs(self, detector):
        detector.configs = {}
        report = detector.compare_all()
        assert report.environments == []
        assert report.diffs == []


# ---------------------------------------------------------------------------
# format_drift_report
# ---------------------------------------------------------------------------

class TestFormatDriftReport:
    def test_basic_output(self):
        diff = ConfigDiff(
            env_a="dev", env_b="prod",
            same_values=5,
            different_values=[{"key": "host", "value_a": "localhost", "value_b": "prod-server"}],
            only_in_a=[{"key": "debug", "value": "true"}],
            only_in_b=[],
        )
        report = DriftReport(environments=["dev", "prod"], diffs=[diff])
        output = format_drift_report(report)
        assert "dev vs prod" in output
        assert "Same: 5" in output
        assert "Different: 1" in output
        assert "host" in output
        assert "localhost" in output
        assert "prod-server" in output
        assert "debug" in output

    def test_warnings_in_output(self):
        report = DriftReport(
            environments=["dev", "prod"],
            diffs=[],
            warnings=["2 keys only in dev (missing from prod)"],
        )
        output = format_drift_report(report)
        assert "Warnings" in output
        assert "2 keys only in dev" in output

    def test_empty_report(self):
        report = DriftReport(environments=[], diffs=[])
        output = format_drift_report(report)
        assert "Config Drift Report" in output


# ---------------------------------------------------------------------------
# Auto-detection: Spring profiles
# ---------------------------------------------------------------------------

class TestLoadSpringProfiles:
    def test_yml_profiles(self, tmp_path):
        res_dir = tmp_path / "src" / "main" / "resources"
        res_dir.mkdir(parents=True)
        (res_dir / "application-dev.yml").write_text("server:\n  port: 8080\nspring:\n  datasource:\n    url: jdbc:h2:mem\n")
        (res_dir / "application-prod.yml").write_text("server:\n  port: 80\nspring:\n  datasource:\n    url: jdbc:mysql://prod\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "dev" in configs
        assert "prod" in configs
        assert configs["dev"]["server.port"] == "8080"
        assert configs["prod"]["server.port"] == "80"

    def test_properties_profiles(self, tmp_path):
        res_dir = tmp_path / "src" / "main" / "resources"
        res_dir.mkdir(parents=True)
        (res_dir / "application-dev.properties").write_text("server.port=8080\n")
        (res_dir / "application-prod.properties").write_text("server.port=80\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert configs["dev"]["server.port"] == "8080"
        assert configs["prod"]["server.port"] == "80"


# ---------------------------------------------------------------------------
# Auto-detection: .env files
# ---------------------------------------------------------------------------

class TestLoadEnvFiles:
    def test_env_files(self, tmp_path):
        (tmp_path / ".env.dev").write_text("DB_HOST=localhost\nDB_PORT=5432\n")
        (tmp_path / ".env.staging").write_text("DB_HOST=staging-db\nDB_PORT=5432\n")
        (tmp_path / ".env.prod").write_text("DB_HOST=prod-db\nDB_PORT=5432\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "dev" in configs
        assert "staging" in configs
        assert "prod" in configs

    def test_skips_example_files(self, tmp_path):
        (tmp_path / ".env.example").write_text("DB_HOST=xxx\n")
        (tmp_path / ".env.template").write_text("DB_HOST=xxx\n")
        (tmp_path / ".env.sample").write_text("DB_HOST=xxx\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "example" not in configs
        assert "template" not in configs
        assert "sample" not in configs


# ---------------------------------------------------------------------------
# Auto-detection: config dirs
# ---------------------------------------------------------------------------

class TestLoadConfigDirs:
    def test_config_directories(self, tmp_path):
        for env in ("dev", "staging", "prod"):
            d = tmp_path / "config" / env
            d.mkdir(parents=True)
            (d / "app.yml").write_text(f"port: {env}\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "dev" in configs
        assert "staging" in configs
        assert "prod" in configs

    def test_ignores_unknown_dirs(self, tmp_path):
        d = tmp_path / "config" / "random"
        d.mkdir(parents=True)
        (d / "app.yml").write_text("port: 8080\n")

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "random" not in configs


# ---------------------------------------------------------------------------
# Auto-detection: K8s ConfigMaps
# ---------------------------------------------------------------------------

class TestLoadK8sConfigs:
    def test_configmap(self, tmp_path):
        k8s_dir = tmp_path / "k8s"
        k8s_dir.mkdir()
        cm = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "app-config-prod"},
            "data": {"DATABASE_URL": "jdbc:mysql://prod", "LOG_LEVEL": "WARN"},
        }
        import yaml
        (k8s_dir / "configmap.yml").write_text(yaml.dump(cm))

        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert "prod" in configs
        assert "app-config-prod.DATABASE_URL" in configs["prod"]

    def test_no_k8s_dir(self, tmp_path):
        detector = ConfigDriftDetector(str(tmp_path))
        configs = detector.load_configs()
        assert len(configs) == 0


# ---------------------------------------------------------------------------
# _guess_env_from_name
# ---------------------------------------------------------------------------

class TestGuessEnvFromName:
    def test_prod(self, detector):
        assert detector._guess_env_from_name("app-config-prod") == "prod"

    def test_staging(self, detector):
        assert detector._guess_env_from_name("myapp-staging-config") == "staging"

    def test_dev(self, detector):
        assert detector._guess_env_from_name("my-dev-config") == "dev"

    def test_unknown(self, detector):
        assert detector._guess_env_from_name("random-name") is None
