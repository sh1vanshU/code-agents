"""Review Responder — reads PR comments and generates replies/fixes."""

import logging
import os
import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reviews.review_responder")

@dataclass
class ReviewComment:
    author: str
    body: str
    file_path: str = ""
    line: int = 0
    diff_hunk: str = ""
    created_at: str = ""

@dataclass
class ReviewResponse:
    comment: ReviewComment
    reply_text: str = ""
    code_fix: str = ""  # if fix is needed
    fix_file: str = ""
    fix_line: int = 0

class ReviewResponder:
    """Reads PR review comments and generates responses."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.server_url = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        logger.info("ReviewResponder created: cwd=%s", cwd)

    def get_pr_comments(self, pr_number: Optional[int] = None) -> list[ReviewComment]:
        """Get review comments from current PR or specified PR number."""
        comments = []

        # Try to detect current PR from branch
        if not pr_number:
            pr_number = self._detect_current_pr()
            logger.info("Auto-detected PR number: %s", pr_number)

        if not pr_number:
            logger.warning("No PR number detected or provided")
            return comments

        logger.info("Fetching comments for PR #%d", pr_number)

        # Try Bitbucket API (since project uses Bitbucket)
        comments = self._fetch_bitbucket_comments(pr_number)
        if not comments:
            # Fallback to git-based approach
            comments = self._fetch_github_comments(pr_number)

        logger.info("Found %d PR comments", len(comments))
        return comments

    def _detect_current_pr(self) -> Optional[int]:
        """Detect PR number from current branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=self.cwd
            )
            branch = result.stdout.strip()
            logger.debug("Current branch: %s", branch)
            # Common patterns: feature/PROJ-123, fix/123, pr/123
            import re
            match = re.search(r'(\d+)', branch)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.debug("Branch detection failed: %s", e)
        return None

    def _fetch_bitbucket_comments(self, pr_number: int) -> list[ReviewComment]:
        """Fetch PR comments from Bitbucket."""
        logger.debug("Fetching Bitbucket comments for PR #%d", pr_number)
        # Would need Bitbucket API integration
        # For now, return empty — can be extended later
        return []

    def _fetch_github_comments(self, pr_number: int) -> list[ReviewComment]:
        """Fetch PR comments from GitHub."""
        logger.debug("Fetching GitHub comments for PR #%d", pr_number)
        return []

    def build_reply_prompt(self, comment: ReviewComment, source_context: str = "") -> str:
        """Build prompt for AI to generate reply."""
        prompt = f"""A code reviewer left this comment on a PR:

**Reviewer:** {comment.author}
**File:** {comment.file_path}:{comment.line}
**Comment:** {comment.body}
"""
        if comment.diff_hunk:
            prompt += f"\n**Code context:**\n```\n{comment.diff_hunk}\n```\n"

        if source_context:
            prompt += f"\n**Full file context:**\n```\n{source_context}\n```\n"

        prompt += """
Generate:
1. A professional reply acknowledging the feedback
2. If a code change is needed, provide the fix
3. If you disagree, explain why with reasoning

Output format:
REPLY: <your reply text>
FIX: <code fix if needed, or "none">
"""
        return prompt

    def get_source_context(self, file_path: str, line: int, context_lines: int = 10) -> str:
        """Get source code context around the commented line."""
        full_path = os.path.join(self.cwd, file_path)
        if not os.path.exists(full_path):
            logger.debug("File not found for context: %s", full_path)
            return ""
        try:
            with open(full_path) as f:
                lines = f.readlines()
            start = max(0, line - context_lines)
            end = min(len(lines), line + context_lines)
            return "".join(lines[start:end])
        except Exception as e:
            logger.debug("Failed to read source context from %s: %s", full_path, e)
            return ""


def format_review_comments(comments: list[ReviewComment]) -> str:
    """Format PR comments for display."""
    lines = []
    for i, c in enumerate(comments, 1):
        lines.append(f"  {i}. [{c.author}] {c.file_path}:{c.line}")
        lines.append(f"     {c.body[:120]}")
    return "\n".join(lines)
