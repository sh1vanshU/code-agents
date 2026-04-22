"""Tests for code_agents.secret_rotation — Secret Rotation Tracker."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.security.secret_rotation import (
    SecretRotationTracker,
    SecretRef,
    RotationReport,
    format_rotation_report,
    rotation_report_to_json,
)


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repo with config files."""
    (tmp_path / ".git").mkdir()

    (tmp_path / ".env").write_text(textwrap.dedent("""\
        DATABASE_URL=postgres://localhost/db
        API_KEY=sk-12345
        SECRET_KEY=mysecret
        DEBUG=true
        PORT=8000
    """))

    (tmp_path / ".env.example").write_text(textwrap.dedent("""\
        DATABASE_URL=
        API_KEY=
        SECRET_KEY=
        JWT_SECRET=
    """))

    (tmp_path / "config.yaml").write_text(textwrap.dedent("""\
        database:
          password: changeme
        redis:
          auth_token: redis-token
        app:
          name: myapp
    """))

    return tmp_path


class TestSecretRotationTracker:
    def test_finds_secrets(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        refs = tracker._find_secret_refs()
        key_names = [r.key_name for r in refs]
        assert any("API_KEY" in k for k in key_names)
        assert any("SECRET_KEY" in k for k in key_names)

    def test_finds_password_in_yaml(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        refs = tracker._find_secret_refs()
        key_names = [r.key_name for r in refs]
        assert any("password" in k.lower() for k in key_names)

    def test_scan_returns_report(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        with patch.object(tracker, "_check_age", return_value=100):
            report = tracker.scan(max_age=90)
        assert report.total > 0
        assert len(report.stale) > 0

    def test_scan_fresh_secrets(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        with patch.object(tracker, "_check_age", return_value=30):
            report = tracker.scan(max_age=90)
        assert len(report.fresh) > 0
        assert len(report.stale) == 0

    def test_scan_unknown_age(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        with patch.object(tracker, "_check_age", return_value=-1):
            report = tracker.scan(max_age=90)
        assert len(report.unknown) > 0

    @patch("subprocess.run")
    def test_check_age_git_failure(self, mock_run, tmp_repo):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        ref = SecretRef(file=".env", line=2, key_name="API_KEY")
        age = tracker._check_age(ref)
        assert age == -1

    def test_generate_runbook_empty(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        runbook = tracker._generate_runbook([])
        assert "No stale secrets" in runbook

    def test_generate_runbook_with_stale(self, tmp_repo):
        tracker = SecretRotationTracker(cwd=str(tmp_repo))
        stale = [SecretRef(file=".env", line=2, key_name="API_KEY", age_days=120)]
        runbook = tracker._generate_runbook(stale)
        assert "API_KEY" in runbook
        assert "rotation" in runbook.lower()


class TestFormatting:
    def test_format_report(self):
        report = RotationReport(
            secrets=[SecretRef(file=".env", line=1, key_name="KEY", age_days=100)],
            stale=[SecretRef(file=".env", line=1, key_name="KEY", age_days=100)],
            max_age_days=90,
        )
        text = format_rotation_report(report)
        assert "KEY" in text
        assert "100" in text
        assert "STALE" in text

    def test_json_export(self):
        report = RotationReport(
            secrets=[SecretRef(file=".env", line=1, key_name="KEY", age_days=50)],
            fresh=[SecretRef(file=".env", line=1, key_name="KEY", age_days=50)],
            max_age_days=90,
        )
        data = rotation_report_to_json(report)
        assert data["total"] == 1
        assert data["fresh_count"] == 1
        assert data["stale_count"] == 0


class TestEdgeCases:
    def test_no_config_files(self, tmp_path):
        tracker = SecretRotationTracker(cwd=str(tmp_path))
        report = tracker.scan()
        assert report.total == 0

    def test_not_git_repo(self, tmp_path):
        (tmp_path / ".env").write_text("API_KEY=test\n")
        tracker = SecretRotationTracker(cwd=str(tmp_path))
        report = tracker.scan()
        # Should still find refs but with unknown age
        assert report.total > 0
        assert len(report.unknown) == report.total
