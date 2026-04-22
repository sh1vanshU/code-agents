"""Coverage tests for chat_slash_nav.py — covers missing lines from coverage_run.json.

Missing lines: 22-24,26,30-42,45-50,57-65,84-94,117,206,208-211,215-216,
271-272,279-283,299-300,302
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_slash_nav import (
    _restart_server,
    _handle_navigation,
)


# ---------------------------------------------------------------------------
# Lines 22-65: _restart_server — full restart flow
# ---------------------------------------------------------------------------


class TestRestartServer:
    def test_restart_server_kills_and_starts(self, capsys):
        """Lines 22-59: full restart — kill PIDs, start new server, verify."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = "12345\n"

        mock_lsof_check = MagicMock()
        mock_lsof_check.stdout = ""  # no stragglers

        call_count = [0]
        def fake_subprocess_run(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_lsof_result  # initial lsof
            elif call_count[0] == 2:
                return mock_lsof_check  # check for stragglers
            return MagicMock()

        with patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("os.kill") as mock_kill, \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _restart_server("http://localhost:8000")

        mock_kill.assert_called_with(12345, 15)
        mock_popen.assert_called_once()
        output = capsys.readouterr().out
        assert "restarted" in output

    def test_restart_server_with_stragglers(self, capsys):
        """Lines 36-42: force-kill straggler PIDs."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = "12345\n"

        mock_lsof_check = MagicMock()
        mock_lsof_check.stdout = "12345\n"  # straggler remains

        call_count = [0]
        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_lsof_result
            elif call_count[0] == 2:
                return mock_lsof_check
            return MagicMock()

        with patch("subprocess.run", side_effect=fake_run), \
             patch("os.kill") as mock_kill, \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _restart_server("http://localhost:8000")

        # Should have been called with signal 15 first, then 9 for straggler
        calls = mock_kill.call_args_list
        assert any(c == ((12345, 9),) for c in calls)

    def test_restart_server_straggler_process_lookup_error(self, capsys):
        """Lines 40-42: ProcessLookupError on straggler kill is swallowed."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = "99999\n"

        mock_lsof_check = MagicMock()
        mock_lsof_check.stdout = "99999\n"

        call_count = [0]
        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_lsof_result
            elif call_count[0] == 2:
                return mock_lsof_check
            return MagicMock()

        kill_count = [0]
        def fake_kill(pid, sig):
            kill_count[0] += 1
            if kill_count[0] > 1:  # second kill (SIGKILL) fails
                raise ProcessLookupError("No such process")

        with patch("subprocess.run", side_effect=fake_run), \
             patch("os.kill", side_effect=fake_kill), \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _restart_server("http://localhost:8000")

    def test_restart_server_no_pids(self, capsys):
        """Lines 30-31: no existing PIDs → just start new server."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = ""  # no PIDs

        with patch("subprocess.run", return_value=mock_lsof_result), \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _restart_server("http://localhost:8000")

        output = capsys.readouterr().out
        assert "restarted" in output

    def test_restart_server_fails_to_start(self, capsys):
        """Lines 61: server fails to start → warning."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = ""

        with patch("subprocess.run", return_value=mock_lsof_result), \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=False):
            _restart_server("http://localhost:8000")

        output = capsys.readouterr().out
        assert "may still be starting" in output

    def test_restart_server_exception(self, capsys):
        """Lines 62-65: exception during restart."""
        with patch("subprocess.run", side_effect=OSError("no lsof")):
            _restart_server("http://localhost:8000")

        output = capsys.readouterr().out
        assert "Could not restart" in output

    def test_restart_server_port_parsing(self, capsys):
        """Line 22-23: port extracted from URL."""
        mock_lsof_result = MagicMock()
        mock_lsof_result.stdout = ""

        with patch("subprocess.run", return_value=mock_lsof_result) as mock_run, \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _restart_server("http://localhost:9090")

        # Should use port 9090
        first_call = mock_run.call_args_list[0]
        assert "-ti:9090" in first_call[0][0]


# ---------------------------------------------------------------------------
# Lines 84-94: /restart command — full flow
# ---------------------------------------------------------------------------


class TestRestartCommand:
    def test_restart_command_kills_and_starts(self, capsys):
        """Lines 84-94: /restart kills existing, starts new, verifies."""
        mock_lsof1 = MagicMock()
        mock_lsof1.stdout = "11111\n"

        mock_lsof2 = MagicMock()
        mock_lsof2.stdout = ""

        call_count = [0]
        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count[0] += 1
            if isinstance(cmd, list) and "lsof" in cmd[0]:
                if call_count[0] <= 1:
                    return mock_lsof1
                return mock_lsof2
            return MagicMock()

        with patch("subprocess.run", side_effect=fake_run), \
             patch("os.kill") as mock_kill, \
             patch("subprocess.Popen") as mock_popen, \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"):
            _handle_navigation("/restart", "", {"repo_path": "/tmp"}, "http://localhost:8000")

        output = capsys.readouterr().out
        assert "restart" in output.lower()

    def test_restart_command_fails(self, capsys):
        """Line 117: server fails to restart after 10 retries."""
        mock_lsof = MagicMock()
        mock_lsof.stdout = ""

        with patch("subprocess.run", return_value=mock_lsof), \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=False), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("builtins.open", MagicMock()):
            _handle_navigation("/restart", "", {"repo_path": "/tmp"}, "http://localhost:8000")

        output = capsys.readouterr().out
        assert "failed" in output.lower()

    def test_restart_exception_during_kill(self, capsys):
        """Lines 93-94: exception during kill is swallowed."""
        with patch("subprocess.run", side_effect=OSError("no lsof")), \
             patch("subprocess.Popen"), \
             patch("time.sleep"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("builtins.open", MagicMock()):
            _handle_navigation("/restart", "", {"repo_path": "/tmp"}, "http://localhost:8000")


# ---------------------------------------------------------------------------
# Lines 206, 208-211, 215-216: /open command
# ---------------------------------------------------------------------------


class TestOpenCommand:
    def test_open_no_output(self, capsys):
        """Line 206: no last output → message."""
        result = _handle_navigation("/open", "", {}, "http://localhost:8000")
        assert result is None
        assert "No output" in capsys.readouterr().out

    def test_open_with_pager(self, capsys):
        """Lines 208-211: open with pager."""
        state = {"_last_output": "some response text"}
        with patch("subprocess.run") as mock_run, \
             patch("os.unlink"):
            _handle_navigation("/open", "", state, "http://localhost:8000")
        mock_run.assert_called_once()

    def test_open_pager_not_found_fallback(self, capsys):
        """Lines 208-211: pager not found → try macOS open."""
        state = {"_last_output": "some text"}
        with patch("subprocess.run", side_effect=[FileNotFoundError, None]) as mock_run, \
             patch("os.unlink"):
            _handle_navigation("/open", "", state, "http://localhost:8000")
        assert mock_run.call_count == 2

    def test_open_fallback_also_fails(self, capsys):
        """Lines 210-211: both pager and open fail → show file path."""
        state = {"_last_output": "some text"}
        with patch("subprocess.run", side_effect=FileNotFoundError), \
             patch("os.unlink"):
            _handle_navigation("/open", "", state, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "Saved to" in output

    def test_open_unlink_oserror(self):
        """Lines 215-216: OSError on unlink is ignored."""
        state = {"_last_output": "text"}
        with patch("subprocess.run"), \
             patch("os.unlink", side_effect=OSError("busy")):
            _handle_navigation("/open", "", state, "http://localhost:8000")


# ---------------------------------------------------------------------------
# Lines 271-272, 279-283: /setup — argocd auto-pattern
# ---------------------------------------------------------------------------


class TestSetupCommand:
    def test_setup_no_arg_lists_sections(self, capsys):
        """Show available sections."""
        result = _handle_navigation("/setup", "", {}, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "jenkins" in output
        assert "argocd" in output

    def test_setup_unknown_section(self, capsys):
        """Unknown section shows error."""
        result = _handle_navigation("/setup", "foobar", {}, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Unknown" in output

    def test_setup_argocd_with_values(self, tmp_path, capsys):
        """Lines 271-272, 279-283: setup argocd with values and auto-pattern."""
        repo = str(tmp_path)
        state = {"repo_path": repo}

        with patch("builtins.input", return_value="https://argocd.example.com"), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=False):
            _handle_navigation("/setup", "argocd", state, "http://localhost:8000")

        env_file = tmp_path / ".env.code-agents"
        assert env_file.exists()
        content = env_file.read_text()
        assert "ARGOCD" in content

    def test_setup_argocd_pattern_already_set(self, tmp_path, capsys):
        """Lines 279-282: ARGOCD_APP_PATTERN already in env → not auto-added."""
        repo = str(tmp_path)
        state = {"repo_path": repo}

        with patch("builtins.input", return_value="test_value"), \
             patch.dict(os.environ, {"ARGOCD_APP_PATTERN": "custom-{env}-{app}"}), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=False):
            _handle_navigation("/setup", "argocd", state, "http://localhost:8000")

    def test_setup_cancelled(self, capsys):
        """Lines 273-275: EOFError during input cancels setup."""
        state = {"repo_path": "/tmp"}
        with patch("builtins.input", side_effect=EOFError):
            result = _handle_navigation("/setup", "jenkins", state, "http://localhost:8000")
        assert result is None
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_setup_with_restart_prompt_yes(self, tmp_path, capsys):
        """Lines 295-302: setup saves values, prompts restart, user says yes."""
        repo = str(tmp_path)
        state = {"repo_path": repo}

        input_values = ["http://jenkins.example.com", "admin", "token123", "build-job", "deploy-job", "deploy-dev", "deploy-qa"]
        input_iter = iter(input_values + ["y"])

        with patch("builtins.input", side_effect=lambda *a: next(input_iter)), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True), \
             patch("code_agents.chat.chat_slash_nav._restart_server") as mock_restart:
            _handle_navigation("/setup", "jenkins", state, "http://localhost:8000")

        mock_restart.assert_called_once()

    def test_setup_with_restart_prompt_no(self, tmp_path, capsys):
        """Lines 299-304: user declines restart."""
        repo = str(tmp_path)
        state = {"repo_path": repo}

        input_values = ["http://jenkins.example.com", "admin", "token", "build", "deploy"]
        input_iter = iter(input_values + ["n"])

        with patch("builtins.input", side_effect=lambda *a: next(input_iter)), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _handle_navigation("/setup", "jenkins", state, "http://localhost:8000")

        output = capsys.readouterr().out
        assert "code-agents restart" in output

    def test_setup_restart_eof(self, tmp_path, capsys):
        """Lines 299-300: EOFError during restart prompt."""
        repo = str(tmp_path)
        state = {"repo_path": repo}

        input_values = ["http://j.com", "admin", "tok", "build", "deploy"]
        call_count = [0]
        def fake_input(*args):
            call_count[0] += 1
            if call_count[0] <= len(input_values):
                return input_values[call_count[0] - 1]
            raise EOFError

        with patch("builtins.input", side_effect=fake_input), \
             patch("code_agents.chat.chat_slash_nav._server_url", return_value="http://localhost:8000"), \
             patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
            _handle_navigation("/setup", "jenkins", state, "http://localhost:8000")


# ---------------------------------------------------------------------------
# Line 302: /setup unknown returns "_not_handled"
# ---------------------------------------------------------------------------


class TestUnknownNavCommand:
    def test_unknown_returns_not_handled(self):
        """Line 302: unrecognized command → _not_handled."""
        result = _handle_navigation("/foobar", "", {}, "http://localhost:8000")
        assert result == "_not_handled"


# ---------------------------------------------------------------------------
# /help command (already mostly covered, but let's ensure it works)
# ---------------------------------------------------------------------------


class TestHelpCommand:
    def test_help_prints_commands(self, capsys):
        """Lines 120+: /help prints full help text."""
        _handle_navigation("/help", "", {}, "http://localhost:8000")
        output = capsys.readouterr().out
        assert "/quit" in output
        assert "/agent" in output
        assert "/run" in output


# ---------------------------------------------------------------------------
# /quit aliases
# ---------------------------------------------------------------------------


class TestQuitCommand:
    def test_quit_returns_quit(self):
        assert _handle_navigation("/quit", "", {}, "u") == "quit"

    def test_exit_returns_quit(self):
        assert _handle_navigation("/exit", "", {}, "u") == "quit"

    def test_q_returns_quit(self):
        assert _handle_navigation("/q", "", {}, "u") == "quit"

    def test_bye_returns_quit(self):
        assert _handle_navigation("/bye", "", {}, "u") == "quit"
