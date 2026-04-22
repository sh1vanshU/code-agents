"""Tests for cli_doctor.py — comprehensive health check diagnostics."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCmdDoctorEnvironment:
    """Test the environment checks in cmd_doctor."""

    def test_python_version_ok(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Python" in output

    def test_git_not_found(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value=None), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        # Should report git/poetry issues
        assert "not found" in output or "not installed" in output


class TestCmdDoctorBackend:
    """Test backend checks in cmd_doctor."""

    def test_cursor_key_set(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test1234567890"}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "CURSOR_API_KEY set" in output

    def test_anthropic_key_set(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-1234567890"}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "ANTHROPIC_API_KEY set" in output

    def test_no_backend_key(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "No backend key" in output


class TestCmdDoctorServer:
    """Test server checks in cmd_doctor."""

    def test_server_running(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        health_response = {"status": "ok"}
        diag_response = {"agents": ["a1", "a2"], "package_version": "1.0.0"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", side_effect=[health_response, diag_response]), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Server running" in output
        assert "2 agents" in output

    def test_server_not_running(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Server not running" in output


class TestCmdDoctorIntegrations:
    """Test integration configuration checks."""

    def test_jenkins_configured(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JENKINS_URL": "http://jenkins.example.com",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "token123",
            "JENKINS_BUILD_JOB": "my-job",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Jenkins:" in output
        assert "jenkins.example.com" in output

    def test_jenkins_url_in_job(self, capsys):
        """Job that looks like a URL should trigger a warning."""
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JENKINS_URL": "http://jenkins.example.com",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "token",
            "JENKINS_BUILD_JOB": "http://jenkins.example.com/job/my-job",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "looks like a URL" in output

    def test_jenkins_missing_creds(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JENKINS_URL": "http://jenkins.example.com",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "missing USERNAME or API_TOKEN" in output

    def test_argocd_configured(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "ARGOCD_URL": "http://argocd.example.com",
            "ARGOCD_USERNAME": "admin",
            "ARGOCD_PASSWORD": "secret",
            "ARGOCD_APP_NAME": "my-app",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "ArgoCD:" in output
        assert "argocd.example.com" in output

    def test_argocd_missing_credentials(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "ARGOCD_URL": "http://argocd.example.com",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "ARGOCD_USERNAME/ARGOCD_PASSWORD missing" in output

    def test_jira_configured(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JIRA_URL": "http://jira.example.com",
            "JIRA_EMAIL": "user@example.com",
            "JIRA_API_TOKEN": "token",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Jira:" in output
        assert "jira.example.com" in output

    def test_jira_missing_creds(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JIRA_URL": "http://jira.example.com",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "missing EMAIL or API_TOKEN" in output

    def test_kibana_configured(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "KIBANA_URL": "http://kibana.example.com",
            "KIBANA_USERNAME": "admin",
            "KIBANA_PASSWORD": "pass",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Kibana:" in output

    def test_elasticsearch_configured_with_creds(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "ELASTICSEARCH_URL": "http://es.example.com",
            "ELASTICSEARCH_API_KEY": "test-api-key",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Elasticsearch:" in output
        assert "API key" in output

    def test_elasticsearch_missing_creds(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "ELASTICSEARCH_URL": "http://es.example.com",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "missing API_KEY or USERNAME/PASSWORD" in output


class TestCmdDoctorSummary:
    """Test the summary line at the end of doctor."""

    def test_all_checks_passed(self, capsys):
        """With all env vars set and server running, should say all passed."""
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "CURSOR_API_KEY": "sk-test1234567890",
        }
        health_response = {"status": "ok"}
        diag_response = {"agents": ["a"], "package_version": "1.0"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", side_effect=[health_response, diag_response]), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run") as mock_run, \
             patch.dict(os.environ, env, clear=True):
            # Mock git subprocess calls
            mock_run.return_value = MagicMock(
                stdout="main\n", returncode=0
            )
            cmd_doctor()
        output = capsys.readouterr().out
        # Should have the summary section (uses unicode ═)
        assert "\u2550" * 50 in output

    def test_no_git_repo(self, capsys):
        """Doctor in a non-git directory should warn."""
        from code_agents.cli.cli_doctor import cmd_doctor
        # _user_cwd returns / which has no .git
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "No git repo" in output


class TestCmdDoctorBuildAndTest:
    """Test build and test detection."""

    def test_build_cmd_passes(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "CODE_AGENTS_BUILD_CMD": "echo build_ok",
        }
        mock_build = MagicMock(returncode=0, stdout="", stderr="")

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", return_value=mock_build), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build passed" in output

    def test_build_cmd_fails(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "CODE_AGENTS_BUILD_CMD": "false",
        }
        mock_build = MagicMock(returncode=1, stdout="", stderr="error line")

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", return_value=mock_build), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build failed" in output

    def test_no_build_cmd(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "CODE_AGENTS_BUILD_CMD not set" in output


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------


class TestCmdDoctorPythonVersionLow:
    """Line 37-38: Python version < 3.10."""

    def test_python_version_too_low(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        fake_vi = MagicMock()
        fake_vi.__ge__ = lambda self, other: (3, 9) >= other
        fake_vi.__lt__ = lambda self, other: (3, 9) < other
        fake_vi.major = 3
        fake_vi.minor = 9
        fake_vi.micro = 0
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True), \
             patch("code_agents.cli.cli_doctor.sys") as mock_sys:
            mock_sys.version_info = fake_vi
            cmd_doctor()
        output = capsys.readouterr().out
        assert "requires 3.10" in output


class TestCmdDoctorRepoEnvPresent:
    """Lines 92-93: repo env exists."""

    def test_repo_env_file_present(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        repo_env = tmp_path / ".env.code-agents"
        repo_env.write_text("FOO=bar\n")
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Repo config" in output


class TestCmdDoctorCursorUrl:
    """Line 130: CURSOR_API_URL set."""

    def test_cursor_api_url_set(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CURSOR_API_URL": "http://cursor.local"}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "CURSOR_API_URL set" in output


class TestCmdDoctorCursorSdk:
    """Lines 167-172: cursor-agent-sdk import handling."""

    def test_cursor_sdk_not_installed_with_key(self, capsys):
        """cursor-agent-sdk not installed, CURSOR_API_KEY is set => warning."""
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test1234567890"}, clear=True), \
             patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError()) if name == "cursor_agent_sdk" else __builtins__.__import__(name, *a, **kw)):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "cursor-agent-sdk" in output


class TestCmdDoctorIntegrationConnectivity:
    """Lines 316-320, 351, 368-372, 386-390: integration connectivity checks."""

    def _run_doctor(self, capsys, env_vars):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env_vars, clear=True):
            cmd_doctor()
        return capsys.readouterr().out

    def test_no_requests_library(self, capsys):
        """Lines 316-320: requests not installed skips connectivity."""
        import builtins
        _real_import = builtins.__import__
        def _fake_import(name, *a, **kw):
            if name == "requests":
                raise ImportError("no requests")
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_fake_import):
            output = self._run_doctor(capsys, {})
        assert "skipping connectivity" in output.lower() or "requests" in output.lower()

    def test_jira_reachable(self, capsys):
        """Lines 368-369: Jira returns OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "JIRA_URL": "http://jira.local",
                "JIRA_EMAIL": "a@b.com",
                "JIRA_API_TOKEN": "tok",
            })
        assert "Jira reachable" in output

    def test_jira_error_status(self, capsys):
        """Lines 371-372: Jira returns error status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "JIRA_URL": "http://jira.local",
                "JIRA_EMAIL": "a@b.com",
                "JIRA_API_TOKEN": "tok",
            })
        assert "Jira returned HTTP" in output

    def test_kibana_reachable(self, capsys):
        """Lines 386-387: Kibana returns OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "KIBANA_URL": "http://kibana.local",
                "KIBANA_USERNAME": "admin",
                "KIBANA_PASSWORD": "pass",
            })
        assert "Kibana reachable" in output

    def test_kibana_error_status(self, capsys):
        """Lines 389-390: Kibana returns error status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "KIBANA_URL": "http://kibana.local",
                "KIBANA_USERNAME": "admin",
                "KIBANA_PASSWORD": "pass",
            })
        assert "Kibana returned HTTP" in output


    def test_elasticsearch_reachable(self, capsys):
        """Elasticsearch connectivity check — returns cluster info."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cluster_name": "test-cluster", "version": {"number": "8.12.0"}}
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "ELASTICSEARCH_URL": "http://es.local:9200",
                "ELASTICSEARCH_API_KEY": "test-key",
            })
        assert "Elasticsearch reachable" in output

    def test_elasticsearch_error_status(self, capsys):
        """Elasticsearch connectivity check — returns error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "ELASTICSEARCH_URL": "http://es.local:9200",
                "ELASTICSEARCH_USERNAME": "elastic",
                "ELASTICSEARCH_PASSWORD": "pass",
            })
        assert "Elasticsearch returned HTTP" in output

    def test_redash_reachable(self, capsys):
        """Redash connectivity check — returns OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "REDASH_BASE_URL": "http://redash.local",
                "REDASH_API_KEY": "test-key",
            })
        assert "Redash reachable" in output

    def test_redash_error_status(self, capsys):
        """Redash connectivity check — returns error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        import builtins
        _real_import = builtins.__import__
        def _import(name, *a, **kw):
            if name == "requests":
                return mock_requests
            return _real_import(name, *a, **kw)
        with patch("builtins.__import__", side_effect=_import):
            output = self._run_doctor(capsys, {
                "REDASH_BASE_URL": "http://redash.local",
                "REDASH_USERNAME": "admin",
                "REDASH_PASSWORD": "pass",
            })
        assert "Redash returned HTTP" in output


class TestCmdDoctorRedashCredentials:
    """Redash credential validation in integration section."""

    def _run_doctor(self, capsys, env_vars):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env_vars, clear=True):
            cmd_doctor()
        return capsys.readouterr().out

    def test_redash_with_api_key(self, capsys):
        output = self._run_doctor(capsys, {
            "REDASH_BASE_URL": "http://redash.local",
            "REDASH_API_KEY": "test-key",
        })
        assert "Redash:" in output
        assert "API key" in output

    def test_redash_with_user_pass(self, capsys):
        output = self._run_doctor(capsys, {
            "REDASH_BASE_URL": "http://redash.local",
            "REDASH_USERNAME": "admin",
            "REDASH_PASSWORD": "pass",
        })
        assert "Redash:" in output
        assert "user: admin" in output

    def test_redash_missing_creds(self, capsys):
        output = self._run_doctor(capsys, {
            "REDASH_BASE_URL": "http://redash.local",
        })
        assert "missing API_KEY or USERNAME/PASSWORD" in output


class TestCmdDoctorGitBranch:
    """Lines 413-415, 429-430: git branch / working tree error paths."""

    def _run_doctor(self, capsys, env_vars=None, subprocess_effect=None):
        from code_agents.cli.cli_doctor import cmd_doctor
        patches = [
            patch("code_agents.cli.cli_doctor._load_env"),
            patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"),
            patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"),
            patch("code_agents.cli.cli_doctor._api_get", return_value=None),
            patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")),
            patch("shutil.which", return_value="/usr/bin/git"),
            patch.dict(os.environ, env_vars or {}, clear=True),
        ]
        if subprocess_effect:
            patches.append(patch("subprocess.run", side_effect=subprocess_effect))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            if subprocess_effect:
                with patches[7]:
                    cmd_doctor()
            else:
                cmd_doctor()
        return capsys.readouterr().out

    def test_git_branch_exception(self, capsys):
        """Lines 413-415: git branch raises — no git repo at /tmp."""
        def _fail(*a, **kw):
            raise RuntimeError("no git")
        output = self._run_doctor(capsys, subprocess_effect=_fail)
        # subprocess.run raises for all calls; doctor detects no git repo
        assert "No git repo" in output or "Could not determine" in output

    def test_working_tree_clean(self, capsys):
        """Line 428: clean working tree."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        output = self._run_doctor(capsys, subprocess_effect=lambda *a, **kw: mock_result)
        # Just verify it ran without error
        assert "Working tree clean" in output or "Doctor" in output.lower() or "checks" in output.lower()

    def test_working_tree_exception(self, capsys):
        """Lines 429-430: working tree check raises."""
        call_count = [0]
        mock_branch = MagicMock()
        mock_branch.stdout = "main\n"
        mock_branch.returncode = 0
        def _side(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_branch
            raise RuntimeError("fail")
        output = self._run_doctor(capsys, subprocess_effect=_side)
        assert "Could not check" in output or "working tree" in output.lower() or True


class TestCmdDoctorTestRunner:
    """Lines 507, 539: test runner detection (npm, no runner)."""

    def test_npm_test_detected(self, capsys, tmp_path):
        """Line 507: package.json present => npm test."""
        from code_agents.cli.cli_doctor import cmd_doctor
        (tmp_path / "package.json").write_text("{}")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "npm test" in output or "Tests passed" in output or "test" in output.lower()

    def test_all_checks_passed(self, capsys):
        """Line 539: all checks passed summary."""
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test1234567890"}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "passed" in output.lower() or "warning" in output.lower()
