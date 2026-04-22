"""Tests for feature_flags.py — feature flag scanner and report formatting."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.feature_flags import (
    FeatureFlag,
    FeatureFlagScanner,
    FlagReport,
    format_flag_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env_repo(tmp_path):
    """Repo with .env files containing feature flags."""
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgres://localhost/db\n"
        "FEATURE_NEW_UI=true\n"
        "ENABLE_CACHING=false\n"
        "SECRET_KEY=abc123\n"
    )
    (tmp_path / ".env.staging").write_text(
        "FEATURE_NEW_UI=false\n"
        "ENABLE_CACHING=true\n"
    )
    (tmp_path / ".env.prod").write_text(
        "FEATURE_NEW_UI=false\n"
        "ENABLE_CACHING=true\n"
    )
    return tmp_path


@pytest.fixture
def java_repo(tmp_path):
    """Repo with Java feature flag annotations."""
    src = tmp_path / "src" / "main"
    src.mkdir(parents=True)
    (src / "FeatureConfig.java").write_text(
        'import org.springframework.beans.factory.annotation.Value;\n'
        '\n'
        'public class FeatureConfig {\n'
        '    @Value("${feature.new-checkout.enabled:false}")\n'
        '    private boolean newCheckout;\n'
        '\n'
        '    @Value("${app.name:MyApp}")\n'
        '    private String appName;\n'
        '}\n'
    )
    (src / "AppConfig.java").write_text(
        'import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;\n'
        '\n'
        '@ConditionalOnProperty(name = "feature.dark-mode")\n'
        'public class AppConfig {}\n'
    )
    return tmp_path


@pytest.fixture
def yaml_repo(tmp_path):
    """Repo with YAML config containing feature flags."""
    (tmp_path / "application.yml").write_text(
        "server:\n"
        "  port: 8080\n"
        "feature:\n"
        "  new-dashboard:\n"
        "    enabled: true\n"
        "  toggle-payments: false\n"
    )
    return tmp_path


@pytest.fixture
def python_repo(tmp_path):
    """Repo with Python code checking feature flags."""
    (tmp_path / "app.py").write_text(
        'import os\n'
        '\n'
        'def main():\n'
        '    if os.getenv("FEATURE_DARK_MODE"):\n'
        '        enable_dark_mode()\n'
        '    cache = os.environ.get("ENABLE_CACHE", "false")\n'
        '    name = os.getenv("APP_NAME", "default")\n'
    )
    return tmp_path


@pytest.fixture
def stale_repo(tmp_path):
    """Repo with a flag in .env that is NOT referenced in code."""
    (tmp_path / ".env").write_text(
        "FEATURE_OLD_FLOW=true\n"
        "FEATURE_ACTIVE_FLOW=true\n"
    )
    # Only FEATURE_ACTIVE_FLOW is referenced in code
    (tmp_path / "app.py").write_text(
        'import os\n'
        'if os.getenv("FEATURE_ACTIVE_FLOW"):\n'
        '    pass\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests — env scanning
# ---------------------------------------------------------------------------

class TestScanEnvFlags:
    """Test _scan_env_flags with .env files."""

    def test_finds_feature_flags(self, env_repo):
        scanner = FeatureFlagScanner(cwd=str(env_repo))
        flags = scanner._scan_env_flags()
        names = {f.name for f in flags}
        assert "FEATURE_NEW_UI" in names
        assert "ENABLE_CACHING" in names

    def test_excludes_non_flags(self, env_repo):
        scanner = FeatureFlagScanner(cwd=str(env_repo))
        flags = scanner._scan_env_flags()
        names = {f.name for f in flags}
        assert "DATABASE_URL" not in names
        assert "SECRET_KEY" not in names

    def test_env_values_per_environment(self, env_repo):
        scanner = FeatureFlagScanner(cwd=str(env_repo))
        flags = scanner._scan_env_flags()
        by_name = {f.name: f for f in flags}
        flag = by_name["FEATURE_NEW_UI"]
        assert "default" in flag.env_values
        assert flag.env_values["default"] == "true"
        assert flag.env_values.get("staging") == "false"
        assert flag.env_values.get("prod") == "false"

    def test_flag_type_detected(self, env_repo):
        scanner = FeatureFlagScanner(cwd=str(env_repo))
        flags = scanner._scan_env_flags()
        by_name = {f.name: f for f in flags}
        assert by_name["FEATURE_NEW_UI"].flag_type == "boolean"
        assert by_name["ENABLE_CACHING"].flag_type == "boolean"

    def test_empty_env_file(self, tmp_path):
        (tmp_path / ".env").write_text("")
        scanner = FeatureFlagScanner(cwd=str(tmp_path))
        flags = scanner._scan_env_flags()
        assert flags == []

    def test_comments_and_blank_lines_skipped(self, tmp_path):
        (tmp_path / ".env").write_text(
            "# This is a comment\n"
            "\n"
            "FEATURE_X=true\n"
            "# FEATURE_DISABLED=false\n"
        )
        scanner = FeatureFlagScanner(cwd=str(tmp_path))
        flags = scanner._scan_env_flags()
        assert len(flags) == 1
        assert flags[0].name == "FEATURE_X"


# ---------------------------------------------------------------------------
# Tests — Java scanning
# ---------------------------------------------------------------------------

class TestScanJavaFlags:
    """Test _scan_java_flags with @Value and @ConditionalOnProperty."""

    def test_finds_value_annotation_flags(self, java_repo):
        scanner = FeatureFlagScanner(cwd=str(java_repo))
        flags = scanner._scan_java_flags()
        names = {f.name for f in flags}
        assert "feature.new-checkout.enabled" in names

    def test_excludes_non_feature_values(self, java_repo):
        scanner = FeatureFlagScanner(cwd=str(java_repo))
        flags = scanner._scan_java_flags()
        names = {f.name for f in flags}
        assert "app.name" not in names

    def test_finds_conditional_on_property(self, java_repo):
        scanner = FeatureFlagScanner(cwd=str(java_repo))
        flags = scanner._scan_java_flags()
        names = {f.name for f in flags}
        assert "feature.dark-mode" in names

    def test_default_value_extracted(self, java_repo):
        scanner = FeatureFlagScanner(cwd=str(java_repo))
        flags = scanner._scan_java_flags()
        by_name = {f.name: f for f in flags}
        assert by_name["feature.new-checkout.enabled"].default_value == "false"


# ---------------------------------------------------------------------------
# Tests — config scanning
# ---------------------------------------------------------------------------

class TestScanConfigFlags:
    """Test _scan_config_flags with YAML/properties."""

    def test_finds_yaml_feature_flags(self, yaml_repo):
        scanner = FeatureFlagScanner(cwd=str(yaml_repo))
        flags = scanner._scan_config_flags()
        assert len(flags) >= 1
        names = {f.name for f in flags}
        # Should find lines containing "feature" or "toggle"
        assert any("enabled" in n or "toggle" in n.lower() for n in names)


# ---------------------------------------------------------------------------
# Tests — code scanning
# ---------------------------------------------------------------------------

class TestScanCodeFlags:
    """Test _scan_code_flags with Python os.getenv."""

    def test_finds_python_feature_flags(self, python_repo):
        scanner = FeatureFlagScanner(cwd=str(python_repo))
        flags = scanner._scan_code_flags()
        names = {f.name for f in flags}
        assert "FEATURE_DARK_MODE" in names
        assert "ENABLE_CACHE" in names

    def test_excludes_non_flag_env_vars(self, python_repo):
        scanner = FeatureFlagScanner(cwd=str(python_repo))
        flags = scanner._scan_code_flags()
        names = {f.name for f in flags}
        # APP_NAME does not match flag patterns
        assert "APP_NAME" not in names


# ---------------------------------------------------------------------------
# Tests — stale detection
# ---------------------------------------------------------------------------

class TestDetectStale:
    """Test _detect_stale marks unreferenced config flags as stale."""

    def test_stale_flag_detected(self, stale_repo):
        scanner = FeatureFlagScanner(cwd=str(stale_repo))
        report = scanner.scan()
        stale_names = {f.name for f in report.stale_flags}
        assert "FEATURE_OLD_FLOW" in stale_names

    def test_active_flag_not_stale(self, stale_repo):
        scanner = FeatureFlagScanner(cwd=str(stale_repo))
        report = scanner.scan()
        stale_names = {f.name for f in report.stale_flags}
        assert "FEATURE_ACTIVE_FLOW" not in stale_names


# ---------------------------------------------------------------------------
# Tests — deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Test that flags from multiple sources are deduplicated."""

    def test_dedup_by_name(self, tmp_path):
        (tmp_path / ".env").write_text("FEATURE_X=true\n")
        (tmp_path / "app.py").write_text('import os\nos.getenv("FEATURE_X")\n')
        scanner = FeatureFlagScanner(cwd=str(tmp_path))
        report = scanner.scan()
        x_flags = [f for f in report.flags if f.name == "FEATURE_X"]
        assert len(x_flags) == 1


# ---------------------------------------------------------------------------
# Tests — env matrix
# ---------------------------------------------------------------------------

class TestEnvMatrix:
    """Test env_matrix generation in FlagReport."""

    def test_matrix_populated(self, env_repo):
        scanner = FeatureFlagScanner(cwd=str(env_repo))
        report = scanner.scan()
        assert "FEATURE_NEW_UI" in report.env_matrix
        matrix = report.env_matrix["FEATURE_NEW_UI"]
        assert matrix["default"] == "true"
        assert matrix.get("staging") == "false"

    def test_no_matrix_when_no_envs(self, python_repo):
        scanner = FeatureFlagScanner(cwd=str(python_repo))
        report = scanner.scan()
        # Code flags have no env_values, so matrix should be empty
        assert report.env_matrix == {}


# ---------------------------------------------------------------------------
# Tests — format report
# ---------------------------------------------------------------------------

class TestFormatFlagReport:
    """Test format_flag_report output."""

    def test_empty_report(self):
        report = FlagReport(total_flags=0)
        output = format_flag_report(report)
        assert "0 found" in output

    def test_active_flags_shown(self):
        flag = FeatureFlag(name="FEATURE_X", file=".env", line=1, default_value="true")
        report = FlagReport(total_flags=1, flags=[flag])
        output = format_flag_report(report)
        assert "FEATURE_X" in output
        assert "Active Flags" in output

    def test_stale_flags_shown(self):
        flag = FeatureFlag(name="FEATURE_OLD", file=".env", line=5, stale=True)
        report = FlagReport(total_flags=1, flags=[flag], stale_flags=[flag])
        output = format_flag_report(report)
        assert "Stale Flags" in output
        assert "FEATURE_OLD" in output

    def test_env_matrix_shown(self):
        flag = FeatureFlag(
            name="FEATURE_X", file=".env", line=1,
            env_values={"dev": "true", "prod": "false"},
        )
        report = FlagReport(
            total_flags=1, flags=[flag],
            env_matrix={"FEATURE_X": {"dev": "true", "prod": "false"}},
        )
        output = format_flag_report(report)
        assert "Environment Matrix" in output
        assert "dev" in output
        assert "prod" in output

    def test_references_count_shown(self):
        flag = FeatureFlag(
            name="FEATURE_X", file=".env", line=1,
            references=[{"file": "app.py"}, {"file": "utils.py"}],
        )
        report = FlagReport(total_flags=1, flags=[flag])
        output = format_flag_report(report)
        assert "Refs: 2" in output


# ---------------------------------------------------------------------------
# Tests — full scan integration
# ---------------------------------------------------------------------------

class TestFullScan:
    """Integration test for the full scan pipeline."""

    def test_scan_empty_dir(self, tmp_path):
        scanner = FeatureFlagScanner(cwd=str(tmp_path))
        report = scanner.scan()
        assert report.total_flags == 0
        assert report.flags == []
        assert report.stale_flags == []
        assert report.env_matrix == {}

    def test_scan_mixed_sources(self, tmp_path):
        """Repo with .env + Python code flags."""
        (tmp_path / ".env").write_text("FEATURE_A=true\nFEATURE_B=false\n")
        (tmp_path / "main.py").write_text('import os\nos.getenv("FEATURE_A")\n')
        scanner = FeatureFlagScanner(cwd=str(tmp_path))
        report = scanner.scan()
        assert report.total_flags >= 2
        names = {f.name for f in report.flags}
        assert "FEATURE_A" in names
        assert "FEATURE_B" in names
