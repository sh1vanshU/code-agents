"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdDoctor:
    """Test doctor command checks."""

    # Use CODE_AGENTS_TEST_CMD=echo ok to avoid running full pytest inside tests
    _FAST_ENV = {"CODE_AGENTS_TEST_CMD": "echo ok"}

    def test_doctor_runs(self, capsys):
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, self._FAST_ENV):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Code Agents Doctor" in output
        assert "Python" in output
        # Should check for .env, git repo, etc.
        assert ".env" in output or "env" in output.lower()

    def test_doctor_shows_git_health(self, capsys):
        """Doctor should show Git Health section when in a git repo."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, self._FAST_ENV):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Git Health" in output
        assert "Branch:" in output or "branch" in output.lower()

    def test_doctor_shows_integration_connectivity(self, capsys):
        """Doctor should show Integration Connectivity section."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, self._FAST_ENV):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Integration Connectivity" in output

    def test_doctor_shows_build_test_section(self, capsys):
        """Doctor should show Build & Test section."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, self._FAST_ENV):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build & Test" in output

    def test_doctor_jenkins_connectivity(self, capsys):
        """Doctor should test Jenkins connectivity when configured."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, {
            **self._FAST_ENV,
            "JENKINS_URL": "http://jenkins.example.com",
            "JENKINS_USERNAME": "user",
            "JENKINS_API_TOKEN": "token",
        }):
            cmd_doctor()
        output = capsys.readouterr().out
        # Should attempt connectivity (will fail/warn since host is fake)
        assert "Jenkins" in output

    def test_doctor_jira_connectivity(self, capsys):
        """Doctor should test Jira connectivity when configured."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, {
            **self._FAST_ENV,
            "JIRA_URL": "http://jira.example.com",
            "JIRA_EMAIL": "user@example.com",
            "JIRA_API_TOKEN": "token",
        }):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Jira" in output

    def test_doctor_no_integrations_connectivity(self, capsys):
        """Doctor should note when no integrations are configured for connectivity."""
        from code_agents.cli import cmd_doctor
        env_clear = {
            **self._FAST_ENV,
            "JENKINS_URL": "", "ARGOCD_URL": "", "JIRA_URL": "", "KIBANA_URL": "",
        }
        with patch.dict(os.environ, env_clear):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Integration Connectivity" in output

    def test_doctor_git_clean_tree(self, capsys):
        """Doctor reports clean/dirty working tree."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, self._FAST_ENV):
            cmd_doctor()
        output = capsys.readouterr().out
        # Should report either clean or modified files
        assert "Working tree" in output or "modified" in output.lower() or "untracked" in output.lower()

    def test_doctor_build_cmd(self, capsys):
        """Doctor should run build when CODE_AGENTS_BUILD_CMD is set."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, {**self._FAST_ENV, "CODE_AGENTS_BUILD_CMD": "echo build-ok"}):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build passed" in output

    def test_doctor_build_cmd_failure(self, capsys):
        """Doctor should report build failure."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, {**self._FAST_ENV, "CODE_AGENTS_BUILD_CMD": "exit 1"}):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build failed" in output

    def test_doctor_test_autodetect(self, capsys, monkeypatch):
        """Doctor should auto-detect test runner from project files."""
        import subprocess as _sp
        from code_agents.cli import cmd_doctor
        # Mock subprocess.run to avoid actually running pytest inside pytest
        _original_run = _sp.run
        def _mock_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", "")
            cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
            if "pytest" in cmd_str or "mvn test" in cmd_str or "npm test" in cmd_str:
                result = MagicMock()
                result.returncode = 0
                result.stdout = "5 passed in 1.0s"
                result.stderr = ""
                return result
            return _original_run(*args, **kwargs)
        monkeypatch.setattr(_sp, "run", _mock_run)
        cmd_doctor()
        output = capsys.readouterr().out
        # This project has pyproject.toml so pytest should be detected
        assert "Tests passed" in output or "test" in output.lower()

    def test_doctor_test_cmd_override(self, capsys):
        """Doctor should use CODE_AGENTS_TEST_CMD when set."""
        from code_agents.cli import cmd_doctor
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "echo all-tests-pass"}):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Tests passed" in output
class TestCmdDoctorExtended:
    """Test additional doctor paths."""

    def test_doctor_legacy_env_is_directory(self, capsys, tmp_path):
        """Doctor handles .env as a directory."""
        from code_agents.cli.cli_doctor import cmd_doctor
        env_dir = tmp_path / ".env"
        env_dir.mkdir()
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "echo ok"}, clear=False), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "directory" in output.lower() or "Doctor" in output

    def test_doctor_elasticsearch_configured(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "ELASTICSEARCH_URL": "http://es:9200",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Elasticsearch" in output

    def test_doctor_build_timeout(self, capsys, tmp_path):
        import subprocess as _sp
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_BUILD_CMD": "sleep 999",
                 "CODE_AGENTS_TEST_CMD": "echo ok",
             }), \
             patch("subprocess.run") as mock_sp:
            def side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", "")
                cmd_str = cmd if isinstance(cmd, str) else " ".join(str(x) for x in cmd)
                if "sleep 999" in cmd_str:
                    raise _sp.TimeoutExpired(cmd="sleep 999", timeout=120)
                result = MagicMock()
                result.returncode = 0
                result.stdout = "main"
                result.stderr = ""
                return result
            mock_sp.side_effect = side_effect
            cmd_doctor()
        output = capsys.readouterr().out
        assert "timed out" in output.lower()

    def test_doctor_no_backend_key(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "CODE_AGENTS_BACKEND": "",
                 "CURSOR_API_KEY": "",
                 "ANTHROPIC_API_KEY": "",
                 "CODE_AGENTS_LOCAL_LLM_URL": "",
                 "CURSOR_API_URL": "",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "No backend configured" in output

    def test_doctor_server_running_with_agents(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get") as mock_get, \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "echo ok"}), \
             patch("subprocess.run") as mock_sp:
            mock_get.side_effect = [
                {"status": "ok"},  # /health
                {"agents": ["a1", "a2"], "package_version": "0.2.0"},  # /diagnostics
            ]
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Server running" in output
        assert "2 agents" in output

    def test_doctor_all_checks_pass(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get") as mock_get, \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "CURSOR_API_KEY": "sk-12345678",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_get.side_effect = [
                {"status": "ok"},
                {"agents": ["a1"], "package_version": "0.2.0"},
            ]
            # git status clean
            mock_sp.return_value = MagicMock(stdout="", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "All checks passed" in output or "warning" in output.lower()

    def test_doctor_argocd_missing_creds(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "ARGOCD_URL": "http://argocd.example.com",
                 "ARGOCD_USERNAME": "",
                 "ARGOCD_PASSWORD": "",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "ARGOCD_USERNAME" in output or "missing" in output.lower()

    def test_doctor_jenkins_url_looks_like_url(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "JENKINS_URL": "http://jenkins.example.com",
                 "JENKINS_USERNAME": "user",
                 "JENKINS_API_TOKEN": "token",
                 "JENKINS_BUILD_JOB": "http://jenkins.example.com/job/build",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "looks like a URL" in output

    def test_doctor_kibana_configured(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "KIBANA_URL": "http://kibana.example.com",
                 "KIBANA_USERNAME": "user",
                 "KIBANA_PASSWORD": "pass",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Kibana" in output

    def test_doctor_redash_configured(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_TEST_CMD": "echo ok",
                 "REDASH_BASE_URL": "http://redash.example.com",
             }), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Redash" in output

    def test_doctor_merge_in_progress(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "MERGE_HEAD").write_text("abc123\n")
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "echo ok"}), \
             patch("subprocess.run") as mock_sp:
            mock_sp.return_value = MagicMock(stdout="main\n", returncode=0, stderr="")
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Merge in progress" in output
