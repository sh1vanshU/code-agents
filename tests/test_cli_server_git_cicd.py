"""Tests for CLI server, git, and CI/CD modules — cli_server.py, cli_git.py, cli_cicd.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(*a, **kw):
    return a[0] if a else ""

def _make_colors():
    """Return 6 identity functions mimicking _colors()."""
    fn = lambda x="": x
    return fn, fn, fn, fn, fn, fn


# ---------------------------------------------------------------------------
# cli_server.py
# ---------------------------------------------------------------------------

class TestCmdStatus:
    """cmd_status — server health & config display."""

    @patch("code_agents.cli.cli_server._api_get")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_status_server_running(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_status

        mock_api.side_effect = [
            {"status": "ok"},  # /health
            {  # /diagnostics
                "package_version": "1.0.0",
                "agents": [{"name": "a1"}, {"name": "a2"}],
                "jenkins_configured": True,
                "argocd_configured": False,
                "elasticsearch_configured": True,
                "pipeline_enabled": True,
            },
        ]
        with patch.dict(os.environ, {"TARGET_REPO_PATH": "/tmp/repo"}):
            cmd_status()
        out = capsys.readouterr().out
        assert "Server is running" in out
        assert "1.0.0" in out
        assert "2" in out  # agent count

    @patch("code_agents.cli.cli_server._api_get", return_value=None)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_status_server_not_running(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_status
        cmd_status()
        out = capsys.readouterr().out
        assert "not running" in out

    @patch("code_agents.cli.cli_server._api_get")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_status_diagnostics_none(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_status
        mock_api.side_effect = [{"status": "ok"}, None]
        with patch.dict(os.environ, {"TARGET_REPO_PATH": "/tmp/repo"}):
            cmd_status()
        out = capsys.readouterr().out
        assert "Server is running" in out


class TestCmdAgents:
    """cmd_agents — list agents from server or YAML fallback."""

    @patch("code_agents.cli.cli_server._api_get")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_agents_from_server_data_format(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_api.return_value = {
            "data": [
                {"name": "code-reasoning", "display_name": "Reasoning", "endpoint": "/v1/agents/code-reasoning/chat/completions"},
                {"name": "code-writer", "display_name": "Writer"},
            ]
        }
        cmd_agents()
        out = capsys.readouterr().out
        assert "code-reasoning" in out
        assert "code-writer" in out
        assert "Total: 2" in out

    @patch("code_agents.cli.cli_server._api_get")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_agents_from_server_list_format(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_api.return_value = [{"name": "git-ops", "display_name": "Git Ops"}]
        cmd_agents()
        out = capsys.readouterr().out
        assert "git-ops" in out
        assert "Total: 1" in out

    @patch("code_agents.cli.cli_server._api_get", return_value=None)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_agents_fallback_yaml(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_loader = MagicMock()
        agent_obj = MagicMock()
        agent_obj.name = "test-agent"
        agent_obj.display_name = "Test"
        agent_obj.backend = "cursor"
        agent_obj.model = "gpt-4"
        agent_obj.permission_mode = "auto"
        mock_loader.list_agents.return_value = [agent_obj]
        with patch("code_agents.core.config.agent_loader", mock_loader):
            cmd_agents()
        out = capsys.readouterr().out
        assert "test-agent" in out

    @patch("code_agents.cli.cli_server._api_get", return_value=None)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_agents_fallback_error(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_agents
        with patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.side_effect = Exception("broken")
            cmd_agents()
        out = capsys.readouterr().out
        assert "Error" in out

    @patch("code_agents.cli.cli_server._api_get")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_agents_empty_dict(self, mock_colors, mock_load, mock_api, capsys):
        from code_agents.cli.cli_server import cmd_agents
        mock_api.return_value = {"unexpected": "format"}
        cmd_agents()
        out = capsys.readouterr().out
        assert "Total: 0" in out


class TestCmdLogs:
    """cmd_logs — tail the log file."""

    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    @patch("code_agents.cli.cli_server._find_code_agents_home")
    def test_logs_no_file(self, mock_home, mock_colors, capsys):
        from code_agents.cli.cli_server import cmd_logs
        mock_home.return_value = Path("/nonexistent/path")
        cmd_logs([])
        out = capsys.readouterr().out
        assert "No log file" in out

    @patch("os.execvp")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    @patch("code_agents.cli.cli_server._find_code_agents_home")
    def test_logs_default_lines(self, mock_home, mock_colors, mock_exec, capsys, tmp_path):
        from code_agents.cli.cli_server import cmd_logs
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "code-agents.log").write_text("line1\n")
        mock_home.return_value = tmp_path
        cmd_logs([])
        mock_exec.assert_called_once_with("tail", ["tail", "-f", "-n", "50", str(log_dir / "code-agents.log")])

    @patch("os.execvp")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    @patch("code_agents.cli.cli_server._find_code_agents_home")
    def test_logs_custom_lines(self, mock_home, mock_colors, mock_exec, capsys, tmp_path):
        from code_agents.cli.cli_server import cmd_logs
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "code-agents.log").write_text("line1\n")
        mock_home.return_value = tmp_path
        cmd_logs(["100"])
        mock_exec.assert_called_once_with("tail", ["tail", "-f", "-n", "100", str(log_dir / "code-agents.log")])


class TestCmdConfig:
    """cmd_config — show configuration."""

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_config_no_env_file(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_config
        with patch("os.path.exists", return_value=False):
            cmd_config()
        out = capsys.readouterr().out
        assert "not found" in out
        assert "code-agents init" in out

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_config_with_env_file(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_config
        mock_parse = MagicMock(return_value={
            "CURSOR_API_KEY": "sk-1234567890abcdef",
            "HOST": "0.0.0.0",
            "PORT": "8000",
            "TARGET_REPO_PATH": "/tmp/repo",
        })
        with patch("os.path.exists", return_value=True), \
             patch("code_agents.cli.cli_server.parse_env_file", mock_parse, create=True), \
             patch("code_agents.setup.setup_env.parse_env_file", mock_parse):
            cmd_config()
        out = capsys.readouterr().out
        assert "found" in out
        # Secret should be masked
        assert "sk-1" in out or "••••" in out


class TestCmdShutdown:
    """cmd_shutdown — kill server process."""

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_shutdown_no_server(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        out = capsys.readouterr().out
        assert "No server running" in out

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_shutdown_kills_pids(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        first_result = MagicMock()
        first_result.stdout = "12345\n"
        second_result = MagicMock()
        second_result.stdout = ""
        with patch("subprocess.run", side_effect=[first_result, second_result]), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep"), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        mock_kill.assert_called_once_with(12345, 15)
        out = capsys.readouterr().out
        assert "stopped" in out

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_shutdown_force_kill(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        first_result = MagicMock()
        first_result.stdout = "12345\n"
        # After SIGTERM, process still running
        second_result = MagicMock()
        second_result.stdout = "12345\n"
        with patch("subprocess.run", side_effect=[first_result, second_result]), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep"), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        # SIGTERM then SIGKILL
        assert mock_kill.call_count == 2
        mock_kill.assert_any_call(12345, 15)
        mock_kill.assert_any_call(12345, 9)
        out = capsys.readouterr().out
        assert "force-stopped" in out

    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_shutdown_exception(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        with patch("subprocess.run", side_effect=Exception("oops")), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        out = capsys.readouterr().out
        assert "Could not find" in out


class TestCmdRestart:
    """cmd_restart — shutdown + start."""

    @patch("code_agents.cli.cli_server._start_background")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_restart_no_running_server(self, mock_colors, mock_cwd, mock_load, mock_start, capsys):
        from code_agents.cli.cli_server import cmd_restart
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_restart()
        mock_start.assert_called_once_with("/tmp/repo")

    @patch("code_agents.cli.cli_server._start_background")
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_restart_with_running_server(self, mock_colors, mock_cwd, mock_load, mock_start, capsys):
        from code_agents.cli.cli_server import cmd_restart
        first = MagicMock(stdout="999\n")
        second = MagicMock(stdout="")
        with patch("subprocess.run", side_effect=[first, second]), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep"), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_restart()
        mock_kill.assert_called_once_with(999, 15)
        mock_start.assert_called_once_with("/tmp/repo")


class TestCmdStart:
    """cmd_start — start server."""

    @patch("code_agents.cli.cli_server._start_background")
    @patch("code_agents.cli.cli_server._check_workspace_trust", return_value=True)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    def test_start_background(self, mock_cwd, mock_load, mock_trust, mock_bg):
        from code_agents.cli.cli_server import cmd_start
        with patch.object(sys, "argv", ["code-agents", "start"]):
            cmd_start()
        mock_bg.assert_called_once_with("/tmp/repo")

    @patch("code_agents.cli.cli_server._check_workspace_trust", return_value=False)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    def test_start_untrusted(self, mock_cwd, mock_load, mock_trust):
        from code_agents.cli.cli_server import cmd_start
        with patch.object(sys, "argv", ["code-agents", "start"]):
            cmd_start()  # should return without starting

    @patch("code_agents.cli.cli_server._start_background")
    @patch("code_agents.cli.cli_server._check_workspace_trust", return_value=True)
    @patch("code_agents.cli.cli_server._load_env")
    @patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_start_foreground(self, mock_colors, mock_cwd, mock_load, mock_trust, mock_bg):
        from code_agents.cli.cli_server import cmd_start
        with patch.object(sys, "argv", ["code-agents", "start", "--fg"]), \
             patch("code_agents.core.main.main") as mock_main:
            cmd_start()
        mock_main.assert_called_once()
        mock_bg.assert_not_called()


class TestStartBackground:
    """_start_background — background server launch with health check."""

    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_start_background_healthy(self, mock_colors, capsys):
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.pid = 42

        mock_response = MagicMock()
        mock_response.status_code = 200

        env_vars = {
            "HOST": "0.0.0.0", "PORT": "8000",
            "CODE_AGENTS_BACKEND": "cursor", "CURSOR_API_KEY": "sk-12345678abcd",
            "CODE_AGENTS_MODEL": "gpt-4",
        }

        with patch("code_agents.core.env_loader.load_all_env"), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_response), \
             patch("subprocess.run") as mock_subrun, \
             patch.dict(os.environ, env_vars, clear=False), \
             patch("os.path.isdir", return_value=True), \
             patch("os.path.isfile", return_value=False):
            mock_subrun.return_value = MagicMock(stdout="main\n")
            _start_background("/tmp/repo")

        out = capsys.readouterr().out
        assert "running" in out.lower() or "Code Agents" in out
        assert "42" in out  # PID

    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_start_background_fails(self, mock_colors, capsys):
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited

        with patch("code_agents.core.env_loader.load_all_env"), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}):
            _start_background("/tmp/repo")

        out = capsys.readouterr().out
        assert "failed to start" in out.lower()

    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_start_background_unhealthy(self, mock_colors, capsys):
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 99

        env_vars = {
            "HOST": "0.0.0.0", "PORT": "8000",
            "CODE_AGENTS_BACKEND": "claude-cli",
            "CODE_AGENTS_MODEL": "sonnet",
        }

        with patch("code_agents.core.env_loader.load_all_env"), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", side_effect=Exception("connection refused")), \
             patch("shutil.which", return_value="/usr/local/bin/claude"), \
             patch("subprocess.run") as mock_subrun, \
             patch.dict(os.environ, env_vars, clear=False), \
             patch("os.path.isdir", return_value=False), \
             patch("os.path.isfile", return_value=False):
            mock_subrun.return_value = MagicMock(stdout="main\n")
            _start_background("/tmp/repo")

        out = capsys.readouterr().out
        assert "starting up" in out.lower() or "starting" in out.lower()

    @patch("code_agents.cli.cli_server._colors", return_value=_make_colors())
    def test_start_background_integrations(self, mock_colors, capsys):
        """Test integration detection in health check."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 50

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_diag_response = MagicMock()
        mock_diag_response.json.return_value = {"agents": [1, 2, 3]}

        env_vars = {
            "HOST": "0.0.0.0", "PORT": "8000",
            "CODE_AGENTS_BACKEND": "claude", "ANTHROPIC_API_KEY": "sk-ant-12345678",
            "JENKINS_URL": "https://jenkins.example.com",
            "ARGOCD_URL": "https://argocd.example.com",
            "JIRA_URL": "https://jira.example.com",
            "CODE_AGENTS_MODEL": "sonnet",
        }

        def mock_httpx_get(url, **kw):
            if "diagnostics" in url:
                return mock_diag_response
            return mock_response

        with patch("code_agents.core.env_loader.load_all_env"), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", side_effect=mock_httpx_get), \
             patch("subprocess.run") as mock_subrun, \
             patch.dict(os.environ, env_vars, clear=False), \
             patch("os.path.isdir", return_value=True), \
             patch("os.path.isfile", return_value=False):
            mock_subrun.return_value = MagicMock(stdout="develop\n")
            _start_background("/tmp/repo")

        out = capsys.readouterr().out
        assert "Jenkins" in out
        assert "ArgoCD" in out
        assert "Jira" in out


# ---------------------------------------------------------------------------
# cli_git.py
# ---------------------------------------------------------------------------

class TestCmdDiff:
    """cmd_diff — show git diff."""

    @patch("code_agents.cli.cli_git._api_get")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_diff_from_server(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_api.return_value = {
            "files_changed": 3,
            "insertions": 50,
            "deletions": 10,
            "changed_files": [
                {"file": "a.py", "insertions": 30, "deletions": 5},
                {"file": "b.py", "insertions": 20, "deletions": 5},
            ],
        }
        cmd_diff(["develop", "HEAD"])
        out = capsys.readouterr().out
        assert "develop" in out
        assert "HEAD" in out
        assert "3" in out
        assert "a.py" in out

    @patch("code_agents.cli.cli_git._api_get")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_diff_default_args(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_api.return_value = {"files_changed": 0, "insertions": 0, "deletions": 0, "changed_files": []}
        cmd_diff([])
        # Should default to main HEAD
        call_args = mock_api.call_args[0][0]
        assert "base=main" in call_args
        assert "head=HEAD" in call_args

    @patch("code_agents.cli.cli_git._api_get", return_value=None)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_diff_fallback_git_client(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_client = MagicMock()

        async def mock_diff(*a, **kw):
            return {"files_changed": 1, "insertions": 5, "deletions": 2, "changed_files": []}

        mock_client.diff = mock_diff
        with patch("code_agents.cicd.git_client.GitClient", return_value=mock_client):
            cmd_diff(["main", "HEAD"])
        out = capsys.readouterr().out
        assert "1" in out  # files changed

    @patch("code_agents.cli.cli_git._api_get", return_value=None)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_diff_fallback_error(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_client = MagicMock()

        async def mock_diff(*a, **kw):
            raise RuntimeError("git not found")

        mock_client.diff = mock_diff
        with patch("code_agents.cicd.git_client.GitClient", return_value=mock_client):
            cmd_diff(["main", "HEAD"])
        out = capsys.readouterr().out
        assert "Error" in out


class TestCmdBranches:
    """cmd_branches — list git branches."""

    @patch("code_agents.cli.cli_git._api_get")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_branches_from_server(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_branches
        mock_api.side_effect = [
            {"branches": [{"name": "main"}, {"name": "develop"}, {"name": "feature/x"}]},
            {"branch": "main"},
        ]
        cmd_branches()
        out = capsys.readouterr().out
        assert "main" in out
        assert "develop" in out
        assert "current" in out

    @patch("code_agents.cli.cli_git._api_get", return_value=None)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_branches_fallback(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_branches
        mock_client = MagicMock()

        async def mock_list_branches():
            return [{"name": "main"}, {"name": "dev"}]

        async def mock_current():
            return "main"

        mock_client.list_branches = mock_list_branches
        mock_client.current_branch = mock_current
        with patch("code_agents.cicd.git_client.GitClient", return_value=mock_client):
            cmd_branches()
        out = capsys.readouterr().out
        assert "main" in out

    @patch("code_agents.cli.cli_git._api_get", return_value=None)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_branches_fallback_error(self, mock_colors, mock_cwd, mock_load, mock_api, capsys):
        from code_agents.cli.cli_git import cmd_branches
        mock_client = MagicMock()

        async def mock_list_branches():
            raise Exception("fail")

        mock_client.list_branches = mock_list_branches
        with patch("code_agents.cicd.git_client.GitClient", return_value=mock_client):
            cmd_branches()
        out = capsys.readouterr().out
        assert "Error" in out


class TestCmdReview:
    """cmd_review — AI code review."""

    @patch("code_agents.cli.cli_git._api_post")
    @patch("code_agents.cli.cli_git._api_get")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_review_success(self, mock_colors, mock_cwd, mock_load, mock_get, mock_post, capsys):
        from code_agents.cli.cli_git import cmd_review
        mock_get.return_value = {
            "files_changed": 2, "insertions": 10, "deletions": 5, "diff": "some diff",
        }
        mock_post.return_value = {
            "choices": [{"message": {"content": "Looks good, minor issue in line 5."}}]
        }
        cmd_review(["main", "HEAD"])
        out = capsys.readouterr().out
        assert "Reviewing" in out
        assert "minor issue" in out

    @patch("code_agents.cli.cli_git._api_post", return_value=None)
    @patch("code_agents.cli.cli_git._api_get", return_value=None)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_review_no_server(self, mock_colors, mock_cwd, mock_load, mock_get, mock_post, capsys):
        from code_agents.cli.cli_git import cmd_review
        cmd_review([])
        out = capsys.readouterr().out
        assert "Could not reach" in out

    @patch("code_agents.cli.cli_git._api_post")
    @patch("code_agents.cli.cli_git._api_get")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_review_default_args(self, mock_colors, mock_cwd, mock_load, mock_get, mock_post, capsys):
        from code_agents.cli.cli_git import cmd_review
        mock_get.return_value = {"files_changed": 0, "diff": ""}
        mock_post.return_value = {"choices": [{"message": {"content": "No changes."}}]}
        cmd_review([])
        out = capsys.readouterr().out
        assert "main" in out
        assert "HEAD" in out


class TestCmdCommit:
    """cmd_commit — smart conventional commit."""

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_error(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {"error": "No staged changes"}
        with patch.object(sys, "argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "No staged changes" in out

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_dry_run(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "feat", "scope": "cli", "files": ["a.py"],
            "ticket": "PROJ-123", "full_message": "feat(cli): add feature\n\nPROJ-123",
        }
        with patch.object(sys, "argv", ["code-agents", "commit", "--dry-run"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "dry run" in out
        assert "feat" in out

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_auto_success(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "fix", "scope": "", "files": ["b.py"],
            "full_message": "fix: resolve bug",
        }
        mock_sc.commit.return_value = True
        with patch.object(sys, "argv", ["code-agents", "commit", "--auto"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "Committed" in out

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_auto_failure(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "fix", "scope": "", "files": ["b.py"],
            "full_message": "fix: resolve bug",
        }
        mock_sc.commit.return_value = False
        with patch.object(sys, "argv", ["code-agents", "commit", "--auto"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "failed" in out.lower()

    @patch("builtins.input", return_value="y")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_interactive_yes(self, mock_colors, mock_cwd, mock_load, mock_input, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "feat", "scope": "", "files": ["c.py"],
            "full_message": "feat: new feature",
        }
        mock_sc.commit.return_value = True
        with patch.object(sys, "argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "Committed" in out

    @patch("builtins.input", return_value="n")
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_interactive_cancel(self, mock_colors, mock_cwd, mock_load, mock_input, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "feat", "scope": "", "files": ["c.py"],
            "full_message": "feat: new feature",
        }
        with patch.object(sys, "argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "Cancelled" in out

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_commit_interactive_interrupt(self, mock_colors, mock_cwd, mock_load, mock_input, capsys):
        from code_agents.cli.cli_git import cmd_commit
        mock_sc = MagicMock()
        mock_sc.generate_message.return_value = {
            "type": "feat", "scope": "", "files": ["c.py"],
            "full_message": "feat: new feature",
        }
        with patch.object(sys, "argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit", return_value=mock_sc):
            cmd_commit()
        out = capsys.readouterr().out
        assert "Cancelled" in out


class TestCmdPrPreview:
    """cmd_pr_preview — preview PR."""

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_pr_preview_no_commits(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_pr_preview
        mock_preview = MagicMock()
        mock_preview.get_commits.return_value = []
        with patch("code_agents.tools.pr_preview.PRPreview", return_value=mock_preview):
            cmd_pr_preview([])
        out = capsys.readouterr().out
        assert "No commits" in out

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_pr_preview_with_commits(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_pr_preview
        mock_preview = MagicMock()
        mock_preview.get_commits.return_value = ["abc123 feat: something"]
        mock_preview.format_preview.return_value = "## PR Preview\nChanges..."
        with patch("code_agents.tools.pr_preview.PRPreview", return_value=mock_preview):
            cmd_pr_preview(["develop"])
        out = capsys.readouterr().out
        assert "PR Preview" in out

    @patch("code_agents.cli.cli_git._load_env")
    @patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_pr_preview_none_args(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_git import cmd_pr_preview
        mock_preview = MagicMock()
        mock_preview.get_commits.return_value = ["abc"]
        mock_preview.format_preview.return_value = "output"
        with patch("code_agents.tools.pr_preview.PRPreview", return_value=mock_preview) as MockPR:
            cmd_pr_preview(None)
        # base defaults to "main"
        MockPR.assert_called_once_with(cwd="/tmp/repo", base="main")


class TestCmdAutoReview:
    """cmd_auto_review — automated code review."""

    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_auto_review_default(self, mock_colors, capsys):
        from code_agents.cli.cli_git import cmd_auto_review
        mock_ra = MagicMock()
        mock_ra.run.return_value = {"status": "ok"}
        with patch("code_agents.reviews.review_autopilot.ReviewAutopilot", return_value=mock_ra) as MockRA, \
             patch("code_agents.reviews.review_autopilot.format_review", return_value="Review output") as mock_fmt, \
             patch.dict(os.environ, {}, clear=False):
            cmd_auto_review()
        MockRA.assert_called_once()
        assert MockRA.call_args.kwargs["base"] == "main"

    @patch("code_agents.cli.cli_git._colors", return_value=_make_colors())
    def test_auto_review_custom_args(self, mock_colors, capsys):
        from code_agents.cli.cli_git import cmd_auto_review
        mock_ra = MagicMock()
        mock_ra.run.return_value = {}
        with patch("code_agents.reviews.review_autopilot.ReviewAutopilot", return_value=mock_ra) as MockRA, \
             patch("code_agents.reviews.review_autopilot.format_review", return_value="output"), \
             patch.dict(os.environ, {}, clear=False):
            cmd_auto_review(["develop", "feature/x"])
        assert MockRA.call_args.kwargs["base"] == "develop"
        assert MockRA.call_args.kwargs["head"] == "feature/x"


# ---------------------------------------------------------------------------
# cli_cicd.py
# ---------------------------------------------------------------------------

class TestCmdTest:
    """cmd_test — run tests."""

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_test_passed(self, mock_colors, mock_cwd, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_post.return_value = {
            "passed": True, "total": 100, "passed_count": 98,
            "failed_count": 2, "error_count": 0, "test_command": "pytest",
        }
        cmd_test([])
        out = capsys.readouterr().out
        assert "PASSED" in out
        assert "98" in out

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_test_failed_with_output(self, mock_colors, mock_cwd, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_post.return_value = {
            "passed": False, "total": 10, "passed_count": 5,
            "failed_count": 5, "error_count": 0, "test_command": "pytest",
            "output": "FAILED test_foo.py::test_bar\nAssertionError\n" * 5,
        }
        cmd_test(["main"])
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "AssertionError" in out

    @patch("code_agents.cli.cli_cicd._api_post", return_value=None)
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_test_fallback(self, mock_colors, mock_cwd, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_client = MagicMock()

        async def mock_run_tests(**kw):
            return {"passed": True, "total": 5, "passed_count": 5, "failed_count": 0, "error_count": 0, "test_command": "pytest"}

        mock_client.run_tests = mock_run_tests
        with patch("code_agents.cicd.testing_client.TestingClient", return_value=mock_client):
            cmd_test([])
        out = capsys.readouterr().out
        assert "PASSED" in out

    @patch("code_agents.cli.cli_cicd._api_post", return_value=None)
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_test_fallback_error(self, mock_colors, mock_cwd, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_test
        mock_client = MagicMock()

        async def mock_run_tests(**kw):
            raise RuntimeError("no test runner")

        mock_client.run_tests = mock_run_tests
        with patch("code_agents.cicd.testing_client.TestingClient", return_value=mock_client):
            cmd_test([])
        out = capsys.readouterr().out
        assert "Error" in out


class TestCmdPipeline:
    """cmd_pipeline — CI/CD pipeline management."""

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_start_with_branch(self, mock_colors, mock_load, mock_get, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_post.return_value = {"run_id": "abc-123", "current_step_name": "test"}
        cmd_pipeline(["start", "feature/x"])
        out = capsys.readouterr().out
        assert "Pipeline started" in out
        assert "abc-123" in out

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_start_auto_branch(self, mock_colors, mock_load, mock_get, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = {"branch": "develop"}
        mock_post.return_value = {"run_id": "xyz", "current_step_name": "build"}
        cmd_pipeline(["start"])
        out = capsys.readouterr().out
        assert "develop" in out

    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_status_by_id(self, mock_colors, mock_load, mock_get, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = {
            "run_id": "abc", "branch": "main", "current_step": 3,
            "current_step_name": "deploy", "steps": {},
        }
        cmd_pipeline(["status", "abc"])
        out = capsys.readouterr().out
        assert "abc" in out

    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_status_not_found(self, mock_colors, mock_load, mock_get, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = None
        cmd_pipeline(["status", "nonexistent"])
        out = capsys.readouterr().out
        assert "not found" in out

    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_status_list_runs(self, mock_colors, mock_load, mock_get, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = {
            "runs": [
                {"run_id": "r1", "branch": "main", "current_step": 1, "current_step_name": "test", "steps": {}},
            ],
        }
        cmd_pipeline(["status"])
        out = capsys.readouterr().out
        assert "r1" in out

    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_status_no_runs(self, mock_colors, mock_load, mock_get, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = {"runs": []}
        cmd_pipeline(["status"])
        out = capsys.readouterr().out
        assert "No pipeline runs" in out

    @patch("code_agents.cli.cli_cicd._api_get")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_default_status(self, mock_colors, mock_load, mock_get, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_get.return_value = {"runs": []}
        cmd_pipeline([])  # defaults to "status"
        out = capsys.readouterr().out
        assert "No pipeline runs" in out

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_advance(self, mock_colors, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_post.return_value = {"current_step": 4, "current_step_name": "deploy"}
        cmd_pipeline(["advance", "abc"])
        out = capsys.readouterr().out
        assert "Advanced" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_advance_no_id(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        cmd_pipeline(["advance"])
        out = capsys.readouterr().out
        assert "Usage" in out

    @patch("code_agents.cli.cli_cicd._api_post")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_rollback(self, mock_colors, mock_load, mock_post, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        mock_post.return_value = {
            "rollback_info": {"instruction": "Reverted to v7.0.0"},
        }
        cmd_pipeline(["rollback", "abc"])
        out = capsys.readouterr().out
        assert "Rollback" in out
        assert "Reverted" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_rollback_no_id(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        cmd_pipeline(["rollback"])
        out = capsys.readouterr().out
        assert "Usage" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_pipeline_unknown_command(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_pipeline
        cmd_pipeline(["foobar"])
        out = capsys.readouterr().out
        assert "Unknown" in out


class TestPrintPipelineStatus:
    """_print_pipeline_status — pretty-print helper."""

    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_print_status_full(self, mock_colors, capsys):
        from code_agents.cli.cli_cicd import _print_pipeline_status
        data = {
            "run_id": "run-1",
            "branch": "main",
            "current_step": 3,
            "current_step_name": "deploy",
            "build_number": 42,
            "error": "timeout",
            "steps": {
                "1": {"status": "success", "name": "test"},
                "2": {"status": "success", "name": "build"},
                "3": {"status": "in_progress", "name": "deploy"},
                "4": {"status": "pending", "name": "sanity"},
                "5": {"status": "skipped", "name": "jira"},
                "6": {"status": "pending", "name": "notify"},
            },
        }
        _print_pipeline_status(data)
        out = capsys.readouterr().out
        assert "run-1" in out
        assert "#42" in out
        assert "timeout" in out
        assert "test" in out
        assert "deploy" in out

    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_print_status_minimal(self, mock_colors, capsys):
        from code_agents.cli.cli_cicd import _print_pipeline_status
        data = {"run_id": "r2", "branch": "dev", "current_step": 1, "current_step_name": "test", "steps": {}}
        _print_pipeline_status(data)
        out = capsys.readouterr().out
        assert "r2" in out


class TestCmdRelease:
    """cmd_release — release automation."""

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_no_args(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        cmd_release([])
        out = capsys.readouterr().out
        assert "Usage" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_flag_only(self, mock_colors, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        cmd_release(["--dry-run"])
        out = capsys.readouterr().out
        assert "Usage" in out

    @patch("code_agents.cli.cli_cicd.prompt_yes_no", return_value=False)
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_cancelled(self, mock_colors, mock_cwd, mock_load, mock_prompt, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "1.0.0"
        mock_mgr.branch_name = "release/1.0.0"
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["1.0.0"])
        out = capsys.readouterr().out
        assert "Cancelled" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_dry_run_success(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "2.0.0"
        mock_mgr.branch_name = "release/2.0.0"
        mock_mgr.steps_completed = []
        mock_mgr.errors = []
        # All steps return True
        mock_mgr.create_branch.return_value = True
        mock_mgr.run_tests.return_value = True
        mock_mgr.generate_changelog.return_value = True
        mock_mgr.bump_version.return_value = True
        mock_mgr.commit_changes.return_value = True
        mock_mgr.push_branch.return_value = True
        mock_mgr.trigger_build.return_value = True
        mock_mgr.deploy_staging.return_value = True
        mock_mgr.run_sanity.return_value = True
        mock_mgr.update_jira.return_value = True
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["2.0.0", "--dry-run"])
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "completed successfully" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_dry_run_skip_flags(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "3.0.0"
        mock_mgr.branch_name = "release/3.0.0"
        mock_mgr.steps_completed = []
        mock_mgr.errors = []
        mock_mgr.create_branch.return_value = True
        mock_mgr.generate_changelog.return_value = True
        mock_mgr.bump_version.return_value = True
        mock_mgr.commit_changes.return_value = True
        mock_mgr.push_branch.return_value = True
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["3.0.0", "--dry-run", "--skip-deploy", "--skip-jira", "--skip-tests"])
        out = capsys.readouterr().out
        # run_tests should NOT have been called
        mock_mgr.run_tests.assert_not_called()
        mock_mgr.trigger_build.assert_not_called()
        mock_mgr.update_jira.assert_not_called()

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_step_failure(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "4.0.0"
        mock_mgr.branch_name = "release/4.0.0"
        mock_mgr.steps_completed = []
        mock_mgr.errors = []
        mock_mgr.create_branch.return_value = True
        mock_mgr.run_tests.return_value = False  # fails
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["4.0.0", "--dry-run"])
        out = capsys.readouterr().out
        assert "failed" in out.lower()

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_step_exception(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        mock_mgr = MagicMock()
        mock_mgr.version = "5.0.0"
        mock_mgr.branch_name = "release/5.0.0"
        mock_mgr.steps_completed = []
        mock_mgr.errors = []
        mock_mgr.create_branch.side_effect = RuntimeError("git error")
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["5.0.0", "--dry-run"])
        out = capsys.readouterr().out
        assert "git error" in out

    @patch("code_agents.cli.cli_cicd.prompt_yes_no")
    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_release_failure_rollback(self, mock_colors, mock_cwd, mock_load, mock_prompt, capsys):
        from code_agents.cli.cli_cicd import cmd_release
        # First prompt: proceed. Second prompt: rollback.
        mock_prompt.side_effect = [True, True]
        mock_mgr = MagicMock()
        mock_mgr.version = "6.0.0"
        mock_mgr.branch_name = "release/6.0.0"
        mock_mgr.steps_completed = ["Create release branch"]
        mock_mgr.errors = ["Run tests: test failure"]
        mock_mgr.create_branch.return_value = True
        mock_mgr.run_tests.return_value = False
        mock_mgr.rollback.return_value = True
        with patch("code_agents.tools.release.ReleaseManager", return_value=mock_mgr):
            cmd_release(["6.0.0"])
        out = capsys.readouterr().out
        mock_mgr.rollback.assert_called_once()


class TestCmdCoverageBoost:
    """cmd_coverage_boost — auto-coverage pipeline."""

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_coverage_boost_dry_run(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_coverage_boost
        mock_boost = MagicMock()
        mock_boost.scan_existing_tests.return_value = {"files": 10, "methods": 50}
        mock_boost.identify_gaps.return_value = [1, 2, 3]
        gap1 = MagicMock(); gap1.risk = "critical"
        gap2 = MagicMock(); gap2.risk = "high"
        gap3 = MagicMock(); gap3.risk = "low"
        mock_boost.prioritize_gaps.return_value = [gap1, gap2, gap3]
        mock_boost.build_test_prompts.return_value = ["p1", "p2"]
        mock_boost.build_delegation_prompt.return_value = "delegate..."
        mock_boost.report = {"summary": "ok"}

        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost), \
             patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="Report output"):
            cmd_coverage_boost(["--dry-run"])
        out = capsys.readouterr().out
        assert "10" in out  # test files
        assert "Report output" in out
        mock_boost.run_coverage_baseline.assert_not_called()

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_coverage_boost_already_meets_target(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_coverage_boost
        mock_boost = MagicMock()
        mock_boost.scan_existing_tests.return_value = {"files": 10, "methods": 50}
        mock_boost.run_coverage_baseline.return_value = {"coverage": 95}

        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost), \
             patch("code_agents.tools.auto_coverage.format_coverage_report", return_value=""):
            cmd_coverage_boost(["--target", "90"])
        out = capsys.readouterr().out
        assert "already meets" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_coverage_boost_custom_target(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_coverage_boost
        mock_boost = MagicMock()
        mock_boost.scan_existing_tests.return_value = {"files": 5, "methods": 20}
        mock_boost.run_coverage_baseline.return_value = {"coverage": 60}
        mock_boost.identify_gaps.return_value = []
        mock_boost.prioritize_gaps.return_value = []
        mock_boost.build_test_prompts.return_value = []
        mock_boost.report = {}

        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost) as MockBoost, \
             patch("code_agents.tools.auto_coverage.format_coverage_report", return_value=""):
            cmd_coverage_boost(["--target", "85"])
        MockBoost.assert_called_once_with(cwd="/tmp/repo", target_pct=85.0)


class TestCmdQaSuite:
    """cmd_qa_suite — QA suite generation."""

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_no_language(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = None
        mock_gen.analyze.return_value = mock_analysis
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""):
            cmd_qa_suite([])
        out = capsys.readouterr().out
        assert "Could not detect" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_analyze_only(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_analysis.existing_test_count = 0
        mock_gen.analyze.return_value = mock_analysis
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="Analysis..."):
            cmd_qa_suite(["--analyze"])
        out = capsys.readouterr().out
        assert "Analyze-only" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_generate_no_output(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "java"
        mock_analysis.has_existing_tests = False
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = []
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""):
            cmd_qa_suite(["--write"])
        out = capsys.readouterr().out
        assert "No test files generated" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_write_files(self, mock_colors, mock_cwd, mock_load, capsys, tmp_path):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = [
            {"path": "tests/test_gen.py", "description": "auto tests", "content": "# test"},
        ]
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value=str(tmp_path)):
            cmd_qa_suite(["--write"])
        out = capsys.readouterr().out
        assert "WROTE" in out
        assert "1 files written" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_existing_tests_hint(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = True
        mock_analysis.existing_test_count = 15
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = [
            {"path": "tests/test_new.py", "description": "new", "content": "#"},
        ]
        mock_gen.build_agent_prompt.return_value = "prompt..."
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""):
            # No flags -- shows hint about existing tests + delegation prompt
            cmd_qa_suite([])
        out = capsys.readouterr().out
        assert "15 existing test files" in out

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._user_cwd", return_value="/tmp/repo")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_delegation_prompt(self, mock_colors, mock_cwd, mock_load, capsys):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = [
            {"path": "tests/test_x.py", "description": "x", "content": "#"},
        ]
        mock_gen.build_agent_prompt.return_value = "delegation prompt text"
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""):
            cmd_qa_suite([])
        out = capsys.readouterr().out
        assert "Delegation prompt ready" in out


class TestCmdQaSuiteCommit:
    """cmd_qa_suite with --commit flag."""

    @patch("code_agents.cli.cli_cicd._load_env")
    @patch("code_agents.cli.cli_cicd._colors", return_value=_make_colors())
    def test_qa_suite_commit(self, mock_colors, mock_load, capsys, tmp_path):
        from code_agents.cli.cli_cicd import cmd_qa_suite
        mock_gen = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.has_existing_tests = False
        mock_gen.analyze.return_value = mock_analysis
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        mock_gen.generate_suite.return_value = [
            {"path": "tests/test_commit.py", "description": "auto", "content": "# committed"},
        ]
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen), \
             patch("code_agents.generators.qa_suite_generator.format_analysis", return_value=""), \
             patch("code_agents.cli.cli_cicd._user_cwd", return_value=str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            cmd_qa_suite(["--commit"])
        out = capsys.readouterr().out
        assert "Committed" in out
        # git checkout, git add, git commit should be called
        assert mock_run.call_count >= 3
