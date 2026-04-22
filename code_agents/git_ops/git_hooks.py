"""Git Hooks Agent — AI-powered pre-commit and pre-push analysis."""

from __future__ import annotations

import logging
import os
import re
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.git_ops.git_hooks")

# ---------------------------------------------------------------------------
# Hook script templates — shell scripts that call back into code-agents CLI
# ---------------------------------------------------------------------------

PRE_COMMIT_SCRIPT = '''#!/bin/sh
# Installed by code-agents — AI-powered pre-commit review
code-agents hook-run pre-commit
exit $?
'''

PRE_PUSH_SCRIPT = '''#!/bin/sh
# Installed by code-agents — AI-powered pre-push impact analysis
code-agents hook-run pre-push
exit $?
'''

_HOOK_SCRIPTS: dict[str, str] = {
    "pre-commit": PRE_COMMIT_SCRIPT,
    "pre-push": PRE_PUSH_SCRIPT,
}

# Marker to identify hooks installed by code-agents
_MARKER = "# Installed by code-agents"

# ---------------------------------------------------------------------------
# Secret detection patterns (reused from tools/pre_push.py)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(
        r'(?:password|secret|token|api_key|apikey|api[-_]?secret)\s*[=:]\s*["\'][^"\']{8,}',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?:AWS|AZURE|GCP|GITHUB|GITLAB|SLACK|STRIPE)[\w_]*(?:KEY|SECRET|TOKEN)\s*[=:]\s*["\'][^"\']+',
        re.IGNORECASE,
    ),
    re.compile(r'-----BEGIN (?:RSA|DSA|EC|PGP|OPENSSH) PRIVATE KEY-----'),
    re.compile(r'ghp_[A-Za-z0-9]{36}'),   # GitHub personal access token
    re.compile(r'sk-[A-Za-z0-9]{48}'),     # OpenAI key
]

# Debug / leftover statement patterns
_DEBUG_PATTERNS = [
    re.compile(r'\bprint\s*\(', re.IGNORECASE),
    re.compile(r'\bconsole\.\w+\s*\('),
    re.compile(r'\bdebugger\b'),
    re.compile(r'\bpdb\.set_trace\s*\('),
    re.compile(r'\bbreakpoint\s*\('),
]

# Security-sensitive patterns
_SECURITY_PATTERNS = [
    (re.compile(r'\beval\s*\('), "eval() usage"),
    (re.compile(r'\bexec\s*\('), "exec() usage"),
    (re.compile(r'shell\s*=\s*True'), "shell=True in subprocess"),
    (re.compile(r'(\+|%|\.format\s*\().*(?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE), "SQL string concatenation"),
]

# TODO / FIXME pattern
_TODO_PATTERN = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE)

# Large file threshold in bytes (1 MB)
_LARGE_FILE_THRESHOLD = 1_048_576


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HookFinding:
    """A single finding from hook analysis."""
    severity: str   # "critical", "warning", "info"
    message: str
    file: str
    line: int = 0


@dataclass
class HookReport:
    """Aggregate report from a hook run."""
    hook_type: str
    findings: list[HookFinding] = field(default_factory=list)
    passed: bool = True
    summary: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")


# ---------------------------------------------------------------------------
# GitHooksManager — install / uninstall / status
# ---------------------------------------------------------------------------

class GitHooksManager:
    """Manage git hook scripts in a repository."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.hooks_dir = os.path.join(repo_path, ".git", "hooks")
        logger.info("GitHooksManager initialized — repo=%s", repo_path)

    def _hook_path(self, name: str) -> str:
        return os.path.join(self.hooks_dir, name)

    def install(self, hooks: list[str] | None = None) -> list[str]:
        """Install hook scripts into .git/hooks/.

        Backs up existing hooks as ``<name>.backup`` before overwriting.
        Returns list of installed hook names.
        """
        if hooks is None:
            hooks = ["pre-commit", "pre-push"]

        if not os.path.isdir(self.hooks_dir):
            logger.error("Not a git repo — missing %s", self.hooks_dir)
            return []

        installed: list[str] = []
        for name in hooks:
            script = _HOOK_SCRIPTS.get(name)
            if script is None:
                logger.warning("Unknown hook type: %s", name)
                continue

            hook_path = self._hook_path(name)
            backup_path = hook_path + ".backup"

            # Backup existing hook (only if it's not ours)
            if os.path.exists(hook_path):
                try:
                    with open(hook_path, "r") as fh:
                        existing = fh.read()
                    if _MARKER not in existing:
                        os.rename(hook_path, backup_path)
                        logger.info("Backed up existing %s -> %s.backup", name, name)
                except OSError as exc:
                    logger.warning("Could not backup %s: %s", name, exc)

            # Write hook script
            with open(hook_path, "w") as fh:
                fh.write(script)
            os.chmod(hook_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            installed.append(name)
            logger.info("Installed %s hook at %s", name, hook_path)

        return installed

    def uninstall(self, hooks: list[str] | None = None) -> list[str]:
        """Remove installed hooks and restore backups.

        Returns list of uninstalled hook names.
        """
        if hooks is None:
            hooks = ["pre-commit", "pre-push"]

        removed: list[str] = []
        for name in hooks:
            hook_path = self._hook_path(name)
            backup_path = hook_path + ".backup"

            if not os.path.exists(hook_path):
                continue

            # Only remove if it's ours
            try:
                with open(hook_path, "r") as fh:
                    content = fh.read()
                if _MARKER not in content:
                    logger.info("Skipping %s — not installed by code-agents", name)
                    continue
            except OSError:
                continue

            os.remove(hook_path)
            logger.info("Removed %s hook", name)

            # Restore backup if it exists
            if os.path.exists(backup_path):
                os.rename(backup_path, hook_path)
                logger.info("Restored %s from backup", name)

            removed.append(name)

        return removed

    def status(self) -> dict[str, bool]:
        """Return which hooks are installed by code-agents."""
        result: dict[str, bool] = {}
        for name in ("pre-commit", "pre-push"):
            hook_path = self._hook_path(name)
            installed = False
            if os.path.exists(hook_path):
                try:
                    with open(hook_path, "r") as fh:
                        installed = _MARKER in fh.read()
                except OSError:
                    pass
            result[name] = installed
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        logger.debug("git %s returned %d: %s", args, result.returncode, result.stderr.strip())
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug("git %s failed: %s", args, exc)
        return ""


def _parse_diff_files(diff: str) -> list[str]:
    """Extract file paths from unified diff output."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


# ---------------------------------------------------------------------------
# PreCommitAnalyzer
# ---------------------------------------------------------------------------

class PreCommitAnalyzer:
    """Analyze staged changes before commit."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        logger.info("PreCommitAnalyzer initialized — repo=%s", repo_path)

    def analyze(self) -> HookReport:
        """Run all pre-commit checks and return a report."""
        report = HookReport(hook_type="pre-commit")

        # 1. Get staged diff
        diff = _run_git(["diff", "--cached"], self.repo_path)
        if not diff:
            report.summary = "No staged changes to analyze."
            return report

        staged_files = _parse_diff_files(diff)

        # 2. Check for secrets
        self._check_secrets(diff, report)

        # 3. Check for large staged files
        self._check_large_files(staged_files, report)

        # 4. Check for debug statements
        self._check_debug_statements(diff, report)

        # 5. Check for TODO/FIXME in new code
        self._check_todos(diff, report)

        # 6. Basic security checks
        self._check_security(diff, report)

        # Determine pass/fail
        report.passed = report.critical_count == 0
        total = len(report.findings)
        if total == 0:
            report.summary = "All checks passed — no issues found."
        else:
            parts: list[str] = []
            if report.critical_count:
                parts.append(f"{report.critical_count} critical")
            if report.warning_count:
                parts.append(f"{report.warning_count} warning(s)")
            if report.info_count:
                parts.append(f"{report.info_count} info")
            report.summary = f"{total} finding(s): {', '.join(parts)}."

        return report

    def _check_secrets(self, diff: str, report: HookReport) -> None:
        current_file = ""
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    report.findings.append(HookFinding(
                        severity="critical",
                        message=f"Potential secret: {line[:60].strip()}",
                        file=current_file,
                        line=i,
                    ))
                    break

    def _check_large_files(self, files: list[str], report: HookReport) -> None:
        for fname in files:
            fpath = os.path.join(self.repo_path, fname)
            try:
                size = os.path.getsize(fpath)
                if size > _LARGE_FILE_THRESHOLD:
                    size_mb = size / 1_048_576
                    report.findings.append(HookFinding(
                        severity="warning",
                        message=f"Large file ({size_mb:.1f} MB)",
                        file=fname,
                    ))
            except OSError:
                pass

    def _check_debug_statements(self, diff: str, report: HookReport) -> None:
        current_file = ""
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _DEBUG_PATTERNS:
                if pattern.search(line):
                    report.findings.append(HookFinding(
                        severity="warning",
                        message=f"Debug statement: {line[:60].strip()}",
                        file=current_file,
                        line=i,
                    ))
                    break

    def _check_todos(self, diff: str, report: HookReport) -> None:
        current_file = ""
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            if _TODO_PATTERN.search(line):
                report.findings.append(HookFinding(
                    severity="info",
                    message=f"TODO/FIXME added: {line[:60].strip()}",
                    file=current_file,
                    line=i,
                ))

    def _check_security(self, diff: str, report: HookReport) -> None:
        current_file = ""
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern, desc in _SECURITY_PATTERNS:
                if pattern.search(line):
                    report.findings.append(HookFinding(
                        severity="warning",
                        message=f"Security: {desc}",
                        file=current_file,
                        line=i,
                    ))
                    break


# ---------------------------------------------------------------------------
# PrePushAnalyzer
# ---------------------------------------------------------------------------

class PrePushAnalyzer:
    """Analyze commits about to be pushed."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        logger.info("PrePushAnalyzer initialized — repo=%s", repo_path)

    def analyze(self) -> HookReport:
        """Run all pre-push checks and return a report."""
        report = HookReport(hook_type="pre-push")

        # 1. Get commits being pushed
        commit_log = _run_git(["log", "--oneline", "@{u}..HEAD"], self.repo_path)
        if not commit_log:
            # Fallback: compare against main
            commit_log = _run_git(["log", "--oneline", "main..HEAD"], self.repo_path)

        commits = [l for l in commit_log.strip().splitlines() if l.strip()] if commit_log else []

        # 2. Get all changed files
        diff = _run_git(["diff", "@{u}..HEAD"], self.repo_path)
        if not diff:
            diff = _run_git(["diff", "main..HEAD"], self.repo_path)

        changed_files = _parse_diff_files(diff) if diff else []

        # 3. Check for secrets in committed code
        self._check_secrets(diff or "", report)

        # 4. Blast radius estimate
        self._check_blast_radius(commits, changed_files, report)

        # 5. Check if tests exist for changed files
        self._check_test_coverage(changed_files, report)

        # Determine pass/fail
        report.passed = report.critical_count == 0
        total = len(report.findings)
        if total == 0:
            report.summary = f"All checks passed — {len(commits)} commit(s), {len(changed_files)} file(s)."
        else:
            parts: list[str] = []
            if report.critical_count:
                parts.append(f"{report.critical_count} critical")
            if report.warning_count:
                parts.append(f"{report.warning_count} warning(s)")
            if report.info_count:
                parts.append(f"{report.info_count} info")
            report.summary = f"{total} finding(s): {', '.join(parts)}."

        return report

    def _check_secrets(self, diff: str, report: HookReport) -> None:
        if not diff:
            return
        current_file = ""
        for i, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    report.findings.append(HookFinding(
                        severity="critical",
                        message=f"Secret in committed code: {line[:60].strip()}",
                        file=current_file,
                        line=i,
                    ))
                    break

    def _check_blast_radius(self, commits: list[str], files: list[str], report: HookReport) -> None:
        file_count = len(files)
        commit_count = len(commits)

        if file_count > 50:
            report.findings.append(HookFinding(
                severity="warning",
                message=f"High blast radius: {file_count} files changed across {commit_count} commit(s)",
                file="(push)",
            ))
        elif file_count > 20:
            report.findings.append(HookFinding(
                severity="info",
                message=f"Moderate blast radius: {file_count} files changed across {commit_count} commit(s)",
                file="(push)",
            ))

    def _check_test_coverage(self, files: list[str], report: HookReport) -> None:
        missing_tests: list[str] = []
        for fname in files:
            # Only check source files
            if not any(fname.endswith(ext) for ext in (".py", ".js", ".ts", ".java", ".go")):
                continue
            # Skip test files themselves
            base = os.path.basename(fname)
            if base.startswith("test_") or base.endswith("_test.py") or ".test." in base or ".spec." in base:
                continue
            # Check if a corresponding test file exists
            stem = Path(fname).stem
            test_candidates = [
                f"tests/test_{stem}.py",
                f"test/test_{stem}.py",
                f"tests/{stem}_test.py",
                f"{os.path.dirname(fname)}/test_{base}",
                f"{os.path.dirname(fname)}/{stem}.test.js",
                f"{os.path.dirname(fname)}/{stem}.test.ts",
                f"{os.path.dirname(fname)}/{stem}.spec.js",
                f"{os.path.dirname(fname)}/{stem}.spec.ts",
            ]
            has_test = any(
                os.path.exists(os.path.join(self.repo_path, t))
                for t in test_candidates
            )
            if not has_test:
                missing_tests.append(fname)

        if missing_tests:
            for f in missing_tests[:10]:
                report.findings.append(HookFinding(
                    severity="info",
                    message="No corresponding test file found",
                    file=f,
                ))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_hook_report(report: HookReport) -> str:
    """Render a HookReport as colored terminal output."""
    lines: list[str] = []

    title = f" {report.hook_type.replace('-', ' ').title()} Review "
    width = max(50, len(title) + 4)

    lines.append("")
    lines.append(f"  \033[1m{'=' * width}\033[0m")
    lines.append(f"  \033[1m{title:^{width}}\033[0m")
    lines.append(f"  \033[1m{'=' * width}\033[0m")
    lines.append("")

    if not report.findings:
        lines.append("  \033[32m  All checks passed — no issues found.\033[0m")
    else:
        for finding in report.findings:
            if finding.severity == "critical":
                icon = "\033[31m  CRITICAL\033[0m"
            elif finding.severity == "warning":
                icon = "\033[33m  WARNING \033[0m"
            else:
                icon = "\033[36m  INFO    \033[0m"

            loc = finding.file
            if finding.line:
                loc = f"{finding.file}:{finding.line}"
            lines.append(f"  {icon}: {finding.message}")
            lines.append(f"  \033[2m          {loc}\033[0m")

    lines.append("")

    if report.passed:
        lines.append(f"  \033[32mResult: PASSED\033[0m — {report.summary}")
    else:
        lines.append(f"  \033[31mResult: BLOCKED\033[0m — {report.summary}")

    lines.append(f"  \033[1m{'=' * width}\033[0m")
    lines.append("")

    return "\n".join(lines)
