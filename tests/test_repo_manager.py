"""Tests for repo_manager.py — multi-repo support."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.domain.repo_manager import (
    RepoManager,
    RepoContext,
    _detect_git_branch,
    _detect_git_remote,
    _load_repo_env_vars,
    get_repo_manager,
    reload_env_for_repo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create a temporary git repo."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


@pytest.fixture
def tmp_git_repo_b(tmp_path):
    """Create a second temporary git repo."""
    repo = tmp_path / "other-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


@pytest.fixture
def tmp_repo_with_env(tmp_git_repo):
    """Create a git repo with .env.code-agents."""
    env_file = tmp_git_repo / ".env.code-agents"
    env_file.write_text(
        "JENKINS_BUILD_JOB=folder/build-a\n"
        "ARGOCD_APP_NAME=app-a\n"
        "# This is a comment\n"
        "\n"
        'JIRA_PROJECT_KEY="PROJ-A"\n'
    )
    return tmp_git_repo


@pytest.fixture
def tmp_repo_b_with_env(tmp_git_repo_b):
    """Create a second git repo with different env."""
    env_file = tmp_git_repo_b / ".env.code-agents"
    env_file.write_text(
        "JENKINS_BUILD_JOB=folder/build-b\n"
        "ARGOCD_APP_NAME=app-b\n"
        "JIRA_PROJECT_KEY=PROJ-B\n"
    )
    return tmp_git_repo_b


@pytest.fixture
def manager():
    """Create a fresh RepoManager."""
    return RepoManager()


# ---------------------------------------------------------------------------
# RepoManager.add_repo
# ---------------------------------------------------------------------------


class TestAddRepo:

    def test_add_valid_repo(self, manager, tmp_git_repo):
        ctx = manager.add_repo(str(tmp_git_repo))
        assert ctx.name == "test-repo"
        assert ctx.path == str(tmp_git_repo.resolve())
        assert str(tmp_git_repo.resolve()) in manager.repos

    def test_add_sets_first_as_active(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        assert manager.active_repo == str(tmp_git_repo.resolve())

    def test_add_nonexistent_path_raises(self, manager):
        with pytest.raises(ValueError, match="does not exist"):
            manager.add_repo("/nonexistent/path/xyz")

    def test_add_non_git_dir_raises(self, manager, tmp_path):
        non_git = tmp_path / "not-a-repo"
        non_git.mkdir()
        with pytest.raises(ValueError, match="Not a git repository"):
            manager.add_repo(str(non_git))

    def test_add_duplicate_returns_existing(self, manager, tmp_git_repo):
        ctx1 = manager.add_repo(str(tmp_git_repo))
        ctx2 = manager.add_repo(str(tmp_git_repo))
        assert ctx1 is ctx2
        assert len(manager.repos) == 1

    def test_add_loads_env_vars(self, manager, tmp_repo_with_env):
        ctx = manager.add_repo(str(tmp_repo_with_env))
        assert ctx.env_vars.get("JENKINS_BUILD_JOB") == "folder/build-a"
        assert ctx.env_vars.get("ARGOCD_APP_NAME") == "app-a"
        assert ctx.env_vars.get("JIRA_PROJECT_KEY") == "PROJ-A"


# ---------------------------------------------------------------------------
# RepoManager.switch_repo
# ---------------------------------------------------------------------------


class TestSwitchRepo:

    def test_switch_by_name(self, manager, tmp_git_repo, tmp_git_repo_b):
        manager.add_repo(str(tmp_git_repo))
        manager.add_repo(str(tmp_git_repo_b))
        ctx = manager.switch_repo("other-repo")
        assert ctx.name == "other-repo"
        assert manager.active_repo == str(tmp_git_repo_b.resolve())

    def test_switch_by_path(self, manager, tmp_git_repo, tmp_git_repo_b):
        manager.add_repo(str(tmp_git_repo))
        manager.add_repo(str(tmp_git_repo_b))
        ctx = manager.switch_repo(str(tmp_git_repo_b))
        assert ctx.name == "other-repo"

    def test_switch_updates_target_repo_path(self, manager, tmp_repo_with_env, tmp_repo_b_with_env):
        manager.add_repo(str(tmp_repo_with_env))
        manager.add_repo(str(tmp_repo_b_with_env))
        manager.switch_repo("other-repo")
        assert os.environ.get("TARGET_REPO_PATH") == str(tmp_repo_b_with_env.resolve())

    def test_switch_unknown_raises(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        with pytest.raises(ValueError, match="No repo matching"):
            manager.switch_repo("nonexistent")

    def test_switch_applies_repo_env_vars(self, manager, tmp_repo_with_env, tmp_repo_b_with_env):
        manager.add_repo(str(tmp_repo_with_env))
        manager.add_repo(str(tmp_repo_b_with_env))

        # Switch to repo B
        manager.switch_repo("other-repo")
        assert os.environ.get("JENKINS_BUILD_JOB") == "folder/build-b"
        assert os.environ.get("ARGOCD_APP_NAME") == "app-b"

    def test_switch_env_isolation(self, manager, tmp_repo_with_env, tmp_repo_b_with_env):
        """Repo A vars don't leak to repo B."""
        manager.add_repo(str(tmp_repo_with_env))
        manager.add_repo(str(tmp_repo_b_with_env))

        # Start at repo A
        manager.switch_repo("test-repo")
        assert os.environ.get("JIRA_PROJECT_KEY") == "PROJ-A"

        # Switch to repo B
        manager.switch_repo("other-repo")
        assert os.environ.get("JIRA_PROJECT_KEY") == "PROJ-B"

        # Switch back to repo A
        manager.switch_repo("test-repo")
        assert os.environ.get("JIRA_PROJECT_KEY") == "PROJ-A"

    def test_switch_partial_name_match(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        ctx = manager.switch_repo("test")
        assert ctx.name == "test-repo"


# ---------------------------------------------------------------------------
# RepoManager.remove_repo
# ---------------------------------------------------------------------------


class TestRemoveRepo:

    def test_remove_inactive_repo(self, manager, tmp_git_repo, tmp_git_repo_b):
        manager.add_repo(str(tmp_git_repo))
        manager.add_repo(str(tmp_git_repo_b))
        assert manager.remove_repo("other-repo") is True
        assert len(manager.repos) == 1

    def test_remove_active_raises(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        with pytest.raises(ValueError, match="Cannot remove active repo"):
            manager.remove_repo("test-repo")

    def test_remove_nonexistent_returns_false(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        assert manager.remove_repo("nope") is False


# ---------------------------------------------------------------------------
# RepoManager.list_repos
# ---------------------------------------------------------------------------


class TestListRepos:

    def test_list_empty(self, manager):
        assert manager.list_repos() == []

    def test_list_returns_all(self, manager, tmp_git_repo, tmp_git_repo_b):
        manager.add_repo(str(tmp_git_repo))
        manager.add_repo(str(tmp_git_repo_b))
        repos = manager.list_repos()
        assert len(repos) == 2

    def test_list_active_first(self, manager, tmp_git_repo, tmp_git_repo_b):
        manager.add_repo(str(tmp_git_repo))
        manager.add_repo(str(tmp_git_repo_b))
        repos = manager.list_repos()
        # First repo added becomes active
        assert repos[0].name == "test-repo"


# ---------------------------------------------------------------------------
# RepoManager.get_active
# ---------------------------------------------------------------------------


class TestGetActive:

    def test_get_active_none(self, manager):
        assert manager.get_active() is None

    def test_get_active_returns_current(self, manager, tmp_git_repo):
        manager.add_repo(str(tmp_git_repo))
        active = manager.get_active()
        assert active is not None
        assert active.name == "test-repo"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:

    def test_detect_git_branch_no_repo(self, tmp_path):
        branch = _detect_git_branch(str(tmp_path))
        assert branch == ""

    @patch("code_agents.domain.repo_manager.subprocess.run")
    def test_detect_git_branch_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        branch = _detect_git_branch("/some/repo")
        assert branch == "main"

    @patch("code_agents.domain.repo_manager.subprocess.run")
    def test_detect_git_remote_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="git@github.com:org/repo.git\n")
        remote = _detect_git_remote("/some/repo")
        assert remote == "git@github.com:org/repo.git"

    def test_load_repo_env_vars_no_file(self, tmp_path):
        vars_dict = _load_repo_env_vars(str(tmp_path))
        assert vars_dict == {}

    def test_load_repo_env_vars_parses(self, tmp_repo_with_env):
        vars_dict = _load_repo_env_vars(str(tmp_repo_with_env))
        assert vars_dict["JENKINS_BUILD_JOB"] == "folder/build-a"
        assert vars_dict["ARGOCD_APP_NAME"] == "app-a"
        # Strips quotes
        assert vars_dict["JIRA_PROJECT_KEY"] == "PROJ-A"
        # Skips comments and blank lines
        assert "#" not in str(vars_dict.keys())


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:

    def test_get_repo_manager_returns_same_instance(self):
        import code_agents.domain.repo_manager as mod
        # Reset singleton
        mod._repo_manager = None
        rm1 = get_repo_manager()
        rm2 = get_repo_manager()
        assert rm1 is rm2
        # Cleanup
        mod._repo_manager = None


# ---------------------------------------------------------------------------
# reload_env_for_repo
# ---------------------------------------------------------------------------


class TestReloadEnvForRepo:

    def test_reload_returns_repo_vars(self, tmp_repo_with_env):
        combined = reload_env_for_repo(str(tmp_repo_with_env))
        assert combined.get("JENKINS_BUILD_JOB") == "folder/build-a"

    def test_reload_empty_dir(self, tmp_path):
        combined = reload_env_for_repo(str(tmp_path))
        # Should still work, just may be empty or only global
        assert isinstance(combined, dict)
