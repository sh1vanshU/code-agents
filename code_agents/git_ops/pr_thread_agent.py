"""PR Thread Agent — respond to PR review comments autonomously.

Fetches review comments from a pull request, classifies them as actionable,
applies fixes where possible, and replies in-thread. All git/GitHub operations
use subprocess with list args (no shell=True).

Usage:
    from code_agents.git_ops.pr_thread_agent import PRThreadAgent
    agent = PRThreadAgent(cwd="/path/to/repo")
    responses = agent.respond_to_reviews(pr_number=42, auto_fix=True)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.pr_thread_agent")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReviewComment:
    """A single review comment from a PR."""

    id: int
    body: str
    path: str
    line: int
    author: str
    created_at: str


@dataclass
class ThreadResponse:
    """Result of responding to a single review comment."""

    comment_id: int
    fix_applied: bool
    reply: str
    diff: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Actionable keyword patterns
# ---------------------------------------------------------------------------

_ACTIONABLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(fix|change|rename|replace|remove|delete|add|update|use|convert)\b", re.I),
    re.compile(r"\b(should|must|please|consider)\b.*\b(be|use|add|remove|change|rename)\b", re.I),
    re.compile(r"\b(error handling|type hint|docstring|logging|validation)\b", re.I),
    re.compile(r"\b(wrap|extract|inline|move|split)\b", re.I),
    re.compile(r"\b(missing|unused|redundant|unnecessary|deprecated)\b", re.I),
]

_NON_ACTIONABLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(lgtm|looks good|approved|\+1|nice|great|thanks|nit:?\s*$)", re.I),
    re.compile(r"^\?+$"),  # just question marks
    re.compile(r"^(why|what|how|when|where|is this|does this|can you explain)\b", re.I),
]


# ---------------------------------------------------------------------------
# Fix patterns — common review feedback categories
# ---------------------------------------------------------------------------

_FIX_RENAME = re.compile(
    r"(?:rename|change)\s+[`'\"]?(\w+)[`'\"]?\s+to\s+[`'\"]?(\w+)[`'\"]?", re.I
)
_FIX_REMOVE = re.compile(
    r"(?:remove|delete)\s+(?:this|these|the)?\s*(?:line|lines|block|code)?", re.I
)
_FIX_ADD_ERROR_HANDLING = re.compile(
    r"(?:add|wrap|include)\s+(?:error|exception)\s+handling", re.I
)
_FIX_ADD_TYPE_HINT = re.compile(
    r"(?:add|include|missing)\s+type\s+hint", re.I
)
_FIX_ADD_DOCSTRING = re.compile(
    r"(?:add|include|missing)\s+docstring", re.I
)
_FIX_ADD_LOGGING = re.compile(
    r"(?:add|include)\s+(?:a\s+)?log(?:ging)?", re.I
)


# ---------------------------------------------------------------------------
# PRThreadAgent
# ---------------------------------------------------------------------------


class PRThreadAgent:
    """Responds to PR review comments — understands feedback, applies fixes, replies."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._owner: Optional[str] = None
        self._repo: Optional[str] = None
        self._changed_files: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def respond_to_reviews(
        self,
        pr_number: int,
        auto_fix: bool = True,
        dry_run: bool = False,
    ) -> list[ThreadResponse]:
        """Respond to all actionable review comments on a PR.

        Args:
            pr_number: The PR number to process.
            auto_fix: If True, attempt to apply code fixes. If False, only reply.
            dry_run: If True, do not commit, push, or reply — just preview.

        Returns:
            List of ThreadResponse objects, one per actionable comment.
        """
        logger.info("Processing review comments for PR #%d (auto_fix=%s, dry_run=%s)",
                     pr_number, auto_fix, dry_run)

        self._resolve_repo_info()
        comments = self._fetch_review_comments(pr_number)
        logger.info("Fetched %d review comments", len(comments))

        responses: list[ThreadResponse] = []

        for comment in comments:
            if not self._is_actionable(comment):
                logger.debug("Skipping non-actionable comment #%d by %s",
                             comment.id, comment.author)
                continue

            logger.info("Processing actionable comment #%d: %.80s",
                        comment.id, comment.body)

            intent = self._understand_feedback(comment)
            diff = ""
            fix_applied = False
            error = ""

            if auto_fix:
                try:
                    diff = self._apply_fix(comment)
                    if diff:
                        fix_applied = True
                        logger.info("Fix applied for comment #%d", comment.id)
                    else:
                        logger.info("No automatic fix available for comment #%d", comment.id)
                except Exception as exc:
                    error = str(exc)
                    logger.warning("Failed to apply fix for comment #%d: %s",
                                   comment.id, error)

            reply = self._build_reply(comment, intent, fix_applied, diff, error)

            if not dry_run:
                self._reply_in_thread(comment.id, reply, pr_number)

            responses.append(ThreadResponse(
                comment_id=comment.id,
                fix_applied=fix_applied,
                reply=reply,
                diff=diff,
                error=error,
            ))

        # Push all fixes in one commit if anything changed
        if auto_fix and self._changed_files and not dry_run:
            push_result = self._push_fixes(pr_number)
            logger.info("Push result: %s", push_result)

        return responses

    # ------------------------------------------------------------------
    # Repo info
    # ------------------------------------------------------------------

    def _resolve_repo_info(self) -> None:
        """Resolve owner/repo from git remote."""
        if self._owner and self._repo:
            return

        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=self.cwd,
            )
            url = result.stdout.strip()
            # Handle SSH: git@github.com:owner/repo.git
            # Handle HTTPS: https://github.com/owner/repo.git
            match = re.search(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
            if match:
                self._owner = match.group(1)
                self._repo = match.group(2)
                logger.debug("Resolved repo: %s/%s", self._owner, self._repo)
            else:
                raise ValueError(f"Cannot parse remote URL: {url}")
        except Exception as exc:
            logger.error("Failed to resolve repo info: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Fetch review comments
    # ------------------------------------------------------------------

    def _fetch_review_comments(self, pr: int) -> list[ReviewComment]:
        """Fetch review comments via gh api."""
        endpoint = f"repos/{self._owner}/{self._repo}/pulls/{pr}/comments"

        result = subprocess.run(
            ["gh", "api", endpoint, "--paginate"],
            capture_output=True, text=True, cwd=self.cwd,
        )

        if result.returncode != 0:
            logger.error("gh api failed: %s", result.stderr)
            raise RuntimeError(f"Failed to fetch review comments: {result.stderr}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error("Invalid JSON from gh api: %.200s", result.stdout)
            raise RuntimeError("Invalid JSON response from gh api")

        comments: list[ReviewComment] = []
        for item in data:
            comments.append(ReviewComment(
                id=item.get("id", 0),
                body=item.get("body", ""),
                path=item.get("path", ""),
                line=item.get("line") or item.get("original_line") or 0,
                author=item.get("user", {}).get("login", "unknown"),
                created_at=item.get("created_at", ""),
            ))

        return comments

    # ------------------------------------------------------------------
    # Classify comments
    # ------------------------------------------------------------------

    def _is_actionable(self, comment: ReviewComment) -> bool:
        """Determine if a review comment is actionable (requests a code change).

        Returns False for approvals, questions, and non-code comments.
        """
        body = comment.body.strip()

        if not body:
            return False

        # Non-actionable first (short-circuit)
        for pattern in _NON_ACTIONABLE_PATTERNS:
            if pattern.search(body):
                return False

        # Must reference a file to be actionable
        if not comment.path:
            return False

        # Check actionable patterns
        for pattern in _ACTIONABLE_PATTERNS:
            if pattern.search(body):
                return True

        return False

    # ------------------------------------------------------------------
    # Understand feedback
    # ------------------------------------------------------------------

    def _understand_feedback(self, comment: ReviewComment) -> str:
        """Extract intent from a review comment — what needs to change."""
        body = comment.body.strip()

        parts = [f"File: {comment.path}, Line: {comment.line}"]

        # Detect rename
        m = _FIX_RENAME.search(body)
        if m:
            parts.append(f"Rename '{m.group(1)}' to '{m.group(2)}'")
            return "; ".join(parts)

        # Detect remove
        if _FIX_REMOVE.search(body):
            parts.append("Remove the indicated code")
            return "; ".join(parts)

        # Detect add error handling
        if _FIX_ADD_ERROR_HANDLING.search(body):
            parts.append("Add error/exception handling")
            return "; ".join(parts)

        # Detect add type hint
        if _FIX_ADD_TYPE_HINT.search(body):
            parts.append("Add type hints")
            return "; ".join(parts)

        # Detect add docstring
        if _FIX_ADD_DOCSTRING.search(body):
            parts.append("Add docstring")
            return "; ".join(parts)

        # Detect add logging
        if _FIX_ADD_LOGGING.search(body):
            parts.append("Add logging")
            return "; ".join(parts)

        # Fallback: use the raw comment
        parts.append(f"Feedback: {body[:200]}")
        return "; ".join(parts)

    # ------------------------------------------------------------------
    # Apply fixes
    # ------------------------------------------------------------------

    def _apply_fix(self, comment: ReviewComment) -> str:
        """Attempt to apply a code fix based on the review comment.

        Returns the diff of changes, or empty string if no fix could be applied.
        """
        file_path = Path(self.cwd) / comment.path
        if not file_path.exists():
            logger.warning("File not found: %s", file_path)
            return ""

        try:
            original = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read file %s: %s", file_path, exc)
            return ""

        lines = original.splitlines(keepends=True)
        body = comment.body.strip()
        modified = False

        # --- Rename ---
        m = _FIX_RENAME.search(body)
        if m:
            old_name, new_name = m.group(1), m.group(2)
            new_content = original.replace(old_name, new_name)
            if new_content != original:
                file_path.write_text(new_content, encoding="utf-8")
                modified = True
                logger.info("Renamed '%s' -> '%s' in %s", old_name, new_name, comment.path)

        # --- Remove lines ---
        if not modified and _FIX_REMOVE.search(body):
            line_idx = comment.line - 1
            if 0 <= line_idx < len(lines):
                removed_line = lines.pop(line_idx)
                new_content = "".join(lines)
                file_path.write_text(new_content, encoding="utf-8")
                modified = True
                logger.info("Removed line %d from %s: %.60s",
                            comment.line, comment.path, removed_line.strip())

        # --- Add error handling (wrap line in try/except) ---
        if not modified and _FIX_ADD_ERROR_HANDLING.search(body):
            line_idx = comment.line - 1
            if 0 <= line_idx < len(lines):
                target_line = lines[line_idx]
                indent = re.match(r"^(\s*)", target_line).group(1)
                inner_indent = indent + "    "
                wrapped = (
                    f"{indent}try:\n"
                    f"{inner_indent}{target_line.lstrip()}"
                    f"{indent}except Exception as exc:\n"
                    f"{inner_indent}logger.error(\"Operation failed: %s\", exc)\n"
                    f"{inner_indent}raise\n"
                )
                lines[line_idx] = wrapped
                new_content = "".join(lines)
                file_path.write_text(new_content, encoding="utf-8")
                modified = True
                logger.info("Added error handling at line %d in %s",
                            comment.line, comment.path)

        # --- Add type hint stub ---
        if not modified and _FIX_ADD_TYPE_HINT.search(body):
            line_idx = comment.line - 1
            if 0 <= line_idx < len(lines):
                target_line = lines[line_idx]
                # Add -> None if it's a def without return annotation
                if re.match(r"\s*def\s+\w+\([^)]*\)\s*:", target_line):
                    new_line = re.sub(
                        r"(\)\s*):",
                        r"\1-> None:",
                        target_line,
                    )
                    if new_line != target_line:
                        lines[line_idx] = new_line
                        new_content = "".join(lines)
                        file_path.write_text(new_content, encoding="utf-8")
                        modified = True
                        logger.info("Added type hint at line %d in %s",
                                    comment.line, comment.path)

        # --- Add docstring ---
        if not modified and _FIX_ADD_DOCSTRING.search(body):
            line_idx = comment.line - 1
            if 0 <= line_idx < len(lines):
                target_line = lines[line_idx]
                if re.match(r"\s*(def|class)\s+", target_line):
                    indent = re.match(r"^(\s*)", target_line).group(1)
                    inner = indent + "    "
                    docstring = f'{inner}"""TODO: Add docstring."""\n'
                    lines.insert(line_idx + 1, docstring)
                    new_content = "".join(lines)
                    file_path.write_text(new_content, encoding="utf-8")
                    modified = True
                    logger.info("Added docstring stub at line %d in %s",
                                comment.line, comment.path)

        # --- Add logging ---
        if not modified and _FIX_ADD_LOGGING.search(body):
            line_idx = comment.line - 1
            if 0 <= line_idx < len(lines):
                target_line = lines[line_idx]
                indent = re.match(r"^(\s*)", target_line).group(1)
                log_line = f'{indent}logger.info("Executing: %s", {target_line.strip()!r})\n'
                lines.insert(line_idx, log_line)
                new_content = "".join(lines)
                file_path.write_text(new_content, encoding="utf-8")
                modified = True
                logger.info("Added logging at line %d in %s",
                            comment.line, comment.path)

        if not modified:
            return ""

        # Track changed file and compute diff
        self._changed_files.append(comment.path)
        diff = self._get_file_diff(comment.path)
        return diff

    # ------------------------------------------------------------------
    # Reply in thread
    # ------------------------------------------------------------------

    def _reply_in_thread(self, comment_id: int, message: str, pr: int) -> bool:
        """Reply to a review comment thread via gh api."""
        endpoint = f"repos/{self._owner}/{self._repo}/pulls/{pr}/comments/{comment_id}/replies"

        result = subprocess.run(
            ["gh", "api", endpoint, "-f", f"body={message}"],
            capture_output=True, text=True, cwd=self.cwd,
        )

        if result.returncode != 0:
            logger.error("Failed to reply to comment #%d: %s", comment_id, result.stderr)
            return False

        logger.info("Replied to comment #%d", comment_id)
        return True

    # ------------------------------------------------------------------
    # Push fixes
    # ------------------------------------------------------------------

    def _push_fixes(self, pr: int) -> str:
        """Stage changed files, commit, and push.

        Never force-pushes. Returns push output or error message.
        """
        if not self._changed_files:
            return "No files to push"

        # Stage only the files we changed
        unique_files = list(set(self._changed_files))
        subprocess.run(
            ["git", "add"] + unique_files,
            capture_output=True, text=True, cwd=self.cwd,
        )

        # Commit
        commit_msg = f"fix: address PR #{pr} review feedback"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True, text=True, cwd=self.cwd,
        )
        if result.returncode != 0:
            logger.warning("Commit failed: %s", result.stderr)
            return f"Commit failed: {result.stderr}"

        # Push (never force)
        result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=self.cwd,
        )
        if result.returncode != 0:
            logger.warning("Push failed: %s", result.stderr)
            return f"Push failed: {result.stderr}"

        logger.info("Pushed fixes for PR #%d (%d files)", pr, len(unique_files))
        return f"Pushed {len(unique_files)} fixed file(s)"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_file_diff(self, path: str) -> str:
        """Get the diff for a single file."""
        result = subprocess.run(
            ["git", "diff", "--", path],
            capture_output=True, text=True, cwd=self.cwd,
        )
        return result.stdout.strip()

    def _build_reply(
        self,
        comment: ReviewComment,
        intent: str,
        fix_applied: bool,
        diff: str,
        error: str,
    ) -> str:
        """Build a reply message for a review comment."""
        parts: list[str] = []

        if fix_applied:
            parts.append("Applied fix for this feedback.")
            if diff:
                # Show a compact diff excerpt
                diff_lines = diff.split("\n")
                # Keep only +/- lines, limit to 20 lines
                change_lines = [
                    ln for ln in diff_lines
                    if ln.startswith("+") or ln.startswith("-")
                ][:20]
                if change_lines:
                    parts.append("")
                    parts.append("```diff")
                    parts.extend(change_lines)
                    parts.append("```")
        elif error:
            parts.append(f"Attempted to fix but encountered an error: {error}")
            parts.append("Will address this manually.")
        else:
            parts.append("Acknowledged. This requires a manual change that I'll address in a follow-up commit.")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------


def format_thread_responses(responses: list[ThreadResponse]) -> str:
    """Format a list of ThreadResponse objects for terminal display.

    Returns a human-readable summary with fix/skip/error counts.
    """
    if not responses:
        return "  No actionable review comments found."

    fixed = sum(1 for r in responses if r.fix_applied)
    acked = sum(1 for r in responses if not r.fix_applied and not r.error)
    errored = sum(1 for r in responses if r.error)

    lines: list[str] = []
    lines.append(f"  Processed {len(responses)} actionable comment(s):")
    lines.append(f"    Fixed:        {fixed}")
    lines.append(f"    Acknowledged: {acked}")
    if errored:
        lines.append(f"    Errors:       {errored}")

    lines.append("")

    for r in responses:
        status = "FIXED" if r.fix_applied else ("ERROR" if r.error else "ACK")
        icon = {"FIXED": "+", "ERROR": "!", "ACK": "-"}.get(status, " ")
        lines.append(f"  [{icon}] Comment #{r.comment_id}: {status}")
        if r.error:
            lines.append(f"      Error: {r.error}")
        if r.diff:
            # Show first 3 diff lines as preview
            preview = r.diff.split("\n")[:3]
            for dl in preview:
                lines.append(f"      {dl}")

    return "\n".join(lines)
