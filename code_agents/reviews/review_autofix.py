"""Review Auto-Fix — generate and apply fixes for review findings.

Extends ReviewAutopilot with the ability to:
1. Generate concrete code fixes for each review finding
2. Apply fixes automatically (with rollback support)
3. Post review comments to GitHub/Bitbucket with inline annotations
4. Score findings by severity with configurable thresholds

Usage:
    from code_agents.reviews.review_autofix import ReviewAutoFixer
    fixer = ReviewAutoFixer(cwd="/path/to/repo")
    report = fixer.run(base="main", fix=True, post_comments=True)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .review_autopilot import ReviewAutopilot, ReviewFinding, ReviewReport, format_review

logger = logging.getLogger("code_agents.reviews.review_autofix")


# ---------------------------------------------------------------------------
# Extended data models
# ---------------------------------------------------------------------------


@dataclass
class ReviewFixSuggestion:
    """A concrete fix suggestion for a review finding."""
    finding_index: int
    file: str
    line: int
    original_code: str
    fixed_code: str
    explanation: str
    confidence: float = 0.0  # 0.0 - 1.0


@dataclass
class ReviewAutoFixReport:
    """Full auto-fix report extending the base review."""
    review: ReviewReport = field(default_factory=lambda: ReviewReport(base="", head=""))
    fix_suggestions: list[ReviewFixSuggestion] = field(default_factory=list)
    fixes_applied: int = 0
    fixes_failed: int = 0
    fixes_skipped: int = 0
    comments_posted: int = 0
    backup_dir: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------


SEVERITY_WEIGHTS = {
    "critical": 20,
    "warning": 5,
    "suggestion": 1,
    "info": 0,
}

CATEGORY_MULTIPLIERS = {
    "security": 2.0,
    "bug": 1.5,
    "performance": 1.0,
    "style": 0.5,
    "test": 0.8,
}


def calculate_severity_score(findings: list[ReviewFinding]) -> dict:
    """Calculate a detailed severity score from findings."""
    score = 100
    breakdown = {
        "total_findings": len(findings),
        "by_severity": {},
        "by_category": {},
        "weighted_deductions": 0,
    }

    for f in findings:
        sev = f.severity
        cat = f.category

        # Count by severity
        breakdown["by_severity"][sev] = breakdown["by_severity"].get(sev, 0) + 1
        breakdown["by_category"][cat] = breakdown["by_category"].get(cat, 0) + 1

        # Calculate weighted deduction
        base_weight = SEVERITY_WEIGHTS.get(sev, 0)
        multiplier = CATEGORY_MULTIPLIERS.get(cat, 1.0)
        deduction = base_weight * multiplier
        breakdown["weighted_deductions"] += deduction
        score -= deduction

    breakdown["final_score"] = max(0, round(score, 1))

    # Grade
    if score >= 90:
        breakdown["grade"] = "A"
    elif score >= 80:
        breakdown["grade"] = "B"
    elif score >= 70:
        breakdown["grade"] = "C"
    elif score >= 60:
        breakdown["grade"] = "D"
    else:
        breakdown["grade"] = "F"

    return breakdown


# ---------------------------------------------------------------------------
# Auto-fixer
# ---------------------------------------------------------------------------


class ReviewAutoFixer:
    """Extends ReviewAutopilot with auto-fix capability."""

    def __init__(
        self,
        cwd: str = "",
        server_url: str = "",
        min_confidence: float = 0.7,
    ):
        self.cwd = cwd or os.getenv("TARGET_REPO_PATH", os.getcwd())
        self.server_url = server_url or os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL",
            f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
        )
        self.min_confidence = min_confidence

    def run(
        self,
        base: str = "main",
        head: str = "HEAD",
        fix: bool = False,
        post_comments: bool = False,
        pr_id: str = "",
        severity_filter: str = "",
        json_output: bool = False,
    ) -> ReviewAutoFixReport:
        """Run full review + optional auto-fix + optional PR comments."""
        report = ReviewAutoFixReport(timestamp=datetime.now().isoformat())

        # Step 1: Run base review
        autopilot = ReviewAutopilot(cwd=self.cwd, base=base, head=head)
        autopilot.server_url = self.server_url
        review = autopilot.run()
        report.review = review

        # Apply severity filter
        if severity_filter:
            allowed = [s.strip().lower() for s in severity_filter.split(",")]
            review.findings = [f for f in review.findings if f.severity in allowed]

        # Step 2: Generate fix suggestions via AI
        if fix and review.findings:
            report.fix_suggestions = self._generate_fixes(review)

            # Step 3: Apply fixes
            if report.fix_suggestions:
                report.backup_dir = self._create_backup(report.fix_suggestions)
                self._apply_fixes(report)

        # Step 4: Post PR comments
        if post_comments and pr_id and review.findings:
            report.comments_posted = self._post_inline_comments(
                pr_id, review, report.fix_suggestions
            )

        return report

    def _generate_fixes(self, review: ReviewReport) -> list[ReviewFixSuggestion]:
        """Use AI to generate fix suggestions for each finding."""
        suggestions = []

        # Read changed files for context
        file_contexts = {}
        for finding in review.findings:
            if finding.file and finding.file not in file_contexts:
                filepath = os.path.join(self.cwd, finding.file)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath) as f:
                            lines = f.readlines()
                        # Get context around the line
                        start = max(0, finding.line - 5)
                        end = min(len(lines), finding.line + 5)
                        file_contexts[finding.file] = {
                            "lines": lines,
                            "context": "".join(lines[start:end]),
                            "start_line": start + 1,
                        }
                    except Exception:
                        pass

        # Build AI prompt for batch fix generation
        findings_text = []
        for i, f in enumerate(review.findings[:20]):
            ctx = file_contexts.get(f.file, {}).get("context", "")
            findings_text.append(
                f"Finding #{i}: [{f.severity}] {f.category} — {f.file}:{f.line}\n"
                f"  Issue: {f.message}\n"
                f"  Context:\n```\n{ctx}\n```"
            )

        prompt = (
            "For each code review finding below, suggest a concrete fix.\n"
            "Respond with a JSON array of fix objects:\n"
            '[{"finding_index": 0, "original_code": "...", "fixed_code": "...", '
            '"explanation": "...", "confidence": 0.9}]\n\n'
            "Only suggest fixes you're confident about (confidence > 0.7).\n"
            "For style issues, use the project's existing conventions.\n\n"
            + "\n\n".join(findings_text)
        )

        ai_response = self._call_agent_sync(prompt, agent="code-writer")
        if ai_response:
            try:
                # Extract JSON array
                match = re.search(r'\[[\s\S]*\]', ai_response)
                if match:
                    fixes_data = json.loads(match.group())
                    for fix_data in fixes_data:
                        idx = fix_data.get("finding_index", 0)
                        if idx < len(review.findings):
                            finding = review.findings[idx]
                            suggestions.append(ReviewFixSuggestion(
                                finding_index=idx,
                                file=finding.file,
                                line=finding.line,
                                original_code=fix_data.get("original_code", ""),
                                fixed_code=fix_data.get("fixed_code", ""),
                                explanation=fix_data.get("explanation", ""),
                                confidence=float(fix_data.get("confidence", 0.5)),
                            ))
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.debug("Failed to parse AI fix suggestions: %s", e)

        return suggestions

    def _create_backup(self, suggestions: list[ReviewFixSuggestion]) -> str:
        """Create a backup of files that will be modified."""
        backup_dir = tempfile.mkdtemp(prefix="code-agents-review-backup-")
        files_backed_up = set()

        for s in suggestions:
            if s.file in files_backed_up:
                continue
            src = os.path.join(self.cwd, s.file)
            if os.path.isfile(src):
                dst_dir = os.path.join(backup_dir, os.path.dirname(s.file))
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, os.path.join(backup_dir, s.file))
                files_backed_up.add(s.file)

        logger.info("Backed up %d files to %s", len(files_backed_up), backup_dir)
        return backup_dir

    def _apply_fixes(self, report: ReviewAutoFixReport):
        """Apply fix suggestions to the codebase."""
        for suggestion in report.fix_suggestions:
            if suggestion.confidence < self.min_confidence:
                report.fixes_skipped += 1
                continue

            filepath = os.path.join(self.cwd, suggestion.file)
            if not os.path.isfile(filepath):
                report.fixes_skipped += 1
                continue

            try:
                content = Path(filepath).read_text()
                if suggestion.original_code and suggestion.original_code in content:
                    new_content = content.replace(
                        suggestion.original_code,
                        suggestion.fixed_code,
                        1,
                    )
                    Path(filepath).write_text(new_content)
                    report.fixes_applied += 1
                    logger.info("Applied fix: %s:%d — %s", suggestion.file, suggestion.line, suggestion.explanation)
                else:
                    report.fixes_skipped += 1
                    logger.debug("Original code not found in %s", suggestion.file)
            except Exception as e:
                report.fixes_failed += 1
                logger.warning("Failed to apply fix to %s: %s", suggestion.file, e)

    def rollback(self, backup_dir: str):
        """Rollback applied fixes from backup."""
        if not os.path.isdir(backup_dir):
            logger.warning("Backup directory not found: %s", backup_dir)
            return

        for root, dirs, files in os.walk(backup_dir):
            for f in files:
                backup_path = os.path.join(root, f)
                rel_path = os.path.relpath(backup_path, backup_dir)
                target_path = os.path.join(self.cwd, rel_path)
                shutil.copy2(backup_path, target_path)
                logger.info("Restored: %s", rel_path)

    def _post_inline_comments(
        self,
        pr_id: str,
        review: ReviewReport,
        suggestions: list[ReviewFixSuggestion],
    ) -> int:
        """Post inline review comments to Bitbucket/GitHub."""
        posted = 0

        # Build a fix map for quick lookup
        fix_map = {}
        for s in suggestions:
            fix_map[s.finding_index] = s

        bb_url = os.getenv("BITBUCKET_URL", "")
        bb_user = os.getenv("BITBUCKET_USERNAME", "")
        bb_pass = os.getenv("BITBUCKET_APP_PASSWORD", "")
        bb_repo = os.getenv("BITBUCKET_REPO_SLUG", "")
        bb_project = os.getenv("BITBUCKET_PROJECT_KEY", "")

        gh_token = os.getenv("GITHUB_TOKEN", "")
        gh_repo = os.getenv("GITHUB_REPOSITORY", "")

        if all([bb_url, bb_user, bb_pass, bb_repo, bb_project]):
            posted = self._post_bitbucket_comments(
                pr_id, review, fix_map, bb_url, bb_user, bb_pass, bb_project, bb_repo
            )
        elif gh_token and gh_repo:
            posted = self._post_github_comments(
                pr_id, review, fix_map, gh_token, gh_repo
            )
        else:
            logger.info("No git hosting configured — skipping PR comments")

        return posted

    def _post_bitbucket_comments(
        self, pr_id, review, fix_map,
        bb_url, bb_user, bb_pass, bb_project, bb_repo,
    ) -> int:
        """Post inline comments to Bitbucket PR."""
        import base64
        auth = base64.b64encode(f"{bb_user}:{bb_pass}".encode()).decode()
        url = f"{bb_url}/rest/api/1.0/projects/{bb_project}/repos/{bb_repo}/pull-requests/{pr_id}/comments"

        posted = 0
        for i, finding in enumerate(review.findings[:30]):
            comment_text = f"**[{finding.severity.upper()}]** {finding.category}: {finding.message}"

            fix = fix_map.get(i)
            if fix and fix.confidence >= self.min_confidence:
                comment_text += f"\n\n**Suggested fix:**\n```\n{fix.fixed_code}\n```\n_{fix.explanation}_"

            payload = json.dumps({
                "text": comment_text,
                "anchor": {
                    "path": finding.file,
                    "line": finding.line,
                    "lineType": "ADDED",
                },
            }).encode()

            try:
                req = urllib.request.Request(
                    url, data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Basic {auth}",
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status < 300:
                        posted += 1
            except Exception as e:
                logger.debug("Failed to post comment: %s", e)

        return posted

    def _post_github_comments(
        self, pr_id, review, fix_map, gh_token, gh_repo,
    ) -> int:
        """Post inline comments to GitHub PR."""
        # Get the latest commit SHA for the PR
        api_url = f"https://api.github.com/repos/{gh_repo}/pulls/{pr_id}"
        try:
            req = urllib.request.Request(
                api_url,
                headers={
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                pr_data = json.loads(resp.read())
                commit_sha = pr_data.get("head", {}).get("sha", "")
        except Exception as e:
            logger.warning("Failed to get PR info: %s", e)
            return 0

        if not commit_sha:
            return 0

        # Post review comments
        comments = []
        for i, finding in enumerate(review.findings[:30]):
            body = f"**[{finding.severity.upper()}]** {finding.category}: {finding.message}"

            fix = fix_map.get(i)
            if fix and fix.confidence >= self.min_confidence:
                body += (
                    f"\n\n**Suggested fix:**\n```suggestion\n{fix.fixed_code}\n```"
                    f"\n_{fix.explanation}_"
                )

            comments.append({
                "path": finding.file,
                "line": finding.line,
                "body": body,
            })

        if not comments:
            return 0

        review_url = f"https://api.github.com/repos/{gh_repo}/pulls/{pr_id}/reviews"
        payload = json.dumps({
            "commit_id": commit_sha,
            "body": f"Code Review Autopilot: {len(review.findings)} findings (score: {review.score}/100)",
            "event": "COMMENT",
            "comments": comments,
        }).encode()

        try:
            req = urllib.request.Request(
                review_url, data=payload,
                headers={
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status < 300:
                    return len(comments)
        except Exception as e:
            logger.warning("Failed to post GitHub review: %s", e)

        return 0

    def _call_agent_sync(self, prompt: str, agent: str = "code-writer") -> str:
        """Synchronous agent call."""
        payload = json.dumps({
            "model": agent,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }).encode()

        try:
            url = f"{self.server_url}/v1/chat/completions"
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Agent": agent,
                },
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("Agent call failed (%s): %s", agent, e)
        return ""


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_autofix_report(report: ReviewAutoFixReport) -> str:
    """Format auto-fix report for terminal display."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        # Base review
        review = report.review
        severity_info = calculate_severity_score(review.findings)
        grade = severity_info.get("grade", "?")
        grade_color = {
            "A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "red bold",
        }.get(grade, "white")

        # Summary panel
        summary = (
            f"Diff: {review.base}...{review.head}  |  "
            f"Files: {review.files_changed}  |  "
            f"+{review.lines_added}/-{review.lines_removed}  |  "
            f"Score: [{grade_color}]{severity_info['final_score']}/100 ({grade})[/{grade_color}]"
        )
        console.print(Panel(summary, title="Code Review + Auto-Fix", border_style="cyan"))

        # Findings table
        if review.findings:
            table = Table(title=f"Findings ({len(review.findings)})", show_lines=True)
            table.add_column("#", justify="center", width=3)
            table.add_column("Severity", justify="center")
            table.add_column("Category")
            table.add_column("File:Line", style="bold")
            table.add_column("Issue", max_width=40)

            sev_colors = {
                "critical": "red bold", "warning": "yellow",
                "suggestion": "cyan", "info": "dim",
            }

            for i, f in enumerate(review.findings[:30]):
                sev_style = sev_colors.get(f.severity, "white")
                table.add_row(
                    str(i), f"[{sev_style}]{f.severity}[/{sev_style}]",
                    f.category, f"{f.file}:{f.line}", f.message,
                )
            console.print(table)

        # Fix suggestions
        if report.fix_suggestions:
            console.print()
            table = Table(title="Fix Suggestions", show_lines=True)
            table.add_column("File:Line", style="bold")
            table.add_column("Confidence", justify="center")
            table.add_column("Fix", max_width=50)

            for s in report.fix_suggestions:
                conf_color = "green" if s.confidence >= 0.8 else "yellow" if s.confidence >= 0.6 else "red"
                table.add_row(
                    f"{s.file}:{s.line}",
                    f"[{conf_color}]{s.confidence:.0%}[/{conf_color}]",
                    s.explanation,
                )
            console.print(table)

        # Fix results
        if report.fixes_applied or report.fixes_failed or report.fixes_skipped:
            console.print()
            console.print(
                f"  Fixes: [green]{report.fixes_applied} applied[/green] | "
                f"[red]{report.fixes_failed} failed[/red] | "
                f"[dim]{report.fixes_skipped} skipped[/dim]"
            )
            if report.backup_dir:
                console.print(f"  Backup: [dim]{report.backup_dir}[/dim]")

        if report.comments_posted:
            console.print(f"  PR Comments: [green]{report.comments_posted} posted[/green]")

        # AI summary
        if review.summary:
            console.print()
            console.print(Panel(review.summary[:500], title="AI Review Summary", border_style="dim"))

        console.print()

    except ImportError:
        # Fallback
        print(format_review(report.review))
        if report.fix_suggestions:
            print(f"\n  Fix Suggestions: {len(report.fix_suggestions)}")
            for s in report.fix_suggestions:
                print(f"    {s.file}:{s.line} ({s.confidence:.0%}) — {s.explanation}")
        if report.fixes_applied:
            print(f"\n  Applied: {report.fixes_applied} | Failed: {report.fixes_failed} | Skipped: {report.fixes_skipped}")

    return ""
