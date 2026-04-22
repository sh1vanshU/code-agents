"""Extra tests for cli_doctor.py — cover missing lines for workspace trust,
connectivity checks, git health, build/test detection."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _doctor_base_patches(**extra_env):
    """Return common patches for cmd_doctor."""
    env = {}
    env.update(extra_env)
    return {
        "load_env": patch("code_agents.cli.cli_doctor._load_env"),
        "user_cwd": patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"),
        "server_url": patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"),
        "api_get": patch("code_agents.cli.cli_doctor._api_get", return_value=None),
        "home": patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")),
        "which": patch("shutil.which", return_value="/usr/bin/git"),
        "env": patch.dict(os.environ, env, clear=True),
    }


class TestDoctorPythonVersion:
    """Lines 37-38: Python version check. Mocking sys.version_info is not
    feasible in Python 3.14 (TypeVar comparisons break), so we just verify
    the happy path is covered."""

    def test_python_current_version_ok(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Python" in output


class TestDoctorGlobalConfig:
    """Lines 87-88, 92-93: global/repo config missing."""

    def test_no_global_config(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", Path("/nonexistent/global.env")), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "No global config" in output or "code-agents init" in output


class TestDoctorWorkspaceTrust:
    """Lines 130, 147-161: Cursor workspace trust auto-fix."""

    def test_workspace_trust_needed_and_fixed(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            if "cursor-agent" in cmd[0]:
                if "--trust" in cmd:
                    result.stderr = ""  # Fixed
                else:
                    result.stderr = "Workspace Trust Required"
            return result

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=mock_run), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_BACKEND": "cursor",
                 "CURSOR_API_KEY": "sk-test1234567890",
             }, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "auto-trusted" in output

    def test_workspace_trust_fix_failed(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = "Workspace Trust Required"
            return result

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=mock_run), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_BACKEND": "cursor",
                 "CURSOR_API_KEY": "sk-test1234567890",
             }, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "auto-trust failed" in output

    def test_workspace_trust_exception(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=Exception("boom")), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_BACKEND": "cursor",
                 "CURSOR_API_KEY": "sk-test1234567890",
             }, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Could not check workspace trust" in output

    def test_workspace_already_trusted(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""  # No trust error = already trusted
            return result

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/cursor-agent"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=mock_run), \
             patch.dict(os.environ, {
                 "CODE_AGENTS_BACKEND": "cursor",
                 "CURSOR_API_KEY": "sk-test1234567890",
             }, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Workspace trusted" in output


class TestDoctorClaudeAgentSdk:
    """Lines 167-180: claude-agent-sdk and cursor-agent-sdk checks."""

    def test_claude_sdk_not_installed(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True), \
             patch.dict("sys.modules", {"claude_agent_sdk": None}):
            # Force ImportError for claude_agent_sdk
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "claude_agent_sdk":
                    raise ImportError("no module")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                cmd_doctor()
        output = capsys.readouterr().out
        assert "claude-agent-sdk" in output


class TestDoctorConnectivity:
    """Lines 316-390: Integration connectivity checks."""

    def test_jenkins_reachable(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JENKINS_URL": "http://jenkins.example.com",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "token",
        }
        mock_resp = MagicMock(status_code=200)
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True), \
             patch("requests.get", return_value=mock_resp):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Jenkins reachable" in output

    def test_jenkins_unreachable(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "JENKINS_URL": "http://jenkins.example.com",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "token",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True), \
             patch("requests.get", side_effect=ConnectionError("refused")):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Jenkins unreachable" in output

    def test_kibana_missing_creds(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "KIBANA_URL": "http://kibana.example.com",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "missing USERNAME or PASSWORD" in output

    def test_redash_configured(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {
            "REDASH_BASE_URL": "http://redash.example.com",
            "REDASH_API_KEY": "test-key",
        }
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Redash:" in output


class TestDoctorGitHealth:
    """Lines 413-446: Git health — behind remote, ahead, dirty tree."""

    def test_git_dirty_tree(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                result.stdout = "main"
            elif "status" in cmd and "--porcelain" in cmd:
                result.stdout = "M file.py\n?? new.py"
            elif "rev-list" in cmd:
                result.stdout = "0"
            else:
                result.stdout = ""
            return result

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=mock_run), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "modified/untracked" in output

    def test_git_behind_remote(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        call_count = [0]

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                result.stdout = "main"
            elif "status" in cmd:
                result.stdout = ""
            elif "rev-list" in cmd:
                if "HEAD..@{upstream}" in " ".join(cmd):
                    result.stdout = "3"  # 3 commits behind
                else:
                    result.stdout = "0"
            else:
                result.stdout = ""
            return result

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", side_effect=mock_run), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "behind remote" in output


class TestDoctorBuildTest:
    """Lines 492-531: Build/test timeout, exception, auto-detect."""

    def test_build_timeout(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {"CODE_AGENTS_BUILD_CMD": "sleep 999"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("cmd", 120)), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "timed out" in output

    def test_build_exception(self, capsys):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {"CODE_AGENTS_BUILD_CMD": "bad-cmd"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run",
                   side_effect=OSError("command not found")), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Build error" in output

    def test_test_auto_detect_maven(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        (tmp_path / "pom.xml").write_text("<project/>")

        mock_result = MagicMock(returncode=0, stdout="Tests passed\n", stderr="")

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Tests passed" in output

    def test_test_failed(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {"CODE_AGENTS_TEST_CMD": "pytest"}
        mock_result = MagicMock(returncode=1, stdout="3 failed\n", stderr="")

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Tests failed" in output

    def test_test_timeout(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {"CODE_AGENTS_TEST_CMD": "pytest"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("cmd", 120)), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "timed out" in output

    def test_test_exception(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        env = {"CODE_AGENTS_TEST_CMD": "bad-runner"}

        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch("code_agents.cli.cli_doctor.subprocess.run",
                   side_effect=OSError("not found")), \
             patch.dict(os.environ, env, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Test error" in output

    def test_log_directory_exists_no_file(self, capsys, tmp_path):
        from code_agents.cli.cli_doctor import cmd_doctor
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "Log directory exists" in output

    def test_summary_warnings_only(self, capsys):
        """Lines 539: warnings but no issues."""
        from code_agents.cli.cli_doctor import cmd_doctor
        with patch("code_agents.cli.cli_doctor._load_env"), \
             patch("code_agents.cli.cli_doctor._user_cwd", return_value="/"), \
             patch("code_agents.cli.cli_doctor._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_doctor._api_get", return_value=None), \
             patch("code_agents.cli.cli_doctor._find_code_agents_home", return_value=Path("/tmp/ca")), \
             patch("shutil.which", return_value="/usr/bin/git"), \
             patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test1234567890"}, clear=True):
            cmd_doctor()
        output = capsys.readouterr().out
        assert "warning" in output.lower() or "passed" in output.lower()
