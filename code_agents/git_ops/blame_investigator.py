"""Blame Investigator — full story of a line of code."""

import logging
import os
import re
import subprocess
import time as _time_mod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.blame_investigator")


@dataclass
class BlameResult:
    file: str
    line: int

    # Git blame info
    commit_hash: str = ""
    author: str = ""
    author_email: str = ""
    date: str = ""
    commit_message: str = ""

    # Context
    line_content: str = ""
    surrounding_lines: list[str] = field(default_factory=list)  # ±5 lines

    # Extended info
    pr_number: Optional[str] = None
    pr_title: Optional[str] = None
    jira_ticket: Optional[str] = None

    # History
    change_count: int = 0  # how many times this line was modified
    previous_versions: list[dict] = field(default_factory=list)  # commit, author, date, content


class BlameInvestigator:
    """Deep investigation of code blame."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def investigate(self, file_path: str, line_number: int) -> BlameResult:
        """Full investigation of a specific line."""
        result = BlameResult(file=file_path, line=line_number)
        logger.info("Investigating blame for %s:%d", file_path, line_number)

        self._git_blame(result)
        self._get_line_content(result)
        self._extract_pr_info(result)
        self._extract_jira_ticket(result)
        self._get_line_history(result)

        logger.info(
            "Blame complete: commit=%s author=%s jira=%s pr=%s changes=%d",
            result.commit_hash[:8] if result.commit_hash else "?",
            result.author, result.jira_ticket, result.pr_number, result.change_count,
        )
        return result

    def _git_blame(self, result: BlameResult):
        """Run git blame on the specific line."""
        try:
            out = subprocess.run(
                ["git", "blame", "-L", f"{result.line},{result.line}", "--porcelain", result.file],
                capture_output=True, text=True, timeout=10, cwd=self.cwd,
            )
            if out.returncode != 0:
                logger.warning("git blame returned %d: %s", out.returncode, out.stderr.strip())
                return

            for line in out.stdout.split("\n"):
                if line.startswith("author "):
                    result.author = line[7:]
                elif line.startswith("author-mail "):
                    result.author_email = line[12:].strip("<>")
                elif line.startswith("author-time "):
                    ts = int(line[12:])
                    result.date = _time_mod.strftime("%Y-%m-%d %H:%M", _time_mod.localtime(ts))
                elif line.startswith("summary "):
                    result.commit_message = line[8:]

            # Get commit hash from first line
            first_line = out.stdout.split("\n")[0]
            result.commit_hash = first_line.split()[0] if first_line else ""

        except Exception as e:
            logger.warning("git blame failed: %s", e)

    def _get_line_content(self, result: BlameResult):
        """Get the line content and surrounding context."""
        full_path = os.path.join(self.cwd, result.file)
        if not os.path.exists(full_path):
            logger.debug("File not found: %s", full_path)
            return
        try:
            with open(full_path) as f:
                lines = f.readlines()
            if 1 <= result.line <= len(lines):
                result.line_content = lines[result.line - 1].rstrip()

            # Surrounding ±5 lines
            start = max(0, result.line - 6)
            end = min(len(lines), result.line + 5)
            for i in range(start, end):
                marker = ">>>" if i == result.line - 1 else "   "
                result.surrounding_lines.append(f"{marker} {i + 1:4d} | {lines[i].rstrip()}")
        except Exception as e:
            logger.debug("Could not read file: %s", e)

    def _extract_pr_info(self, result: BlameResult):
        """Try to find the PR that introduced this commit."""
        if not result.commit_hash:
            return

        # Strategy 1: Search commit message for PR reference
        pr_match = re.search(r'(?:pr|pull request|merge)\s*#?(\d+)', result.commit_message, re.IGNORECASE)
        if pr_match:
            result.pr_number = pr_match.group(1)

        # Strategy 2: Look for merge commit that contains this commit
        try:
            out = subprocess.run(
                ["git", "log", "--merges", "--oneline", "--ancestry-path", f"{result.commit_hash}..HEAD"],
                capture_output=True, text=True, timeout=10, cwd=self.cwd,
            )
            if out.returncode == 0 and out.stdout.strip():
                first_merge = out.stdout.strip().split("\n")[0]
                match = re.search(r'(?:pull request|pr|merge)\s*#?(\d+)', first_merge, re.IGNORECASE)
                if match:
                    result.pr_number = match.group(1)
                    result.pr_title = first_merge.split(" ", 1)[1] if " " in first_merge else ""
        except Exception as e:
            logger.debug("PR extraction failed: %s", e)

    def _extract_jira_ticket(self, result: BlameResult):
        """Extract Jira ticket from commit message or branch."""
        # Search in commit message
        match = re.search(r'([A-Z]{2,10}-\d+)', result.commit_message)
        if match:
            result.jira_ticket = match.group(1)
            return

        # Try to find from the branch the commit was on
        if result.commit_hash:
            try:
                out = subprocess.run(
                    ["git", "branch", "--contains", result.commit_hash, "--format=%(refname:short)"],
                    capture_output=True, text=True, timeout=10, cwd=self.cwd,
                )
                if out.returncode == 0:
                    for branch in out.stdout.strip().split("\n"):
                        match = re.search(r'([A-Z]{2,10}-\d+)', branch)
                        if match:
                            result.jira_ticket = match.group(1)
                            return
            except Exception as e:
                logger.debug("Jira ticket extraction from branch failed: %s", e)

    def _get_line_history(self, result: BlameResult):
        """Get the modification history of this line."""
        try:
            out = subprocess.run(
                ["git", "log", "--follow", "-p", f"-L{result.line},{result.line}:{result.file}"],
                capture_output=True, text=True, timeout=15, cwd=self.cwd,
            )
            if out.returncode != 0:
                return

            # Parse log output for commits that touched this line
            commits = []
            current_commit = {}
            for line in out.stdout.split("\n"):
                if line.startswith("commit "):
                    if current_commit:
                        commits.append(current_commit)
                    current_commit = {"commit": line[7:12]}  # short hash
                elif line.startswith("Author: "):
                    current_commit["author"] = line[8:].split(" <")[0]
                elif line.startswith("Date: "):
                    current_commit["date"] = line[6:].strip()[:10]
                elif line.startswith("+") and not line.startswith("+++"):
                    current_commit.setdefault("content", line[1:].strip())

            if current_commit:
                commits.append(current_commit)

            result.change_count = len(commits)
            result.previous_versions = commits[:10]

        except Exception as e:
            logger.debug("Line history failed: %s", e)


def format_blame(result: BlameResult) -> str:
    """Format blame result for terminal display."""
    lines = []
    header = f"BLAME: {result.file}:{result.line}"
    lines.append(f"  \u2554\u2550\u2550 {header} \u2550\u2550\u2557")
    lines.append(f"  \u2551 Author: {result.author} <{result.author_email}>")
    lines.append(f"  \u2551 Date: {result.date}")
    lines.append(f"  \u2551 Commit: {result.commit_hash[:8]}")
    if result.jira_ticket:
        lines.append(f"  \u2551 Jira: {result.jira_ticket}")
    if result.pr_number:
        pr_info = f"PR #{result.pr_number}"
        if result.pr_title:
            pr_info += f" \u2014 {result.pr_title}"
        lines.append(f"  \u2551 {pr_info}")
    lines.append(f"  \u255a{'=' * (len(header) + 4)}\u255d")

    # Commit message
    lines.append(f"\n  Commit Message:")
    lines.append(f"    {result.commit_message}")

    # Code context
    if result.surrounding_lines:
        lines.append(f"\n  Code Context:")
        for sl in result.surrounding_lines:
            lines.append(f"    {sl}")

    # History
    if result.previous_versions:
        lines.append(f"\n  Line History ({result.change_count} changes):")
        for ver in result.previous_versions[:5]:
            lines.append(f"    {ver.get('commit', '?')} by {ver.get('author', '?')} ({ver.get('date', '?')})")
            if ver.get('content'):
                lines.append(f"      {ver['content'][:100]}")

    return "\n".join(lines)
