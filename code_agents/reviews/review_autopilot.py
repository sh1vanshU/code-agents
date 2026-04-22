"""Code Review Autopilot — automated diff review via code-reviewer agent."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reviews.review_autopilot")


@dataclass
class ReviewFinding:
    """A single review finding."""

    file: str
    line: int
    severity: str  # critical, warning, suggestion, info
    category: str  # bug, security, style, performance, test
    message: str


@dataclass
class ReviewReport:
    """Full review report."""

    base: str
    head: str
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    findings: list[ReviewFinding] = field(default_factory=list)
    score: int = 100  # 0-100, starts at 100 and deducts
    summary: str = ""

    @property
    def by_severity(self) -> dict[str, list[ReviewFinding]]:
        groups: dict[str, list[ReviewFinding]] = {}
        for f in self.findings:
            groups.setdefault(f.severity, []).append(f)
        return groups

    @property
    def by_category(self) -> dict[str, list[ReviewFinding]]:
        groups: dict[str, list[ReviewFinding]] = {}
        for f in self.findings:
            groups.setdefault(f.category, []).append(f)
        return groups


class ReviewAutopilot:
    """Reads git diff, sends to code-reviewer agent, formats review."""

    def __init__(self, cwd: str, base: str = "main", head: str = "HEAD"):
        self.cwd = cwd
        self.base = base
        self.head = head
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self.report = ReviewReport(base=base, head=head)
        logger.info("ReviewAutopilot initialized — base=%s head=%s", base, head)

    def get_diff(self) -> str:
        """Get git diff between base and head."""
        try:
            result = subprocess.run(
                ["git", "diff", f"{self.base}...{self.head}"],
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return ""

    def get_diff_stats(self) -> dict:
        """Get diff stat summary."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{self.base}...{self.head}"],
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                # Parse last line: "N files changed, X insertions(+), Y deletions(-)"
                if lines:
                    import re
                    last = lines[-1]
                    files_m = re.search(r'(\d+) files? changed', last)
                    ins_m = re.search(r'(\d+) insertions?', last)
                    del_m = re.search(r'(\d+) deletions?', last)
                    return {
                        "files_changed": int(files_m.group(1)) if files_m else 0,
                        "insertions": int(ins_m.group(1)) if ins_m else 0,
                        "deletions": int(del_m.group(1)) if del_m else 0,
                    }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {}

    def analyze_diff(self, diff: str) -> list[ReviewFinding]:
        """Local static analysis of diff for common issues."""
        findings: list[ReviewFinding] = []
        current_file = ""
        current_line = 0

        for line in diff.splitlines():
            if line.startswith("diff --git"):
                parts = line.split(" b/")
                current_file = parts[-1] if len(parts) > 1 else ""
            elif line.startswith("@@"):
                import re
                m = re.search(r'\+(\d+)', line)
                if m:
                    current_line = int(m.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                current_line += 1
                content = line[1:]

                # Check for common issues
                if "print(" in content and current_file.endswith(".py"):
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="suggestion", category="style",
                        message="Debug print statement — consider using logging",
                    ))
                if "console.log(" in content:
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="suggestion", category="style",
                        message="Console.log statement — consider using a logger",
                    ))
                if "TODO" in content or "FIXME" in content:
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="info", category="style",
                        message="TODO/FIXME comment in new code",
                    ))
                if "password" in content.lower() and "=" in content:
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="critical", category="security",
                        message="Possible hardcoded password",
                    ))
                if "eval(" in content:
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="critical", category="security",
                        message="eval() usage — potential code injection",
                    ))
                if "except:" in content and "pass" not in content:
                    findings.append(ReviewFinding(
                        file=current_file, line=current_line,
                        severity="warning", category="bug",
                        message="Bare except clause — catches all exceptions",
                    ))

        return findings

    def send_to_agent(self, diff: str) -> Optional[str]:
        """Send diff to code-reviewer agent for AI review."""
        prompt = (
            "Review this git diff for bugs, security issues, style, performance, "
            "and test coverage. Be specific with file and line references.\n\n"
            f"```diff\n{diff[:10000]}\n```"
        )
        payload = json.dumps({
            "model": "code-reviewer",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }).encode()

        try:
            url = f"{self.server_url}/v1/chat/completions"
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("Failed to send to code-reviewer: %s", e)
        return None

    def run(self) -> ReviewReport:
        """Run full review: diff + local analysis + optional AI review."""
        diff = self.get_diff()
        stats = self.get_diff_stats()

        self.report.files_changed = stats.get("files_changed", 0)
        self.report.lines_added = stats.get("insertions", 0)
        self.report.lines_removed = stats.get("deletions", 0)

        # Local static analysis
        findings = self.analyze_diff(diff)
        self.report.findings = findings

        # Calculate score
        deductions = {
            "critical": 20,
            "warning": 5,
            "suggestion": 1,
            "info": 0,
        }
        total_deduct = sum(deductions.get(f.severity, 0) for f in findings)
        self.report.score = max(0, 100 - total_deduct)

        # Try AI review
        ai_review = self.send_to_agent(diff)
        if ai_review:
            self.report.summary = ai_review

        return self.report

    def post_pr_comment(self, pr_id: str, content: str) -> bool:
        """Post review as PR comment via Bitbucket API (if configured)."""
        bb_url = os.getenv("BITBUCKET_URL", "")
        bb_user = os.getenv("BITBUCKET_USERNAME", "")
        bb_pass = os.getenv("BITBUCKET_APP_PASSWORD", "")
        bb_repo = os.getenv("BITBUCKET_REPO_SLUG", "")
        bb_project = os.getenv("BITBUCKET_PROJECT_KEY", "")

        if not all([bb_url, bb_user, bb_pass, bb_repo, bb_project]):
            logger.info("Bitbucket not configured — skipping PR comment")
            return False

        url = f"{bb_url}/rest/api/1.0/projects/{bb_project}/repos/{bb_repo}/pull-requests/{pr_id}/comments"
        payload = json.dumps({"text": content}).encode()

        import base64
        auth = base64.b64encode(f"{bb_user}:{bb_pass}".encode()).decode()

        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status < 300
        except Exception as e:
            logger.warning("Failed to post PR comment: %s", e)
            return False


def format_review(report: ReviewReport) -> str:
    """Format review report for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Code Review Autopilot")
    lines.append("  " + "=" * 50)
    lines.append(f"  Diff: {report.base}...{report.head}")
    lines.append(f"  Files changed: {report.files_changed}")
    lines.append(f"  Lines: +{report.lines_added} / -{report.lines_removed}")
    lines.append(f"  Score: {report.score}/100")
    lines.append("")

    if not report.findings:
        lines.append("  No issues found — looks good!")
        return "\n".join(lines)

    severity_icons = {
        "critical": "[!!]",
        "warning": "[!]",
        "suggestion": "[~]",
        "info": "[i]",
    }

    by_sev = report.by_severity
    for sev in ["critical", "warning", "suggestion", "info"]:
        items = by_sev.get(sev, [])
        if not items:
            continue
        icon = severity_icons.get(sev, "[?]")
        lines.append(f"  {sev.upper()} ({len(items)})")
        lines.append("  " + "-" * 40)
        for f in items[:15]:
            lines.append(f"    {icon} {f.file}:{f.line} — {f.message}")
        if len(items) > 15:
            lines.append(f"    ... and {len(items) - 15} more")
        lines.append("")

    if report.summary:
        lines.append("  AI Review Summary:")
        lines.append("  " + "-" * 40)
        for sl in report.summary.splitlines()[:20]:
            lines.append(f"    {sl}")
        lines.append("")

    return "\n".join(lines)
