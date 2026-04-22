"""Code Archaeology — trace the origin and intent behind any line of code.

Given a file + line or function, reconstructs the full story:
git blame -> PR -> Jira issue -> change history -> reconstructed intent.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.code_archaeology")


@dataclass
class ArchaeologyReport:
    """Full archaeology report for a code location."""

    file_path: str
    line: int
    function: str
    blame: dict = field(default_factory=dict)
    pr: Optional[dict] = None
    issue: Optional[str] = None
    history: list[dict] = field(default_factory=list)
    intent: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "function": self.function,
            "blame": self.blame,
            "pr": self.pr,
            "issue": self.issue,
            "history": self.history,
            "intent": self.intent,
            "error": self.error,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        parts: list[str] = []
        parts.append(f"Archaeology Report: {self.file_path}")
        if self.line:
            parts.append(f"  Line: {self.line}")
        if self.function:
            parts.append(f"  Function: {self.function}")
        parts.append("")

        if self.blame:
            parts.append("  Blame:")
            parts.append(f"    Commit:  {self.blame.get('commit', 'unknown')[:10]}")
            parts.append(f"    Author:  {self.blame.get('author', 'unknown')}")
            parts.append(f"    Date:    {self.blame.get('date', 'unknown')}")
            parts.append(f"    Message: {self.blame.get('message', '')}")
            parts.append("")

        if self.pr:
            parts.append("  Pull Request:")
            parts.append(f"    #{self.pr.get('number', '?')} — {self.pr.get('title', '')}")
            if self.pr.get("url"):
                parts.append(f"    URL: {self.pr['url']}")
            parts.append("")

        if self.issue:
            parts.append(f"  Issue: {self.issue}")
            parts.append("")

        if self.history:
            parts.append(f"  Change History ({len(self.history)} commits):")
            for entry in self.history[:10]:
                sha = entry.get("commit", "")[:8]
                msg = entry.get("message", "")
                date = entry.get("date", "")
                parts.append(f"    {sha} {date} — {msg}")
            if len(self.history) > 10:
                parts.append(f"    ... and {len(self.history) - 10} more")
            parts.append("")

        if self.intent:
            parts.append("  Reconstructed Intent:")
            for line in self.intent.split("\n"):
                parts.append(f"    {line}")

        if self.error:
            parts.append(f"  Error: {self.error}")

        return "\n".join(parts)


class CodeArchaeologist:
    """Investigate the origin and intent behind code."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("CodeArchaeologist initialized for %s", cwd)

    def investigate(
        self,
        file_path: str,
        line: int = 0,
        function: str = "",
    ) -> ArchaeologyReport:
        """Run a full archaeology investigation on a code location.

        Args:
            file_path: Relative path to the file.
            line: Line number to investigate (0 = skip blame).
            function: Function name to trace history for.

        Returns:
            ArchaeologyReport with blame, PR, issue, history, and intent.
        """
        report = ArchaeologyReport(file_path=file_path, line=line, function=function)

        full_path = os.path.join(self.cwd, file_path)
        if not os.path.isfile(full_path):
            report.error = f"File not found: {file_path}"
            logger.warning("File not found: %s", full_path)
            return report

        # Step 1: git blame
        if line > 0:
            blame = self._git_blame(file_path, line)
            report.blame = blame
            logger.debug("Blame result: %s", blame)

            # Step 2: find associated PR
            if blame.get("commit"):
                pr = self._find_pr(blame["commit"])
                report.pr = pr

            # Step 3: find issue references in commit message
            if blame.get("message"):
                issue = self._find_issue(blame["message"])
                report.issue = issue

        # Step 4: trace function history
        if function:
            history = self._trace_history(file_path, function)
            report.history = history
        elif line > 0 and report.blame.get("commit"):
            # Trace file-level history limited to the area around the line
            history = self._trace_file_history(file_path, max_entries=15)
            report.history = history

        # Step 5: reconstruct intent
        report.intent = self._reconstruct_intent(
            report.blame, report.pr, report.issue, report.history
        )

        logger.info(
            "Archaeology complete for %s (line=%d, fn=%s): %d history entries",
            file_path, line, function, len(report.history),
        )
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _git_blame(self, path: str, line: int) -> dict:
        """Run git blame for a specific line.

        Returns dict with commit, author, date, message.
        """
        try:
            result = subprocess.run(
                ["git", "blame", "-L", f"{line},{line}", "--porcelain", path],
                capture_output=True, text=True, cwd=self.cwd, timeout=15,
            )
            if result.returncode != 0:
                logger.warning("git blame failed: %s", result.stderr.strip())
                return {}

            output = result.stdout
            blame: dict = {}

            # Parse porcelain output
            lines = output.splitlines()
            if lines:
                first_parts = lines[0].split()
                if first_parts:
                    blame["commit"] = first_parts[0]

            for bline in lines:
                if bline.startswith("author "):
                    blame["author"] = bline[len("author "):]
                elif bline.startswith("author-time "):
                    try:
                        ts = int(bline.split()[1])
                        blame["date"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    except (ValueError, IndexError):
                        pass
                elif bline.startswith("summary "):
                    blame["message"] = bline[len("summary "):]

            # Get full commit message if we have a sha
            if blame.get("commit") and not blame["commit"].startswith("0000"):
                try:
                    msg_result = subprocess.run(
                        ["git", "log", "-1", "--format=%B", blame["commit"]],
                        capture_output=True, text=True, cwd=self.cwd, timeout=10,
                    )
                    if msg_result.returncode == 0:
                        blame["full_message"] = msg_result.stdout.strip()
                except (subprocess.TimeoutExpired, OSError):
                    pass

            return blame

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("git blame error: %s", exc)
            return {}

    def _find_pr(self, commit_sha: str) -> dict | None:
        """Find the PR that introduced a commit using gh CLI.

        Falls back to git log --merges if gh is unavailable.
        """
        # Try gh first
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--search", commit_sha, "--state", "merged",
                 "--json", "number,title,url,author", "--limit", "1"],
                capture_output=True, text=True, cwd=self.cwd, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    pr = prs[0]
                    return {
                        "number": pr.get("number"),
                        "title": pr.get("title", ""),
                        "url": pr.get("url", ""),
                        "author": pr.get("author", {}).get("login", ""),
                    }
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            logger.debug("gh pr list failed, trying git log fallback")

        # Fallback: find merge commit that contains this commit
        try:
            result = subprocess.run(
                ["git", "log", "--merges", "--ancestry-path",
                 f"{commit_sha}..HEAD", "--oneline", "-1"],
                capture_output=True, text=True, cwd=self.cwd, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                merge_line = result.stdout.strip()
                # Try to extract PR number from merge commit message
                m = re.search(r"#(\d+)", merge_line)
                if m:
                    return {
                        "number": int(m.group(1)),
                        "title": merge_line.split(None, 1)[-1] if " " in merge_line else "",
                        "url": "",
                        "author": "",
                    }
        except (subprocess.TimeoutExpired, OSError):
            pass

        return None

    def _find_issue(self, commit_msg: str) -> str | None:
        """Extract issue/ticket reference from a commit message.

        Supports: JIRA-123, PROJECT-456, #789, GH-123, fixes #123
        """
        # JIRA-style: ABC-123
        m = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", commit_msg)
        if m:
            return m.group(1)

        # GitHub-style: #123 or fixes #123
        m = re.search(r"(?:fixes|closes|resolves|refs?)?\s*#(\d+)", commit_msg, re.IGNORECASE)
        if m:
            return f"#{m.group(1)}"

        return None

    def _trace_history(self, path: str, function: str) -> list[dict]:
        """Trace the change history of a specific function using git log -L.

        Returns list of {commit, author, date, message} dicts.
        """
        try:
            result = subprocess.run(
                ["git", "log", f"-L::{function}:{path}", "--format=%H|%an|%ai|%s",
                 "--no-patch", "-20"],
                capture_output=True, text=True, cwd=self.cwd, timeout=20,
            )
            if result.returncode != 0:
                logger.debug("git log -L failed for %s:%s, falling back", path, function)
                return self._trace_file_history(path, max_entries=15)

            entries: list[dict] = []
            for line in result.stdout.strip().splitlines():
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    entries.append({
                        "commit": parts[0],
                        "author": parts[1],
                        "date": parts[2][:10],
                        "message": parts[3],
                    })
            return entries

        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("trace_history error: %s", exc)
            return self._trace_file_history(path, max_entries=15)

    def _trace_file_history(self, path: str, max_entries: int = 15) -> list[dict]:
        """Trace file-level change history."""
        try:
            result = subprocess.run(
                ["git", "log", f"-{max_entries}", "--format=%H|%an|%ai|%s", "--", path],
                capture_output=True, text=True, cwd=self.cwd, timeout=15,
            )
            if result.returncode != 0:
                return []

            entries: list[dict] = []
            for line in result.stdout.strip().splitlines():
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    entries.append({
                        "commit": parts[0],
                        "author": parts[1],
                        "date": parts[2][:10],
                        "message": parts[3],
                    })
            return entries

        except (subprocess.TimeoutExpired, OSError):
            return []

    def _reconstruct_intent(
        self,
        blame: dict,
        pr: dict | None,
        issue: str | None,
        history: list[dict],
    ) -> str:
        """Reconstruct the likely intent behind the code.

        Uses blame, PR info, issue references, and change history to build
        a narrative about why the code exists.
        """
        parts: list[str] = []

        if blame.get("message"):
            msg = blame.get("full_message", blame["message"])
            parts.append(f"This code was introduced by {blame.get('author', 'unknown')} "
                         f"on {blame.get('date', 'unknown date')}.")
            parts.append(f"Commit message: \"{msg}\"")

        if pr:
            parts.append(f"It was part of PR #{pr.get('number', '?')}: "
                         f"\"{pr.get('title', '')}\"")
            if pr.get("author"):
                parts.append(f"PR authored by: {pr['author']}")

        if issue:
            parts.append(f"Related issue/ticket: {issue}")

        if history:
            parts.append(f"This area has been modified {len(history)} time(s).")
            if len(history) >= 5:
                parts.append("Frequent changes suggest this is a hotspot — "
                             "consider extra review attention.")
            authors = {e.get("author", "") for e in history if e.get("author")}
            if len(authors) > 1:
                parts.append(f"Contributors: {', '.join(sorted(authors)[:5])}")

        if not parts:
            return "Unable to reconstruct intent — no blame or history available."

        return "\n".join(parts)


def format_report_rich(report: ArchaeologyReport) -> str:
    """Format an archaeology report with terminal colors."""
    lines: list[str] = []
    lines.append(f"\n  \033[1mCode Archaeology: {report.file_path}\033[0m")
    if report.line:
        lines.append(f"  Line {report.line}")
    if report.function:
        lines.append(f"  Function: {report.function}")
    lines.append("")

    if report.error:
        lines.append(f"  \033[31mError: {report.error}\033[0m")
        return "\n".join(lines)

    if report.blame:
        lines.append("  \033[36mBlame\033[0m")
        lines.append(f"    Commit:  {report.blame.get('commit', '?')[:10]}")
        lines.append(f"    Author:  {report.blame.get('author', '?')}")
        lines.append(f"    Date:    {report.blame.get('date', '?')}")
        lines.append(f"    Message: {report.blame.get('message', '')}")
        lines.append("")

    if report.pr:
        lines.append("  \033[36mPull Request\033[0m")
        lines.append(f"    #{report.pr.get('number', '?')} — {report.pr.get('title', '')}")
        if report.pr.get("url"):
            lines.append(f"    {report.pr['url']}")
        lines.append("")

    if report.issue:
        lines.append(f"  \033[36mIssue:\033[0m {report.issue}")
        lines.append("")

    if report.history:
        lines.append(f"  \033[36mChange History\033[0m ({len(report.history)} commits)")
        for entry in report.history[:8]:
            sha = entry.get("commit", "")[:8]
            msg = entry.get("message", "")
            date = entry.get("date", "")
            lines.append(f"    \033[2m{sha}\033[0m {date} — {msg}")
        if len(report.history) > 8:
            lines.append(f"    ... and {len(report.history) - 8} more")
        lines.append("")

    if report.intent:
        lines.append("  \033[36mReconstructed Intent\033[0m")
        for iline in report.intent.split("\n"):
            lines.append(f"    {iline}")

    lines.append("")
    return "\n".join(lines)
