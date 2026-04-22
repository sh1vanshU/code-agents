"""Tests for review_responder.py — Review Responder feature."""

from __future__ import annotations

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from code_agents.reviews.review_responder import (
    ReviewComment,
    ReviewResponse,
    ReviewResponder,
    format_review_comments,
)


class TestReviewCommentDataclass:
    """Verify ReviewComment dataclass defaults and fields."""

    def test_required_fields(self):
        c = ReviewComment(author="alice", body="Fix the typo")
        assert c.author == "alice"
        assert c.body == "Fix the typo"
        assert c.file_path == ""
        assert c.line == 0
        assert c.diff_hunk == ""
        assert c.created_at == ""

    def test_all_fields(self):
        c = ReviewComment(
            author="bob",
            body="Use constant",
            file_path="src/auth.py",
            line=42,
            diff_hunk="- old\n+ new",
            created_at="2026-04-01T10:00:00",
        )
        assert c.file_path == "src/auth.py"
        assert c.line == 42
        assert c.diff_hunk == "- old\n+ new"


class TestReviewResponseDataclass:
    """Verify ReviewResponse dataclass."""

    def test_defaults(self):
        c = ReviewComment(author="a", body="b")
        r = ReviewResponse(comment=c)
        assert r.reply_text == ""
        assert r.code_fix == ""
        assert r.fix_file == ""
        assert r.fix_line == 0


class TestDetectCurrentPR:
    """Verify _detect_current_pr extracts PR numbers from branch names."""

    def test_feature_branch_with_number(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="feature/PROJ-123-add-auth\n")
            result = resp._detect_current_pr()
            assert result == 123

    def test_fix_branch(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="fix/456\n")
            result = resp._detect_current_pr()
            assert result == 456

    def test_branch_no_number(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="main\n")
            result = resp._detect_current_pr()
            assert result is None

    def test_subprocess_failure(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch("subprocess.run", side_effect=Exception("not a git repo")):
            result = resp._detect_current_pr()
            assert result is None

    def test_pr_branch_pattern(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="pr/789\n")
            result = resp._detect_current_pr()
            assert result == 789


class TestBuildReplyPrompt:
    """Verify build_reply_prompt includes all relevant sections."""

    def test_basic_prompt(self):
        resp = ReviewResponder(cwd="/tmp")
        c = ReviewComment(author="alice", body="Use a constant here", file_path="src/config.py", line=10)
        prompt = resp.build_reply_prompt(c)
        assert "alice" in prompt
        assert "Use a constant here" in prompt
        assert "src/config.py:10" in prompt
        assert "REPLY:" in prompt
        assert "FIX:" in prompt

    def test_prompt_with_diff_hunk(self):
        resp = ReviewResponder(cwd="/tmp")
        c = ReviewComment(
            author="bob", body="Rename var",
            file_path="main.py", line=5,
            diff_hunk="- x = 1\n+ y = 1",
        )
        prompt = resp.build_reply_prompt(c)
        assert "Code context" in prompt
        assert "- x = 1" in prompt

    def test_prompt_with_source_context(self):
        resp = ReviewResponder(cwd="/tmp")
        c = ReviewComment(author="carol", body="Add docstring", file_path="app.py", line=1)
        prompt = resp.build_reply_prompt(c, source_context="def main():\n    pass\n")
        assert "Full file context" in prompt
        assert "def main():" in prompt

    def test_prompt_without_optional_sections(self):
        resp = ReviewResponder(cwd="/tmp")
        c = ReviewComment(author="dave", body="Looks good")
        prompt = resp.build_reply_prompt(c)
        assert "Code context" not in prompt
        assert "Full file context" not in prompt


class TestGetSourceContext:
    """Verify get_source_context reads correct lines from file."""

    def test_reads_context_around_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            for i in range(1, 21):
                f.write(f"line {i}\n")
            f.flush()
            path = f.name

        try:
            # Use the directory as cwd, file basename as path
            cwd = os.path.dirname(path)
            fname = os.path.basename(path)
            resp = ReviewResponder(cwd=cwd)
            ctx = resp.get_source_context(fname, line=10, context_lines=3)
            assert "line 8" in ctx
            assert "line 10" in ctx
            assert "line 12" in ctx
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        resp = ReviewResponder(cwd="/tmp")
        ctx = resp.get_source_context("nonexistent_file_xyz.py", line=5)
        assert ctx == ""

    def test_line_at_start(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            for i in range(1, 6):
                f.write(f"line {i}\n")
            f.flush()
            path = f.name

        try:
            cwd = os.path.dirname(path)
            fname = os.path.basename(path)
            resp = ReviewResponder(cwd=cwd)
            ctx = resp.get_source_context(fname, line=1, context_lines=3)
            assert "line 1" in ctx
            # Should not crash on negative index
            assert ctx != ""
        finally:
            os.unlink(path)


class TestFormatReviewComments:
    """Verify format_review_comments output."""

    def test_empty_comments(self):
        output = format_review_comments([])
        assert output == ""

    def test_single_comment(self):
        comments = [ReviewComment(author="alice", body="Fix typo", file_path="main.py", line=5)]
        output = format_review_comments(comments)
        assert "1." in output
        assert "alice" in output
        assert "main.py:5" in output
        assert "Fix typo" in output

    def test_multiple_comments(self):
        comments = [
            ReviewComment(author="alice", body="Fix typo", file_path="a.py", line=1),
            ReviewComment(author="bob", body="Add test", file_path="b.py", line=2),
        ]
        output = format_review_comments(comments)
        assert "1." in output
        assert "2." in output
        assert "alice" in output
        assert "bob" in output

    def test_long_body_truncated(self):
        long_body = "x" * 200
        comments = [ReviewComment(author="a", body=long_body, file_path="f.py", line=1)]
        output = format_review_comments(comments)
        # Should be truncated to 120 chars
        assert len(output.split("\n")[1].strip()) <= 125  # truncated body line


class TestGetPRComments:
    """Verify get_pr_comments flow."""

    def test_no_pr_detected_returns_empty(self):
        resp = ReviewResponder(cwd="/tmp")
        with patch.object(resp, "_detect_current_pr", return_value=None):
            assert resp.get_pr_comments() == []

    def test_with_explicit_pr_number(self):
        resp = ReviewResponder(cwd="/tmp")
        # Both fetchers return empty by default
        comments = resp.get_pr_comments(pr_number=42)
        assert comments == []
