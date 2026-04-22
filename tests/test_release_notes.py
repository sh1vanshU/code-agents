"""Tests for the release notes generator."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from code_agents.git_ops.release_notes import (
    ReleaseNotesGenerator, ReleaseNote,
)


class TestReleaseNote:
    """Test ReleaseNote dataclass."""

    def test_defaults(self):
        n = ReleaseNote(category="Features", description="Added login")
        assert n.pr_number == 0

    def test_with_pr(self):
        n = ReleaseNote(category="Bug Fixes", description="Fixed crash", pr_number=42)
        assert n.pr_number == 42


class TestCategorize:
    """Test commit message categorization."""

    def _gen(self, tmp_path):
        return ReleaseNotesGenerator(cwd=str(tmp_path))

    def test_feat(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("feat: add login") == "Features"
        assert g._categorize("feat(auth): add token refresh") == "Features"

    def test_fix(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("fix: resolve crash on startup") == "Bug Fixes"
        assert g._categorize("fix(db): connection leak") == "Bug Fixes"

    def test_perf(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("perf: optimize query") == "Performance"

    def test_docs(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("docs: update README") == "Documentation"

    def test_fallback_heuristic(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("add new payment method") == "Features"
        assert g._categorize("fix broken link") == "Bug Fixes"
        assert g._categorize("update dependencies") == "Maintenance"

    def test_unknown(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._categorize("miscellaneous change") == "Other"


class TestHumanize:
    """Test commit message humanization."""

    def _gen(self, tmp_path):
        return ReleaseNotesGenerator(cwd=str(tmp_path))

    def test_strip_prefix(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._humanize("feat: add login page") == "Added login page"

    def test_strip_scoped_prefix(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._humanize("fix(auth): resolve token expiry") == "Resolved token expiry"

    def test_strip_pr_ref(self, tmp_path):
        g = self._gen(tmp_path)
        result = g._humanize("feat: add feature (#123)")
        assert "#123" not in result
        assert "Added feature" in result

    def test_capitalize(self, tmp_path):
        g = self._gen(tmp_path)
        result = g._humanize("chore: update deps")
        assert result[0].isupper()

    def test_past_tense(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._humanize("feat: add X") == "Added X"
        assert g._humanize("fix: fix crash") == "Fixed crash"
        assert g._humanize("refactor: remove dead code") == "Removed dead code"
        assert g._humanize("perf: improve latency") == "Improved latency"

    def test_empty(self, tmp_path):
        g = self._gen(tmp_path)
        assert g._humanize("") == ""


class TestGetChanges:
    """Test git log parsing."""

    def test_parses_commits(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        mock_output = (
            "abc123|feat: add login (#42)|Alice|2025-01-01 12:00:00\n"
            "def456|fix: crash on startup|Bob|2025-01-02 12:00:00\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")
            changes = g._get_changes("v1.0", "v1.1")
            assert len(changes) == 2
            assert changes[0]["pr_number"] == 42
            assert changes[1]["pr_number"] == 0

    def test_empty_log(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            changes = g._get_changes("v1.0", "v1.1")
            assert changes == []

    def test_git_failure(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fatal: bad")
            changes = g._get_changes("v1.0", "v1.1")
            assert changes == []


class TestGenerate:
    """Test full generation flow."""

    def test_generate(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        with patch.object(g, "_get_changes", return_value=[
            {"message": "feat: add login (#42)", "pr_number": 42},
            {"message": "fix: crash on null input", "pr_number": 0},
        ]):
            notes = g.generate("v1.0", "v1.1")
            assert len(notes) == 2
            assert notes[0].category == "Features"
            assert notes[1].category == "Bug Fixes"

    def test_generate_empty(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        with patch.object(g, "_get_changes", return_value=[]):
            notes = g.generate("v1.0", "v1.1")
            assert notes == []


class TestFormatMarkdown:
    """Test Markdown formatting."""

    def test_empty(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        md = g.format_markdown([])
        assert "No changes" in md

    def test_with_notes(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        notes = [
            ReleaseNote(category="Features", description="Added login", pr_number=42),
            ReleaseNote(category="Bug Fixes", description="Fixed crash"),
        ]
        md = g.format_markdown(notes)
        assert "## Features" in md
        assert "## Bug Fixes" in md
        assert "(#42)" in md
        assert "Added login" in md


class TestFormatSlack:
    """Test Slack formatting."""

    def test_empty(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        text = g.format_slack([])
        assert "No changes" in text

    def test_with_notes(self, tmp_path):
        g = ReleaseNotesGenerator(cwd=str(tmp_path))
        notes = [
            ReleaseNote(category="Features", description="Added login"),
            ReleaseNote(category="Bug Fixes", description="Fixed crash"),
        ]
        text = g.format_slack(notes)
        assert "*Features*" in text
        assert "*Bug Fixes*" in text
        assert "Added login" in text
