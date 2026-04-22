"""Tests for Dependency Upgrade Pilot."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.domain.dep_upgrade import (
    DependencyUpgradePilot,
    UpgradeCandidate,
    UpgradeReport,
    UpgradeResult,
    format_upgrade_report,
)


class TestDependencyUpgradePilot:
    """Tests for DependencyUpgradePilot."""

    def test_init_defaults(self):
        pilot = DependencyUpgradePilot()
        assert pilot.dry_run is True

    def test_detect_poetry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "pyproject.toml")).write_text("[tool.poetry]\nname = 'test'")
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            assert pilot.package_manager == "poetry"

    def test_detect_npm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "package.json")).write_text('{"name": "test"}')
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            assert pilot.package_manager == "npm"

    def test_detect_pip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "requirements.txt")).write_text("flask==2.0.0")
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            assert pilot.package_manager == "pip"

    def test_detect_unknown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            assert pilot.package_manager == "unknown"

    def test_is_major_bump(self):
        pilot = DependencyUpgradePilot()
        assert pilot._is_major_bump("1.2.3", "2.0.0") is True
        assert pilot._is_major_bump("1.2.3", "1.3.0") is False
        assert pilot._is_major_bump("1.2.3", "1.2.4") is False

    @patch.object(DependencyUpgradePilot, "_run")
    def test_scan_poetry(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="requests  2.28.0   2.28.0   2.31.0\nflask     2.2.0    2.2.0    3.0.0",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "pyproject.toml")).write_text("[tool.poetry]\nname = 'test'")
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            candidates = pilot.scan()
            assert len(candidates) == 2
            assert candidates[0].name == "requests"

    @patch.object(DependencyUpgradePilot, "_run")
    def test_scan_npm(self, mock_run):
        data = {"lodash": {"current": "4.17.0", "latest": "4.17.21"}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "package.json")).write_text('{"name": "test"}')
            pilot = DependencyUpgradePilot(cwd=tmpdir)
            candidates = pilot.scan()
            assert len(candidates) == 1
            assert candidates[0].name == "lodash"

    def test_try_upgrade_dry_run(self):
        pilot = DependencyUpgradePilot(dry_run=True)
        candidate = UpgradeCandidate(
            name="requests", current_version="2.28.0",
            latest_version="2.31.0", source_file="pyproject.toml",
        )
        result = pilot._try_upgrade_one(candidate)
        assert result.status == "skipped"
        assert "Dry run" in result.test_output


class TestUpgradeReport:
    """Tests for UpgradeReport."""

    def test_properties(self):
        report = UpgradeReport(
            results=[
                UpgradeResult(candidate=UpgradeCandidate(name="a", current_version="1", latest_version="2", source_file="f"), status="success"),
                UpgradeResult(candidate=UpgradeCandidate(name="b", current_version="1", latest_version="2", source_file="f"), status="test_failed"),
                UpgradeResult(candidate=UpgradeCandidate(name="c", current_version="1", latest_version="2", source_file="f"), status="skipped"),
            ],
            candidates=[
                UpgradeCandidate(name="a", current_version="1", latest_version="2", source_file="f"),
                UpgradeCandidate(name="b", current_version="1", latest_version="2", source_file="f"),
                UpgradeCandidate(name="c", current_version="1", latest_version="2", source_file="f"),
            ],
        )
        assert report.total_outdated == 3
        assert report.upgraded == 1
        assert report.failed == 1
        assert report.skipped == 1


class TestFormatUpgradeReport:
    """Tests for format_upgrade_report."""

    def test_format_with_candidates(self):
        report = UpgradeReport(
            package_manager="poetry",
            candidates=[
                UpgradeCandidate(
                    name="requests", current_version="2.28.0",
                    latest_version="2.31.0", source_file="pyproject.toml",
                ),
            ],
        )
        output = format_upgrade_report(report)
        assert "requests" in output
        assert "poetry" in output
        assert "2.28.0" in output

    def test_format_empty(self):
        report = UpgradeReport(package_manager="pip")
        output = format_upgrade_report(report)
        assert "pip" in output
