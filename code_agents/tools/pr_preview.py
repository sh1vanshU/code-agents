"""PR Preview — show what a PR would look like before creating it.

Provides diff stats, affected tests, risk score, breaking change detection,
auto-generated title and body. All git operations are subprocess-based.

Usage:
    from code_agents.tools.pr_preview import PRPreview
    preview = PRPreview(cwd="/path/to/repo", base="main")
    print(preview.format_preview())
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("code_agents.tools.pr_preview")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileStat:
    """Stats for a single changed file."""
    path: str
    insertions: int = 0
    deletions: int = 0
    status: str = ""  # A=added, M=modified, D=deleted, R=renamed
    rename_from: str = ""


@dataclass
class CommitInfo:
    """A single commit on the branch."""
    sha: str
    message: str


@dataclass
class RiskFactor:
    """A single risk factor contributing to the score."""
    level: str  # green, yellow, orange, red
    message: str
    points: int = 0


@dataclass
class TestResult:
    """Mapping of a source file to its test file."""
    source_file: str
    test_file: Optional[str] = None
    test_exists: bool = False
    test_modified: bool = False


@dataclass
class BreakingChange:
    """A detected breaking change."""
    category: str  # api_signature, removed_method, db_migration
    description: str
    file: str


# ---------------------------------------------------------------------------
# Critical path patterns
# ---------------------------------------------------------------------------

CRITICAL_PATTERNS = [
    (r"(?i)(payment|billing|charge|refund|transaction)", "Payment/billing path"),
    (r"(?i)(auth|login|oauth|token|credential|session|security)", "Authentication/security"),
    (r"(?i)(config|settings|application\.ya?ml|\.env)", "Configuration file"),
    (r"(?i)(migration|migrate|schema|flyway|liquibase|alembic)", "Database migration"),
    (r"(?i)(deploy|dockerfile|k8s|kubernetes|helm)", "Deployment config"),
]

# Test file detection patterns
TEST_PATTERNS = [
    # Java/Kotlin: src/main/... -> src/test/...
    (r"^src/main/(.+)\.java$", "src/test/{0}Test.java"),
    (r"^src/main/(.+)\.kt$", "src/test/{0}Test.kt"),
    # Python: module.py -> test_module.py / tests/test_module.py
    (r"^(.+)/([^/]+)\.py$", "{0}/test_{1}.py"),
    (r"^([^/]+)\.py$", "test_{0}.py"),
    # JavaScript/TypeScript
    (r"^(.+)\.([jt]sx?)$", "{0}.test.{1}"),
    (r"^src/(.+)\.([jt]sx?)$", "tests/{0}.test.{1}"),
    # Go
    (r"^(.+)\.go$", "{0}_test.go"),
]


class PRPreview:
    """Generate a preview of what a PR would look like."""

    def __init__(self, cwd: str, base: str = "main"):
        self.cwd = cwd
        self.base = base
        self._branch: Optional[str] = None
        self._file_stats: Optional[list[FileStat]] = None
        self._commits: Optional[list[CommitInfo]] = None

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _run_git(self, *args: str, timeout: int = 15) -> tuple[int, str]:
        """Run a git command and return (returncode, stdout)."""
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=self.cwd,
            )
            return result.returncode, result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("git command failed: %s — %s", " ".join(cmd), exc)
            return 1, ""

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        if self._branch is None:
            rc, out = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
            self._branch = out if rc == 0 else "HEAD"
        return self._branch

    # ------------------------------------------------------------------
    # Diff stats
    # ------------------------------------------------------------------

    def get_diff_stats(self) -> list[FileStat]:
        """Get per-file diff stats: insertions, deletions, status, renames."""
        if self._file_stats is not None:
            return self._file_stats

        merge_base = self._merge_base()
        if not merge_base:
            self._file_stats = []
            return self._file_stats

        # --numstat for insertions/deletions
        rc, numstat_out = self._run_git(
            "diff", "--numstat", f"{merge_base}...HEAD",
        )
        numstat_lines = numstat_out.splitlines() if rc == 0 else []

        # --name-status for status (A/M/D/R) + rename detection
        rc, status_out = self._run_git(
            "diff", "--name-status", "-M", f"{merge_base}...HEAD",
        )
        status_lines = status_out.splitlines() if rc == 0 else []

        # Build status map: path -> (status, rename_from)
        status_map: dict[str, tuple[str, str]] = {}
        for line in status_lines:
            parts = line.split("\t")
            if len(parts) >= 2:
                status_code = parts[0][0]  # first char: A, M, D, R, C
                if status_code == "R" and len(parts) >= 3:
                    status_map[parts[2]] = ("R", parts[1])
                else:
                    status_map[parts[1]] = (status_code, "")

        # Parse numstat
        stats: list[FileStat] = []
        for line in numstat_lines:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            ins_str, del_str, path = parts[0], parts[1], parts[2]
            # Binary files show '-' for insertions/deletions
            ins = int(ins_str) if ins_str != "-" else 0
            dels = int(del_str) if del_str != "-" else 0
            status_code, rename_from = status_map.get(path, ("M", ""))
            stats.append(FileStat(
                path=path,
                insertions=ins,
                deletions=dels,
                status=status_code,
                rename_from=rename_from,
            ))

        self._file_stats = stats
        return self._file_stats

    def get_total_stats(self) -> tuple[int, int, int]:
        """Return (files_changed, total_insertions, total_deletions)."""
        stats = self.get_diff_stats()
        return (
            len(stats),
            sum(f.insertions for f in stats),
            sum(f.deletions for f in stats),
        )

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    def get_commits(self) -> list[CommitInfo]:
        """List commits on current branch not in base."""
        if self._commits is not None:
            return self._commits

        merge_base = self._merge_base()
        if not merge_base:
            self._commits = []
            return self._commits

        rc, out = self._run_git(
            "log", "--oneline", f"{merge_base}..HEAD",
        )
        commits: list[CommitInfo] = []
        if rc == 0 and out:
            for line in out.splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    commits.append(CommitInfo(sha=parts[0], message=parts[1]))
        self._commits = commits
        return self._commits

    # ------------------------------------------------------------------
    # Affected tests
    # ------------------------------------------------------------------

    def get_affected_tests(self) -> list[TestResult]:
        """Find test files corresponding to changed source files."""
        stats = self.get_diff_stats()
        changed_paths = {f.path for f in stats}
        results: list[TestResult] = []

        for fstat in stats:
            path = fstat.path
            # Skip test files themselves, config files, docs
            if self._is_test_file(path):
                continue
            if self._is_non_code_file(path):
                continue

            # Try to find corresponding test
            test_path = self._find_test_path(path)
            if test_path:
                test_exists = self._file_exists(test_path)
                test_modified = test_path in changed_paths
                results.append(TestResult(
                    source_file=path,
                    test_file=test_path,
                    test_exists=test_exists,
                    test_modified=test_modified,
                ))
            else:
                results.append(TestResult(
                    source_file=path,
                    test_file=None,
                    test_exists=False,
                    test_modified=False,
                ))

        return results

    # ------------------------------------------------------------------
    # Risk score
    # ------------------------------------------------------------------

    def calculate_risk_score(self) -> tuple[int, list[RiskFactor]]:
        """Calculate risk score 0-100 with contributing factors."""
        factors: list[RiskFactor] = []
        score = 0

        stats = self.get_diff_stats()
        files_changed, total_ins, total_del = self.get_total_stats()
        total_lines = total_ins + total_del
        tests = self.get_affected_tests()
        breaking = self.detect_breaking_changes()

        # --- File count ---
        if files_changed > 20:
            factors.append(RiskFactor("red", f"{files_changed} files changed (>20 = high risk)", 20))
            score += 20
        elif files_changed > 10:
            factors.append(RiskFactor("yellow", f"{files_changed} files changed (>10 = higher risk)", 10))
            score += 10
        elif files_changed > 5:
            factors.append(RiskFactor("yellow", f"{files_changed} files changed", 5))
            score += 5
        else:
            factors.append(RiskFactor("green", f"{files_changed} files changed", 0))

        # --- Diff size ---
        if total_lines > 1000:
            factors.append(RiskFactor("red", f"+{total_ins}/-{total_del} lines (>1000 = large diff)", 20))
            score += 20
        elif total_lines > 500:
            factors.append(RiskFactor("orange", f"+{total_ins}/-{total_del} lines (>500)", 10))
            score += 10
        elif total_lines > 200:
            factors.append(RiskFactor("yellow", f"+{total_ins}/-{total_del} lines", 5))
            score += 5

        # --- Critical paths ---
        critical_hits: list[str] = []
        for fstat in stats:
            for pattern, label in CRITICAL_PATTERNS:
                if re.search(pattern, fstat.path):
                    if label not in critical_hits:
                        critical_hits.append(label)
        for hit in critical_hits:
            factors.append(RiskFactor("orange", f"Critical path: {hit}", 10))
            score += 10

        # --- Test coverage of changes ---
        if tests:
            missing = [t for t in tests if not t.test_exists]
            covered = [t for t in tests if t.test_exists]
            modified = [t for t in tests if t.test_modified]

            if missing:
                factors.append(RiskFactor(
                    "red" if len(missing) > 2 else "yellow",
                    f"{len(missing)} changed file(s) have no tests",
                    min(len(missing) * 5, 15),
                ))
                score += min(len(missing) * 5, 15)
            if modified:
                factors.append(RiskFactor("green", f"Tests updated for {len(modified)} file(s)", 0))
            if covered and not missing:
                factors.append(RiskFactor("green", "All changed files have tests", 0))
                score = max(score - 5, 0)
        else:
            factors.append(RiskFactor("green", "No testable source files changed", 0))

        # --- Breaking changes ---
        if breaking:
            for bc in breaking:
                factors.append(RiskFactor("red", f"Breaking: {bc.description}", 10))
                score += 10

        # --- DB migrations ---
        has_migration = any(
            re.search(r"(?i)(migration|migrate|flyway|liquibase|alembic)", f.path)
            for f in stats
        )
        if has_migration:
            factors.append(RiskFactor("orange", "Database migration present", 10))
            score += 10
        else:
            factors.append(RiskFactor("green", "No DB migrations", 0))

        return min(score, 100), factors

    # ------------------------------------------------------------------
    # Breaking change detection
    # ------------------------------------------------------------------

    def detect_breaking_changes(self) -> list[BreakingChange]:
        """Detect potential breaking changes in the diff."""
        merge_base = self._merge_base()
        if not merge_base:
            return []

        rc, diff_text = self._run_git("diff", f"{merge_base}...HEAD", timeout=30)
        if rc != 0 or not diff_text:
            return []

        breaking: list[BreakingChange] = []
        current_file = ""

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                # Extract b/ path
                parts = line.split(" b/")
                current_file = parts[-1] if len(parts) > 1 else ""
                continue

            # Removed public method (Java/Kotlin)
            if line.startswith("-") and not line.startswith("---"):
                stripped = line[1:].strip()
                if re.match(r"public\s+\w+\s+\w+\s*\(", stripped):
                    method_match = re.search(r"public\s+\w+\s+(\w+)\s*\(", stripped)
                    if method_match:
                        breaking.append(BreakingChange(
                            category="removed_method",
                            description=f"Removed public method: {method_match.group(1)}()",
                            file=current_file,
                        ))

            # Removed Python def
            if line.startswith("-") and not line.startswith("---"):
                stripped = line[1:].strip()
                if re.match(r"def\s+[a-z]\w*\s*\(", stripped) and not stripped.startswith("def _"):
                    func_match = re.search(r"def\s+(\w+)\s*\(", stripped)
                    if func_match:
                        breaking.append(BreakingChange(
                            category="removed_method",
                            description=f"Removed public function: {func_match.group(1)}()",
                            file=current_file,
                        ))

            # API route changes
            if line.startswith("-") and not line.startswith("---"):
                stripped = line[1:].strip()
                if re.search(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(', stripped):
                    breaking.append(BreakingChange(
                        category="api_signature",
                        description=f"API endpoint mapping changed in {current_file}",
                        file=current_file,
                    ))
                elif re.search(r'@(app|router)\.(get|post|put|delete|patch)\s*\(', stripped):
                    breaking.append(BreakingChange(
                        category="api_signature",
                        description=f"API route removed/changed in {current_file}",
                        file=current_file,
                    ))

        return breaking

    # ------------------------------------------------------------------
    # PR title and body generation
    # ------------------------------------------------------------------

    def generate_pr_title(self) -> str:
        """Auto-generate a PR title from commits (conventional commit prefix)."""
        commits = self.get_commits()
        branch = self.get_current_branch()

        if not commits:
            return f"Changes from {branch}"

        # Try to extract conventional commit prefix from first/majority of commits
        type_counts: dict[str, int] = {}
        first_type: str = ""
        for c in commits:
            match = re.match(r"^(feat|fix|docs|test|chore|refactor|perf|ci|style|build)\b", c.message)
            if match:
                ctype = match.group(1)
                # Track the earliest commit's type (last in git log order)
                first_type = ctype
                type_counts[ctype] = type_counts.get(ctype, 0) + 1

        # Use most common type, or infer from branch name
        if type_counts:
            max_count = max(type_counts.values())
            # On tie, prefer the earliest commit's type
            candidates = [t for t, c in type_counts.items() if c == max_count]
            dominant_type = first_type if first_type in candidates else candidates[0]
        else:
            # Infer from branch
            if re.search(r"(?i)^(fix|bug|hotfix)/", branch):
                dominant_type = "fix"
            elif re.search(r"(?i)^feat(ure)?/", branch):
                dominant_type = "feat"
            elif re.search(r"(?i)^(docs|doc)/", branch):
                dominant_type = "docs"
            elif re.search(r"(?i)^(test|spec)/", branch):
                dominant_type = "test"
            else:
                dominant_type = "feat"

        # Extract scope from branch name
        scope = ""
        scope_match = re.search(r"/(?:[A-Z]+-\d+-)?(\w+)", branch)
        if scope_match:
            scope = scope_match.group(1).replace("_", "-")
            # Truncate long scopes
            if len(scope) > 20:
                scope = scope[:20]

        # Use first commit message as base, clean it up
        base_msg = commits[0].message
        # Remove conventional prefix if present
        base_msg = re.sub(r"^(feat|fix|docs|test|chore|refactor|perf|ci|style|build)(\([^)]+\))?:\s*", "", base_msg)

        if scope:
            return f"{dominant_type}({scope}): {base_msg}"
        return f"{dominant_type}: {base_msg}"

    def generate_pr_body(self) -> str:
        """Generate a markdown PR body with summary, changes, risk, test plan."""
        commits = self.get_commits()
        files_changed, total_ins, total_del = self.get_total_stats()
        score, factors = self.calculate_risk_score()
        tests = self.get_affected_tests()
        breaking = self.detect_breaking_changes()

        lines: list[str] = []

        # Summary
        lines.append("## Summary")
        for c in commits[:10]:
            lines.append(f"- {c.message}")
        if len(commits) > 10:
            lines.append(f"- ... and {len(commits) - 10} more commits")
        lines.append("")

        # Changes
        lines.append("## Changes")
        lines.append(f"**{files_changed}** files changed, **+{total_ins}** insertions, **-{total_del}** deletions")
        lines.append("")

        # Breaking changes
        if breaking:
            lines.append("## Breaking Changes")
            for bc in breaking:
                lines.append(f"- {bc.description} (`{bc.file}`)")
            lines.append("")

        # Risk
        level = self._risk_level(score)
        lines.append(f"## Risk: {score}/100 ({level})")
        for f in factors:
            icon = {"green": "+", "yellow": "!", "orange": "!!", "red": "!!!"}.get(f.level, "-")
            lines.append(f"- [{icon}] {f.message}")
        lines.append("")

        # Test plan
        lines.append("## Test Plan")
        if tests:
            for t in tests:
                if t.test_modified:
                    lines.append(f"- [x] {t.test_file} (updated)")
                elif t.test_exists:
                    lines.append(f"- [ ] {t.test_file} (exists, not modified)")
                else:
                    test_name = t.test_file or f"test for {t.source_file}"
                    lines.append(f"- [ ] {test_name} (MISSING)")
        else:
            lines.append("- [ ] Manual testing required")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Terminal format
    # ------------------------------------------------------------------

    def format_preview(self) -> str:
        """Format the full PR preview for terminal display."""
        branch = self.get_current_branch()
        title = self.generate_pr_title()
        stats = self.get_diff_stats()
        files_changed, total_ins, total_del = self.get_total_stats()
        commits = self.get_commits()
        score, factors = self.calculate_risk_score()
        tests = self.get_affected_tests()
        body = self.generate_pr_body()

        lines: list[str] = []

        # Header
        header = f"PR Preview: {branch} -> {self.base}"
        lines.append(f"  {header}")
        lines.append("  " + "=" * len(header))
        lines.append("")

        # Title
        lines.append(f"  Title: {title}")
        lines.append("")

        # Diff stats
        lines.append(f"  Diff Stats:")
        lines.append(f"    {files_changed} files changed, +{total_ins}, -{total_del}")

        # Show top files (max 8, tree-style)
        sorted_stats = sorted(stats, key=lambda f: f.insertions + f.deletions, reverse=True)
        show_count = min(len(sorted_stats), 8)
        for i, fstat in enumerate(sorted_stats[:show_count]):
            connector = "|--" if i < show_count - 1 else "`--"
            status_tag = ""
            if fstat.status == "A":
                status_tag = " [NEW]"
            elif fstat.status == "D":
                status_tag = " [DELETED]"
            elif fstat.status == "R":
                status_tag = f" [RENAMED from {fstat.rename_from}]"

            ins_del = ""
            if fstat.insertions and fstat.deletions:
                ins_del = f" (+{fstat.insertions}, -{fstat.deletions})"
            elif fstat.insertions:
                ins_del = f" (+{fstat.insertions})"
            elif fstat.deletions:
                ins_del = f" (-{fstat.deletions})"

            lines.append(f"    {connector} {fstat.path}{ins_del}{status_tag}")

        remaining = len(sorted_stats) - show_count
        if remaining > 0:
            lines.append(f"    ... {remaining} more")
        lines.append("")

        # Commits
        if commits:
            lines.append(f"  Commits ({len(commits)}):")
            for c in commits[:8]:
                lines.append(f"    {c.sha} {c.message}")
            if len(commits) > 8:
                lines.append(f"    ... {len(commits) - 8} more")
            lines.append("")

        # Risk score
        level = self._risk_level(score)
        lines.append(f"  Risk Score: {score}/100 ({level})")
        for f in factors:
            icon = {"green": "[+]", "yellow": "[!]", "orange": "[!!]", "red": "[!!!]"}.get(f.level, "[-]")
            lines.append(f"    {icon} {f.message}")
        lines.append("")

        # Affected tests
        if tests:
            lines.append("  Affected Tests:")
            for t in tests:
                if t.test_modified:
                    lines.append(f"    [ok] {t.test_file} (modified)")
                elif t.test_exists:
                    lines.append(f"    [ok] {t.test_file} (exists)")
                else:
                    test_name = t.test_file or f"test for {t.source_file}"
                    lines.append(f"    [MISSING] {test_name} -- no test for {t.source_file}")
            lines.append("")

        # Suggested PR body
        lines.append("  Suggested PR Body:")
        for body_line in body.splitlines():
            lines.append(f"    {body_line}")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge_base(self) -> str:
        """Find the merge base between HEAD and the base branch."""
        rc, out = self._run_git("merge-base", self.base, "HEAD")
        if rc == 0 and out:
            return out
        # Fallback: try origin/base
        rc, out = self._run_git("merge-base", f"origin/{self.base}", "HEAD")
        return out if rc == 0 else ""

    def _file_exists(self, path: str) -> bool:
        """Check if a file exists in the working tree."""
        return os.path.isfile(os.path.join(self.cwd, path))

    def _is_test_file(self, path: str) -> bool:
        """Check if path looks like a test file."""
        basename = os.path.basename(path).lower()
        return (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename.endswith("_test.go")
            or "test" in basename.lower() and basename.endswith((".java", ".kt"))
            or basename.endswith((".test.js", ".test.ts", ".test.jsx", ".test.tsx"))
            or basename.endswith((".spec.js", ".spec.ts", ".spec.jsx", ".spec.tsx"))
        )

    @staticmethod
    def _is_non_code_file(path: str) -> bool:
        """Check if path is a non-code file (docs, config, assets)."""
        ext = os.path.splitext(path)[1].lower()
        return ext in (
            ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
            ".xml", ".csv", ".svg", ".png", ".jpg", ".gif", ".ico",
            ".lock", ".sum", ".mod",
        )

    def _find_test_path(self, source_path: str) -> Optional[str]:
        """Find the expected test file path for a source file."""
        for pattern, template in TEST_PATTERNS:
            match = re.match(pattern, source_path)
            if match:
                groups = match.groups()
                test_path = template.format(*groups)
                return test_path
        return None

    @staticmethod
    def _risk_level(score: int) -> str:
        """Convert numeric score to label."""
        if score >= 70:
            return "HIGH"
        elif score >= 40:
            return "MEDIUM"
        elif score >= 20:
            return "LOW"
        return "MINIMAL"
