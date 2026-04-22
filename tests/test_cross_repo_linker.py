"""Tests for the cross-repo linker module."""

from __future__ import annotations

import os
import pytest

from code_agents.knowledge.cross_repo_linker import (
    CrossRepoLinker, CrossRepoResult, RepoLink, link_cross_repos,
)


class TestCrossRepoLinker:
    """Test CrossRepoLinker methods."""

    def test_init(self, tmp_path):
        linker = CrossRepoLinker(cwd=str(tmp_path))
        assert linker.cwd == str(tmp_path)

    def test_analyze_single_repo(self, tmp_path):
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "app.py").write_text("import os\ndef main():\n    pass\n")
        linker = CrossRepoLinker(cwd=str(tmp_path))
        result = linker.analyze(repo_paths=[str(tmp_path)])
        assert isinstance(result, CrossRepoResult)
        assert result.repos_analyzed == 1

    def test_analyze_detects_cross_deps(self, tmp_path):
        # Create two "repos"
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        (repo_a / ".git").mkdir()
        (repo_a / "__init__.py").write_text("")
        (repo_a / "models.py").write_text("class User:\n    pass\n")
        (repo_a / "pyproject.toml").write_text('[tool.poetry]\nname = "repo_a"\n')

        repo_b = tmp_path / "repo_b"
        repo_b.mkdir()
        (repo_b / ".git").mkdir()
        (repo_b / "__init__.py").write_text("")
        (repo_b / "service.py").write_text("import repo_a\nfrom repo_a import models\n")
        (repo_b / "pyproject.toml").write_text('[tool.poetry]\nname = "repo_b"\n')

        linker = CrossRepoLinker(cwd=str(repo_b))
        result = linker.analyze(repo_paths=[str(repo_a), str(repo_b)])
        assert len(result.links) >= 1
        assert any(l.target_repo == "repo_a" for l in result.links)

    def test_extract_packages(self, tmp_path):
        (tmp_path / "mypackage").mkdir()
        (tmp_path / "mypackage" / "__init__.py").write_text("")
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "my-project"\n')

        linker = CrossRepoLinker(cwd=str(tmp_path))
        packages = linker._extract_packages(str(tmp_path))
        assert "mypackage" in packages
        assert "my-project" in packages or "my_project" in packages

    def test_shared_interfaces(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "models.py").write_text("class Order:\n    pass\nclass Product:\n    pass\n")
        linker = CrossRepoLinker(cwd=str(repo))
        interfaces = linker._extract_interfaces(str(repo))
        names = [i.name for i in interfaces]
        assert "Order" in names
        assert "Product" in names

    def test_convenience_function(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "app.py").write_text("import os\n")
        result = link_cross_repos(cwd=str(tmp_path), repo_paths=[str(tmp_path)])
        assert isinstance(result, dict)
        assert "links" in result
        assert "shared_interfaces" in result
        assert "summary" in result
