"""Tests for code_agents.sandbox — macOS sandbox-exec wrapper."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from code_agents.devops.sandbox import (
    generate_sandbox_profile,
    is_sandbox_available,
    is_sandbox_enabled,
    wrap_command,
)


# ---------------------------------------------------------------------------
# is_sandbox_available
# ---------------------------------------------------------------------------

class TestIsSandboxAvailable:
    def test_macos_with_binary(self):
        with patch("code_agents.devops.sandbox.platform.system", return_value="Darwin"), \
             patch("code_agents.devops.sandbox.os.path.exists", return_value=True):
            assert is_sandbox_available() is True

    def test_macos_without_binary(self):
        with patch("code_agents.devops.sandbox.platform.system", return_value="Darwin"), \
             patch("code_agents.devops.sandbox.os.path.exists", return_value=False):
            assert is_sandbox_available() is False

    def test_linux(self):
        with patch("code_agents.devops.sandbox.platform.system", return_value="Linux"):
            assert is_sandbox_available() is False

    def test_windows(self):
        with patch("code_agents.devops.sandbox.platform.system", return_value="Windows"):
            assert is_sandbox_available() is False


# ---------------------------------------------------------------------------
# is_sandbox_enabled
# ---------------------------------------------------------------------------

class TestIsSandboxEnabled:
    def test_enabled_with_1(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}):
            assert is_sandbox_enabled() is True

    def test_enabled_with_true(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "true"}):
            assert is_sandbox_enabled() is True

    def test_enabled_with_yes(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "YES"}):
            assert is_sandbox_enabled() is True

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_SANDBOX", None)
            assert is_sandbox_enabled() is False

    def test_disabled_with_0(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "0"}):
            assert is_sandbox_enabled() is False

    def test_disabled_with_no(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "no"}):
            assert is_sandbox_enabled() is False

    def test_whitespace_trimmed(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "  true  "}):
            assert is_sandbox_enabled() is True


# ---------------------------------------------------------------------------
# generate_sandbox_profile
# ---------------------------------------------------------------------------

class TestGenerateSandboxProfile:
    def test_contains_deny_default(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(deny default)" in profile

    def test_contains_version(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(version 1)" in profile

    def test_contains_cwd_realpath(self, tmp_path):
        cwd = str(tmp_path / "myproject")
        profile = generate_sandbox_profile(cwd)
        assert os.path.realpath(cwd) in profile

    def test_allows_read_broadly(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(allow file-read*)" in profile

    def test_restricts_write_to_cwd_and_tmp(self):
        profile = generate_sandbox_profile("/Users/dev/repo")
        assert '(subpath "/Users/dev/repo")' in profile
        assert '(subpath "/tmp")' in profile
        assert '(subpath "/private/tmp")' in profile
        assert '(subpath "/private/var/folders")' in profile

    def test_allows_network_by_default(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(allow network*)" in profile

    def test_denies_network_when_requested(self):
        profile = generate_sandbox_profile("/tmp/project", allow_network=False)
        assert "(deny network*)" in profile
        assert "(allow network*)" not in profile

    def test_allows_process(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(allow process*)" in profile

    def test_allows_system_services(self):
        profile = generate_sandbox_profile("/tmp/project")
        assert "(allow sysctl-read)" in profile
        assert "(allow mach-lookup)" in profile
        assert "(allow ipc-posix*)" in profile


# ---------------------------------------------------------------------------
# wrap_command
# ---------------------------------------------------------------------------

class TestWrapCommand:
    def test_returns_original_when_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_SANDBOX", None)
            assert wrap_command("echo hello", "/tmp") == "echo hello"

    def test_wraps_when_enabled_and_available(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=True):
            result = wrap_command("echo hello", "/tmp")
            assert result.startswith("sandbox-exec -p '")
            assert "/bin/bash -c" in result
            assert "echo hello" in result

    def test_returns_original_on_non_macos(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=False):
            assert wrap_command("echo hello", "/tmp") == "echo hello"

    def test_preserves_command_in_quotes(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=True):
            result = wrap_command("ls -la | grep foo", "/tmp")
            assert "ls -la | grep foo" in result

    def test_handles_single_quotes_in_command(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=True):
            result = wrap_command("echo 'hello world'", "/tmp")
            assert "sandbox-exec" in result

    def test_network_restriction_passed_through(self):
        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=True):
            result = wrap_command("curl example.com", "/tmp", allow_network=False)
            assert "(deny network*)" in result


# ---------------------------------------------------------------------------
# BashTool integration
# ---------------------------------------------------------------------------

class TestBashToolSandboxIntegration:
    def test_execute_uses_sandbox_when_enabled(self):
        from code_agents.agent_system.bash_tool import BashTool

        with patch.dict(os.environ, {"CODE_AGENTS_SANDBOX": "1"}), \
             patch("code_agents.devops.sandbox.is_sandbox_available", return_value=True), \
             patch("code_agents.agent_system.bash_tool.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {
                "stdout": "", "stderr": "", "returncode": 0,
            })()
            tool = BashTool(cwd="/tmp")
            result = tool.execute("echo hi")

            called_cmd = mock_run.call_args[0][0]
            assert "sandbox-exec" in called_cmd
            # BashResult stores the original command
            assert result.command == "echo hi"

    def test_execute_no_sandbox_by_default(self):
        from code_agents.agent_system.bash_tool import BashTool

        with patch.dict(os.environ, {}, clear=False), \
             patch("code_agents.agent_system.bash_tool.subprocess.run") as mock_run:
            os.environ.pop("CODE_AGENTS_SANDBOX", None)
            mock_run.return_value = type("R", (), {
                "stdout": "hi", "stderr": "", "returncode": 0,
            })()
            tool = BashTool(cwd="/tmp")
            result = tool.execute("echo hi")

            called_cmd = mock_run.call_args[0][0]
            assert called_cmd == "echo hi"
            assert result.command == "echo hi"
