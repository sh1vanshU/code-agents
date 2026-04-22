"""Tests for the semantic merge module."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
import pytest

from code_agents.git_ops.semantic_merge import (
    SemanticMerger, SemanticMergeResult, ConflictRegion, BranchIntent,
    semantic_merge,
)


class TestSemanticMerger:
    """Test SemanticMerger methods."""

    def test_init(self, tmp_path):
        merger = SemanticMerger(cwd=str(tmp_path))
        assert merger.cwd == str(tmp_path)

    def test_parse_conflicts(self, tmp_path):
        content = '''normal line
<<<<<<< HEAD
our_change = True
=======
their_change = True
>>>>>>> main
another line
'''
        merger = SemanticMerger(cwd=str(tmp_path))
        conflicts = merger._parse_conflicts(content, "test.py")
        assert len(conflicts) == 1
        assert "our_change" in conflicts[0].ours
        assert "their_change" in conflicts[0].theirs

    def test_resolve_identical(self, tmp_path):
        merger = SemanticMerger(cwd=str(tmp_path))
        conflict = ConflictRegion(ours="same\n", theirs="same\n")
        ours_intent = BranchIntent(change_type="feature")
        theirs_intent = BranchIntent(change_type="feature")
        result = merger._resolve_conflict(conflict, ours_intent, theirs_intent)
        assert result["strategy"] == "identical"
        assert result["confidence"] == 1.0

    def test_resolve_one_empty(self, tmp_path):
        merger = SemanticMerger(cwd=str(tmp_path))
        conflict = ConflictRegion(ours="", theirs="new_code\n")
        ours_intent = BranchIntent(change_type="feature")
        theirs_intent = BranchIntent(change_type="feature")
        result = merger._resolve_conflict(conflict, ours_intent, theirs_intent)
        assert result["strategy"] == "theirs"
        assert result["confidence"] >= 0.8

    def test_resolve_bugfix_priority(self, tmp_path):
        merger = SemanticMerger(cwd=str(tmp_path))
        # Use overlapping lines so combine strategy is not triggered
        conflict = ConflictRegion(
            ours="value = 42\nresult = True\n",
            theirs="value = 42\nresult = False\n",
        )
        ours_intent = BranchIntent(change_type="bugfix")
        theirs_intent = BranchIntent(change_type="feature")
        result = merger._resolve_conflict(conflict, ours_intent, theirs_intent)
        assert result["strategy"] == "ours"

    @patch("code_agents.git_ops.semantic_merge.subprocess.run")
    def test_analyze_no_conflicts(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        merger = SemanticMerger(cwd=str(tmp_path))
        result = merger.analyze()
        assert isinstance(result, SemanticMergeResult)
        assert len(result.conflicts) == 0

    def test_convenience_function(self, tmp_path):
        with patch("code_agents.git_ops.semantic_merge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            result = semantic_merge(cwd=str(tmp_path))
            assert isinstance(result, dict)
            assert "conflicts" in result
            assert "summary" in result
