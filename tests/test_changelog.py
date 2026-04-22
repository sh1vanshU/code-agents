"""Tests for code_agents.changelog — automated changelog generator."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.git_ops.changelog import (
    ChangelogGenerator,
    Changelog,
    ChangelogEntry,
    CommitInfo,
    PRInfo,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def gen():
    return ChangelogGenerator(cwd="/tmp/test-repo")


# ── TestCommitParsing ────────────────────────────────────────────────────────


class TestCommitParsing:
    """Test _get_commits parses git log output correctly."""

    GIT_LOG_OUTPUT = (
        "abc1234def|feat: add login page|Alice|2026-04-01T10:00:00+05:30\n"
        "bbb2345eee|fix(auth): handle expired tokens|Bob|2026-04-02T11:00:00+05:30\n"
        "ccc3456fff|docs: update README|Charlie|2026-04-03T12:00:00+05:30\n"
        "ddd4567ggg|random commit message|Dave|2026-04-04T13:00:00+05:30\n"
    )

    @patch("subprocess.run")
    def test_parse_commits_from_git_log(self, mock_run, gen):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=self.GIT_LOG_OUTPUT),  # git log
            MagicMock(returncode=0, stdout="file1.py\nfile2.py\n"),  # diff-tree commit 1
            MagicMock(returncode=0, stdout="file3.py\n"),  # diff-tree commit 2
            MagicMock(returncode=0, stdout="README.md\n"),  # diff-tree commit 3
            MagicMock(returncode=0, stdout="foo.py\nbar.py\nbaz.py\n"),  # diff-tree commit 4
        ]
        commits = gen._get_commits("v1.0.0", "HEAD")

        assert len(commits) == 4
        assert commits[0].sha == "abc1234def"
        assert commits[0].message == "feat: add login page"
        assert commits[0].author == "Alice"
        assert commits[0].files_changed == 2
        assert commits[1].author == "Bob"

    @patch("subprocess.run")
    def test_empty_git_log(self, mock_run, gen):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        commits = gen._get_commits("v1.0.0", "HEAD")
        assert commits == []

    @patch("subprocess.run")
    def test_git_log_failure(self, mock_run, gen):
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: bad ref")
        commits = gen._get_commits("v1.0.0", "HEAD")
        assert commits == []

    @patch("subprocess.run")
    def test_git_log_timeout(self, mock_run, gen):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="git", timeout=30)
        commits = gen._get_commits("v1.0.0", "HEAD")
        assert commits == []


# ── TestCategorize ───────────────────────────────────────────────────────────


class TestCategorize:
    """Test _categorize sorts commits and PRs into correct buckets."""

    def test_feat_prefix(self, gen):
        commits = [CommitInfo(sha="aaa", message="feat: add search", author="A", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.features) == 1
        assert cl.features[0].description == "add search"

    def test_fix_prefix(self, gen):
        commits = [CommitInfo(sha="bbb", message="fix: null pointer", author="B", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.fixes) == 1
        assert cl.fixes[0].description == "null pointer"

    def test_docs_prefix(self, gen):
        commits = [CommitInfo(sha="ccc", message="docs: update API guide", author="C", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.docs) == 1
        assert cl.docs[0].description == "update API guide"

    def test_breaking_bang(self, gen):
        commits = [CommitInfo(sha="ddd", message="feat!: remove v1 API", author="D", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.breaking) == 1

    def test_refactor_prefix(self, gen):
        commits = [CommitInfo(sha="eee", message="refactor: simplify auth", author="E", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.refactoring) == 1

    def test_unknown_prefix_goes_to_other(self, gen):
        commits = [CommitInfo(sha="fff", message="random stuff", author="F", date="2026-04-01")]
        cl = gen._categorize(commits, [])
        assert len(cl.other) == 1

    def test_pr_with_label(self, gen):
        prs = [PRInfo(number=42, title="Add feature X", body="", labels=["enhancement"], author="alice")]
        cl = gen._categorize([], prs)
        assert len(cl.features) == 1
        assert cl.features[0].pr_number == 42

    def test_pr_bug_label(self, gen):
        prs = [PRInfo(number=99, title="Fix crash on startup", body="", labels=["bug"], author="bob")]
        cl = gen._categorize([], prs)
        assert len(cl.fixes) == 1

    def test_pr_dedup_with_commit(self, gen):
        """Commits referencing a PR number already covered by a PR should be skipped."""
        commits = [CommitInfo(sha="aaa", message="feat: add X (#42)", author="A", date="2026-04-01")]
        prs = [PRInfo(number=42, title="Add X", body="", labels=["enhancement"], author="alice")]
        cl = gen._categorize(commits, prs)
        # Only the PR entry should exist, not the commit
        assert len(cl.features) == 1
        assert cl.features[0].pr_number == 42

    def test_mixed_commits_and_prs(self, gen):
        commits = [
            CommitInfo(sha="aaa", message="feat: add login", author="A", date="2026-04-01"),
            CommitInfo(sha="bbb", message="fix: crash bug", author="B", date="2026-04-02"),
        ]
        prs = [
            PRInfo(number=10, title="docs: update guide", body="", labels=["documentation"], author="C"),
        ]
        cl = gen._categorize(commits, prs)
        assert len(cl.features) == 1
        assert len(cl.fixes) == 1
        assert len(cl.docs) == 1


# ── TestMarkdown ─────────────────────────────────────────────────────────────


class TestMarkdown:
    """Test format_markdown output structure."""

    def test_basic_markdown(self, gen):
        cl = Changelog(version="v1.3.0", date="2026-04-09")
        cl.features.append(ChangelogEntry(category="feature", description="Add mindmap generator", pr_number=123, author="alice"))
        cl.fixes.append(ChangelogEntry(category="fix", description="Fix ANSI rendering", pr_number=125, author="bob"))

        md = gen.format_markdown(cl)

        assert "## v1.3.0 (2026-04-09)" in md
        assert "### Features" in md
        assert "### Bug Fixes" in md
        assert "Add mindmap generator (#123)" in md
        assert "Fix ANSI rendering (#125)" in md
        assert "@alice" in md

    def test_empty_changelog(self, gen):
        cl = Changelog(version="v0.1.0", date="2026-04-09")
        md = gen.format_markdown(cl)
        assert "No changes found." in md

    def test_breaking_section(self, gen):
        cl = Changelog(version="v2.0.0", date="2026-04-09")
        cl.breaking.append(ChangelogEntry(category="breaking", description="Remove legacy API", commit_sha="abc1234"))
        md = gen.format_markdown(cl)
        assert "### Breaking Changes" in md
        assert "Remove legacy API (abc1234)" in md

    def test_commit_sha_shown_when_no_pr(self, gen):
        cl = Changelog(version="v1.0.0", date="2026-04-09")
        cl.other.append(ChangelogEntry(category="other", description="chore stuff", commit_sha="def5678"))
        md = gen.format_markdown(cl)
        assert "(def5678)" in md

    def test_sections_ordered_correctly(self, gen):
        cl = Changelog(version="v1.0.0", date="2026-04-09")
        cl.other.append(ChangelogEntry(category="other", description="other thing"))
        cl.features.append(ChangelogEntry(category="feature", description="new thing"))
        cl.breaking.append(ChangelogEntry(category="breaking", description="break thing"))
        md = gen.format_markdown(cl)
        # Breaking should come before Features, Features before Other
        assert md.index("Breaking Changes") < md.index("Features")
        assert md.index("Features") < md.index("Other Changes")


# ── TestTerminal ─────────────────────────────────────────────────────────────


class TestTerminal:
    """Test format_terminal output."""

    def test_basic_terminal(self, gen):
        cl = Changelog(version="v1.3.0", date="2026-04-09")
        cl.features.append(ChangelogEntry(category="feature", description="Add login", pr_number=10))
        cl.fixes.append(ChangelogEntry(category="fix", description="Fix crash", commit_sha="abc1234"))

        output = gen.format_terminal(cl)

        assert "Changelog" in output
        assert "v1.3.0" in output
        assert "[+] Features (1)" in output
        assert "[*] Bug Fixes (1)" in output
        assert "Add login (#10)" in output
        assert "Fix crash (abc1234)" in output
        assert "Total entries: 2" in output

    def test_empty_terminal(self, gen):
        cl = Changelog(version="v0.1.0", date="2026-04-09")
        output = gen.format_terminal(cl)
        assert "No changes found." in output

    def test_breaking_icon(self, gen):
        cl = Changelog(version="v2.0.0", date="2026-04-09")
        cl.breaking.append(ChangelogEntry(category="breaking", description="Remove old API"))
        output = gen.format_terminal(cl)
        assert "[!] Breaking Changes" in output


# ── TestPRParsing ────────────────────────────────────────────────────────────


class TestPRParsing:
    """Test _get_merged_prs with mocked gh output."""

    GH_OUTPUT = '[{"number":42,"title":"feat: add X","body":"desc","labels":[{"name":"enhancement"}],"author":{"login":"alice"},"mergedAt":"2026-04-05T10:00:00Z"}]'

    @patch("subprocess.run")
    def test_parse_gh_output(self, mock_run, gen):
        # Mock date range calls + gh call
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="2026-04-01T00:00:00+05:30\n"),  # from_ref date
            MagicMock(returncode=0, stdout="2026-04-09T00:00:00+05:30\n"),  # to_ref date
            MagicMock(returncode=0, stdout=self.GH_OUTPUT),  # gh pr list
        ]
        prs = gen._get_merged_prs("v1.0.0", "HEAD")
        assert len(prs) == 1
        assert prs[0].number == 42
        assert prs[0].author == "alice"
        assert "enhancement" in prs[0].labels

    @patch("subprocess.run")
    def test_gh_not_installed(self, mock_run, gen):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="2026-04-01T00:00:00+05:30\n"),
            MagicMock(returncode=0, stdout="2026-04-09T00:00:00+05:30\n"),
            FileNotFoundError("gh not found"),
        ]
        prs = gen._get_merged_prs("v1.0.0", "HEAD")
        assert prs == []

    @patch("subprocess.run")
    def test_gh_failure(self, mock_run, gen):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="2026-04-01T00:00:00+05:30\n"),
            MagicMock(returncode=0, stdout="2026-04-09T00:00:00+05:30\n"),
            MagicMock(returncode=1, stdout="", stderr="not authenticated"),
        ]
        prs = gen._get_merged_prs("v1.0.0", "HEAD")
        assert prs == []


# ── TestHelpers ──────────────────────────────────────────────────────────────


class TestHelpers:
    """Test helper methods."""

    def test_category_from_message_feat(self, gen):
        assert gen._category_from_message("feat: add search") == "feature"

    def test_category_from_message_fix(self, gen):
        assert gen._category_from_message("fix: null pointer") == "fix"

    def test_category_from_message_docs(self, gen):
        assert gen._category_from_message("docs: update guide") == "docs"

    def test_category_from_message_breaking_bang(self, gen):
        assert gen._category_from_message("feat!: remove API") == "breaking"

    def test_category_from_message_unknown(self, gen):
        assert gen._category_from_message("random stuff") == "other"

    def test_clean_message_strips_prefix(self, gen):
        assert gen._clean_message("feat: add login") == "add login"
        assert gen._clean_message("fix(auth): handle token") == "handle token"

    def test_clean_message_no_prefix(self, gen):
        assert gen._clean_message("random commit") == "random commit"

    def test_extract_pr_number(self, gen):
        assert gen._extract_pr_number("feat: add X (#42)") == 42
        assert gen._extract_pr_number("just a message") is None

    def test_category_from_pr_label(self, gen):
        pr = PRInfo(number=1, title="whatever", body="", labels=["bug"], author="a")
        assert gen._category_from_pr(pr) == "fix"

    def test_category_from_pr_title_fallback(self, gen):
        pr = PRInfo(number=1, title="feat: add thing", body="", labels=[], author="a")
        assert gen._category_from_pr(pr) == "feature"


# ── TestWriteMarkdown ────────────────────────────────────────────────────────


class TestWriteMarkdown:
    """Test write_markdown file operations."""

    def test_write_new_file(self, tmp_path):
        gen = ChangelogGenerator(cwd=str(tmp_path))
        cl = Changelog(version="v1.0.0", date="2026-04-09")
        cl.features.append(ChangelogEntry(category="feature", description="init"))
        path = gen.write_markdown(cl, filepath=str(tmp_path / "CHANGELOG.md"))
        content = (tmp_path / "CHANGELOG.md").read_text()
        assert "# Changelog" in content
        assert "## v1.0.0" in content

    def test_prepend_to_existing(self, tmp_path):
        changelog_path = tmp_path / "CHANGELOG.md"
        changelog_path.write_text("# Changelog\n\n## v0.9.0 (2026-03-01)\n\n- Old stuff\n")
        gen = ChangelogGenerator(cwd=str(tmp_path))
        cl = Changelog(version="v1.0.0", date="2026-04-09")
        cl.features.append(ChangelogEntry(category="feature", description="new"))
        gen.write_markdown(cl, filepath=str(changelog_path))
        content = changelog_path.read_text()
        assert "v1.0.0" in content
        assert "v0.9.0" in content
        assert content.index("v1.0.0") < content.index("v0.9.0")
