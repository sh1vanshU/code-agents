"""Tests for the branch cleanup analyzer."""

from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from code_agents.git_ops.branch_cleanup import (
    BranchCleanup, BranchInfo, CleanupAction, CleanupReport,
)


class TestBranchInfo:
    """Test BranchInfo dataclass."""

    def test_defaults(self):
        b = BranchInfo(name="feature/test")
        assert b.is_merged is False
        assert b.is_remote is False
        assert b.status == "active"
        assert b.is_protected is False

    def test_custom(self):
        b = BranchInfo(name="old-branch", days_inactive=120, is_merged=True, status="merged")
        assert b.days_inactive == 120
        assert b.is_merged is True


class TestCleanupReport:
    """Test CleanupReport."""

    def test_summary(self):
        r = CleanupReport(
            branches=[MagicMock()] * 5,
            actions=[MagicMock()] * 2,
            merged_count=2, stale_count=1, protected_count=1,
        )
        assert "5 branches" in r.summary
        assert "2 merged" in r.summary
        assert "1 stale" in r.summary


class TestBranchCleanup:
    """Test BranchCleanup."""

    def _make_cleanup(self, tmp_path, stale_days=90):
        return BranchCleanup(cwd=str(tmp_path), stale_days=stale_days)

    def test_is_protected_main(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        assert cleanup._is_protected("main") is True
        assert cleanup._is_protected("master") is True
        assert cleanup._is_protected("develop") is True
        assert cleanup._is_protected("release/v1.0") is True

    def test_is_protected_feature(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        assert cleanup._is_protected("feature/my-feature") is False
        assert cleanup._is_protected("bugfix/fix-123") is False

    def test_suggest_action_merged(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        branch = BranchInfo(name="feature/done", is_merged=True, days_inactive=10)
        action = cleanup._suggest_action(branch)
        assert action is not None
        assert action.action == "delete_local"
        assert action.safe is True
        assert "git branch -d" in action.command

    def test_suggest_action_stale(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        branch = BranchInfo(name="feature/old", is_merged=False, days_inactive=120, status="stale")
        action = cleanup._suggest_action(branch)
        assert action is not None
        assert action.action == "archive"
        assert action.safe is False  # unmerged stale is unsafe

    def test_suggest_action_protected(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        branch = BranchInfo(name="main", is_protected=True)
        action = cleanup._suggest_action(branch)
        assert action is None

    def test_analyze_with_mocks(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        branches = [
            BranchInfo(name="main", days_inactive=0),
            BranchInfo(name="feature/done", days_inactive=5),
            BranchInfo(name="feature/old", days_inactive=120),
        ]
        with patch.object(cleanup, "_get_local_branches", return_value=branches), \
             patch.object(cleanup, "_get_merged_branches", return_value={"feature/done"}), \
             patch.object(cleanup, "_get_current_branch", return_value="main"):
            report = cleanup.analyze()

        assert report.protected_count == 1
        assert report.merged_count == 1
        assert report.stale_count == 1

    def test_execute_dry_run(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        actions = [
            CleanupAction(
                branch=BranchInfo(name="old"),
                action="delete_local", reason="merged",
                safe=True, command="git branch -d old",
            ),
        ]
        result = cleanup.execute_actions(actions, dry_run=True)
        assert len(result) == 1
        assert "[DRY RUN]" in result[0]

    def test_execute_skip_unsafe(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        actions = [
            CleanupAction(
                branch=BranchInfo(name="risky"),
                action="archive", reason="stale",
                safe=False, command="git branch -D risky",
            ),
        ]
        result = cleanup.execute_actions(actions, dry_run=False)
        assert len(result) == 0  # skipped

    def test_generate_script(self, tmp_path):
        cleanup = self._make_cleanup(tmp_path)
        report = CleanupReport(
            branches=[], protected_count=0, stale_count=0, merged_count=1,
            actions=[
                CleanupAction(
                    branch=BranchInfo(name="done"),
                    action="delete_local", reason="merged",
                    safe=True, command="git branch -d done",
                ),
                CleanupAction(
                    branch=BranchInfo(name="risky"),
                    action="archive", reason="stale",
                    safe=False, command="git branch -D risky",
                ),
            ],
        )
        script = cleanup.generate_script(report)
        assert "#!/bin/bash" in script
        assert "git branch -d done" in script
        assert "SKIPPED" in script
