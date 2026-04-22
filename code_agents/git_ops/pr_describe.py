"""Auto-PR Description Generator — git diff → structured PR description."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.pr_describe")


@dataclass
class SuggestedReviewer:
    name: str
    email: str
    files_owned: list[str] = field(default_factory=list)
    blame_percentage: float = 0.0


@dataclass
class RiskArea:
    file: str
    reason: str
    severity: str = "medium"  # high, medium, low


@dataclass
class PRDescription:
    title: str
    summary: str
    changes: list[str] = field(default_factory=list)
    risk_areas: list[RiskArea] = field(default_factory=list)
    test_coverage: dict = field(default_factory=dict)
    suggested_reviewers: list[SuggestedReviewer] = field(default_factory=list)
    diff_stats: dict = field(default_factory=dict)
    commit_count: int = 0
    files_changed: list[str] = field(default_factory=list)


# Security-sensitive patterns for risk detection
_SECURITY_PATTERNS = [
    (r"password|secret|token|api_key|apikey|credential", "Contains sensitive keywords"),
    (r"eval\(|exec\(|subprocess\.call|os\.system", "Dynamic code execution"),
    (r"SQL|INSERT|UPDATE|DELETE|DROP", "Direct SQL operations"),
    (r"\.env|config\.json|credentials", "Configuration/secrets file"),
]

_HIGH_RISK_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rb", ".sh"}
_TEST_PATTERNS = {"test_", "_test.", ".test.", "spec.", "_spec."}


class PRDescriptionGenerator:
    """Generates structured PR descriptions from git branch diffs."""

    def __init__(self, cwd: str = ".", base: str = "main", include_reviewers: bool = True,
                 include_risk: bool = True, include_test_coverage: bool = True):
        self.cwd = os.path.abspath(cwd)
        self.base = base
        self.include_reviewers = include_reviewers
        self.include_risk = include_risk
        self.include_test_coverage = include_test_coverage

    def generate(self) -> PRDescription:
        """Generate a complete PR description."""
        commits = self._get_commits()
        changed_files = self._get_changed_files()
        diff_stats = self._get_diff_stats()

        title = self._generate_title(commits)
        summary = self._generate_summary(commits, diff_stats, changed_files)
        changes = self._extract_changes(commits)

        risk_areas = self._assess_risk(changed_files) if self.include_risk else []
        test_cov = self._check_test_coverage(changed_files) if self.include_test_coverage else {}
        reviewers = self._find_reviewers(changed_files) if self.include_reviewers else []

        return PRDescription(
            title=title,
            summary=summary,
            changes=changes,
            risk_areas=risk_areas,
            test_coverage=test_cov,
            suggested_reviewers=reviewers,
            diff_stats=diff_stats,
            commit_count=len(commits),
            files_changed=changed_files,
        )

    def _run_git(self, *args: str) -> str:
        """Run a git command and return stdout."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("git command failed: %s", exc)
            return ""

    def _get_commits(self) -> list[dict]:
        """Get commits between base and HEAD."""
        log = self._run_git(
            "log", f"{self.base}..HEAD",
            "--pretty=format:%H|%an|%ae|%s|%b",
            "--no-merges",
        )
        if not log:
            return []
        commits = []
        for line in log.split("\n"):
            parts = line.split("|", 4)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "email": parts[2],
                    "subject": parts[3],
                    "body": parts[4] if len(parts) > 4 else "",
                })
        return commits

    def _get_changed_files(self) -> list[str]:
        """Get list of changed files."""
        output = self._run_git("diff", "--name-only", f"{self.base}...HEAD")
        return [f for f in output.split("\n") if f.strip()] if output else []

    def _get_diff_stats(self) -> dict:
        """Get diff statistics."""
        output = self._run_git("diff", "--stat", f"{self.base}...HEAD")
        if not output:
            return {"files": 0, "insertions": 0, "deletions": 0}

        lines = output.strip().split("\n")
        summary_line = lines[-1] if lines else ""
        files = insertions = deletions = 0

        m = re.search(r"(\d+) files? changed", summary_line)
        if m:
            files = int(m.group(1))
        m = re.search(r"(\d+) insertions?", summary_line)
        if m:
            insertions = int(m.group(1))
        m = re.search(r"(\d+) deletions?", summary_line)
        if m:
            deletions = int(m.group(1))

        return {"files": files, "insertions": insertions, "deletions": deletions}

    def _generate_title(self, commits: list[dict]) -> str:
        """Generate a PR title from commits."""
        if not commits:
            return "Update"
        if len(commits) == 1:
            return commits[0]["subject"]
        # Find common prefix pattern (feat:, fix:, etc.)
        subjects = [c["subject"] for c in commits]
        prefixes = [s.split(":")[0] if ":" in s else "" for s in subjects]
        common = Counter(prefixes).most_common(1)
        if common and common[0][1] > len(commits) // 2:
            prefix = common[0][0]
            return f"{prefix}: {len(commits)} changes"
        return commits[0]["subject"]

    def _generate_summary(self, commits: list[dict], stats: dict, files: list[str]) -> str:
        """Generate a PR summary paragraph."""
        parts = []
        if commits:
            parts.append(f"This PR includes {len(commits)} commit(s)")
        if stats.get("files"):
            parts.append(
                f"touching {stats['files']} file(s) "
                f"(+{stats.get('insertions', 0)}/-{stats.get('deletions', 0)} lines)"
            )
        # Group files by directory
        dirs = Counter(str(Path(f).parent) for f in files)
        top_dirs = dirs.most_common(3)
        if top_dirs:
            dir_str = ", ".join(f"`{d}`" for d, _ in top_dirs)
            parts.append(f"primarily in {dir_str}")
        return ". ".join(parts) + "." if parts else "No changes detected."

    def _extract_changes(self, commits: list[dict]) -> list[str]:
        """Extract change bullet points from commit messages."""
        changes = []
        for c in commits:
            subj = c["subject"].strip()
            if subj:
                changes.append(f"- {subj}")
            body = c.get("body", "").strip()
            if body:
                for line in body.split("\n"):
                    line = line.strip()
                    if line and line.startswith(("- ", "* ")):
                        changes.append(f"  {line}")
        return changes

    def _assess_risk(self, changed_files: list[str]) -> list[RiskArea]:
        """Identify risk areas in changed files."""
        risks = []
        for f in changed_files:
            ext = Path(f).suffix
            # Check for security-sensitive patterns in filename
            for pattern, reason in _SECURITY_PATTERNS:
                if re.search(pattern, f, re.IGNORECASE):
                    risks.append(RiskArea(file=f, reason=reason, severity="high"))
                    break

            # Check for large files (heuristic: many lines changed)
            if ext in _HIGH_RISK_EXTENSIONS:
                diff = self._run_git("diff", f"{self.base}...HEAD", "--", f)
                added = diff.count("\n+") if diff else 0
                if added > 200:
                    risks.append(RiskArea(
                        file=f,
                        reason=f"Large change ({added}+ lines added)",
                        severity="medium",
                    ))

            # Check for no corresponding test
            if ext in _HIGH_RISK_EXTENSIONS and not any(p in f for p in _TEST_PATTERNS):
                test_file = self._guess_test_file(f)
                if test_file and test_file not in changed_files:
                    risks.append(RiskArea(
                        file=f,
                        reason="No corresponding test file updated",
                        severity="low",
                    ))

        return risks

    def _guess_test_file(self, source_file: str) -> Optional[str]:
        """Guess the test file path for a source file."""
        p = Path(source_file)
        stem = p.stem
        test_name = f"test_{stem}{p.suffix}"
        # Check common test directories
        for test_dir in ["tests", "test", "spec"]:
            candidate = os.path.join(self.cwd, test_dir, test_name)
            if os.path.exists(candidate):
                return os.path.join(test_dir, test_name)
        return None

    def _check_test_coverage(self, changed_files: list[str]) -> dict:
        """Check test coverage for changed files."""
        source_files = [f for f in changed_files
                        if Path(f).suffix in _HIGH_RISK_EXTENSIONS
                        and not any(p in f for p in _TEST_PATTERNS)]
        test_files = [f for f in changed_files if any(p in f for p in _TEST_PATTERNS)]

        covered = 0
        for sf in source_files:
            test_name = f"test_{Path(sf).stem}"
            if any(test_name in tf for tf in test_files):
                covered += 1

        return {
            "source_files_changed": len(source_files),
            "test_files_changed": len(test_files),
            "source_files_with_tests": covered,
            "coverage_pct": round(covered / max(len(source_files), 1) * 100, 1),
        }

    def _find_reviewers(self, changed_files: list[str]) -> list[SuggestedReviewer]:
        """Suggest reviewers based on git blame of changed files."""
        author_files: dict[str, list[str]] = defaultdict(list)
        author_emails: dict[str, str] = {}

        for f in changed_files[:20]:  # Limit to avoid slowness
            blame = self._run_git("blame", "--porcelain", "-L1,20", f)
            if not blame:
                continue
            for line in blame.split("\n"):
                if line.startswith("author "):
                    name = line[7:].strip()
                elif line.startswith("author-mail "):
                    email = line[12:].strip().strip("<>")
                    if name and email:
                        author_files[name].append(f)
                        author_emails[name] = email

        # Current user (exclude from reviewers)
        current_user = self._run_git("config", "user.name")

        reviewers = []
        for name, files in sorted(author_files.items(), key=lambda x: -len(x[1])):
            if name == current_user or name == "Not Committed Yet":
                continue
            reviewers.append(SuggestedReviewer(
                name=name,
                email=author_emails.get(name, ""),
                files_owned=list(set(files)),
                blame_percentage=round(len(files) / max(len(changed_files), 1) * 100, 1),
            ))

        return reviewers[:5]  # Top 5


def format_pr_description(desc: PRDescription, fmt: str = "md") -> str:
    """Format PR description as markdown or JSON."""
    if fmt == "json":
        import json
        from dataclasses import asdict
        return json.dumps(asdict(desc), indent=2)

    lines = [f"## {desc.title}", ""]
    if desc.summary:
        lines.extend([desc.summary, ""])

    if desc.changes:
        lines.extend(["### Changes", ""])
        lines.extend(desc.changes)
        lines.append("")

    if desc.risk_areas:
        lines.extend(["### Risk Areas", ""])
        for r in desc.risk_areas:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.severity, "⚪")
            lines.append(f"- {icon} **{r.file}**: {r.reason}")
        lines.append("")

    if desc.test_coverage:
        tc = desc.test_coverage
        lines.extend([
            "### Test Coverage", "",
            f"- Source files changed: {tc.get('source_files_changed', 0)}",
            f"- Test files changed: {tc.get('test_files_changed', 0)}",
            f"- Coverage: {tc.get('coverage_pct', 0)}%",
            "",
        ])

    if desc.suggested_reviewers:
        lines.extend(["### Suggested Reviewers", ""])
        for r in desc.suggested_reviewers:
            lines.append(f"- **{r.name}** ({r.email}) — {r.blame_percentage}% ownership")
        lines.append("")

    stats = desc.diff_stats
    lines.extend([
        "---",
        f"*{desc.commit_count} commits, {stats.get('files', 0)} files changed, "
        f"+{stats.get('insertions', 0)}/-{stats.get('deletions', 0)} lines*",
    ])

    return "\n".join(lines)
