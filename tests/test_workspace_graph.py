"""Tests for workspace_graph.py and workspace_pr.py — multi-repo orchestration."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.knowledge.workspace_graph import CrossRepoDependency, WorkspaceGraph
from code_agents.knowledge.workspace_pr import CoordinatedPRCreator, PRResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_repos(tmp_path):
    """Create two minimal git repos that share a package name."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"

    # Repo A: defines a "shared_lib" package
    repo_a.mkdir()
    (repo_a / "shared_lib").mkdir()
    (repo_a / "shared_lib" / "__init__.py").write_text("")
    (repo_a / "shared_lib" / "utils.py").write_text(
        "def helper():\n    return 42\n"
    )
    (repo_a / "main.py").write_text(
        "from shared_lib import utils\n\ndef run():\n    return utils.helper()\n"
    )

    # Repo B: imports "shared_lib" (cross-repo dep)
    repo_b.mkdir()
    (repo_b / "app").mkdir()
    (repo_b / "app" / "__init__.py").write_text("")
    (repo_b / "app" / "service.py").write_text(
        "import shared_lib\n\ndef serve():\n    pass\n"
    )

    # Init git repos
    for repo in [repo_a, repo_b]:
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
        )

    return str(repo_a), str(repo_b)


# ---------------------------------------------------------------------------
# TestCrossRepoDeps
# ---------------------------------------------------------------------------


class TestCrossRepoDeps:
    """Test cross-repo dependency detection."""

    def test_find_shared_packages(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()
        deps = wg.find_cross_repo_deps()

        # repo_b imports shared_lib which is defined in repo_a
        cross_deps = [d for d in deps if d.target_repo == repo_a and d.source_repo == repo_b]
        assert len(cross_deps) > 0
        assert any(d.import_path == "shared_lib" for d in cross_deps)

    def test_no_self_deps(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()
        deps = wg.find_cross_repo_deps()

        for d in deps:
            assert d.source_repo != d.target_repo, "No self-referencing deps"

    def test_empty_repos(self, tmp_path):
        """No crash on repos with no parseable files."""
        empty = tmp_path / "empty"
        empty.mkdir()
        subprocess.run(["git", "init"], cwd=empty, capture_output=True)

        wg = WorkspaceGraph([str(empty)])
        stats = wg.build_all()
        deps = wg.find_cross_repo_deps()
        assert deps == []

    def test_nonexistent_repo_skipped(self, tmp_path):
        """Non-existent paths are skipped without error."""
        wg = WorkspaceGraph([str(tmp_path / "does_not_exist")])
        stats = wg.build_all()
        assert stats == {}

    def test_dependency_dataclass_fields(self):
        dep = CrossRepoDependency(
            source_repo="/a", target_repo="/b",
            import_path="shared_lib.utils", source_file="app/service.py",
        )
        assert dep.source_repo == "/a"
        assert dep.target_repo == "/b"
        assert dep.import_path == "shared_lib.utils"
        assert dep.source_file == "app/service.py"


# ---------------------------------------------------------------------------
# TestQueryAll
# ---------------------------------------------------------------------------


class TestQueryAll:
    """Test cross-repo querying."""

    def test_query_finds_across_repos(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        results = wg.query_all(["helper"])
        assert len(results) > 0
        # Should annotate with repo info
        assert "repo" in results[0]
        assert "repo_path" in results[0]

    def test_query_empty_keywords(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        results = wg.query_all([])
        assert results == []

    def test_query_no_matches(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        results = wg.query_all(["nonexistent_symbol_xyz"])
        assert results == []

    def test_query_max_results(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        results = wg.query_all(["def"], max_results=1)
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# TestBlastRadius
# ---------------------------------------------------------------------------


class TestBlastRadius:
    """Test cross-repo blast radius analysis."""

    def test_blast_radius_in_source_repo(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        impact = wg.blast_radius_cross_repo("shared_lib/utils.py", repo_a)
        # Should at least include the source repo
        assert repo_a in impact

    def test_blast_radius_cross_repo_impact(self, two_repos):
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        impact = wg.blast_radius_cross_repo("shared_lib/utils.py", repo_a)
        # repo_b imports shared_lib, so should be affected
        assert repo_b in impact

    def test_blast_radius_no_cross_impact(self, two_repos):
        """A file that isn't imported cross-repo should have no cross-repo impact."""
        repo_a, repo_b = two_repos
        wg = WorkspaceGraph([repo_a, repo_b])
        wg.build_all()

        # main.py is only in repo_a — repo_b doesn't import it
        impact = wg.blast_radius_cross_repo("main.py", repo_a)
        assert repo_b not in impact


# ---------------------------------------------------------------------------
# TestCoordinatedPR
# ---------------------------------------------------------------------------


class TestCoordinatedPR:
    """Test coordinated PR creation with mocked subprocess."""

    def test_no_changes_returns_empty(self):
        """When no repos have changes, return empty list."""
        with patch("code_agents.knowledge.workspace_pr.subprocess.run") as mock_run:
            # git status --porcelain returns empty
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            creator = CoordinatedPRCreator(["/fake/repo-a", "/fake/repo-b"])
            results = creator.create_linked_prs("feature/x", "Title", "Body")
            assert results == []

    def test_create_linked_prs_success(self):
        """Test successful PR creation across repos."""
        call_count = {"n": 0}

        def mock_run_side_effect(cmd, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""

            if cmd[0] == "git" and cmd[1] == "status":
                result.stdout = "M file.py\n"
            elif cmd[0] == "git" and cmd[1] == "checkout":
                result.stdout = ""
            elif cmd[0] == "git" and cmd[1] == "add":
                result.stdout = ""
            elif cmd[0] == "git" and cmd[1] == "commit":
                result.stdout = ""
            elif cmd[0] == "git" and cmd[1] == "push":
                result.stdout = ""
            elif cmd[0] == "gh" and cmd[1] == "pr":
                result.stdout = "https://github.com/org/repo/pull/42\n"
            else:
                result.stdout = ""
            return result

        with patch("code_agents.knowledge.workspace_pr.subprocess.run", side_effect=mock_run_side_effect):
            creator = CoordinatedPRCreator(["/fake/repo-a"])
            results = creator.create_linked_prs("feature/x", "Title", "Body")

            assert len(results) == 1
            assert results[0].success is True
            assert "github.com" in results[0].pr_url

    def test_create_pr_handles_push_failure(self):
        """Test that push failure is captured gracefully."""
        def mock_run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.stderr = ""

            if cmd[0] == "git" and cmd[1] == "status":
                result.returncode = 0
                result.stdout = "M file.py\n"
            elif cmd[0] == "git" and cmd[1] == "push":
                result.returncode = 1
                result.stdout = ""
                result.stderr = "remote: Permission denied"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with patch("code_agents.knowledge.workspace_pr.subprocess.run", side_effect=mock_run_side_effect):
            creator = CoordinatedPRCreator(["/fake/repo-a"])
            results = creator.create_linked_prs("feature/x", "Title", "Body")

            # Should get a result with success=False
            failed = [r for r in results if not r.success]
            assert len(failed) > 0
            assert "Permission denied" in failed[0].error

    def test_status_returns_pr_list(self):
        """Test status() parses gh pr list output."""
        pr_json = json.dumps([
            {"number": 1, "title": "Test PR", "url": "https://github.com/x/y/pull/1",
             "state": "OPEN", "headRefName": "feature/x"}
        ])

        with patch("code_agents.knowledge.workspace_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=pr_json, stderr="")

            creator = CoordinatedPRCreator(["/fake/repo-a"])
            statuses = creator.status()

            assert len(statuses) == 1
            assert len(statuses[0]["open_prs"]) == 1
            assert statuses[0]["open_prs"][0]["number"] == 1

    def test_status_handles_gh_failure(self):
        """Test status() handles gh CLI failure gracefully."""
        with patch("code_agents.knowledge.workspace_pr.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")

            creator = CoordinatedPRCreator(["/fake/repo-a"])
            statuses = creator.status()

            assert len(statuses) == 1
            assert statuses[0]["open_prs"] == []

    def test_pr_result_dataclass(self):
        r = PRResult(repo="/a", branch="main", pr_url="https://x", success=True)
        assert r.error == ""
        assert r.success is True
