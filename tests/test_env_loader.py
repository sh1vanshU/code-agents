"""Tests for env_loader.py — centralized .env configuration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.core.env_loader import (
    GLOBAL_VARS,
    REPO_VARS,
    RUNTIME_VARS,
    PER_REPO_FILENAME,
    load_all_env,
    split_vars,
)


class TestSplitVars:
    """Test variable classification into global vs per-repo."""

    def test_api_keys_are_global(self):
        g, r = split_vars({
            "CURSOR_API_KEY": "sk-123",
            "ANTHROPIC_API_KEY": "sk-456",
        })
        assert "CURSOR_API_KEY" in g
        assert "ANTHROPIC_API_KEY" in g
        assert r == {}

    def test_jenkins_creds_are_global(self):
        g, r = split_vars({
            "JENKINS_URL": "http://jenkins",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "tok",
        })
        assert "JENKINS_URL" in g
        assert "JENKINS_USERNAME" in g
        assert "JENKINS_API_TOKEN" in g
        assert r == {}

    def test_jenkins_jobs_are_per_repo(self):
        g, r = split_vars({
            "JENKINS_BUILD_JOB": "folder/build",
            "JENKINS_DEPLOY_JOB": "folder/deploy",
        })
        assert g == {}
        assert "JENKINS_BUILD_JOB" in r
        assert "JENKINS_DEPLOY_JOB" in r

    def test_argocd_creds_global_app_repo(self):
        g, r = split_vars({
            "ARGOCD_URL": "http://argocd",
            "ARGOCD_USERNAME": "admin",
            "ARGOCD_PASSWORD": "secret",
            "ARGOCD_APP_NAME": "myapp",
        })
        assert "ARGOCD_URL" in g
        assert "ARGOCD_USERNAME" in g
        assert "ARGOCD_APP_NAME" in r

    def test_target_repo_path_never_stored(self):
        g, r = split_vars({
            "TARGET_REPO_PATH": "/some/path",
            "CURSOR_API_KEY": "sk-123",
        })
        assert "TARGET_REPO_PATH" not in g
        assert "TARGET_REPO_PATH" not in r
        assert "CURSOR_API_KEY" in g

    def test_mixed_vars_split_correctly(self):
        g, r = split_vars({
            "CURSOR_API_KEY": "sk-123",
            "HOST": "0.0.0.0",
            "JENKINS_URL": "http://jenkins",
            "ARGOCD_URL": "http://argocd",
            "TARGET_REPO_PATH": "/path",
            "REDASH_BASE_URL": "http://redash",
            "TARGET_TEST_COMMAND": "pytest",
        })
        assert "CURSOR_API_KEY" in g
        assert "HOST" in g
        assert "REDASH_BASE_URL" in g
        assert "JENKINS_URL" in g
        assert "ARGOCD_URL" in g
        assert "TARGET_TEST_COMMAND" in r
        assert "TARGET_REPO_PATH" not in g
        assert "TARGET_REPO_PATH" not in r

    def test_empty_input(self):
        g, r = split_vars({})
        assert g == {}
        assert r == {}

    def test_unknown_vars_default_to_global(self):
        g, r = split_vars({"MY_CUSTOM_VAR": "value"})
        assert "MY_CUSTOM_VAR" in g
        assert r == {}

    def test_server_vars_are_global(self):
        g, r = split_vars({"HOST": "0.0.0.0", "PORT": "8000", "LOG_LEVEL": "DEBUG"})
        assert len(g) == 3
        assert r == {}

    def test_redash_vars_are_global(self):
        g, r = split_vars({
            "REDASH_BASE_URL": "http://redash",
            "REDASH_USERNAME": "user",
            "REDASH_PASSWORD": "pass",
        })
        assert len(g) == 3
        assert r == {}

    def test_testing_vars_are_per_repo(self):
        g, r = split_vars({
            "TARGET_TEST_COMMAND": "pytest --cov",
            "TARGET_COVERAGE_THRESHOLD": "80",
            "TARGET_REPO_REMOTE": "origin",
        })
        assert g == {}
        assert len(r) == 3


class TestLoadAllEnv:
    """Test the centralized env loading order."""

    def test_sets_target_repo_path_from_cwd(self, tmp_path, monkeypatch):
        """TARGET_REPO_PATH is always set to cwd."""
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
        load_all_env(str(tmp_path))
        assert os.environ["TARGET_REPO_PATH"] == str(tmp_path)

    def test_loads_global_config(self, tmp_path, monkeypatch):
        """Global config is loaded first."""
        global_dir = tmp_path / "home" / ".code-agents"
        global_dir.mkdir(parents=True)
        global_env = global_dir / "config.env"
        global_env.write_text("CURSOR_API_KEY=global-key\n")

        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env):
            load_all_env(str(tmp_path))

        assert os.environ.get("CURSOR_API_KEY") == "global-key"

    def test_legacy_env_overrides_global(self, tmp_path, monkeypatch):
        """Legacy .env overrides global config."""
        global_dir = tmp_path / "home" / ".code-agents"
        global_dir.mkdir(parents=True)
        global_env = global_dir / "config.env"
        global_env.write_text("CURSOR_API_KEY=global-key\n")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("CURSOR_API_KEY=legacy-key\n")

        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env):
            load_all_env(str(repo))

        assert os.environ.get("CURSOR_API_KEY") == "legacy-key"

    def test_per_repo_overrides_legacy(self, tmp_path, monkeypatch):
        """Per-repo .env.code-agents overrides legacy .env."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("JENKINS_URL=legacy-url\n")
        (repo / PER_REPO_FILENAME).write_text("JENKINS_URL=repo-url\n")

        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(repo))

        assert os.environ.get("JENKINS_URL") == "repo-url"

    def test_env_directory_ignored(self, tmp_path, monkeypatch):
        """A .env directory is ignored (not loaded)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").mkdir()  # directory, not file

        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(repo))  # should not crash

        assert os.environ["TARGET_REPO_PATH"] == str(repo)

    def test_no_files_still_sets_target(self, tmp_path, monkeypatch):
        """Even with no config files, TARGET_REPO_PATH is set."""
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(tmp_path))

        assert os.environ["TARGET_REPO_PATH"] == str(tmp_path)

    def test_merged_config_overrides_stale_shell_backend(self, tmp_path, monkeypatch):
        """Stale CODE_AGENTS_BACKEND in the shell must not block values from config files."""
        global_dir = tmp_path / "home" / ".code-agents"
        global_dir.mkdir(parents=True)
        global_env = global_dir / "config.env"
        global_env.write_text("CODE_AGENTS_BACKEND=local\nCODE_AGENTS_LOCAL_LLM_URL=http://127.0.0.1:11434/v1\n")

        monkeypatch.setenv("CODE_AGENTS_BACKEND", "claude-cli")
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env):
            load_all_env(str(tmp_path))

        assert os.environ.get("CODE_AGENTS_BACKEND") == "local"
        assert "11434" in os.environ.get("CODE_AGENTS_LOCAL_LLM_URL", "")


class TestVarClassification:
    """Verify all expected variables are classified."""

    def test_no_overlap_between_global_and_repo(self):
        assert GLOBAL_VARS & REPO_VARS == set()

    def test_no_overlap_with_runtime(self):
        assert GLOBAL_VARS & RUNTIME_VARS == set()
        assert REPO_VARS & RUNTIME_VARS == set()

    def test_cursor_key_is_global(self):
        assert "CURSOR_API_KEY" in GLOBAL_VARS

    def test_jenkins_creds_global_jobs_repo(self):
        assert "JENKINS_URL" in GLOBAL_VARS
        assert "JENKINS_API_TOKEN" in GLOBAL_VARS
        assert "JENKINS_BUILD_JOB" in REPO_VARS
        assert "JENKINS_DEPLOY_JOB" in REPO_VARS
        assert "JENKINS_DEPLOY_JOB_DEV" in REPO_VARS
        assert "JENKINS_DEPLOY_JOB_QA" in REPO_VARS

    def test_target_repo_path_is_runtime(self):
        assert "TARGET_REPO_PATH" in RUNTIME_VARS


# ── Additional env_loader tests ──────────────────────────────────────


class TestRepoNameFromCwd:
    """Test _repo_name_from_cwd helper."""

    def test_git_root_found(self, tmp_path):
        from code_agents.core.env_loader import _repo_name_from_cwd
        (tmp_path / ".git").mkdir()
        assert _repo_name_from_cwd(str(tmp_path)) == tmp_path.name

    def test_nested_subdir(self, tmp_path):
        from code_agents.core.env_loader import _repo_name_from_cwd
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "main"
        subdir.mkdir(parents=True)
        assert _repo_name_from_cwd(str(subdir)) == tmp_path.name

    def test_no_git_fallback(self, tmp_path):
        from code_agents.core.env_loader import _repo_name_from_cwd
        assert _repo_name_from_cwd(str(tmp_path)) == tmp_path.name


class TestRepoConfigPath:
    """Test repo_config_path helper."""

    def test_returns_centralized_path(self, tmp_path):
        from code_agents.core.env_loader import repo_config_path, REPOS_DIR
        (tmp_path / ".git").mkdir()
        path = repo_config_path(str(tmp_path))
        assert REPOS_DIR / tmp_path.name / "config.env" == path


class TestReloadEnvForRepo:
    """Test reload_env_for_repo — reads files without modifying os.environ."""

    def test_loads_global_and_repo(self, tmp_path):
        from code_agents.core.env_loader import reload_env_for_repo, GLOBAL_ENV_PATH, PER_REPO_FILENAME

        global_dir = tmp_path / "global"
        global_dir.mkdir()
        global_env = global_dir / "config.env"
        global_env.write_text("KEY1=global_val\nKEY2=global2\n")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / PER_REPO_FILENAME).write_text("KEY2=repo_val\nKEY3=repo3\n")

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", global_env):
            combined = reload_env_for_repo(str(repo))

        assert combined["KEY1"] == "global_val"
        assert combined["KEY2"] == "repo_val"  # repo overrides global
        assert combined["KEY3"] == "repo3"

    def test_handles_comments_and_blanks(self, tmp_path):
        from code_agents.core.env_loader import reload_env_for_repo

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env.code-agents").write_text("# comment\n\nKEY=val\n")

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "missing"):
            combined = reload_env_for_repo(str(repo))

        assert combined == {"KEY": "val"}

    def test_handles_quoted_values(self, tmp_path):
        from code_agents.core.env_loader import reload_env_for_repo

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env.code-agents").write_text('MY_KEY="quoted value"\n')

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "missing"):
            combined = reload_env_for_repo(str(repo))

        assert combined["MY_KEY"] == "quoted value"

    def test_empty_repo_no_files(self, tmp_path):
        from code_agents.core.env_loader import reload_env_for_repo

        with patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "missing"):
            combined = reload_env_for_repo(str(tmp_path))

        assert combined == {}


class TestSanitizeSslCertEnvironment:
    """PEM paths must not contain shell fragments (e.g. #compdef) merged into SSL_CERT_FILE."""

    def test_strips_hash_fragment_when_file_exists(self, tmp_path):
        from code_agents.core.env_loader import sanitize_ssl_cert_environment

        pem = tmp_path / "corp.pem"
        pem.write_text("-----BEGIN CERTIFICATE-----\n")
        bad = f"{pem}#compdef _zsh"
        with patch.dict(os.environ, {"SSL_CERT_FILE": bad, "HOME": str(tmp_path)}, clear=False):
            n = sanitize_ssl_cert_environment()
            assert n >= 1
            assert os.environ["SSL_CERT_FILE"] == str(pem)

    def test_removes_var_when_path_still_missing(self):
        from code_agents.core.env_loader import sanitize_ssl_cert_environment

        with patch.dict(os.environ, {"SSL_CERT_FILE": "/nope/missing.pem#compdef"}, clear=False):
            sanitize_ssl_cert_environment()
            assert "SSL_CERT_FILE" not in os.environ

    def test_removes_missing_path_without_hash_fragment(self):
        """Broken NODE_EXTRA_CA_CERTS without #compdef should still be dropped."""
        from code_agents.core.env_loader import sanitize_ssl_cert_environment

        with patch.dict(
            os.environ,
            {"NODE_EXTRA_CA_CERTS": "/nonexistent/corporate-ca.pem"},
            clear=False,
        ):
            sanitize_ssl_cert_environment()
            assert "NODE_EXTRA_CA_CERTS" not in os.environ

    def test_skip_extra_certs_flag_clears_all_ca_vars(self):
        from code_agents.core.env_loader import _SSL_CERT_ENV_KEYS, sanitize_ssl_cert_environment

        extra = {k: "/tmp/x" for k in _SSL_CERT_ENV_KEYS}
        extra["CODE_AGENTS_SKIP_EXTRA_CA_CERTS"] = "1"
        with patch.dict(os.environ, extra, clear=False):
            n = sanitize_ssl_cert_environment()
            assert n == len(_SSL_CERT_ENV_KEYS)
            for k in _SSL_CERT_ENV_KEYS:
                assert k not in os.environ
            assert os.environ.get("CODE_AGENTS_SKIP_EXTRA_CA_CERTS") == "1"


class TestLoadAllEnvWithoutDotenv:
    """Test load_all_env when dotenv is not available."""

    def test_fallback_without_dotenv(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "dotenv":
                raise ImportError("no dotenv")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            load_all_env(str(tmp_path))

        assert os.environ["TARGET_REPO_PATH"] == str(tmp_path)
