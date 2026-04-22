"""Tests for code_agents.cli.cli_cicd.cmd_coverage — batch coverage CLI."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.cli.cli_cicd import cmd_coverage


@pytest.fixture
def _mock_colors():
    """Patch _colors to return identity functions."""
    identity = lambda x: x  # noqa: E731
    with patch(
        "code_agents.cli.cli_cicd._colors",
        return_value=(identity, identity, identity, identity, identity, identity),
    ):
        yield


@pytest.fixture
def fake_test_dir(tmp_path):
    """Create a fake project layout with test files."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_alpha.py").write_text("pass")
    (tests / "test_beta.py").write_text("pass")
    (tests / "test_gamma.py").write_text("pass")
    src = tmp_path / "code_agents"
    src.mkdir()
    (src / "__init__.py").write_text("")
    return tmp_path


class TestCmdCoverageDiscovery:
    def test_no_matching_files(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ):
            cmd_coverage(["nonexistent_xyz"])
        out = capsys.readouterr().out
        assert "No test files matching" in out

    def test_finds_test_files(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            cmd_coverage(["alpha"])
        out = capsys.readouterr().out
        assert "1 test file(s)" in out

    def test_pattern_filters_files(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            cmd_coverage(["beta"])
        out = capsys.readouterr().out
        assert "1 test file(s)" in out


class TestCmdCoverageExecution:
    def _make_cov_json(self, tmp_file, pct=85.0, stmts=100, miss=15):
        data = {
            "totals": {
                "percent_covered": pct,
                "num_statements": stmts,
                "missing_lines": miss,
            }
        }
        with open(tmp_file, "w") as f:
            json.dump(data, f)

    def test_successful_run_shows_summary(self, _mock_colors, fake_test_dir, capsys):
        def fake_run(cmd, **kw):
            # Write coverage JSON to the tmp file specified in the command
            for i, arg in enumerate(cmd):
                if isinstance(arg, str) and arg.startswith("json:"):
                    self._make_cov_json(arg[5:], pct=92.3, stmts=200, miss=15)
            return MagicMock(returncode=0)

        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run", side_effect=fake_run):
            cmd_coverage([])

        out = capsys.readouterr().out
        assert "Coverage Summary" in out
        assert "92.3%" in out

    def test_timeout_handled(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch(
            "code_agents.cli.cli_cicd.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=120),
        ):
            cmd_coverage(["alpha"])

        out = capsys.readouterr().out
        assert "TIMEOUT" in out

    def test_exception_handled(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch(
            "code_agents.cli.cli_cicd.subprocess.run",
            side_effect=OSError("disk error"),
        ):
            cmd_coverage(["alpha"])

        out = capsys.readouterr().out
        assert "ERROR" in out

    def test_no_results_message(self, _mock_colors, fake_test_dir, capsys):
        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            cmd_coverage(["alpha"])

        out = capsys.readouterr().out
        assert "No coverage data" in out or "FAIL" in out


class TestCmdCoverageArgs:
    def test_top_flag(self, _mock_colors, fake_test_dir, capsys):
        def fake_run(cmd, **kw):
            for arg in cmd:
                if isinstance(arg, str) and arg.startswith("json:"):
                    data = {"totals": {"percent_covered": 50.0, "num_statements": 10, "missing_lines": 5}}
                    with open(arg[5:], "w") as f:
                        json.dump(data, f)
            return MagicMock(returncode=0)

        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run", side_effect=fake_run):
            cmd_coverage(["--top", "1"])

        out = capsys.readouterr().out
        assert "... and" in out  # only 1 shown, rest truncated


class TestCmdCoverageCleanup:
    def test_temp_files_cleaned_up(self, _mock_colors, fake_test_dir):
        tmp_files = []

        original_named = __import__("tempfile").NamedTemporaryFile

        def tracking_tmp(**kw):
            f = original_named(**kw)
            tmp_files.append(f.name)
            return f

        with patch(
            "code_agents.cli.cli_cicd._find_code_agents_home",
            return_value=fake_test_dir,
        ), patch("code_agents.cli.cli_cicd.subprocess.run") as mock_run, \
             patch("code_agents.cli.cli_cicd.tempfile.NamedTemporaryFile", side_effect=tracking_tmp):
            mock_run.return_value = MagicMock(returncode=0)
            cmd_coverage(["alpha"])

        for tf in tmp_files:
            assert not os.path.exists(tf), f"Temp file not cleaned up: {tf}"
