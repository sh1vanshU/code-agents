"""Tests for changelog_gen.py — changelog generator."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.generators.changelog_gen import (
    ChangelogGenerator, ChangelogData, CommitEntry,
    format_changelog_terminal,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary directory simulating a git repo."""
    return tmp_path


class TestChangelogGenerator:
    """Tests for ChangelogGenerator."""

    def test_parse_conventional_feat(self):
        gen = ChangelogGenerator(cwd="/tmp")
        entries = gen.parse_commits(["abc1234 feat: add new feature"])
        assert len(entries) == 1
        assert entries[0].type == "feat"
        assert entries[0].message == "add new feature"

    def test_parse_conventional_fix_with_scope(self):
        gen = ChangelogGenerator(cwd="/tmp")
        entries = gen.parse_commits(["abc1234 fix(auth): handle expired tokens"])
        assert len(entries) == 1
        assert entries[0].type == "fix"
        assert entries[0].scope == "auth"
        assert entries[0].message == "handle expired tokens"

    def test_parse_breaking_change(self):
        gen = ChangelogGenerator(cwd="/tmp")
        entries = gen.parse_commits(["abc1234 feat!: remove deprecated API"])
        assert len(entries) == 1
        assert entries[0].type == "breaking"
        assert entries[0].breaking is True

    def test_parse_non_conventional(self):
        gen = ChangelogGenerator(cwd="/tmp")
        entries = gen.parse_commits(["abc1234 random commit message"])
        assert len(entries) == 1
        assert entries[0].type == "chore"  # defaults to chore

    def test_parse_multiple_types(self):
        gen = ChangelogGenerator(cwd="/tmp")
        entries = gen.parse_commits([
            "abc1234 feat: add login",
            "def5678 fix: fix crash",
            "aab9012 docs: update readme",
            "bbc3456 test: add unit tests",
        ])
        assert len(entries) == 4
        types = {e.type for e in entries}
        assert "feat" in types
        assert "fix" in types
        assert "docs" in types
        assert "test" in types

    def test_format_markdown(self):
        gen = ChangelogGenerator(cwd="/tmp", version="1.0.0")
        data = ChangelogData(
            version="1.0.0",
            date="2026-04-01",
            commits=[
                CommitEntry(hash="abc1234", type="feat", scope="", message="add login", breaking=False),
                CommitEntry(hash="def5678", type="fix", scope="auth", message="fix crash", breaking=False),
            ],
        )
        md = gen.format_markdown(data)
        assert "## [1.0.0]" in md
        assert "### Features" in md
        assert "### Bug Fixes" in md
        assert "add login" in md
        assert "**auth**" in md

    def test_format_empty(self):
        gen = ChangelogGenerator(cwd="/tmp")
        data = ChangelogData(version="0.1.0", date="2026-04-01", commits=[])
        md = gen.format_markdown(data)
        assert "No conventional commits" in md

    def test_prepend_to_new_changelog(self, tmp_path):
        gen = ChangelogGenerator(cwd=str(tmp_path))
        data = ChangelogData(
            version="1.0.0",
            date="2026-04-01",
            commits=[CommitEntry(hash="abc", type="feat", scope="", message="init", breaking=False)],
        )
        path = gen.prepend_to_changelog(data, filepath=str(tmp_path / "CHANGELOG.md"))
        content = (tmp_path / "CHANGELOG.md").read_text()
        assert "# Changelog" in content
        assert "## [1.0.0]" in content

    def test_prepend_to_existing_changelog(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [0.9.0] - 2026-03-01\n\n- Old stuff\n")
        gen = ChangelogGenerator(cwd=str(tmp_path))
        data = ChangelogData(
            version="1.0.0",
            date="2026-04-01",
            commits=[CommitEntry(hash="abc", type="feat", scope="", message="new", breaking=False)],
        )
        gen.prepend_to_changelog(data, filepath=str(changelog))
        content = changelog.read_text()
        assert "## [1.0.0]" in content
        assert "## [0.9.0]" in content
        # New version should appear before old
        assert content.index("1.0.0") < content.index("0.9.0")

    @patch("subprocess.run")
    def test_get_last_tag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="v1.2.3\n")
        gen = ChangelogGenerator(cwd="/tmp")
        tag = gen.get_last_tag()
        assert tag == "v1.2.3"

    @patch("subprocess.run")
    def test_get_last_tag_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        gen = ChangelogGenerator(cwd="/tmp")
        tag = gen.get_last_tag()
        assert tag is None


class TestFormatChangelog:
    """Tests for format_changelog_terminal."""

    def test_format_terminal(self):
        data = ChangelogData(
            version="1.0.0",
            date="2026-04-01",
            commits=[
                CommitEntry(hash="abc1234", type="feat", scope="", message="add login", breaking=False),
            ],
        )
        output = format_changelog_terminal(data)
        assert "Changelog" in output
        assert "Features" in output
        assert "add login" in output

    def test_format_terminal_empty(self):
        data = ChangelogData(version="0.1.0", date="2026-04-01", commits=[])
        output = format_changelog_terminal(data)
        assert "No conventional commits" in output


# ── get_commits_since_tag (lines 84-102) ────────────────────────────────────


class TestGetCommitsSinceTag:
    @patch("subprocess.run")
    def test_with_tag(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc1234 feat: new\ndef5678 fix: bug\n"
        )
        gen = ChangelogGenerator(cwd="/tmp")
        commits = gen.get_commits_since_tag("v1.0.0")
        assert len(commits) == 2
        # Check command uses tag
        cmd = mock_run.call_args[0][0]
        assert "v1.0.0..HEAD" in cmd

    @patch("subprocess.run")
    def test_without_tag(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc1234 feat: new\n"
        )
        gen = ChangelogGenerator(cwd="/tmp")
        commits = gen.get_commits_since_tag(None)
        assert len(commits) == 1

    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="git", timeout=10)
        gen = ChangelogGenerator(cwd="/tmp")
        commits = gen.get_commits_since_tag("v1.0.0")
        assert commits == []

    @patch("subprocess.run")
    def test_git_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        gen = ChangelogGenerator(cwd="/tmp")
        commits = gen.get_commits_since_tag("v1.0.0")
        assert commits == []


# ── get_last_tag timeout (lines 84-85) ─────────────────────────────────────


class TestGetLastTagTimeout:
    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="git", timeout=10)
        gen = ChangelogGenerator(cwd="/tmp")
        assert gen.get_last_tag() is None


# ── generate (lines 126-129) ───────────────────────────────────────────────


class TestGenerate:
    @patch("subprocess.run")
    def test_generate_full(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="v1.0.0\n"),  # describe --tags
            MagicMock(returncode=0, stdout="abc1234 feat: new feature\n"),  # log
        ]
        gen = ChangelogGenerator(cwd="/tmp", version="2.0.0")
        data = gen.generate()
        assert data.version == "2.0.0"
        assert len(data.commits) == 1
        assert data.commits[0].type == "feat"


# ── prepend_to_changelog without header (line 177) ─────────────────────────


class TestPrependWithoutHeader:
    def test_prepend_no_heading(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("Some content without a heading\n")
        gen = ChangelogGenerator(cwd=str(tmp_path))
        data = ChangelogData(
            version="1.0.0",
            date="2026-04-01",
            commits=[CommitEntry(hash="abc", type="feat", scope="", message="new", breaking=False)],
        )
        gen.prepend_to_changelog(data, filepath=str(changelog))
        content = changelog.read_text()
        assert "## [1.0.0]" in content
        assert "Some content" in content
