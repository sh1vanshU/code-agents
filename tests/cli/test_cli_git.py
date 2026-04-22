"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdDiff:
    """Test diff command."""

    def test_diff_with_api(self, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_data = {
            "files_changed": 3,
            "insertions": 50,
            "deletions": 10,
            "changed_files": [
                {"file": "foo.py", "insertions": 30, "deletions": 5},
                {"file": "bar.py", "insertions": 20, "deletions": 5},
            ]
        }
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_git._api_get", return_value=mock_data):
            cmd_diff(["main", "HEAD"])
        output = capsys.readouterr().out
        assert "main" in output
        assert "HEAD" in output
        assert "foo.py" in output

    def test_diff_fallback_git(self, capsys):
        from code_agents.cli.cli_git import cmd_diff
        mock_data = {
            "files_changed": 1,
            "insertions": 5,
            "deletions": 2,
            "changed_files": []
        }
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_git._api_get", return_value=None), \
             patch("asyncio.run", return_value=mock_data):
            cmd_diff([])
        output = capsys.readouterr().out
        assert "main" in output  # default base
class TestCmdBranches:
    """Test branches command."""

    def test_branches_with_api(self, capsys):
        from code_agents.cli.cli_git import cmd_branches
        mock_branches = {
            "branches": [
                {"name": "main"},
                {"name": "feature/new"},
            ]
        }
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_git._api_get") as mock_get:
            mock_get.side_effect = [mock_branches, {"branch": "main"}]
            cmd_branches()
        output = capsys.readouterr().out
        assert "main" in output
        assert "feature/new" in output
class TestCmdReview:
    """Test review command."""

    def test_review_with_api(self, capsys):
        from code_agents.cli.cli_git import cmd_review
        mock_diff = {"files_changed": 2, "insertions": 10, "deletions": 5, "diff": "some diff"}
        mock_review = {"choices": [{"message": {"content": "LGTM with minor suggestions"}}]}
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_git._api_get", return_value=mock_diff), \
             patch("code_agents.cli.cli_git._api_post", return_value=mock_review):
            cmd_review(["main", "HEAD"])
        output = capsys.readouterr().out
        assert "Reviewing changes" in output
        assert "LGTM" in output

    def test_review_no_server(self, capsys):
        from code_agents.cli.cli_git import cmd_review
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.cli.cli_git._api_get", return_value=None), \
             patch("code_agents.cli.cli_git._api_post", return_value=None):
            cmd_review([])
        output = capsys.readouterr().out
        assert "Could not reach" in output
class TestCmdPrPreview:
    """Test pr-preview command."""

    def test_pr_preview_no_commits(self, capsys):
        from code_agents.cli.cli_git import cmd_pr_preview
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.tools.pr_preview.PRPreview") as MockPreview:
            MockPreview.return_value.get_commits.return_value = []
            cmd_pr_preview([])
        output = capsys.readouterr().out
        assert "No commits found" in output

    def test_pr_preview_with_commits(self, capsys):
        from code_agents.cli.cli_git import cmd_pr_preview
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.tools.pr_preview.PRPreview") as MockPreview:
            MockPreview.return_value.get_commits.return_value = ["abc123 feat: new thing"]
            MockPreview.return_value.format_preview.return_value = "PR Preview Output"
            cmd_pr_preview(["develop"])
        output = capsys.readouterr().out
        assert "PR Preview Output" in output
class TestCmdAutoReview:
    """Test auto-review command."""

    def test_auto_review_default(self, capsys):
        from code_agents.cli.cli_git import cmd_auto_review
        mock_report = MagicMock()
        with patch("code_agents.reviews.review_autopilot.ReviewAutopilot") as MockRA, \
             patch("code_agents.reviews.review_autopilot.format_review", return_value="Review Output"), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}):
            MockRA.return_value.run.return_value = mock_report
            cmd_auto_review([])
        output = capsys.readouterr().out
        assert "Code Review Autopilot" in output
        assert "Review Output" in output

    def test_auto_review_custom_branches(self, capsys):
        from code_agents.cli.cli_git import cmd_auto_review
        mock_report = MagicMock()
        with patch("code_agents.reviews.review_autopilot.ReviewAutopilot") as MockRA, \
             patch("code_agents.reviews.review_autopilot.format_review", return_value="Review"), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}):
            MockRA.return_value.run.return_value = mock_report
            cmd_auto_review(["develop", "feature-branch"])
        output = capsys.readouterr().out
        assert "develop" in output
        assert "feature-branch" in output
class TestCmdCommitPaths:
    """Test commit command interactive paths."""

    def test_commit_error(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC:
            MockSC.return_value.generate_message.return_value = {"error": "No staged changes"}
            cmd_commit()
        output = capsys.readouterr().out
        assert "No staged changes" in output

    def test_commit_dry_run(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit", "--dry-run"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC:
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "cli", "files": ["a.py"],
                "full_message": "feat(cli): add feature", "ticket": None,
            }
            cmd_commit()
        output = capsys.readouterr().out
        assert "dry run" in output.lower()

    def test_commit_auto(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit", "--auto"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC:
            MockSC.return_value.generate_message.return_value = {
                "type": "fix", "scope": "", "files": ["b.py"],
                "full_message": "fix: bug fix", "ticket": "PROJ-123",
            }
            MockSC.return_value.commit.return_value = True
            cmd_commit()
        output = capsys.readouterr().out
        assert "Committed" in output

    def test_commit_auto_fails(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit", "--auto"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC:
            MockSC.return_value.generate_message.return_value = {
                "type": "fix", "scope": "", "files": ["b.py"],
                "full_message": "fix: bug", "ticket": None,
            }
            MockSC.return_value.commit.return_value = False
            cmd_commit()
        output = capsys.readouterr().out
        assert "failed" in output.lower()

    def test_commit_interactive_confirm(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC, \
             patch("builtins.input", return_value="y"):
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "", "files": ["c.py"],
                "full_message": "feat: new", "ticket": None,
            }
            MockSC.return_value.commit.return_value = True
            cmd_commit()
        output = capsys.readouterr().out
        assert "Committed" in output

    def test_commit_interactive_cancel(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC, \
             patch("builtins.input", return_value="n"):
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "", "files": ["c.py"],
                "full_message": "feat: new", "ticket": None,
            }
            cmd_commit()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_commit_interactive_edit(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        input_values = iter(["e", "custom commit msg", ""])
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC, \
             patch("builtins.input", side_effect=input_values):
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "", "files": ["c.py"],
                "full_message": "feat: new", "ticket": None,
            }
            MockSC.return_value.commit.return_value = True
            cmd_commit()
        output = capsys.readouterr().out
        assert "custom message" in output.lower()

    def test_commit_interactive_edit_empty(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        input_values = iter(["e", ""])
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC, \
             patch("builtins.input", side_effect=input_values):
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "", "files": ["c.py"],
                "full_message": "feat: new", "ticket": None,
            }
            cmd_commit()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_commit_keyboard_interrupt(self, capsys):
        from code_agents.cli.cli_git import cmd_commit
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("sys.argv", ["code-agents", "commit"]), \
             patch("code_agents.tools.smart_commit.SmartCommit") as MockSC, \
             patch("builtins.input", side_effect=KeyboardInterrupt):
            MockSC.return_value.generate_message.return_value = {
                "type": "feat", "scope": "", "files": ["c.py"],
                "full_message": "feat: new", "ticket": None,
            }
            cmd_commit()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_diff_fallback_error(self, capsys):
        from code_agents.cli.cli_git import cmd_diff
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_git._api_get", return_value=None), \
             patch("asyncio.run", side_effect=Exception("git error")):
            cmd_diff([])
        output = capsys.readouterr().out
        assert "Error" in output

    def test_branches_fallback(self, capsys):
        from code_agents.cli.cli_git import cmd_branches
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_git._api_get", return_value=None), \
             patch("asyncio.run") as mock_async:
            mock_async.side_effect = [
                [{"name": "main"}, {"name": "dev"}],
                "main",
            ]
            cmd_branches()
        output = capsys.readouterr().out
        assert "main" in output

    def test_branches_fallback_error(self, capsys):
        from code_agents.cli.cli_git import cmd_branches
        with patch("code_agents.cli.cli_git._load_env"), \
             patch("code_agents.cli.cli_git._user_cwd", return_value="/tmp"), \
             patch("code_agents.cli.cli_git._api_get", return_value=None), \
             patch("asyncio.run", side_effect=Exception("git error")):
            cmd_branches()
        output = capsys.readouterr().out
        assert "Error" in output
