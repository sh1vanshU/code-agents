"""Tests for setup/* modules — setup.py, setup_env.py, setup_ui.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# setup_ui.py tests
# ═══════════════════════════════════════════════════════════════════════════


class TestColorHelpers:
    """Test ANSI color wrapping functions."""

    def test_bold(self):
        from code_agents.setup.setup_ui import _wrap
        result = _wrap("1", "hello")
        # Either wrapped or plain depending on isatty
        assert "hello" in result

    def test_green(self):
        from code_agents.setup.setup_ui import green
        assert "test" in green("test")

    def test_yellow(self):
        from code_agents.setup.setup_ui import yellow
        assert "test" in yellow("test")

    def test_red(self):
        from code_agents.setup.setup_ui import red
        assert "test" in red("test")

    def test_cyan(self):
        from code_agents.setup.setup_ui import cyan
        assert "test" in cyan("test")

    def test_dim(self):
        from code_agents.setup.setup_ui import dim
        assert "test" in dim("test")

    def test_bold_fn(self):
        from code_agents.setup.setup_ui import bold
        assert "test" in bold("test")


class TestValidators:
    """Test input validators."""

    def test_validate_url_valid(self):
        from code_agents.setup.setup_ui import validate_url
        assert validate_url("https://example.com") is True
        assert validate_url("http://localhost:8080") is True

    def test_validate_url_invalid(self):
        from code_agents.setup.setup_ui import validate_url
        assert validate_url("not-a-url") is False
        assert validate_url("") is False

    def test_validate_port_valid(self):
        from code_agents.setup.setup_ui import validate_port
        assert validate_port("8000") is True
        assert validate_port("1") is True
        assert validate_port("65535") is True

    def test_validate_port_invalid(self):
        from code_agents.setup.setup_ui import validate_port
        assert validate_port("0") is False
        assert validate_port("70000") is False
        assert validate_port("abc") is False

    def test_validate_job_path_valid(self):
        from code_agents.setup.setup_ui import validate_job_path
        assert validate_job_path("folder/my-job") is True
        assert validate_job_path("my-job") is True

    def test_validate_job_path_url_rejected(self):
        from code_agents.setup.setup_ui import validate_job_path
        assert validate_job_path("https://jenkins.com/job/x") is False
        assert validate_job_path("http://jenkins.com/job/x") is False

    def test_validate_job_path_empty(self):
        from code_agents.setup.setup_ui import validate_job_path
        assert validate_job_path("/") is False


class TestCleanJobPath:
    """Test Jenkins job path cleaning."""

    def test_already_clean(self):
        from code_agents.setup.setup_ui import clean_job_path
        assert clean_job_path("folder/my-service") == "folder/my-service"

    def test_strips_job_prefix(self):
        from code_agents.setup.setup_ui import clean_job_path
        result = clean_job_path("job/folder/job/my-service")
        assert result == "folder/my-service"

    def test_single_job_prefix(self):
        from code_agents.setup.setup_ui import clean_job_path
        result = clean_job_path("job/my-service")
        assert result == "my-service"

    def test_trailing_slashes(self):
        from code_agents.setup.setup_ui import clean_job_path
        result = clean_job_path("/folder/my-service/")
        assert result == "folder/my-service"


class TestPrompt:
    """Test the prompt() function with mocked input."""

    def test_prompt_default(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", return_value=""):
            result = prompt("Test", default="default_val")
        assert result == "default_val"

    def test_prompt_user_input(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", return_value="my_value"):
            result = prompt("Test")
        assert result == "my_value"

    def test_prompt_required_retries(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", side_effect=["", "", "finally"]):
            result = prompt("Test", required=True)
        assert result == "finally"

    def test_prompt_validator_retries(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", side_effect=["bad", "8000"]):
            from code_agents.setup.setup_ui import validate_port
            result = prompt("Port", validator=validate_port)
        assert result == "8000"

    def test_prompt_secret(self):
        from code_agents.setup.setup_ui import prompt
        with patch("getpass.getpass", return_value="secret123"):
            result = prompt("Key", secret=True)
        assert result == "secret123"

    def test_prompt_transform(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", return_value="  VALUE  "):
            result = prompt("Test", transform=lambda v: v.lower())
        assert result == "value"

    def test_prompt_eof_returns_empty(self):
        from code_agents.setup.setup_ui import prompt
        with patch("builtins.input", side_effect=EOFError):
            result = prompt("Test", default="fallback")
        assert result == "fallback"


class TestPromptYesNo:
    """Test yes/no prompt."""

    def test_default_yes(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", return_value=""):
            assert prompt_yes_no("Continue?", default=True) is True

    def test_default_no(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", return_value=""):
            assert prompt_yes_no("Continue?", default=False) is False

    def test_yes_input(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", return_value="y"):
            assert prompt_yes_no("Continue?") is True

    def test_no_input(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", return_value="no"):
            assert prompt_yes_no("Continue?") is False

    def test_invalid_then_valid(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", side_effect=["maybe", "y"]):
            assert prompt_yes_no("Continue?") is True

    def test_eof_returns_default(self):
        from code_agents.setup.setup_ui import prompt_yes_no
        with patch("builtins.input", side_effect=EOFError):
            assert prompt_yes_no("Continue?", default=True) is True


class TestPromptChoice:
    """Test numbered choice prompt."""

    def test_default_choice(self):
        from code_agents.setup.setup_ui import prompt_choice
        with patch("builtins.input", return_value=""):
            result = prompt_choice("Pick", ["A", "B", "C"], default=2)
        assert result == 2

    def test_explicit_choice(self):
        from code_agents.setup.setup_ui import prompt_choice
        with patch("builtins.input", return_value="3"):
            result = prompt_choice("Pick", ["A", "B", "C"])
        assert result == 3

    def test_invalid_then_valid(self):
        from code_agents.setup.setup_ui import prompt_choice
        with patch("builtins.input", side_effect=["5", "abc", "1"]):
            result = prompt_choice("Pick", ["A", "B", "C"])
        assert result == 1

    def test_eof_returns_default(self):
        from code_agents.setup.setup_ui import prompt_choice
        with patch("builtins.input", side_effect=EOFError):
            result = prompt_choice("Pick", ["A", "B"], default=1)
        assert result == 1


# ═══════════════════════════════════════════════════════════════════════════
# setup_env.py tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMergedConfigForCwd:
    def test_centralized_overrides_global(self, tmp_path, monkeypatch):
        from code_agents.setup.setup_env import merged_config_for_cwd
        from code_agents.core import env_loader

        fake_global = tmp_path / "g.env"
        fake_global.write_text("CODE_AGENTS_BACKEND=cursor\nCODE_AGENTS_CLAUDE_CLI_MODEL=old-model\n")
        monkeypatch.setattr(env_loader, "GLOBAL_ENV_PATH", fake_global)

        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        central = env_loader.repo_config_path(str(tmp_path))
        central.parent.mkdir(parents=True, exist_ok=True)
        central.write_text("CODE_AGENTS_BACKEND=claude-cli\n")

        merged = merged_config_for_cwd(str(tmp_path))
        assert merged["CODE_AGENTS_BACKEND"] == "claude-cli"
        assert merged["CODE_AGENTS_CLAUDE_CLI_MODEL"] == "old-model"


class TestParseEnvFile:
    """Test .env file parsing."""

    def test_parse_basic(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\nBAZ=qux\n")
        result = parse_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_parse_quoted_values(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text('KEY1="value one"\nKEY2=\'value two\'\n')
        result = parse_env_file(env_file)
        assert result["KEY1"] == "value one"
        assert result["KEY2"] == "value two"

    def test_parse_skips_comments(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nKEY=val\n# another\n")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}

    def test_parse_skips_blank_lines(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nKEY=val\n\n")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}

    def test_parse_nonexistent_file(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        result = parse_env_file(tmp_path / "missing.env")
        assert result == {}

    def test_parse_values_with_equals(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text("URL=http://host:8000/path?a=1\n")
        result = parse_env_file(env_file)
        assert result["URL"] == "http://host:8000/path?a=1"

    def test_parse_spaces_around_equals(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        env_file = tmp_path / ".env"
        env_file.write_text("KEY = value\n")
        result = parse_env_file(env_file)
        assert result["KEY"] == "value"

    def test_parse_directory_returns_empty(self, tmp_path):
        from code_agents.setup.setup_env import parse_env_file
        result = parse_env_file(tmp_path)
        assert result == {}


class TestWriteEnvToPath:
    """Test _write_env_to_path section-grouped writing."""

    def test_write_new_file(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        env_vars = {"HOST": "0.0.0.0", "PORT": "8000", "CURSOR_API_KEY": "sk-test"}
        _write_env_to_path(env_path, env_vars, "test config")
        content = env_path.read_text()
        assert "HOST=0.0.0.0" in content
        assert "PORT=8000" in content
        assert "CURSOR_API_KEY=sk-test" in content
        assert "# Server" in content
        assert "# Core" in content

    def test_write_creates_parent_dirs(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / "sub" / "dir" / ".env"
        _write_env_to_path(env_path, {"HOST": "localhost"}, "nested")
        assert env_path.exists()

    def test_write_with_spaces_in_value(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        _write_env_to_path(env_path, {"MY_VAR": "has spaces"}, "test")
        content = env_path.read_text()
        assert 'MY_VAR="has spaces"' in content

    def test_write_with_double_quotes_in_value(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        _write_env_to_path(env_path, {"MY_VAR": 'has "quotes"'}, "test")
        content = env_path.read_text()
        assert "MY_VAR='has \"quotes\"'" in content

    def test_write_remaining_section(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        _write_env_to_path(env_path, {"CUSTOM_KEY": "custom_val"}, "test")
        content = env_path.read_text()
        assert "# Other" in content
        assert "CUSTOM_KEY=custom_val" in content

    def test_merge_existing(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        env_path.write_text("HOST=old_host\n")
        # Simulate merge: user picks "m"
        with patch("builtins.input", return_value="m"):
            _write_env_to_path(env_path, {"PORT": "9000"}, "test")
        content = env_path.read_text()
        assert "HOST=old_host" in content
        assert "PORT=9000" in content

    def test_overwrite_existing(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        env_path.write_text("HOST=old_host\n")
        # Source auto-merges: existing keys preserved, new keys added
        _write_env_to_path(env_path, {"PORT": "9000"}, "test")
        content = env_path.read_text()
        assert "HOST=old_host" in content  # preserved via auto-merge
        assert "PORT=9000" in content

    def test_unset_keys_remove_stale_vars(self, tmp_path):
        from code_agents.setup.setup_env import _write_env_to_path
        env_path = tmp_path / ".env"
        env_path.write_text(
            "CODE_AGENTS_BACKEND=claude-cli\nCODE_AGENTS_CLAUDE_CLI_MODEL=claude-opus-4-6\n",
        )
        with patch("builtins.print"):
            _write_env_to_path(
                env_path,
                {"CODE_AGENTS_BACKEND": "cursor", "CURSOR_API_KEY": "sk"},
                "test",
                unset_keys={"CODE_AGENTS_CLAUDE_CLI_MODEL"},
            )
        content = env_path.read_text()
        assert "CODE_AGENTS_BACKEND=cursor" in content
        assert "CURSOR_API_KEY=sk" in content
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" not in content


class TestEnvSections:
    def test_sections_defined(self):
        from code_agents.setup.setup_env import _ENV_SECTIONS
        assert isinstance(_ENV_SECTIONS, list)
        assert len(_ENV_SECTIONS) > 0
        for section_name, keys in _ENV_SECTIONS:
            assert section_name.startswith("#")
            assert isinstance(keys, list)


# ═══════════════════════════════════════════════════════════════════════════
# setup.py tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckPython:
    """Test Python version check."""

    def test_check_python_passes(self):
        from code_agents.setup.setup import check_python
        # Current Python is >= 3.10 (or tests wouldn't run), so should not exit
        check_python()

    def test_check_python_old_version(self):
        from code_agents.setup.setup import check_python

        class FakeVersionInfo(tuple):
            major = 3
            minor = 8
            micro = 0

        fake_version = FakeVersionInfo((3, 8, 0))
        with patch.object(sys, "version_info", fake_version):
            with pytest.raises(SystemExit):
                check_python()


class TestDetectTargetRepo:
    def test_detect_git_repo_yes(self, tmp_path):
        from code_agents.setup.setup import detect_target_repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("os.getcwd", return_value=str(tmp_path)):
            with patch("code_agents.setup.setup.prompt_yes_no", return_value=True):
                result = detect_target_repo()
        assert result["TARGET_REPO_PATH"] == str(tmp_path)

    def test_detect_git_repo_no_manual(self, tmp_path):
        from code_agents.setup.setup import detect_target_repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("os.getcwd", return_value=str(tmp_path)):
            with patch("code_agents.setup.setup.prompt_yes_no", return_value=False):
                with patch("code_agents.setup.setup.prompt", return_value="/other/path"):
                    result = detect_target_repo()
        assert result["TARGET_REPO_PATH"] == "/other/path"

    def test_detect_no_git_dir(self, tmp_path):
        from code_agents.setup.setup import detect_target_repo
        with patch("os.getcwd", return_value=str(tmp_path)):
            with patch("code_agents.setup.setup.prompt", return_value=str(tmp_path)):
                result = detect_target_repo()
        assert result["TARGET_REPO_PATH"] == str(tmp_path)


class TestPromptBackendKeys:
    def test_local_llm(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_choice", return_value=1):
            with patch(
                "code_agents.setup.setup.prompt",
                side_effect=["http://127.0.0.1:11434/v1", "local", "qwen2.5-coder:7b"],
            ):
                result, unset = prompt_backend_keys()
        assert result["CODE_AGENTS_BACKEND"] == "local"
        assert result["CODE_AGENTS_LOCAL_LLM_URL"] == "http://127.0.0.1:11434/v1"
        assert result["CODE_AGENTS_MODEL"] == "qwen2.5-coder:7b"
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in unset

    def test_cursor_only(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_choice", return_value=2):
            with patch("code_agents.setup.setup.prompt", side_effect=["sk-key", ""]):
                result, unset = prompt_backend_keys()
        assert result["CURSOR_API_KEY"] == "sk-key"
        assert "ANTHROPIC_API_KEY" not in result
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in unset

    def test_claude_only(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_choice", return_value=3):
            with patch("code_agents.setup.setup.prompt", return_value="ant-key"):
                result, unset = prompt_backend_keys()
        assert result["ANTHROPIC_API_KEY"] == "ant-key"
        assert "CURSOR_API_KEY" not in result
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in unset

    def test_claude_cli(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_choice", side_effect=[4, 2]):
            result, unset = prompt_backend_keys()
        assert result["CODE_AGENTS_BACKEND"] == "claude-cli"
        assert result["CODE_AGENTS_CLAUDE_CLI_MODEL"] == "claude-sonnet-4-6"
        assert unset == frozenset()

    def test_both_backends(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_choice", return_value=5):
            with patch("code_agents.setup.setup.prompt", side_effect=["sk-key", "http://example.com", "ant-key"]):
                result, unset = prompt_backend_keys()
        assert "CURSOR_API_KEY" in result
        assert "ANTHROPIC_API_KEY" in result
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in unset


class TestPromptServerConfig:
    def test_default_values(self):
        from code_agents.setup.setup import prompt_server_config
        with patch("code_agents.setup.setup.prompt", side_effect=["0.0.0.0", "8000"]):
            result = prompt_server_config()
        assert result == {"HOST": "0.0.0.0", "PORT": "8000"}


class TestPromptCicdPipeline:
    def test_skip_all(self):
        from code_agents.setup.setup import prompt_cicd_pipeline
        with patch("code_agents.setup.setup.prompt_yes_no", return_value=False):
            result = prompt_cicd_pipeline()
        assert result == {}

    def test_jenkins_configured(self):
        from code_agents.setup.setup import prompt_cicd_pipeline
        yes_no_responses = [True, False, False]  # Jenkins yes, ArgoCD no, Testing no
        prompt_responses = ["https://jenkins.com", "admin", "token123", "folder/job", "folder/job"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no_responses):
            with patch("code_agents.setup.setup.prompt", side_effect=prompt_responses):
                result = prompt_cicd_pipeline()
        assert result["JENKINS_URL"] == "https://jenkins.com"
        assert result["JENKINS_USERNAME"] == "admin"


class TestPromptIntegrations:
    def test_skip_all(self):
        from code_agents.setup.setup import prompt_integrations
        with patch("code_agents.setup.setup.prompt_yes_no", return_value=False):
            result = prompt_integrations()
        assert result == {}


class TestPrintBanner:
    def test_print_banner_runs(self, capsys):
        from code_agents.setup.setup import print_banner
        print_banner()
        captured = capsys.readouterr()
        assert "Code Agents" in captured.out


class TestMain:
    def test_keyboard_interrupt(self):
        from code_agents.setup.setup import main
        with patch("code_agents.setup.setup.print_banner", side_effect=KeyboardInterrupt):
            with pytest.raises(SystemExit):
                main()

    def test_eof_error(self):
        from code_agents.setup.setup import main
        with patch("code_agents.setup.setup.print_banner", side_effect=EOFError):
            with pytest.raises(SystemExit):
                main()


# ═══════════════════════════════════════════════════════════════════════════
# Additional setup.py tests for coverage
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckDependencies:
    """Test check_dependencies step."""

    def test_all_installed(self):
        from code_agents.setup.setup import check_dependencies
        # All deps (fastapi, uvicorn, etc.) are installed in test env
        check_dependencies()

    def test_all_deps_installed_passes(self):
        """When all deps are installed, check_dependencies succeeds."""
        from code_agents.setup.setup import check_dependencies
        # In test environment, all deps are installed, so this should pass
        check_dependencies()  # no SystemExit


class TestPromptIntegrationsDetailed:
    """Test integration prompts in detail."""

    def test_elasticsearch_configured(self):
        from code_agents.setup.setup import prompt_integrations
        yes_no = [True, False, False]  # ES yes, Atlassian no, Redash no
        prompts = ["https://elastic.example.com", "api-key-123"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_integrations()
        assert result["ELASTICSEARCH_URL"] == "https://elastic.example.com"
        assert result["ELASTICSEARCH_API_KEY"] == "api-key-123"

    def test_atlassian_configured(self):
        from code_agents.setup.setup import prompt_integrations
        yes_no = [False, True, False]  # ES no, Atlassian yes, Redash no
        prompts = ["client-id", "client-secret", "https://company.atlassian.net"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_integrations()
        assert result["ATLASSIAN_OAUTH_CLIENT_ID"] == "client-id"
        assert result["ATLASSIAN_CLOUD_SITE_URL"] == "https://company.atlassian.net"

    def test_redash_with_api_key(self):
        from code_agents.setup.setup import prompt_integrations
        yes_no = [False, False, True]  # ES no, Atlassian no, Redash yes
        prompts = ["https://redash.example.com", "redash-key"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_integrations()
        assert result["REDASH_BASE_URL"] == "https://redash.example.com"
        assert result["REDASH_API_KEY"] == "redash-key"

    def test_redash_with_credentials(self):
        from code_agents.setup.setup import prompt_integrations
        yes_no = [False, False, True]  # ES no, Atlassian no, Redash yes
        prompts = ["https://redash.example.com", "", "myuser", "mypass"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_integrations()
        assert result["REDASH_USERNAME"] == "myuser"
        assert result["REDASH_PASSWORD"] == "mypass"


class TestPromptCicdDetailed:
    """Test CI/CD pipeline prompts in detail."""

    def test_argocd_configured(self):
        from code_agents.setup.setup import prompt_cicd_pipeline
        # Jenkins no, ArgoCD yes, pattern correct? yes, Testing no
        yes_no = [False, True, True, False]
        prompts = ["https://argocd.example.com", "admin", "secret"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_cicd_pipeline()
        assert result["ARGOCD_URL"] == "https://argocd.example.com"
        assert result["ARGOCD_APP_PATTERN"] == "{env}-project-bombay-{app}"

    def test_testing_configured(self):
        from code_agents.setup.setup import prompt_cicd_pipeline
        yes_no = [False, False, True]  # Jenkins no, ArgoCD no, Testing yes
        prompts = ["pytest --cov", "80"]
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_cicd_pipeline()
        assert result["TARGET_TEST_COMMAND"] == "pytest --cov"
        assert result["TARGET_COVERAGE_THRESHOLD"] == "80"

    def test_testing_default_threshold(self):
        from code_agents.setup.setup import prompt_cicd_pipeline
        yes_no = [False, False, True]  # Jenkins no, ArgoCD no, Testing yes
        prompts = ["", "100"]  # blank test cmd, default threshold
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=yes_no):
            with patch("code_agents.setup.setup.prompt", side_effect=prompts):
                result = prompt_cicd_pipeline()
        assert "TARGET_TEST_COMMAND" not in result
        # 100 is default, so not stored
        assert "TARGET_COVERAGE_THRESHOLD" not in result


class TestStartServer:
    """Test start_server function."""

    def test_start_server_loads_env(self):
        from code_agents.setup.setup import start_server
        with patch("code_agents.core.main.main", side_effect=KeyboardInterrupt):
            with patch("dotenv.load_dotenv"):
                try:
                    start_server()
                except KeyboardInterrupt:
                    pass


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------


class TestInstallDepsPoetryFail:
    """Lines 85-86: poetry install fails."""

    def test_poetry_install_fails(self, capsys):
        from code_agents.setup.setup import check_dependencies
        import shutil
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error installing"
        with patch("shutil.which", return_value="/usr/bin/poetry"), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("subprocess.run", return_value=mock_result):
            # Temporarily make check_dependencies think "yaml" is missing
            # by patching the missing list directly
            import code_agents.setup.setup as _setup_mod
            _orig_fn = _setup_mod.check_dependencies
            def _patched():
                """Inject missing package to trigger poetry install path."""
                import builtins
                _orig = builtins.__import__
                def _fi(name, *a, **kw):
                    if name == "yaml":
                        raise ImportError("no yaml")
                    return _orig(name, *a, **kw)
                builtins.__import__ = _fi
                try:
                    _orig_fn()
                finally:
                    builtins.__import__ = _orig
            with pytest.raises(SystemExit):
                _patched()

    def test_poetry_install_skipped(self, capsys):
        """Line 88: user skips poetry install."""
        from code_agents.setup.setup import check_dependencies
        with patch("shutil.which", return_value="/usr/bin/poetry"), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=False):
            import builtins
            _orig = builtins.__import__
            def _fi(name, *a, **kw):
                if name == "yaml":
                    raise ImportError("no yaml")
                return _orig(name, *a, **kw)
            builtins.__import__ = _fi
            try:
                check_dependencies()
            finally:
                builtins.__import__ = _orig
        output = capsys.readouterr().out
        assert "Skipping" in output


class TestInstallDepsPip:
    """Lines 90-106: pip fallback path."""

    def test_pip_install_success(self, capsys, tmp_path):
        from code_agents.setup.setup import install_deps
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("shutil.which", return_value=None), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("subprocess.run", return_value=mock_result), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("os.path.isfile", return_value=False):
            install_deps()
        output = capsys.readouterr().out
        assert "Dependencies installed" in output or "pip" in output.lower()

    def test_pip_install_fail(self, capsys, tmp_path):
        """Lines 101-102: pip install fails."""
        from code_agents.setup.setup import install_deps
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "pip error"
        with patch("shutil.which", return_value=None), \
             patch("code_agents.setup.setup.prompt_yes_no", return_value=True), \
             patch("subprocess.run", return_value=mock_result), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.__init__", return_value=None), \
             patch("os.path.isfile", return_value=False):
            with pytest.raises(SystemExit):
                install_deps()

    def test_no_poetry_no_requirements(self, capsys):
        """Lines 104-106: neither poetry nor requirements.txt."""
        from code_agents.setup.setup import install_deps
        with patch("shutil.which", return_value=None), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("os.path.isfile", return_value=False):
            with pytest.raises(SystemExit):
                install_deps()


class TestDiscoverModels:
    """Lines 166: _discover_claude_cli_models sort key."""

    def test_discover_models_sort_order(self):
        from code_agents.setup.setup import _discover_claude_cli_models
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "claude-haiku-3\nclaude-sonnet-3\nclaude-opus-3\nclaude-unknown-1\n"
        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("subprocess.run", return_value=mock_result):
            models = _discover_claude_cli_models()
        assert models[0] == "claude-opus-3"
        assert models[1] == "claude-sonnet-3"
        assert models[2] == "claude-haiku-3"
        assert models[3] == "claude-unknown-1"


class TestPromptBackendKeysModelDisplay:
    """Line 237: model display with haiku label."""

    def test_model_display_labels(self):
        from code_agents.setup.setup import prompt_backend_keys
        with patch("code_agents.setup.setup.prompt_yes_no", side_effect=[False, True, False, False, False]), \
             patch("code_agents.setup.setup._discover_claude_models", return_value=["claude-opus-3", "claude-sonnet-3", "claude-haiku-3", "claude-other"]), \
             patch("code_agents.setup.setup.prompt_choice", side_effect=[4, 2]), \
             patch("shutil.which", return_value="/usr/bin/claude"):
            result, _ = prompt_backend_keys()
        assert "CODE_AGENTS_CLAUDE_CLI_MODEL" in result


class TestMainEntryPoint:
    """Line 465: __main__ entry point."""

    def test_main_function_exists(self):
        from code_agents.setup.setup import main
        assert callable(main)
