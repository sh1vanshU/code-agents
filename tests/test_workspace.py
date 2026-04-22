"""Tests for workspace — multi-repo workspace management."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.knowledge.workspace import RepoInfo, Workspace, WorkspaceManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a fake git repo."""
    repo = tmp_path / "primary-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").touch()
    return repo


@pytest.fixture
def tmp_other_repo(tmp_path):
    """Create a second fake git repo."""
    repo = tmp_path / "other-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "package.json").touch()
    return repo


@pytest.fixture
def wm(tmp_repo):
    """Create a WorkspaceManager with mocked git calls."""
    with patch("code_agents.knowledge.workspace.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        mgr = WorkspaceManager(str(tmp_repo))
        yield mgr


# ---------------------------------------------------------------------------
# RepoInfo
# ---------------------------------------------------------------------------


class TestRepoInfo:
    """Tests for RepoInfo dataclass."""

    def test_defaults(self):
        r = RepoInfo(path="/some/path")
        assert r.path == "/some/path"
        assert r.name == ""
        assert r.branch == ""

    def test_with_values(self):
        r = RepoInfo(path="/p", name="myrepo", branch="main", language="Python")
        assert r.name == "myrepo"
        assert r.language == "Python"


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class TestWorkspace:
    """Tests for Workspace dataclass."""

    def test_defaults(self):
        w = Workspace()
        assert w.repos == []
        assert w.primary_repo == ""

    def test_with_repos(self):
        w = Workspace(primary_repo="/p", repos=[RepoInfo(path="/p")])
        assert len(w.repos) == 1


# ---------------------------------------------------------------------------
# WorkspaceManager
# ---------------------------------------------------------------------------


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    def test_init(self, tmp_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm = WorkspaceManager(str(tmp_repo))
            assert wm.primary == str(tmp_repo)

    def test_load_creates_new(self, wm, tmp_repo):
        ws = wm._load()
        assert ws.primary_repo == str(tmp_repo)
        assert len(ws.repos) >= 1

    def test_save_creates_file(self, wm, tmp_repo):
        wm._load()
        wm._save()
        config_file = tmp_repo / ".code-agents" / "workspace.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["primary_repo"] == str(tmp_repo)

    def test_save_and_reload(self, tmp_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm1 = WorkspaceManager(str(tmp_repo))
            wm1._load()
            wm1._save()

            wm2 = WorkspaceManager(str(tmp_repo))
            ws = wm2._load()
            assert ws.primary_repo == str(tmp_repo)


class TestAddRepo:
    """Tests for adding repos to workspace."""

    def test_add_repo(self, wm, tmp_other_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            info = wm.add_repo(str(tmp_other_repo))
            assert info.name == "other-repo"
            assert info.path == str(tmp_other_repo.resolve())

    def test_add_nonexistent_raises(self, wm):
        with pytest.raises(ValueError, match="Not a directory"):
            wm.add_repo("/nonexistent/path")

    def test_add_non_git_raises(self, wm, tmp_path):
        non_git = tmp_path / "not-git"
        non_git.mkdir()
        with pytest.raises(ValueError, match="Not a git repository"):
            wm.add_repo(str(non_git))

    def test_add_duplicate_raises(self, wm, tmp_other_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm.add_repo(str(tmp_other_repo))
            with pytest.raises(ValueError, match="already in workspace"):
                wm.add_repo(str(tmp_other_repo))

    def test_add_persists(self, wm, tmp_other_repo, tmp_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm.add_repo(str(tmp_other_repo))
            repos = wm.list_repos()
            assert len(repos) == 2  # primary + other


class TestRemoveRepo:
    """Tests for removing repos from workspace."""

    def test_remove_by_name(self, wm, tmp_other_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm.add_repo(str(tmp_other_repo))
            assert wm.remove_repo("other-repo") is True
            assert len(wm.list_repos()) == 1

    def test_remove_nonexistent(self, wm):
        assert wm.remove_repo("ghost") is False

    def test_remove_primary_raises(self, wm, tmp_repo):
        with pytest.raises(ValueError, match="Cannot remove the primary"):
            wm.remove_repo(str(tmp_repo.resolve()))


class TestListRepos:
    """Tests for listing repos."""

    def test_list_default(self, wm):
        repos = wm.list_repos()
        assert len(repos) >= 1

    def test_list_after_add(self, wm, tmp_other_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm.add_repo(str(tmp_other_repo))
            repos = wm.list_repos()
            assert len(repos) == 2


class TestDetectLanguage:
    """Tests for language detection."""

    def test_python(self, wm, tmp_path):
        repo = tmp_path / "py-repo"
        repo.mkdir()
        (repo / "pyproject.toml").touch()
        assert wm._detect_language(str(repo)) == "Python"

    def test_javascript(self, wm, tmp_path):
        repo = tmp_path / "js-repo"
        repo.mkdir()
        (repo / "package.json").touch()
        assert wm._detect_language(str(repo)) == "JavaScript"

    def test_go(self, wm, tmp_path):
        repo = tmp_path / "go-repo"
        repo.mkdir()
        (repo / "go.mod").touch()
        assert wm._detect_language(str(repo)) == "Go"

    def test_unknown(self, wm, tmp_path):
        repo = tmp_path / "empty"
        repo.mkdir()
        assert wm._detect_language(str(repo)) == "Unknown"


class TestBuildContext:
    """Tests for building cross-repo context."""

    def test_single_repo_empty(self, wm):
        context = wm.build_context()
        assert context == ""

    def test_multi_repo_context(self, wm, tmp_other_repo):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1)):
            wm.add_repo(str(tmp_other_repo))
            context = wm.build_context()
            assert "[Workspace Context" in context
            assert "other-repo" in context


class TestWorkspaceStatus:
    """Tests for workspace status."""

    def test_status_structure(self, wm):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
            status = wm.status()
            assert "primary" in status
            assert "repo_count" in status
            assert "repos" in status
            assert len(status["repos"]) >= 1

    def test_status_repo_fields(self, wm):
        with patch("code_agents.knowledge.workspace.subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
            status = wm.status()
            repo = status["repos"][0]
            assert "name" in repo
            assert "branch" in repo
            assert "clean" in repo
