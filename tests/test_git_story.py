"""Tests for the GitStoryTeller module."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.git_ops.git_story import GitStoryTeller, GitStoryConfig, CodeStory, StoryChapter, format_story


class TestGitStoryTeller:
    """Test GitStoryTeller functionality."""

    def test_config_defaults(self):
        config = GitStoryConfig()
        assert config.cwd == "."
        assert config.max_history_depth == 10
        assert config.include_pr is True

    def test_read_current_content(self, tmp_path):
        test_file = tmp_path / "sample.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        config = GitStoryConfig(cwd=str(tmp_path))
        teller = GitStoryTeller(config)
        story = CodeStory(file="sample.py", line=2)
        teller._read_current_content(story)

        assert story.current_content == "line 2"

    def test_read_current_content_missing_file(self, tmp_path):
        config = GitStoryConfig(cwd=str(tmp_path))
        teller = GitStoryTeller(config)
        story = CodeStory(file="nonexistent.py", line=1)
        teller._read_current_content(story)
        assert story.current_content == ""

    def test_extract_jira(self):
        config = GitStoryConfig(cwd="/tmp")
        teller = GitStoryTeller(config)
        story = CodeStory(file="a.py", line=1)
        story.chapters = [
            StoryChapter(timestamp="2024-01-01", event_type="commit",
                         author="dev", title="PAY-1234: fix payment flow"),
        ]
        teller._extract_jira(story)
        assert story.jira_ticket == "PAY-1234"

    def test_extract_jira_no_ticket(self):
        config = GitStoryConfig(cwd="/tmp")
        teller = GitStoryTeller(config)
        story = CodeStory(file="a.py", line=1)
        story.chapters = [
            StoryChapter(timestamp="2024-01-01", event_type="commit",
                         author="dev", title="fix: improve error handling"),
        ]
        teller._extract_jira(story)
        assert story.jira_ticket == ""

    def test_build_summary(self):
        config = GitStoryConfig(cwd="/tmp")
        teller = GitStoryTeller(config)
        story = CodeStory(
            file="a.py", line=1,
            original_author="Alice",
            original_date="2024-01-15T10:00:00",
            times_modified=3,
            pr_number="42",
            jira_ticket="PAY-100",
        )
        summary = teller._build_summary(story)
        assert "Alice" in summary
        assert "2024-01-15" in summary
        assert "3 times" in summary
        assert "#42" in summary
        assert "PAY-100" in summary

    def test_format_story(self):
        story = CodeStory(
            file="stream.py",
            line=42,
            current_content="    return prompt",
            summary="Written by Alice on 2024-01-15",
            times_modified=2,
            contributors=["Alice", "Bob"],
            chapters=[
                StoryChapter(timestamp="2024-01-15", event_type="commit",
                             author="Alice", title="initial implementation"),
            ],
        )
        output = format_story(story)
        assert "stream.py:42" in output
        assert "Alice" in output
        assert "return prompt" in output


class TestGitStoryIntegration:
    """Integration-style tests using mocked git commands."""

    @patch("code_agents.tools._git_helpers.find_pr_for_commit")
    @patch("code_agents.tools._git_helpers.git_blame_range")
    @patch("code_agents.tools._git_helpers._run_git")
    def test_tell_story_full(self, mock_run, mock_blame, mock_pr, tmp_path):
        from code_agents.tools._git_helpers import BlameLine, PRInfo

        test_file = tmp_path / "sample.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        mock_blame.return_value = [
            BlameLine(sha="abc123def456" * 3 + "abcd", author="Alice",
                      date="2024-01-15", line_number=2, content="line 2"),
        ]
        mock_pr.return_value = PRInfo(number="42", title="Fix payment")
        mock_run.return_value = ""

        config = GitStoryConfig(cwd=str(tmp_path))
        story = GitStoryTeller(config).tell_story("sample.py", 2)

        assert story.last_modified_by == "Alice"
        assert story.pr_number == "42"
