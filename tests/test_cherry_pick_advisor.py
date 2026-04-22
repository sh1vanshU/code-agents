"""Tests for the cherry-pick advisor."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.cherry_pick_advisor import (
    CherryPickAdvisor, CommitInfo, Dependency, CherryPickPlan, SearchResult,
)


class TestCommitInfo:
    """Test CommitInfo dataclass."""

    def test_defaults(self):
        c = CommitInfo(sha="abc123")
        assert c.short_sha == ""
        assert c.files == []
        assert c.branches == []

    def test_custom(self):
        c = CommitInfo(sha="abc123", short_sha="abc1", message="fix: bug",
                       author="dev", files=["a.py"], additions=10)
        assert c.additions == 10


class TestSearchResult:
    """Test SearchResult."""

    def test_summary(self):
        r = SearchResult(
            commits=[CommitInfo(sha="a"), CommitInfo(sha="b")],
            query="fix auth",
        )
        assert "2 commits" in r.summary
        assert "fix auth" in r.summary


class TestCherryPickPlan:
    """Test CherryPickPlan."""

    def test_summary_safe(self):
        plan = CherryPickPlan(
            target_commit=CommitInfo(sha="abc", short_sha="abc"),
            target_branch="release/v1",
            safe=True,
        )
        assert "safe" in plan.summary

    def test_summary_risky(self):
        plan = CherryPickPlan(
            target_commit=CommitInfo(sha="abc", short_sha="abc"),
            target_branch="release/v1",
            safe=False,
            dependencies=[MagicMock()],
        )
        assert "RISKY" in plan.summary
        assert "1 deps" in plan.summary


class TestCherryPickAdvisor:
    """Test CherryPickAdvisor."""

    def _make_advisor(self, tmp_path):
        return CherryPickAdvisor(cwd=str(tmp_path))

    def test_search_commits(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        with patch.object(advisor, "_search_all", return_value=[
            CommitInfo(sha="aaa111", short_sha="aaa1", message="fix: auth bug"),
            CommitInfo(sha="bbb222", short_sha="bbb2", message="fix: auth timeout"),
        ]):
            with patch.object(advisor, "_find_branches_containing", return_value=["main"]):
                result = advisor.search_commits("fix auth")
        assert len(result.commits) == 2

    def test_search_deduplicates(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        with patch.object(advisor, "_search_all", return_value=[
            CommitInfo(sha="aaa111", short_sha="a1", message="fix"),
            CommitInfo(sha="aaa111", short_sha="a1", message="fix"),  # duplicate
        ]):
            with patch.object(advisor, "_find_branches_containing", return_value=[]):
                result = advisor.search_commits("fix")
        assert len(result.commits) == 1

    def test_plan_already_on_branch(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        commit = CommitInfo(sha="abc123", short_sha="abc1", message="fix", files=["a.py"])
        with patch.object(advisor, "_get_commit_info", return_value=commit):
            with patch.object(advisor, "_get_branch_commits", return_value=[
                CommitInfo(sha="abc123"),  # already there
            ]):
                plan = advisor.plan_cherry_pick("abc123", "release")
        assert plan.safe is False
        assert any("already on" in w for w in plan.warnings)

    def test_plan_clean_cherry_pick(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        commit = CommitInfo(sha="abc123", short_sha="abc1", message="fix", files=["a.py"])
        with patch.object(advisor, "_get_commit_info", return_value=commit), \
             patch.object(advisor, "_get_branch_commits", return_value=[
                 CommitInfo(sha="def456"),
             ]), \
             patch.object(advisor, "_find_dependencies", return_value=[]), \
             patch.object(advisor, "_check_conflicts", return_value=[]):
            plan = advisor.plan_cherry_pick("abc123", "release")
        assert plan.safe is True
        assert len(plan.commands) >= 2
        assert any("cherry-pick" in c for c in plan.commands)

    def test_plan_with_conflicts(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        commit = CommitInfo(sha="abc123", short_sha="abc1", message="fix", files=["a.py"])
        with patch.object(advisor, "_get_commit_info", return_value=commit), \
             patch.object(advisor, "_get_branch_commits", return_value=[]), \
             patch.object(advisor, "_find_dependencies", return_value=[]), \
             patch.object(advisor, "_check_conflicts", return_value=["a.py"]):
            plan = advisor.plan_cherry_pick("abc123", "release")
        assert plan.conflicts_likely is True
        assert "a.py" in plan.conflict_files
        assert any("conflict" in w.lower() for w in plan.warnings)

    def test_plan_with_prerequisites(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        commit = CommitInfo(sha="abc123", short_sha="abc1", message="fix", files=["a.py"])
        dep = Dependency(commit_sha="abc123", depends_on_sha="pre111", reason="same_file", files=["a.py"])
        prereq = CommitInfo(sha="pre111", short_sha="pre1", message="prereq")
        with patch.object(advisor, "_get_commit_info") as mock_info, \
             patch.object(advisor, "_get_branch_commits", return_value=[]), \
             patch.object(advisor, "_find_dependencies", return_value=[dep]), \
             patch.object(advisor, "_check_conflicts", return_value=[]):
            mock_info.side_effect = [commit, prereq]
            plan = advisor.plan_cherry_pick("abc123", "release")
        assert len(plan.prerequisite_commits) == 1
        assert any("prerequisite" in w.lower() for w in plan.warnings)

    def test_find_branches(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        with patch.object(advisor, "_git", return_value="  main\n  feature/auth\n* develop"):
            branches = advisor.find_commit_on_branches("abc123")
        assert "main" in branches
        assert "develop" in branches

    def test_generate_commands_with_prereqs(self, tmp_path):
        advisor = self._make_advisor(tmp_path)
        plan = CherryPickPlan(
            target_commit=CommitInfo(sha="abc123", short_sha="abc1", message="fix"),
            target_branch="release",
            prerequisite_commits=[CommitInfo(sha="pre111", message="prereq change")],
            conflicts_likely=False,
        )
        cmds = advisor._generate_commands(plan)
        assert cmds[0] == "git checkout release"
        assert any("pre111" in c for c in cmds)
        assert any("abc123" in c for c in cmds)
