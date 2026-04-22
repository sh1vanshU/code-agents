"""Pre-Push Checklist — checks before git push + hook installer."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.tools.pre_push")

_HOOK_SCRIPT = """#!/bin/sh
# Pre-push hook installed by code-agents
# Runs pre-push checks before allowing push

code-agents pre-push-check
exit $?
"""

# Patterns for secret detection
_SECRET_PATTERNS = [
    re.compile(r'(?:password|secret|token|api_key|apikey|api[-_]?secret)\s*[=:]\s*["\'][^"\']{8,}', re.IGNORECASE),
    re.compile(r'(?:AWS|AZURE|GCP|GITHUB|GITLAB|SLACK|STRIPE)[\w_]*(?:KEY|SECRET|TOKEN)\s*[=:]\s*["\'][^"\']+', re.IGNORECASE),
    re.compile(r'-----BEGIN (?:RSA|DSA|EC|PGP|OPENSSH) PRIVATE KEY-----'),
    re.compile(r'ghp_[A-Za-z0-9]{36}'),  # GitHub personal access token
    re.compile(r'sk-[A-Za-z0-9]{48}'),   # OpenAI key
]


@dataclass
class CheckResult:
    """Result of a single pre-push check."""

    name: str
    passed: bool
    message: str = ""
    details: list[str] = field(default_factory=list)


@dataclass
class PrePushReport:
    """Full pre-push check report."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c.passed)
        total = len(self.checks)
        return f"{passed}/{total} checks passed"


class PrePushChecklist:
    """Runs pre-push checks and installs git hook."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.report = PrePushReport()
        logger.info("PrePushChecklist initialized — cwd=%s", cwd)

    def run_checks(self) -> PrePushReport:
        """Run all pre-push checks."""
        checks = [
            ("Tests Pass", self._check_tests),
            ("No Secrets in Diff", self._check_secrets),
            ("No TODOs in New Code", self._check_todos),
            ("Lint Clean", self._check_lint),
            ("Markdown Size Limit", self._check_markdown_size),
        ]
        for name, fn in checks:
            try:
                fn()
            except Exception as e:
                self.report.checks.append(CheckResult(
                    name=name, passed=False, message=str(e),
                ))
        return self.report

    def _get_diff(self) -> str:
        """Get diff of staged + unstaged changes vs main."""
        try:
            result = subprocess.run(
                ["git", "diff", "main...HEAD"],
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _check_tests(self):
        test_cmd = os.getenv("CODE_AGENTS_TEST_CMD", "")
        if not test_cmd:
            if os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
                test_cmd = "pytest --tb=short -q"
            elif os.path.exists(os.path.join(self.cwd, "pom.xml")):
                test_cmd = "mvn test -q"
            elif os.path.exists(os.path.join(self.cwd, "package.json")):
                test_cmd = "npm test"
            else:
                self.report.checks.append(CheckResult(
                    name="Tests Pass", passed=True,
                    message="No test command detected — skipped",
                ))
                return

        try:
            result = subprocess.run(
                test_cmd.split(),
                cwd=self.cwd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self.report.checks.append(CheckResult(
                    name="Tests Pass", passed=True, message="All tests passed",
                ))
            else:
                out = result.stdout.strip().splitlines()
                self.report.checks.append(CheckResult(
                    name="Tests Pass", passed=False,
                    message="Tests failed",
                    details=out[-5:] if out else [],
                ))
        except subprocess.TimeoutExpired:
            self.report.checks.append(CheckResult(
                name="Tests Pass", passed=False, message="Test run timed out",
            ))

    def _check_secrets(self):
        diff = self._get_diff()
        if not diff:
            self.report.checks.append(CheckResult(
                name="No Secrets in Diff", passed=True,
                message="No diff to check",
            ))
            return

        findings: list[str] = []
        for i, line in enumerate(diff.splitlines(), 1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"Line {i}: {line[:80].strip()}")
                    break

        if findings:
            self.report.checks.append(CheckResult(
                name="No Secrets in Diff", passed=False,
                message=f"Found {len(findings)} potential secrets",
                details=findings[:10],
            ))
        else:
            self.report.checks.append(CheckResult(
                name="No Secrets in Diff", passed=True,
                message="No secrets detected in diff",
            ))

    def _check_todos(self):
        diff = self._get_diff()
        if not diff:
            self.report.checks.append(CheckResult(
                name="No TODOs in New Code", passed=True,
                message="No diff to check",
            ))
            return

        todos: list[str] = []
        todo_pattern = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE)
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                if todo_pattern.search(line):
                    todos.append(line[:80].strip())

        if todos:
            self.report.checks.append(CheckResult(
                name="No TODOs in New Code", passed=False,
                message=f"Found {len(todos)} TODO/FIXME in new code",
                details=todos[:10],
            ))
        else:
            self.report.checks.append(CheckResult(
                name="No TODOs in New Code", passed=True,
                message="No TODOs in new code",
            ))

    def _check_lint(self):
        # Try common linters
        lint_cmds = []
        if os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
            lint_cmds.append(("ruff check .", "ruff"))
            lint_cmds.append(("flake8 --max-line-length=120 .", "flake8"))
        elif os.path.exists(os.path.join(self.cwd, "package.json")):
            lint_cmds.append(("npx eslint .", "eslint"))

        if not lint_cmds:
            self.report.checks.append(CheckResult(
                name="Lint Clean", passed=True,
                message="No linter detected — skipped",
            ))
            return

        for cmd, name in lint_cmds:
            try:
                result = subprocess.run(
                    cmd.split(),
                    cwd=self.cwd, capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    self.report.checks.append(CheckResult(
                        name="Lint Clean", passed=True,
                        message=f"{name}: clean",
                    ))
                    return
                else:
                    # Linter found issues
                    out = result.stdout.strip().splitlines()
                    self.report.checks.append(CheckResult(
                        name="Lint Clean", passed=False,
                        message=f"{name}: issues found",
                        details=out[-5:] if out else [],
                    ))
                    return
            except FileNotFoundError:
                continue  # try next linter
            except subprocess.TimeoutExpired:
                self.report.checks.append(CheckResult(
                    name="Lint Clean", passed=False,
                    message=f"{name}: timed out",
                ))
                return

        self.report.checks.append(CheckResult(
            name="Lint Clean", passed=True,
            message="No linter available — skipped",
        ))

    def _check_markdown_size(self):
        """Check that no markdown file exceeds the line limit."""
        max_lines = int(os.getenv("CODE_AGENTS_MD_MAX_LINES", "300"))
        oversized: list[str] = []

        for root, dirs, files in os.walk(self.cwd):
            # Skip hidden dirs, node_modules, .venv, etc.
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__")]
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="ignore") as f:
                        line_count = sum(1 for _ in f)
                    if line_count > max_lines:
                        rel = os.path.relpath(fpath, self.cwd)
                        oversized.append(f"{rel} ({line_count} lines, limit {max_lines})")
                except OSError:
                    continue

        if oversized:
            self.report.checks.append(CheckResult(
                name="Markdown Size Limit",
                passed=False,
                message=f"{len(oversized)} markdown file(s) exceed {max_lines} lines",
                details=oversized[:10],
            ))
        else:
            self.report.checks.append(CheckResult(
                name="Markdown Size Limit",
                passed=True,
                message=f"All markdown files under {max_lines} lines",
            ))

    @staticmethod
    def install_hook(cwd: str) -> str:
        """Install pre-push git hook."""
        hooks_dir = os.path.join(cwd, ".git", "hooks")
        if not os.path.isdir(hooks_dir):
            return "Not a git repository (no .git/hooks directory)"

        hook_path = os.path.join(hooks_dir, "pre-push")
        with open(hook_path, "w") as f:
            f.write(_HOOK_SCRIPT)
        os.chmod(hook_path, 0o755)
        return f"Pre-push hook installed at {hook_path}"


def format_pre_push_report(report: PrePushReport) -> str:
    """Format pre-push report for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Pre-Push Checklist")
    lines.append("  " + "=" * 50)
    lines.append("")

    for check in report.checks:
        icon = "[OK]" if check.passed else "[FAIL]"
        lines.append(f"  {icon} {check.name}: {check.message}")
        for detail in check.details[:5]:
            lines.append(f"       {detail}")

    lines.append("")
    lines.append(f"  Result: {report.summary}")
    if report.all_passed:
        lines.append("  Ready to push!")
    else:
        lines.append("  Fix issues before pushing.")

    lines.append("")
    return "\n".join(lines)
