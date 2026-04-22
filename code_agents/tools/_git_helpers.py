"""Git helpers — shared utilities for git operations.

Used by: git_story, conflict_resolver, commit_splitter, branch_cleanup,
         cherry_pick_advisor, pr_writer, incident_timeline, etc.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.tools._git_helpers")


@dataclass
class CommitInfo:
    """Structured git commit."""
    sha: str
    author: str
    author_email: str = ""
    date: str = ""
    message: str = ""
    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class BlameLine:
    """A single line from git blame."""
    sha: str
    author: str
    date: str
    line_number: int
    content: str = ""
    original_line: int = 0


@dataclass
class DiffFile:
    """A changed file in a diff."""
    path: str
    status: str = ""  # A, M, D, R
    insertions: int = 0
    deletions: int = 0
    old_path: str = ""  # for renames


@dataclass
class BranchInfo:
    """Git branch metadata."""
    name: str
    is_current: bool = False
    upstream: str = ""
    last_commit_date: str = ""
    last_commit_sha: str = ""
    is_merged: bool = False
    ahead: int = 0
    behind: int = 0


@dataclass
class PRInfo:
    """Pull request info extracted from git/GitHub."""
    number: str = ""
    title: str = ""
    url: str = ""
    author: str = ""
    state: str = ""  # open, closed, merged


def _run_git(cwd: str, args: list[str], timeout: int = 30) -> str:
    """Run a git command and return stdout."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("git command failed: %s — %s", " ".join(cmd), exc)
        return ""


def git_log(
    cwd: str,
    max_count: int = 50,
    since: str = "",
    author: str = "",
    path: str = "",
) -> list[CommitInfo]:
    """Get structured git log."""
    args = ["log", f"--max-count={max_count}", "--format=%H|%an|%ae|%aI|%s"]
    if since:
        args.append(f"--since={since}")
    if author:
        args.append(f"--author={author}")
    if path:
        args.extend(["--", path])

    output = _run_git(cwd, args)
    if not output:
        return []

    commits: list[CommitInfo] = []
    for line in output.splitlines():
        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append(CommitInfo(
                sha=parts[0],
                author=parts[1],
                author_email=parts[2],
                date=parts[3],
                message=parts[4],
            ))
    return commits


def git_blame_range(
    cwd: str, file_path: str, start_line: int, end_line: int
) -> list[BlameLine]:
    """Get structured git blame for a line range."""
    args = ["blame", f"-L{start_line},{end_line}", "--porcelain", file_path]
    output = _run_git(cwd, args)
    if not output:
        return []

    results: list[BlameLine] = []
    lines = output.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Header line: SHA orig_line final_line [num_lines]
        match = re.match(r"^([0-9a-f]{40})\s+(\d+)\s+(\d+)", line)
        if match:
            sha = match.group(1)
            orig_line = int(match.group(2))
            final_line = int(match.group(3))
            author = ""
            date = ""
            content = ""

            # Read metadata lines until we hit the content line
            i += 1
            while i < len(lines) and not lines[i].startswith("\t"):
                if lines[i].startswith("author "):
                    author = lines[i][7:]
                elif lines[i].startswith("author-time "):
                    date = lines[i][12:]
                i += 1

            # Content line starts with tab
            if i < len(lines) and lines[i].startswith("\t"):
                content = lines[i][1:]

            results.append(BlameLine(
                sha=sha,
                author=author,
                date=date,
                line_number=final_line,
                content=content,
                original_line=orig_line,
            ))
        i += 1
    return results


def git_diff_files(cwd: str, base: str = "HEAD~1", head: str = "HEAD") -> list[DiffFile]:
    """Get list of changed files between two refs."""
    args = ["diff", "--numstat", "--diff-filter=AMDRC", base, head]
    output = _run_git(cwd, args)
    if not output:
        return []

    results: list[DiffFile] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            ins = int(parts[0]) if parts[0] != "-" else 0
            dels = int(parts[1]) if parts[1] != "-" else 0
            path = parts[2]
            results.append(DiffFile(
                path=path,
                insertions=ins,
                deletions=dels,
            ))
    return results


def git_branches(cwd: str, include_remote: bool = False) -> list[BranchInfo]:
    """List branches with metadata."""
    args = ["branch", "--format=%(refname:short)|%(HEAD)|%(upstream:short)|%(creatordate:iso8601)|%(objectname:short)"]
    if include_remote:
        args.append("-a")
    output = _run_git(cwd, args)
    if not output:
        return []

    branches: list[BranchInfo] = []
    for line in output.splitlines():
        parts = line.split("|")
        if len(parts) >= 5:
            branches.append(BranchInfo(
                name=parts[0],
                is_current=parts[1] == "*",
                upstream=parts[2],
                last_commit_date=parts[3],
                last_commit_sha=parts[4],
            ))
    return branches


def find_pr_for_commit(cwd: str, sha: str) -> Optional[PRInfo]:
    """Find PR associated with a commit via gh CLI or merge commit pattern."""
    # Try gh CLI first
    output = _run_git(cwd, ["log", "--oneline", "-1", sha])
    if not output:
        return None

    # Check for merge commit pattern: "Merge pull request #123"
    pr_match = re.search(r"#(\d+)", output)
    if pr_match:
        pr_num = pr_match.group(1)
        return PRInfo(number=pr_num, title=output)

    # Try gh CLI
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--search", sha, "--json", "number,title,url,author,state", "--limit", "1"],
            cwd=cwd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            data = json.loads(result.stdout)
            if data:
                pr = data[0]
                return PRInfo(
                    number=str(pr.get("number", "")),
                    title=pr.get("title", ""),
                    url=pr.get("url", ""),
                    author=pr.get("author", {}).get("login", ""),
                    state=pr.get("state", ""),
                )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def get_file_history(cwd: str, file_path: str, max_count: int = 20) -> list[CommitInfo]:
    """Get commit history for a specific file."""
    return git_log(cwd, max_count=max_count, path=file_path)


def get_current_branch(cwd: str) -> str:
    """Get current branch name."""
    return _run_git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])


def get_merge_base(cwd: str, branch1: str, branch2: str) -> str:
    """Find common ancestor of two branches."""
    return _run_git(cwd, ["merge-base", branch1, branch2])
