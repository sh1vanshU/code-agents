"""Tests for git_client.py — async git operations."""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from code_agents.cicd.git_client import GitClient, GitOpsError, _validate_ref


# --- Unit tests (no git repo needed) ---


class TestValidateRef:
    def test_valid_refs(self):
        for ref in ("main", "feature/foo", "release-1.0", "v1.2.3", "HEAD"):
            _validate_ref(ref)  # should not raise

    def test_invalid_refs(self):
        for ref in ("", "branch name", "foo;rm -rf /", "$(whoami)", "a\nb"):
            with pytest.raises(GitOpsError, match="Invalid"):
                _validate_ref(ref)


# --- Integration tests (use a real temporary git repo) ---


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    def run(cmd):
        result = os.popen(f"cd {repo} && {cmd} 2>&1").read()
        return result

    run("git init")
    run("git config user.email 'test@test.com'")
    run("git config user.name 'Test'")
    # Create initial commit on main
    run("echo 'hello' > file1.txt")
    run("git add file1.txt")
    run("git commit -m 'initial commit'")
    # Rename default branch to main if needed
    run("git branch -M main")
    return repo


class TestGitClient:
    def test_current_branch(self, tmp_repo):
        client = GitClient(tmp_repo)
        branch = asyncio.run(client.current_branch())
        assert branch == "main"

    def test_list_branches(self, tmp_repo):
        client = GitClient(tmp_repo)
        branches = asyncio.run(client.list_branches())
        names = [b["name"] for b in branches]
        assert "main" in names

    def test_log(self, tmp_repo):
        client = GitClient(tmp_repo)
        commits = asyncio.run(client.log("main"))
        assert len(commits) >= 1
        assert commits[0]["message"] == "initial commit"

    def test_status_clean(self, tmp_repo):
        client = GitClient(tmp_repo)
        status = asyncio.run(client.status())
        assert status["clean"] is True

    def test_status_dirty(self, tmp_repo):
        # Create an untracked file
        with open(os.path.join(tmp_repo, "new.txt"), "w") as f:
            f.write("new")
        client = GitClient(tmp_repo)
        status = asyncio.run(client.status())
        assert status["clean"] is False
        assert any(f["file"] == "new.txt" for f in status["files"])

    def test_diff(self, tmp_repo):
        # Create a feature branch with changes
        os.popen(f"cd {tmp_repo} && git checkout -b feature 2>&1").read()
        with open(os.path.join(tmp_repo, "file2.txt"), "w") as f:
            f.write("new file content\n")
        os.popen(f"cd {tmp_repo} && git add file2.txt && git commit -m 'add file2' 2>&1").read()

        client = GitClient(tmp_repo)
        diff = asyncio.run(client.diff("main", "feature"))
        assert diff["files_changed"] >= 1
        assert diff["insertions"] >= 1
        assert any("file2.txt" in f["file"] for f in diff["changed_files"])

    def test_diff_invalid_ref(self, tmp_repo):
        client = GitClient(tmp_repo)
        with pytest.raises(GitOpsError, match="Invalid"):
            asyncio.run(client.diff("main", "bad;ref"))

    def test_log_invalid_branch(self, tmp_repo):
        client = GitClient(tmp_repo)
        with pytest.raises(GitOpsError, match="Invalid"):
            asyncio.run(client.log("$(whoami)"))


# --- Mock-based tests for checkout, stash, merge, add, commit ---


class TestCheckout:
    def test_checkout_clean(self, tmp_repo):
        """Checkout succeeds on a clean working tree."""
        client = GitClient(tmp_repo)
        # Create branch first, then switch back to main
        os.popen(f"cd {tmp_repo} && git checkout -b feature-clean 2>&1").read()
        os.popen(f"cd {tmp_repo} && git checkout main 2>&1").read()
        result = asyncio.run(client.checkout("feature-clean"))
        assert result["success"] is True
        assert result["branch"] == "feature-clean"
        assert result["created"] is False

    def test_checkout_create(self, tmp_repo):
        """Checkout with create=True passes -b flag and creates new branch."""
        client = GitClient(tmp_repo)
        result = asyncio.run(client.checkout("new-feature", create=True))
        assert result["success"] is True
        assert result["branch"] == "new-feature"
        assert result["created"] is True

    def test_checkout_dirty_tree(self, tmp_repo):
        """Checkout raises GitOpsError when working tree is dirty."""
        # Create an uncommitted file
        with open(os.path.join(tmp_repo, "dirty.txt"), "w") as f:
            f.write("uncommitted")
        os.popen(f"cd {tmp_repo} && git add dirty.txt 2>&1").read()
        client = GitClient(tmp_repo)
        with pytest.raises(GitOpsError, match="uncommitted change"):
            asyncio.run(client.checkout("main"))


class TestStash:
    def test_stash_push(self, tmp_repo):
        """Stash push saves dirty changes."""
        with open(os.path.join(tmp_repo, "file1.txt"), "w") as f:
            f.write("modified")
        client = GitClient(tmp_repo)
        result = asyncio.run(client.stash("push", message="test stash"))
        assert result["action"] == "push"
        # Working tree should be clean after stash
        status = asyncio.run(client.status())
        assert status["clean"] is True

    def test_stash_pop(self, tmp_repo):
        """Stash pop restores stashed changes."""
        # Create dirty state, stash, then pop
        with open(os.path.join(tmp_repo, "file1.txt"), "w") as f:
            f.write("modified for pop")
        client = GitClient(tmp_repo)
        asyncio.run(client.stash("push", message="pop test"))
        result = asyncio.run(client.stash("pop"))
        assert result["action"] == "pop"
        # Working tree should be dirty again
        status = asyncio.run(client.status())
        assert status["clean"] is False

    def test_stash_list(self, tmp_repo):
        """Stash list returns output without error."""
        client = GitClient(tmp_repo)
        result = asyncio.run(client.stash("list"))
        assert result["action"] == "list"

    def test_stash_invalid_action(self):
        """Invalid stash action raises GitOpsError."""
        client = GitClient("/tmp")
        with pytest.raises(GitOpsError, match="Invalid stash action"):
            asyncio.run(client.stash("invalid"))


class TestMerge:
    def test_merge(self, tmp_repo):
        """Merge integrates a branch into current branch."""
        # Create feature branch with a commit
        os.popen(f"cd {tmp_repo} && git checkout -b merge-feature 2>&1").read()
        with open(os.path.join(tmp_repo, "merge_file.txt"), "w") as f:
            f.write("merge content")
        os.popen(f"cd {tmp_repo} && git add merge_file.txt && git commit -m 'merge commit' 2>&1").read()
        os.popen(f"cd {tmp_repo} && git checkout main 2>&1").read()

        client = GitClient(tmp_repo)
        result = asyncio.run(client.merge("merge-feature"))
        assert result["success"] is True
        assert result["merged"] == "merge-feature"
        assert result["into"] == "main"

    def test_merge_no_ff(self, tmp_repo):
        """Merge with no_ff=True passes --no-ff flag."""
        # Create feature branch with a commit
        os.popen(f"cd {tmp_repo} && git checkout -b noff-feature 2>&1").read()
        with open(os.path.join(tmp_repo, "noff_file.txt"), "w") as f:
            f.write("no-ff content")
        os.popen(f"cd {tmp_repo} && git add noff_file.txt && git commit -m 'noff commit' 2>&1").read()
        os.popen(f"cd {tmp_repo} && git checkout main 2>&1").read()

        client = GitClient(tmp_repo)
        result = asyncio.run(client.merge("noff-feature", no_ff=True))
        assert result["success"] is True
        assert result["merged"] == "noff-feature"


class TestAdd:
    def test_add_specific_files(self, tmp_repo):
        """git add -- file1 file2 stages specific files."""
        with open(os.path.join(tmp_repo, "add1.txt"), "w") as f:
            f.write("add1")
        with open(os.path.join(tmp_repo, "add2.txt"), "w") as f:
            f.write("add2")
        client = GitClient(tmp_repo)
        result = asyncio.run(client.add(["add1.txt", "add2.txt"]))
        assert "output" in result
        # Verify files are staged
        status = asyncio.run(client.status())
        staged_files = [f["file"] for f in status["files"]]
        assert "add1.txt" in staged_files
        assert "add2.txt" in staged_files

    def test_add_all(self, tmp_repo):
        """git add -A stages all changes when files=None."""
        with open(os.path.join(tmp_repo, "all1.txt"), "w") as f:
            f.write("all1")
        with open(os.path.join(tmp_repo, "all2.txt"), "w") as f:
            f.write("all2")
        client = GitClient(tmp_repo)
        result = asyncio.run(client.add(None))
        assert "output" in result
        status = asyncio.run(client.status())
        staged_files = [f["file"] for f in status["files"]]
        assert "all1.txt" in staged_files
        assert "all2.txt" in staged_files

    def test_add_invalid_path(self):
        """Paths with '..' raise GitOpsError for safety."""
        client = GitClient("/tmp")
        with pytest.raises(GitOpsError, match="Invalid file path"):
            asyncio.run(client.add(["../etc/passwd"]))


class TestCommit:
    def test_commit(self, tmp_repo):
        """git commit -m creates a commit with the given message."""
        with open(os.path.join(tmp_repo, "commit_file.txt"), "w") as f:
            f.write("commit content")
        client = GitClient(tmp_repo)
        asyncio.run(client.add(["commit_file.txt"]))
        result = asyncio.run(client.commit("test commit message"))
        assert result["success"] is True
        assert result["message"] == "test commit message"
        assert len(result["hash"]) > 0

    def test_commit_empty_message(self):
        """Empty commit message raises GitOpsError."""
        client = GitClient("/tmp")
        with pytest.raises(GitOpsError, match="empty"):
            asyncio.run(client.commit(""))

        with pytest.raises(GitOpsError, match="empty"):
            asyncio.run(client.commit("   "))
