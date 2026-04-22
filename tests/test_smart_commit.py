"""Tests for smart_commit.py — conventional commit message generation."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.smart_commit import SmartCommit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    def run(cmd):
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=repo,
        ).stdout

    run("git init")
    run("git config user.email 'test@test.com'")
    run("git config user.name 'Test'")
    run("echo 'hello' > file1.txt")
    run("git add file1.txt")
    run("git commit -m 'initial commit'")
    run("git branch -M main")
    return repo


@pytest.fixture
def sc(tmp_repo):
    """SmartCommit instance for the temp repo."""
    return SmartCommit(cwd=tmp_repo)


# ---------------------------------------------------------------------------
# extract_jira_ticket
# ---------------------------------------------------------------------------


class TestExtractJiraTicket:
    def test_feature_branch(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("feature/PROJ-123-add-login") == "PROJ-123"

    def test_fix_branch(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("fix/BUG-456") == "BUG-456"

    def test_bare_ticket(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("AB-99") == "AB-99"

    def test_no_ticket(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("feature/add-login") is None

    def test_no_ticket_main(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("main") is None

    def test_jira_project_key_env(self):
        sc = SmartCommit(cwd="/tmp")
        with patch.dict(os.environ, {"JIRA_PROJECT_KEY": "MYPROJ"}):
            assert sc.extract_jira_ticket("feature/myproj-42-stuff") == "MYPROJ-42"

    def test_multiple_tickets_returns_first(self):
        sc = SmartCommit(cwd="/tmp")
        assert sc.extract_jira_ticket("feature/PROJ-10-and-PROJ-20") == "PROJ-10"

    def test_lowercase_branch_no_match(self):
        sc = SmartCommit(cwd="/tmp")
        # lowercase doesn't match the [A-Z] pattern
        assert sc.extract_jira_ticket("feature/proj-123") is None

    def test_from_current_branch(self, tmp_repo):
        """extract_jira_ticket with no arg reads current branch."""
        sc = SmartCommit(cwd=tmp_repo)
        # main branch has no ticket
        assert sc.extract_jira_ticket() is None


# ---------------------------------------------------------------------------
# classify_change
# ---------------------------------------------------------------------------


class TestClassifyChange:
    def setup_method(self):
        self.sc = SmartCommit(cwd="/tmp")

    def test_test_files(self):
        files = ["tests/test_foo.py", "tests/test_bar.py"]
        assert self.sc.classify_change(files, "") == "test"

    def test_spec_files(self):
        files = ["src/foo.spec.ts", "src/bar.spec.ts"]
        assert self.sc.classify_change(files, "") == "test"

    def test_docs_files(self):
        files = ["README.md", "CHANGELOG.md"]
        assert self.sc.classify_change(files, "") == "docs"

    def test_config_files(self):
        files = ["docker-compose.yml", "Dockerfile"]
        assert self.sc.classify_change(files, "") == "chore"

    @patch("subprocess.run")
    def test_fix_from_diff(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        files = ["src/auth.py"]
        diff = "fix: resolved bug with error handling in auth"
        assert self.sc.classify_change(files, diff) == "fix"

    @patch("subprocess.run")
    def test_refactor_from_diff(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        files = ["src/utils.py"]
        diff = "refactor the helper function to extract common logic"
        assert self.sc.classify_change(files, diff) == "refactor"

    @patch("subprocess.run")
    def test_new_files_classified_as_feat(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/new_feature.py\n"
        )
        files = ["src/new_feature.py"]
        assert self.sc.classify_change(files, "") == "feat"

    @patch("subprocess.run")
    def test_default_feat(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        files = ["src/something.py"]
        assert self.sc.classify_change(files, "some normal change") == "feat"


# ---------------------------------------------------------------------------
# generate_scope
# ---------------------------------------------------------------------------


class TestGenerateScope:
    def setup_method(self):
        self.sc = SmartCommit(cwd="/tmp")

    def test_single_dir(self):
        files = ["agents/router/config.yaml"]
        assert self.sc.generate_scope(files) in ("agents", "router")

    def test_tests_dir(self):
        files = ["tests/test_foo.py", "tests/test_bar.py"]
        assert self.sc.generate_scope(files) == "tests"

    def test_docs_dir(self):
        files = ["docs/guide.md"]
        assert self.sc.generate_scope(files) == "docs"

    def test_empty_files(self):
        assert self.sc.generate_scope([]) == ""

    def test_root_file(self):
        files = ["README.md"]
        assert self.sc.generate_scope(files) == ""

    def test_code_agents_dir_is_empty_scope(self):
        # code_agents maps to "" so no scope
        files = ["code_agents/cli/cli.py"]
        scope = self.sc.generate_scope(files)
        assert scope == "cli"


# ---------------------------------------------------------------------------
# generate_description
# ---------------------------------------------------------------------------


class TestGenerateDescription:
    def setup_method(self):
        self.sc = SmartCommit(cwd="/tmp")

    def test_single_file_feat(self):
        desc = self.sc.generate_description(["src/auth.py"], "", "feat")
        assert "auth" in desc

    def test_single_file_test(self):
        desc = self.sc.generate_description(["tests/test_auth.py"], "", "test")
        assert "test" in desc.lower()

    def test_single_file_docs(self):
        desc = self.sc.generate_description(["README.md"], "", "docs")
        assert "README.md" in desc

    def test_single_file_fix(self):
        desc = self.sc.generate_description(["src/bug.py"], "", "fix")
        assert "fix" in desc.lower()

    def test_multiple_files_test(self):
        files = ["tests/test_a.py", "tests/test_b.py"]
        desc = self.sc.generate_description(files, "", "test")
        assert "2 files" in desc

    def test_multiple_files_docs(self):
        files = ["docs/a.md", "docs/b.md", "docs/c.md"]
        desc = self.sc.generate_description(files, "", "docs")
        assert "3 files" in desc

    @patch("subprocess.run")
    def test_multiple_files_feat_with_new(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/new.py\n"
        )
        files = ["src/new.py", "src/existing.py"]
        desc = self.sc.generate_description(files, "", "feat")
        assert "new" in desc


# ---------------------------------------------------------------------------
# generate_message (integration)
# ---------------------------------------------------------------------------


class TestGenerateMessage:
    def test_no_staged_files(self, sc):
        """No staged files returns error."""
        result = sc.generate_message()
        assert "error" in result
        assert "No staged" in result["error"]

    def test_single_new_file(self, tmp_repo):
        """Staged new file generates feat message."""
        subprocess.run(
            "echo 'new content' > newfile.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "newfile.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        assert "error" not in result
        assert result["type"] == "feat"
        assert "newfile" in result["description"]
        assert result["full_message"].startswith("feat")
        assert isinstance(result["files"], list)
        assert "newfile.py" in result["files"]

    def test_docs_file(self, tmp_repo):
        """Staged .md file classified as docs."""
        subprocess.run(
            "echo '# Guide' > guide.md",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "guide.md"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        assert result["type"] == "docs"
        assert result["full_message"].startswith("docs")

    def test_message_format_conventional(self, tmp_repo):
        """Message follows conventional commit format: type[(scope)]: description."""
        subprocess.run(
            "echo 'x' > feature.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "feature.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        header = result["full_message"].split("\n")[0]
        # Should match pattern: type: description  or  type(scope): description
        assert ": " in header
        prefix = header.split(": ")[0]
        assert prefix in (
            "feat", "fix", "docs", "test", "chore", "refactor",
            # with scope
        ) or "(" in prefix

    def test_ticket_in_message(self, tmp_repo):
        """Jira ticket from branch appears in message footer."""
        subprocess.run(
            ["git", "checkout", "-b", "feature/PROJ-42-thing"],
            cwd=tmp_repo,
        )
        subprocess.run(
            "echo 'y' > thing.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "thing.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        assert result["ticket"] == "PROJ-42"
        assert "Refs: PROJ-42" in result["full_message"]

    def test_multiple_files_body(self, tmp_repo):
        """Multiple staged files produce a body listing files."""
        for name in ("a.py", "b.py", "c.py"):
            subprocess.run(
                f"echo 'x' > {name}",
                shell=True, cwd=tmp_repo,
            )
        subprocess.run(
            ["git", "add", "a.py", "b.py", "c.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        assert len(result["files"]) == 3
        assert "- a.py" in result["full_message"]
        assert "- b.py" in result["full_message"]
        assert "- c.py" in result["full_message"]

    def test_result_dict_keys(self, tmp_repo):
        """Result dict has all expected keys."""
        subprocess.run(
            "echo 'z' > z.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "z.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        result = sc.generate_message()

        for key in ("type", "scope", "description", "body", "ticket", "files", "full_message"):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


class TestCommit:
    def test_commit_success(self, tmp_repo):
        """Successful commit returns True."""
        subprocess.run(
            "echo 'content' > committed.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "committed.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        assert sc.commit("feat: add committed") is True

        # Verify commit was made
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=tmp_repo,
        )
        assert "feat: add committed" in log.stdout

    def test_commit_no_staged(self, sc):
        """Commit with nothing staged returns False."""
        assert sc.commit("feat: nothing") is False


# ---------------------------------------------------------------------------
# get_staged_files / get_current_branch / get_staged_diff
# ---------------------------------------------------------------------------


class TestGitHelpers:
    def test_get_staged_files_empty(self, sc):
        assert sc.get_staged_files() == []

    def test_get_staged_files_with_staged(self, tmp_repo):
        subprocess.run(
            "echo 'x' > staged.py",
            shell=True, cwd=tmp_repo,
        )
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=tmp_repo,
        )
        sc = SmartCommit(cwd=tmp_repo)
        assert "staged.py" in sc.get_staged_files()

    def test_get_current_branch(self, sc, tmp_repo):
        branch = sc.get_current_branch()
        assert branch == "main"

    def test_get_staged_diff_empty(self, sc):
        diff = sc.get_staged_diff()
        assert "Stats:" in diff
        assert "Diff:" in diff

    def test_get_staged_files_git_error(self):
        sc = SmartCommit(cwd="/nonexistent")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert sc.get_staged_files() == []


# ---------------------------------------------------------------------------
# classify_change edge cases (line 116)
# ---------------------------------------------------------------------------


class TestClassifyChangeEdge:
    def test_half_new_files_classified_as_feat(self):
        sc = SmartCommit(cwd="/tmp")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="src/a.py\nsrc/b.py\n"
            )
            result = sc.classify_change(["src/a.py", "src/b.py", "src/c.py"], "")
        assert result == "feat"


# ---------------------------------------------------------------------------
# generate_description edge cases (lines 185-210)
# ---------------------------------------------------------------------------


class TestGenerateDescriptionEdge:
    def test_single_file_refactor(self):
        sc = SmartCommit(cwd="/tmp")
        desc = sc.generate_description(["src/mod.py"], "", "refactor")
        assert "refactor" in desc.lower()

    def test_multiple_files_fix(self):
        sc = SmartCommit(cwd="/tmp")
        files = ["a.py", "b.py", "c.py"]
        desc = sc.generate_description(files, "", "fix")
        assert "3 files" in desc

    def test_multiple_files_refactor(self):
        sc = SmartCommit(cwd="/tmp")
        files = ["a.py", "b.py"]
        desc = sc.generate_description(files, "", "refactor")
        assert "2 files" in desc

    @patch("subprocess.run")
    def test_multiple_files_no_new_files(self, mock_run):
        sc = SmartCommit(cwd="/tmp")
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        files = ["a.py", "b.py"]
        desc = sc.generate_description(files, "", "feat")
        assert "2 files" in desc

    @patch("subprocess.run")
    def test_generate_message_with_scope(self, mock_run):
        """Message with scope gets parentheses."""
        sc = SmartCommit(cwd="/tmp")
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="tests/test_a.py\n"),  # staged files
            MagicMock(returncode=0, stdout="", stderr=""),  # diff stat
            MagicMock(returncode=0, stdout="", stderr=""),  # diff
            MagicMock(returncode=0, stdout="main", stderr=""),  # branch
            MagicMock(returncode=0, stdout="tests/test_a.py\n"),  # new files check
        ]
        with patch.object(sc, "get_staged_files", return_value=["tests/test_a.py"]), \
             patch.object(sc, "get_staged_diff", return_value="Stats:\n\nDiff:\n"), \
             patch.object(sc, "get_current_branch", return_value="main"):
            result = sc.generate_message()
        assert "error" not in result
        assert result["type"] == "test"
