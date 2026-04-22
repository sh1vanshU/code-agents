"""Tests for cli_reports.py — standup, perf-baseline commands."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# cmd_standup (lines 43-56, 67-70, 107-108)
# ---------------------------------------------------------------------------


class TestCmdStandup:
    """Test cmd_standup Jira and build status paths."""

    def _mock_colors(self):
        return tuple(lambda x: x for _ in range(6))

    def test_standup_jira_configured_success(self, tmp_path, capsys):
        """When Jira is configured and returns issues (lines 43-52)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Fix login page"}},
                {"key": "PROJ-2", "fields": {"summary": "Add tests"}},
            ]
        }

        mock_git = MagicMock()
        mock_git.stdout = "abc1234 fix: something\ndef5678 feat: another"

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "JIRA_URL": "http://jira.example.com",
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", return_value=mock_git), \
             patch("httpx.get", return_value=mock_resp):
            cmd_standup()

        out = capsys.readouterr().out
        assert "PROJ-1" in out
        assert "Fix login page" in out

    def test_standup_jira_configured_no_issues(self, tmp_path, capsys):
        """When Jira returns empty issues list (lines 53-54)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"issues": []}

        mock_git = MagicMock()
        mock_git.stdout = "abc fix: something"

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "JIRA_URL": "http://jira.example.com",
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", return_value=mock_git), \
             patch("httpx.get", return_value=mock_resp):
            cmd_standup()

        out = capsys.readouterr().out
        assert "No tickets" in out

    def test_standup_jira_configured_exception(self, tmp_path, capsys):
        """When Jira request fails (lines 55-56)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_git = MagicMock()
        mock_git.stdout = "abc fix: something"

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "JIRA_URL": "http://jira.example.com",
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", return_value=mock_git), \
             patch("httpx.get", side_effect=Exception("connection refused")):
            cmd_standup()

        out = capsys.readouterr().out
        assert "not reachable" in out

    def test_standup_build_status_healthy(self, tmp_path, capsys):
        """When server is healthy (lines 67-68)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_git = MagicMock()
        mock_git.stdout = "abc fix: something"

        mock_health = MagicMock()
        mock_health.status_code = 200

        def httpx_get_side_effect(url, **kwargs):
            if "/health" in url:
                return mock_health
            raise Exception("not jira")

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", return_value=mock_git), \
             patch("httpx.get", side_effect=httpx_get_side_effect):
            cmd_standup()

        out = capsys.readouterr().out
        assert "running" in out

    def test_standup_build_status_unhealthy(self, tmp_path, capsys):
        """When server is unhealthy (line 70)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_git = MagicMock()
        mock_git.stdout = "abc fix: something"

        mock_health = MagicMock()
        mock_health.status_code = 500

        def httpx_get_side_effect(url, **kwargs):
            if "/health" in url:
                return mock_health
            raise Exception("not jira")

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", return_value=mock_git), \
             patch("httpx.get", side_effect=httpx_get_side_effect):
            cmd_standup()

        out = capsys.readouterr().out
        assert "unhealthy" in out

    def test_standup_clipboard_copy_fails(self, tmp_path, capsys):
        """When pbcopy fails (lines 107-108)."""
        from code_agents.cli.cli_reports import cmd_standup

        mock_git = MagicMock()
        mock_git.stdout = "abc fix: something"

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "pbcopy":
                raise Exception("not available")
            return mock_git

        with patch("code_agents.cli.cli_reports._colors", return_value=self._mock_colors()), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_USER_CWD": str(tmp_path),
                 "CODE_AGENTS_NICKNAME": "user",
             }), \
             patch("subprocess.run", side_effect=run_side_effect), \
             patch("httpx.get", side_effect=Exception("no server")):
            cmd_standup()

        # Should not crash
        out = capsys.readouterr().out
        assert "Standup" in out


# ---------------------------------------------------------------------------
# cmd_perf_baseline iterations parse (lines 471-472)
# ---------------------------------------------------------------------------


class TestCmdPerfBaseline:
    def test_perf_baseline_iterations_parse(self, capsys):
        """--iterations flag with invalid value uses default (lines 470-472)."""
        from code_agents.cli.cli_reports import cmd_perf_baseline

        with patch("code_agents.cli.cli_reports._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_reports._find_code_agents_home", return_value=MagicMock()), \
             patch("code_agents.observability.performance.PerformanceProfiler") as mock_prof:
            mock_profiler = MagicMock()
            mock_profiler.discover_endpoints.return_value = []
            mock_prof.return_value = mock_profiler
            cmd_perf_baseline(["--iterations", "notanumber"])

        out = capsys.readouterr().out
        assert "No endpoints" in out
