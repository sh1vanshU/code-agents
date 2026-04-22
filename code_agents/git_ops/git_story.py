"""Git Story — reconstruct the full story behind a line of code.

Traces git blame → commit → PR → Jira ticket → reviewer comments
to answer "why was this code written this way?"

Usage:
    from code_agents.git_ops.git_story import GitStoryTeller
    teller = GitStoryTeller("/path/to/repo")
    result = teller.tell_story("code_agents/stream.py", 42)
    print(format_story(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.git_story")


@dataclass
class GitStoryConfig:
    """Configuration for git story telling."""
    cwd: str = "."
    max_history_depth: int = 10
    include_pr: bool = True
    include_jira: bool = True


@dataclass
class StoryChapter:
    """A chapter in the code's story (one commit/event)."""
    timestamp: str
    event_type: str  # "commit", "pr_created", "pr_merged", "pr_review", "jira_link"
    author: str
    title: str
    detail: str = ""
    sha: str = ""
    url: str = ""


@dataclass
class CodeStory:
    """The full story of a piece of code."""
    file: str
    line: int
    current_content: str = ""
    summary: str = ""  # one-line summary of the story

    # Story elements
    original_author: str = ""
    original_date: str = ""
    original_commit: str = ""
    times_modified: int = 0
    chapters: list[StoryChapter] = field(default_factory=list)

    # Linked artifacts
    pr_number: str = ""
    pr_title: str = ""
    pr_url: str = ""
    jira_ticket: str = ""
    jira_url: str = ""

    # Contextual info
    last_modified_by: str = ""
    last_modified_date: str = ""
    contributors: list[str] = field(default_factory=list)


class GitStoryTeller:
    """Reconstruct the story behind code."""

    def __init__(self, config: GitStoryConfig):
        self.config = config

    def tell_story(self, file_path: str, line_number: int) -> CodeStory:
        """Tell the full story of a line of code."""
        logger.info("Telling story for %s:%d", file_path, line_number)

        from code_agents.tools._git_helpers import (
            _run_git, git_log, git_blame_range, find_pr_for_commit,
        )

        story = CodeStory(file=file_path, line=line_number)

        # Get current line content
        self._read_current_content(story)

        # Git blame for the specific line
        blame_lines = git_blame_range(self.config.cwd, file_path, line_number, line_number)
        if blame_lines:
            blame = blame_lines[0]
            story.last_modified_by = blame.author
            story.last_modified_date = blame.date
            story.original_commit = blame.sha

            # Add first chapter
            story.chapters.append(StoryChapter(
                timestamp=blame.date,
                event_type="commit",
                author=blame.author,
                title=f"Last modified in {blame.sha[:8]}",
                sha=blame.sha,
            ))

        # Get full history of this file line
        self._get_line_history(story, file_path, line_number)

        # Find associated PR
        if self.config.include_pr and story.original_commit:
            pr_info = find_pr_for_commit(self.config.cwd, story.original_commit)
            if pr_info:
                story.pr_number = pr_info.number
                story.pr_title = pr_info.title
                story.pr_url = pr_info.url
                story.chapters.append(StoryChapter(
                    timestamp="",
                    event_type="pr_merged",
                    author=pr_info.author,
                    title=f"PR #{pr_info.number}: {pr_info.title}",
                    url=pr_info.url,
                ))

        # Extract Jira ticket from commit messages
        if self.config.include_jira:
            self._extract_jira(story)

        # Build summary
        story.summary = self._build_summary(story)

        return story

    def _read_current_content(self, story: CodeStory):
        """Read the current content of the line."""
        full_path = os.path.join(self.config.cwd, story.file)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if 0 < story.line <= len(lines):
                story.current_content = lines[story.line - 1].rstrip()
        except OSError:
            pass

    def _get_line_history(self, story: CodeStory, file_path: str, line_number: int):
        """Get the modification history of a line."""
        from code_agents.tools._git_helpers import _run_git

        # Use git log -L to get line-level history
        output = _run_git(
            self.config.cwd,
            ["log", f"-L{line_number},{line_number}:{file_path}",
             f"--max-count={self.config.max_history_depth}",
             "--format=%H|%an|%aI|%s"],
            timeout=15,
        )

        if not output:
            return

        contributors = set()
        count = 0
        for line in output.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 4 and len(parts[0]) == 40:
                count += 1
                author = parts[1]
                contributors.add(author)

                if count == 1:
                    continue  # Skip first (already added from blame)

                story.chapters.append(StoryChapter(
                    timestamp=parts[2],
                    event_type="commit",
                    author=author,
                    title=parts[3],
                    sha=parts[0],
                ))

        # First commit = original author
        if story.chapters:
            last_chapter = story.chapters[-1]
            story.original_author = last_chapter.author
            story.original_date = last_chapter.timestamp
            story.original_commit = last_chapter.sha

        story.times_modified = count
        story.contributors = sorted(contributors)

    def _extract_jira(self, story: CodeStory):
        """Extract Jira ticket references from commit messages."""
        jira_pattern = re.compile(r"[A-Z]{2,10}-\d+")
        for chapter in story.chapters:
            match = jira_pattern.search(chapter.title)
            if match:
                story.jira_ticket = match.group(0)
                break

    def _build_summary(self, story: CodeStory) -> str:
        """Build a one-line story summary."""
        parts = []
        if story.original_author:
            parts.append(f"Written by {story.original_author}")
        if story.original_date:
            parts.append(f"on {story.original_date[:10]}")
        if story.times_modified > 1:
            parts.append(f"modified {story.times_modified} times")
        if story.pr_number:
            parts.append(f"via PR #{story.pr_number}")
        if story.jira_ticket:
            parts.append(f"for {story.jira_ticket}")
        return ", ".join(parts) if parts else "No history available"


def format_story(story: CodeStory) -> str:
    """Format code story for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Code Story: {story.file}:{story.line}")
    lines.append(f"{'=' * 60}")

    if story.current_content:
        lines.append(f"\n  Current code: {story.current_content}")

    lines.append(f"\n  Summary: {story.summary}")
    lines.append(f"  Modified {story.times_modified} time(s) by {len(story.contributors)} contributor(s)")

    if story.pr_number:
        lines.append(f"  PR: #{story.pr_number} — {story.pr_title}")
    if story.jira_ticket:
        lines.append(f"  Jira: {story.jira_ticket}")

    if story.chapters:
        lines.append(f"\n  Timeline:")
        for ch in story.chapters:
            icon = {"commit": "o", "pr_merged": "*", "pr_review": "!", "jira_link": "#"}.get(ch.event_type, "-")
            date_str = ch.timestamp[:10] if ch.timestamp else "          "
            lines.append(f"    {icon} {date_str}  {ch.author:20s}  {ch.title[:60]}")

    lines.append("")
    return "\n".join(lines)
