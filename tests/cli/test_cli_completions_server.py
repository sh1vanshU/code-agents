"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdCompletions:
    """Test completions command."""

    def test_completions_no_args(self, capsys):
        from code_agents.cli.cli_completions import cmd_completions
        cmd_completions([])
        output = capsys.readouterr().out
        assert "completion" in output.lower()
        assert "--install" in output
        assert "--zsh" in output
        assert "--bash" in output

    def test_completions_zsh(self, capsys):
        from code_agents.cli.cli_completions import cmd_completions
        cmd_completions(["--zsh"])
        output = capsys.readouterr().out
        assert "compdef" in output
        assert "_code_agents" in output

    def test_completions_bash(self, capsys):
        from code_agents.cli.cli_completions import cmd_completions
        cmd_completions(["--bash"])
        output = capsys.readouterr().out
        assert "complete -F" in output
        assert "_code_agents_completions" in output

    def test_completions_install_zsh(self, capsys, tmp_path):
        from code_agents.cli.cli_completions import cmd_completions
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# existing config\n")
        with patch("os.path.expanduser", return_value=str(zshrc)), \
             patch("os.path.exists", return_value=True):
            cmd_completions(["--install"])
        output = capsys.readouterr().out
        assert "installed" in output.lower() or "Completions" in output
        content = zshrc.read_text()
        assert "code-agents completion" in content

    def test_completions_install_already_installed(self, capsys, tmp_path):
        from code_agents.cli.cli_completions import cmd_completions
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# code-agents completion\n_code_agents() {}\n")
        with patch("os.path.expanduser", return_value=str(zshrc)), \
             patch("os.path.exists", return_value=True):
            cmd_completions(["--install"])
        output = capsys.readouterr().out
        assert "already installed" in output.lower()

    def test_completions_install_no_shell_config(self, capsys, tmp_path):
        from code_agents.cli.cli_completions import cmd_completions
        with patch("os.path.exists", return_value=False):
            cmd_completions(["--install"])
        output = capsys.readouterr().out
        assert "Could not detect" in output
class TestGenerateCompletions:
    """Test shell completion script generation."""

    def test_generate_zsh(self):
        from code_agents.cli.cli_completions import _generate_zsh_completion
        output = _generate_zsh_completion()
        assert "compdef _code_agents code-agents" in output
        assert "init" in output
        assert "chat" in output

    def test_generate_bash(self):
        from code_agents.cli.cli_completions import _generate_bash_completion
        output = _generate_bash_completion()
        assert "complete -F _code_agents_completions code-agents" in output
        assert "init" in output
class TestCmdStartForeground:
    """Test cmd_start with foreground flag."""

    def test_start_foreground(self, capsys):
        from code_agents.cli.cli_server import cmd_start
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_server._check_workspace_trust", return_value=True), \
             patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}), \
             patch("sys.argv", ["code-agents", "start", "--fg"]), \
             patch("code_agents.core.main.main") as mock_run:
            cmd_start()
        mock_run.assert_called_once()

    def test_start_trust_fails(self, capsys):
        from code_agents.cli.cli_server import cmd_start
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_server._check_workspace_trust", return_value=False):
            cmd_start()
class TestStartBackground:
    """Test _start_background function."""

    def test_start_background_healthy(self, capsys, tmp_path):
        from code_agents.cli.cli_server import _start_background
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_diag_resp = MagicMock()
        mock_diag_resp.json.return_value = {"agents": ["a1", "a2"]}
        with patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get") as mock_httpx_get, \
             patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}), \
             patch("subprocess.run") as mock_sp_run, \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "config.env"), \
             patch("code_agents.core.env_loader.repo_config_path", return_value=tmp_path / "repo.env"):
            mock_httpx_get.side_effect = [mock_resp, mock_diag_resp]
            mock_sp_run.return_value = MagicMock(stdout="main", returncode=0)
            _start_background("/tmp/repo")
        output = capsys.readouterr().out
        assert "running" in output.lower() or "PID" in output

    def test_start_background_process_dies(self, capsys, tmp_path):
        from code_agents.cli.cli_server import _start_background
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process died
        with patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}):
            _start_background("/tmp/repo")
        output = capsys.readouterr().out
        assert "failed to start" in output.lower()
class TestCmdRestart:
    """Test cmd_restart."""

    def test_restart_with_running_server(self, capsys, tmp_path):
        from code_agents.cli.cli_server import cmd_restart
        lsof_result = MagicMock()
        lsof_result.stdout = "12345\n"
        lsof_check = MagicMock()
        lsof_check.stdout = ""
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp"), \
             patch("subprocess.run", side_effect=[lsof_result, lsof_check]), \
             patch("os.kill"), \
             patch("time.sleep"), \
             patch("code_agents.cli.cli_server._start_background") as mock_start, \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_restart()
        mock_start.assert_called_once()

    def test_restart_no_running_server(self, capsys):
        from code_agents.cli.cli_server import cmd_restart
        lsof_result = MagicMock()
        lsof_result.stdout = ""
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._user_cwd", return_value="/tmp"), \
             patch("subprocess.run", return_value=lsof_result), \
             patch("code_agents.cli.cli_server._start_background") as mock_start, \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_restart()
        mock_start.assert_called_once()
class TestCmdShutdownForceKill:
    """Test cmd_shutdown with force kill."""

    def test_shutdown_force_kill_needed(self, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        first_lsof = MagicMock()
        first_lsof.stdout = "12345\n"
        second_lsof = MagicMock()
        second_lsof.stdout = "12345\n"  # still running
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("subprocess.run", side_effect=[first_lsof, second_lsof]), \
             patch("os.kill") as mock_kill, \
             patch("time.sleep"), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        # Should have called SIGTERM then SIGKILL
        assert mock_kill.call_count >= 2

    def test_shutdown_exception(self, capsys):
        from code_agents.cli.cli_server import cmd_shutdown
        with patch("code_agents.cli.cli_server._load_env"), \
             patch("subprocess.run", side_effect=Exception("lsof error")), \
             patch.dict(os.environ, {"PORT": "8000"}):
            cmd_shutdown()
        output = capsys.readouterr().out
        assert "Could not find" in output
