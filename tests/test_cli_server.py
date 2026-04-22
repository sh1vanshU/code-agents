"""Tests for cli_server.py — start, shutdown, restart, status, agents, logs, config commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_colors():
    """Return color functions that are identity functions."""
    identity = lambda x: x
    return (identity, identity, identity, identity, identity, identity)


@pytest.fixture
def mock_env(tmp_path):
    """Set up minimal env for CLI commands."""
    env = {
        "CODE_AGENTS_USER_CWD": str(tmp_path),
        "HOST": "0.0.0.0",
        "PORT": "8000",
    }
    with patch.dict(os.environ, env, clear=False):
        yield tmp_path


# ---------------------------------------------------------------------------
# _start_background health check paths (lines 91-116)
# ---------------------------------------------------------------------------


class TestStartBackground:
    """Test _start_background backend validation and health check paths."""

    def test_backend_validation_success(self, tmp_path, capsys):
        """When validate_backend returns valid, prints verified line (line 91-92)."""
        from code_agents.cli.cli_server import _start_background

        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Backend" in out

    def test_backend_validation_failure_fallback_cursor(self, tmp_path, capsys):
        """When validate_backend raises, falls back to config check (lines 96-114)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no module")), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "CODE_AGENTS_BACKEND": "cursor",
                 "CURSOR_API_KEY": "sk-test-1234567890",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Backend" in out

    def test_backend_validation_failure_claude_cli(self, tmp_path, capsys):
        """When backend is claude-cli, check shutil.which (lines 99-106)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no")), \
             patch("shutil.which", return_value="/usr/bin/claude"), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "CODE_AGENTS_BACKEND": "claude-cli",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "claude-cli" in out

    def test_backend_validation_failure_claude_cli_not_found(self, tmp_path, capsys):
        """When backend is claude-cli and claude not found (lines 105-106)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no")), \
             patch("shutil.which", return_value=None), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "CODE_AGENTS_BACKEND": "claude-cli",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "not found" in out

    def test_backend_validation_failure_claude_api(self, tmp_path, capsys):
        """When backend is claude and anthropic key set (lines 107-109)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no")), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "CODE_AGENTS_BACKEND": "claude",
                 "ANTHROPIC_API_KEY": "sk-ant-1234567890",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "claude API" in out

    def test_backend_validation_failure_no_key(self, tmp_path, capsys):
        """When no API key configured (line 116)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        env = {
            "PORT": "8000", "HOST": "0.0.0.0",
            "CODE_AGENTS_BACKEND": "cursor",
        }
        # Remove keys that might be set
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("CURSOR_API_KEY", "ANTHROPIC_API_KEY")}
        clean_env.update(env)

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no")), \
             patch.dict(os.environ, clean_env, clear=True):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "not configured" in out

    def test_backend_validation_failure_fallback_local_url(self, tmp_path, capsys):
        """When validate_backend raises and backend is local with URL, config fallback succeeds."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no module")), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "CODE_AGENTS_BACKEND": "local",
                 "CODE_AGENTS_LOCAL_LLM_URL": "http://127.0.0.1:11434/v1",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Backend: local" in out

    def test_model_display_backend_not_ok(self, tmp_path, capsys):
        """Model line when backend not verified (line 126)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200

        env = {
            "PORT": "8000", "HOST": "0.0.0.0",
            "CODE_AGENTS_BACKEND": "cursor",
            "CODE_AGENTS_MODEL": "test-model",
        }
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("CURSOR_API_KEY", "ANTHROPIC_API_KEY")}
        clean_env.update(env)

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", side_effect=Exception("no")), \
             patch.dict(os.environ, clean_env, clear=True):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "test-model" in out

    def test_agents_diagnostics_empty(self, tmp_path, capsys):
        """When diagnostics shows 0 agents (lines 139-141)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health_ok = MagicMock()
        mock_health_ok.status_code = 200

        mock_diag = MagicMock()
        mock_diag.status_code = 200
        mock_diag.json.return_value = {"agents": []}

        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        call_count = [0]
        def httpx_get_side_effect(url, **kwargs):
            call_count[0] += 1
            if "/diagnostics" in url:
                return mock_diag
            return mock_health_ok

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", side_effect=httpx_get_side_effect), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Agents" in out

    def test_agents_diagnostics_exception(self, tmp_path, capsys):
        """When diagnostics endpoint throws (line 140-141)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        call_count = [0]
        def httpx_get_side_effect(url, **kwargs):
            call_count[0] += 1
            if "/diagnostics" in url:
                raise Exception("timeout")
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", side_effect=httpx_get_side_effect), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "checking" in out

    def test_integrations_configured(self, tmp_path, capsys):
        """When integrations are configured (lines 154-160)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200
        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, {
                 "PORT": "8000", "HOST": "0.0.0.0",
                 "JENKINS_URL": "http://jenkins",
                 "ARGOCD_URL": "http://argocd",
             }):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Jenkins" in out

    def test_no_integrations(self, tmp_path, capsys):
        """When no integrations configured (line 160)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200
        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("JENKINS_URL", "ARGOCD_URL", "JIRA_URL", "KIBANA_URL", "REDASH_BASE_URL")}
        clean_env.update({"PORT": "8000", "HOST": "0.0.0.0"})

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, clean_env, clear=True):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "none configured" in out

    def test_git_branch_exception(self, tmp_path, capsys):
        """When git branch detection fails (lines 170-171)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200
        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        # Create .git dir
        (tmp_path / ".git").mkdir()

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch("subprocess.run", side_effect=Exception("git fail")), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Git" in out

    def test_config_legacy_env(self, tmp_path, capsys):
        """When legacy .env.code-agents exists (line 181)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        mock_health = MagicMock()
        mock_health.status_code = 200
        mock_result = SimpleNamespace(valid=True, backend="cursor", message="ok")

        # Create legacy config
        (tmp_path / ".env.code-agents").write_text("FOO=bar\n")

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch("code_agents.core.env_loader.repo_config_path", return_value=tmp_path / "nonexistent"), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "Config" in out

    def test_server_failed_to_start(self, tmp_path, capsys):
        """When server process exits immediately (lines 318-323 area)."""
        from code_agents.cli.cli_server import _start_background

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "failed to start" in out

    def test_validation_not_valid(self, tmp_path, capsys):
        """When validate_backend returns not valid (line 95)."""
        from code_agents.cli.cli_server import _start_background

        mock_result = SimpleNamespace(valid=False, backend="cursor", message="timeout")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 99

        mock_health = MagicMock()
        mock_health.status_code = 200

        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._find_code_agents_home", return_value=tmp_path), \
             patch("code_agents.core.env_loader.load_all_env"), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("time.sleep"), \
             patch("httpx.get", return_value=mock_health), \
             patch("asyncio.run", return_value=mock_result), \
             patch.dict(os.environ, {"PORT": "8000", "HOST": "0.0.0.0"}):
            (tmp_path / "logs").mkdir(exist_ok=True)
            _start_background(str(tmp_path))

        out = capsys.readouterr().out
        assert "timeout" in out


# ---------------------------------------------------------------------------
# cmd_agents (line 406)
# ---------------------------------------------------------------------------


class TestCmdAgents:
    def test_agents_dict_response(self, capsys):
        """When server returns non-list, non-dict data for agents (line 406)."""
        from code_agents.cli.cli_server import cmd_agents
        with patch("code_agents.cli.cli_server._colors", return_value=tuple(lambda x: x for _ in range(6))), \
             patch("code_agents.cli.cli_server._load_env"), \
             patch("code_agents.cli.cli_server._api_get", return_value="unexpected_string"):
            cmd_agents()
        out = capsys.readouterr().out
        assert "0" in out  # 0 agents
