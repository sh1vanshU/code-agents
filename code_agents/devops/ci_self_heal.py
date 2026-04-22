"""CI Pipeline Self-Healing — autonomous red-to-green loop.

On CI failure: read logs -> diagnose -> apply fix -> re-trigger.
Supports Jenkins, GitHub Actions, and generic log sources.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.ci_self_heal")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Diagnosis:
    """Result of analyzing CI failure logs."""

    category: str  # "lint", "test", "compile", "dependency", "config", "timeout", "unknown"
    root_cause: str
    affected_files: list[str]
    suggested_fix: str
    confidence: float  # 0-1


@dataclass
class HealAttempt:
    """Record of a single heal attempt."""

    attempt: int
    diagnosis: Diagnosis
    fix_applied: str
    retrigger_url: str = ""
    success: bool = False


@dataclass
class HealResult:
    """Overall result of the self-healing process."""

    build_id: str
    original_error: str
    attempts: list[HealAttempt] = field(default_factory=list)
    healed: bool = False
    total_attempts: int = 0
    final_status: str = "failed"


# ---------------------------------------------------------------------------
# Diagnostic patterns — order matters (first match wins)
# ---------------------------------------------------------------------------

_LINT_PATTERNS = [
    re.compile(r"SyntaxError:\s*(.+)", re.IGNORECASE),
    re.compile(r"IndentationError:\s*(.+)", re.IGNORECASE),
    re.compile(r"E\d{3}\s+.+", re.IGNORECASE),  # flake8 / pycodestyle
    re.compile(r"error:\s*Parsing error", re.IGNORECASE),  # eslint
    re.compile(r"black would reformat", re.IGNORECASE),
    re.compile(r"prettier.*--check.*failed", re.IGNORECASE),
]

_TEST_PATTERNS = [
    re.compile(r"FAILED\s+(\S+::\S+)", re.IGNORECASE),
    re.compile(r"AssertionError", re.IGNORECASE),
    re.compile(r"AssertionError", re.IGNORECASE),
    re.compile(r"AssertError", re.IGNORECASE),
    re.compile(r"assert\s+.+==\s+.+", re.IGNORECASE),
    re.compile(r"test_\S+\s+FAILED", re.IGNORECASE),
    re.compile(r"pytest.*(\d+)\s+failed", re.IGNORECASE),
    re.compile(r"FAIL:\s*test_", re.IGNORECASE),
    re.compile(r"jest.*Tests:\s*\d+\s+failed", re.IGNORECASE),
]

_DEPENDENCY_PATTERNS = [
    re.compile(r"ModuleNotFoundError:\s*No module named ['\"](\S+)['\"]", re.IGNORECASE),
    re.compile(r"ImportError:\s*cannot import name ['\"](\S+)['\"]", re.IGNORECASE),
    re.compile(r"ImportError:\s*(.+)", re.IGNORECASE),
    re.compile(r"ModuleNotFoundError:\s*(.+)", re.IGNORECASE),
    re.compile(r"Cannot find module ['\"](\S+)['\"]", re.IGNORECASE),
    re.compile(r"ERROR:\s*Could not find a version that satisfies", re.IGNORECASE),
    re.compile(r"npm ERR! 404\s+Not Found", re.IGNORECASE),
    re.compile(r"No matching distribution found", re.IGNORECASE),
]

_COMPILE_PATTERNS = [
    re.compile(r"CompileError", re.IGNORECASE),
    re.compile(r"cannot find symbol", re.IGNORECASE),
    re.compile(r"error:\s*expected .+ before", re.IGNORECASE),
    re.compile(r"error TS\d+:", re.IGNORECASE),  # TypeScript
    re.compile(r"compilation failed", re.IGNORECASE),
    re.compile(r"Build FAILED", re.IGNORECASE),
]

_CONFIG_PATTERNS = [
    re.compile(r"ConnectionRefused", re.IGNORECASE),
    re.compile(r"Connection refused", re.IGNORECASE),
    re.compile(r"ECONNREFUSED", re.IGNORECASE),
    re.compile(r"Could not resolve host", re.IGNORECASE),
    re.compile(r"Permission denied", re.IGNORECASE),
    re.compile(r"EACCES", re.IGNORECASE),
]

_TIMEOUT_PATTERNS = [
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"timed?\s*out", re.IGNORECASE),
    re.compile(r"deadline exceeded", re.IGNORECASE),
    re.compile(r"Build timed out", re.IGNORECASE),
]

# Map: file path extraction from tracebacks
_FILE_PATTERN = re.compile(r'File "([^"]+)",\s*line\s*(\d+)')
_JS_FILE_PATTERN = re.compile(r"at\s+\S+\s+\(([^:]+):(\d+):\d+\)")
_TS_FILE_PATTERN = re.compile(r"(\S+\.\w{1,5})\((\d+),\d+\)")
_GENERIC_FILE_PATTERN = re.compile(r"(\S+\.\w{1,5}):(\d+)")


# ---------------------------------------------------------------------------
# CISelfHealer
# ---------------------------------------------------------------------------


class CISelfHealer:
    """Autonomous CI pipeline self-healing engine.

    Reads failure logs, diagnoses root cause, applies fix, re-triggers build.
    Repeats up to *max_attempts* times or until the build passes.
    """

    def __init__(self, cwd: str, max_attempts: int = 3, dry_run: bool = False):
        self.cwd = cwd
        self.max_attempts = max_attempts
        self.dry_run = dry_run
        logger.info(
            "CISelfHealer initialized: cwd=%s, max_attempts=%d, dry_run=%s",
            cwd,
            max_attempts,
            dry_run,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(
        self,
        build_url: str = "",
        build_id: str = "",
        source: str = "jenkins",
        log_text: str = "",
    ) -> HealResult:
        """Main self-healing loop: diagnose -> fix -> retrigger, up to max_attempts.

        Parameters
        ----------
        build_url : str
            Optional URL to the build (used for display / re-trigger).
        build_id : str
            Build identifier (e.g. Jenkins build number, GH Actions run id).
        source : str
            CI system — "jenkins", "github", or "generic".
        log_text : str
            If provided, use this text instead of fetching logs.

        Returns
        -------
        HealResult
            Summary of all attempts.
        """
        result = HealResult(build_id=build_id or "unknown", original_error="")
        logger.info("Starting self-heal loop for build %s (source=%s)", build_id, source)

        for attempt_num in range(1, self.max_attempts + 1):
            logger.info("=== Attempt %d/%d ===", attempt_num, self.max_attempts)

            # 1. Fetch logs
            if attempt_num == 1 and log_text:
                logs = log_text
            else:
                logs = self._fetch_logs(build_id, source, build_url)
            if not logs:
                logger.warning("No logs available — cannot diagnose")
                result.final_status = "no_logs"
                break

            if attempt_num == 1:
                # Capture a snippet of the original error for the result
                result.original_error = _extract_error_snippet(logs)

            # 2. Diagnose
            diagnosis = self._diagnose(logs)
            logger.info(
                "Diagnosis: category=%s, confidence=%.2f, root_cause=%s",
                diagnosis.category,
                diagnosis.confidence,
                diagnosis.root_cause,
            )

            if diagnosis.category == "unknown":
                logger.warning("Cannot diagnose failure — stopping")
                result.attempts.append(
                    HealAttempt(
                        attempt=attempt_num,
                        diagnosis=diagnosis,
                        fix_applied="none — unrecognized failure",
                    )
                )
                result.final_status = "undiagnosable"
                break

            # 3. Apply fix
            fix_description = self._apply_fix(diagnosis)
            if not fix_description:
                logger.warning("Could not apply fix for %s — stopping", diagnosis.category)
                result.attempts.append(
                    HealAttempt(
                        attempt=attempt_num,
                        diagnosis=diagnosis,
                        fix_applied="none — fix not applicable",
                    )
                )
                result.final_status = "unfixable"
                break

            # 4. Commit
            if not self.dry_run:
                self._commit_fix(diagnosis)

            # 5. Re-trigger
            retrigger_url = ""
            if not self.dry_run:
                retrigger_url = self._retrigger(source, build_url, build_id)

            attempt = HealAttempt(
                attempt=attempt_num,
                diagnosis=diagnosis,
                fix_applied=fix_description,
                retrigger_url=retrigger_url,
            )

            # 6. Wait for result (skip in dry-run)
            if self.dry_run:
                logger.info("[dry-run] Skipping re-trigger and wait")
                attempt.success = False
                result.attempts.append(attempt)
                result.final_status = "dry_run"
                break

            success = self._wait_for_result(retrigger_url, source, build_id)
            attempt.success = success
            result.attempts.append(attempt)

            if success:
                logger.info("Build healed after %d attempt(s)", attempt_num)
                result.healed = True
                result.final_status = "healed"
                break
            else:
                logger.info("Build still failing after attempt %d", attempt_num)

        result.total_attempts = len(result.attempts)
        if not result.healed and result.final_status == "failed":
            result.final_status = "max_attempts_reached"
        logger.info(
            "Self-heal complete: healed=%s, attempts=%d, status=%s",
            result.healed,
            result.total_attempts,
            result.final_status,
        )
        return result

    # ------------------------------------------------------------------
    # Log fetching
    # ------------------------------------------------------------------

    def _fetch_logs(self, build_id: str, source: str, build_url: str = "") -> str:
        """Fetch CI build logs from the given source."""
        logger.debug("Fetching logs: source=%s, build_id=%s", source, build_id)

        if source == "jenkins":
            return self._fetch_jenkins_logs(build_id, build_url)
        elif source == "github":
            return self._fetch_github_logs(build_id)
        elif source == "generic":
            return self._fetch_generic_logs(build_id)
        else:
            logger.warning("Unknown source %s, trying generic", source)
            return self._fetch_generic_logs(build_id)

    def _fetch_jenkins_logs(self, build_id: str, build_url: str = "") -> str:
        """Fetch Jenkins build console text."""
        url = build_url.rstrip("/") if build_url else ""
        if not url:
            jenkins_url = os.environ.get("JENKINS_URL", "")
            jenkins_job = os.environ.get("JENKINS_JOB", "")
            if jenkins_url and jenkins_job:
                url = f"{jenkins_url}/job/{jenkins_job}/{build_id}"
            else:
                logger.warning("No Jenkins URL or build URL provided")
                return ""

        console_url = f"{url}/consoleText"
        try:
            out = subprocess.run(
                ["curl", "-sS", "--max-time", "30", console_url],
                capture_output=True,
                text=True,
                timeout=45,
                cwd=self.cwd,
            )
            if out.returncode == 0 and out.stdout:
                logger.debug("Fetched %d bytes of Jenkins logs", len(out.stdout))
                return out.stdout
            logger.warning("curl failed for Jenkins logs: %s", out.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("Failed to fetch Jenkins logs: %s", exc)
        return ""

    def _fetch_github_logs(self, build_id: str) -> str:
        """Fetch GitHub Actions run logs via gh CLI."""
        if not build_id:
            logger.warning("No build_id for GitHub Actions")
            return ""
        try:
            out = subprocess.run(
                ["gh", "run", "view", build_id, "--log-failed"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.cwd,
            )
            if out.returncode == 0 and out.stdout:
                logger.debug("Fetched %d bytes of GH Actions logs", len(out.stdout))
                return out.stdout
            # Fallback to full log
            out2 = subprocess.run(
                ["gh", "run", "view", build_id, "--log"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.cwd,
            )
            if out2.returncode == 0:
                return out2.stdout
            logger.warning("gh run view failed: %s", out.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("Failed to fetch GH Actions logs: %s", exc)
        return ""

    def _fetch_generic_logs(self, build_id: str) -> str:
        """Read logs from a file path (build_id treated as path) or stdin."""
        if build_id and Path(build_id).is_file():
            try:
                return Path(build_id).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Failed to read log file %s: %s", build_id, exc)
        return ""

    # ------------------------------------------------------------------
    # Diagnosis engine
    # ------------------------------------------------------------------

    def _diagnose(self, logs: str) -> Diagnosis:
        """Analyze logs and produce a diagnosis."""
        affected = _extract_affected_files(logs)

        # Check categories in order of specificity
        for patterns, category in [
            (_LINT_PATTERNS, "lint"),
            (_DEPENDENCY_PATTERNS, "dependency"),
            (_COMPILE_PATTERNS, "compile"),
            (_TEST_PATTERNS, "test"),
            (_TIMEOUT_PATTERNS, "timeout"),
            (_CONFIG_PATTERNS, "config"),
        ]:
            for pat in patterns:
                m = pat.search(logs)
                if m:
                    root_cause = m.group(0).strip()[:200]
                    fix = _suggest_fix(category, root_cause, affected)
                    confidence = _compute_confidence(category, logs, m)
                    return Diagnosis(
                        category=category,
                        root_cause=root_cause,
                        affected_files=affected,
                        suggested_fix=fix,
                        confidence=confidence,
                    )

        return Diagnosis(
            category="unknown",
            root_cause="Could not determine failure cause from logs",
            affected_files=affected,
            suggested_fix="Manual investigation required",
            confidence=0.0,
        )

    # ------------------------------------------------------------------
    # Fix application
    # ------------------------------------------------------------------

    def _apply_fix(self, diagnosis: Diagnosis) -> str:
        """Apply an automated fix based on the diagnosis. Returns description or empty string."""
        category = diagnosis.category
        logger.info("Applying fix for category=%s", category)

        if self.dry_run:
            desc = f"[dry-run] Would apply {category} fix: {diagnosis.suggested_fix}"
            logger.info(desc)
            return desc

        if category == "lint":
            return self._fix_lint(diagnosis)
        elif category == "dependency":
            return self._fix_dependency(diagnosis)
        elif category == "test":
            return self._fix_test(diagnosis)
        elif category == "compile":
            return self._fix_compile(diagnosis)
        elif category in ("config", "timeout"):
            logger.info("Category %s requires manual intervention", category)
            return ""
        return ""

    def _fix_lint(self, diagnosis: Diagnosis) -> str:
        """Run auto-formatters to fix lint issues."""
        fixed = []
        # Try black (Python)
        if self._run_tool(["python", "-m", "black", "."]):
            fixed.append("black")
        # Try isort (Python imports)
        if self._run_tool(["python", "-m", "isort", "."]):
            fixed.append("isort")
        # Try prettier (JS/TS)
        if Path(self.cwd, "package.json").exists():
            if self._run_tool(["npx", "prettier", "--write", "."]):
                fixed.append("prettier")
        # Try gofmt (Go)
        if any(Path(self.cwd).glob("*.go")) or any(Path(self.cwd).glob("**/*.go")):
            if self._run_tool(["gofmt", "-w", "."]):
                fixed.append("gofmt")

        if fixed:
            return f"Auto-formatted with {', '.join(fixed)}"
        return "Attempted auto-format but no formatters succeeded"

    def _fix_dependency(self, diagnosis: Diagnosis) -> str:
        """Install missing dependencies."""
        root = diagnosis.root_cause
        # Extract module name from "No module named 'foo'" or "Cannot find module 'foo'"
        mod_match = re.search(r"named\s+['\"]([^'\"]+)['\"]", root)
        if not mod_match:
            mod_match = re.search(r"module\s+['\"]([^'\"]+)['\"]", root)

        module_name = mod_match.group(1) if mod_match else ""

        if not module_name:
            logger.warning("Could not extract module name from: %s", root)
            return ""

        # Determine package manager
        if Path(self.cwd, "pyproject.toml").exists() or Path(self.cwd, "requirements.txt").exists():
            # Python project
            req_file = Path(self.cwd, "requirements.txt")
            if req_file.exists():
                try:
                    content = req_file.read_text()
                    if module_name not in content:
                        with open(req_file, "a") as f:
                            f.write(f"\n{module_name}\n")
                        self._run_tool(["pip", "install", module_name])
                        return f"Added {module_name} to requirements.txt and installed"
                except OSError:
                    pass
            # Fallback: just install
            if self._run_tool(["pip", "install", module_name]):
                return f"Installed {module_name} via pip"

        elif Path(self.cwd, "package.json").exists():
            # Node project
            if self._run_tool(["npm", "install", module_name]):
                return f"Installed {module_name} via npm"

        return ""

    def _fix_test(self, diagnosis: Diagnosis) -> str:
        """Attempt minimal test fix — re-run tests to identify flaky failures."""
        # For test failures, we can't auto-fix the logic, but we can detect flaky tests
        # by running the failing test again
        if not diagnosis.affected_files:
            return ""

        test_files = [f for f in diagnosis.affected_files if "test" in f.lower()]
        if not test_files:
            return ""

        # Try running the specific test file to check if it's flaky
        for tf in test_files[:3]:  # limit to 3 files
            if Path(self.cwd, tf).exists():
                result = subprocess.run(
                    ["python", "-m", "pytest", tf, "-x", "--tb=short"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=self.cwd,
                )
                if result.returncode == 0:
                    return f"Test {tf} passed on re-run (likely flaky)"

        return ""

    def _fix_compile(self, diagnosis: Diagnosis) -> str:
        """Attempt to fix compile errors — limited to obvious syntax issues."""
        if not diagnosis.affected_files:
            return ""

        # For Python syntax errors, try to fix with autopep8 or black on specific files
        fixed_files = []
        for fpath in diagnosis.affected_files[:5]:
            full = Path(self.cwd, fpath)
            if full.exists() and full.suffix == ".py":
                if self._run_tool(["python", "-m", "black", str(full)]):
                    fixed_files.append(fpath)

        if fixed_files:
            return f"Auto-formatted {len(fixed_files)} file(s) with black"
        return ""

    def _run_tool(self, cmd: list[str]) -> bool:
        """Run an external tool, return True on success."""
        try:
            logger.debug("Running: %s", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.cwd,
            )
            if result.returncode == 0:
                logger.debug("Tool succeeded: %s", cmd[0])
                return True
            logger.debug("Tool failed (%d): %s", result.returncode, result.stderr[:200])
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("Tool unavailable or timed out: %s — %s", cmd[0], exc)
        return False

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _commit_fix(self, diagnosis: Diagnosis) -> str:
        """Commit the fix with a descriptive message."""
        msg = f"fix(ci): auto-heal {diagnosis.category} — {diagnosis.root_cause[:80]}"

        # Stage only affected files (or all changed files if none identified)
        if diagnosis.affected_files:
            for fpath in diagnosis.affected_files:
                full = Path(self.cwd, fpath)
                if full.exists():
                    subprocess.run(
                        ["git", "add", fpath],
                        capture_output=True,
                        cwd=self.cwd,
                    )
        else:
            # Stage tracked modified files only
            subprocess.run(
                ["git", "add", "-u"],
                capture_output=True,
                cwd=self.cwd,
            )

        # Check if there's anything staged
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            cwd=self.cwd,
        )
        if status.returncode == 0:
            logger.info("No changes staged — skipping commit")
            return ""

        result = subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True,
            text=True,
            cwd=self.cwd,
        )
        if result.returncode == 0:
            logger.info("Committed fix: %s", msg)
            # Push
            push = subprocess.run(
                ["git", "push"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.cwd,
            )
            if push.returncode == 0:
                logger.info("Pushed fix to remote")
            else:
                logger.warning("Push failed: %s", push.stderr[:200])
            return msg
        else:
            logger.warning("Commit failed: %s", result.stderr[:200])
            return ""

    # ------------------------------------------------------------------
    # Re-trigger
    # ------------------------------------------------------------------

    def _retrigger(self, source: str, build_url: str = "", build_id: str = "") -> str:
        """Re-trigger the CI build. Returns a URL/identifier for the new build."""
        logger.info("Re-triggering build: source=%s", source)

        if source == "jenkins":
            return self._retrigger_jenkins(build_url)
        elif source == "github":
            return self._retrigger_github(build_id)
        return ""

    def _retrigger_jenkins(self, build_url: str) -> str:
        """Re-trigger a Jenkins build."""
        if not build_url:
            jenkins_url = os.environ.get("JENKINS_URL", "")
            jenkins_job = os.environ.get("JENKINS_JOB", "")
            if jenkins_url and jenkins_job:
                build_url = f"{jenkins_url}/job/{jenkins_job}"
            else:
                logger.warning("No Jenkins URL to re-trigger")
                return ""

        # Strip build number from URL if present
        url = re.sub(r"/\d+/?$", "", build_url.rstrip("/"))
        trigger_url = f"{url}/build"

        try:
            result = subprocess.run(
                ["curl", "-sS", "--max-time", "30", "-X", "POST", trigger_url],
                capture_output=True,
                text=True,
                timeout=45,
                cwd=self.cwd,
            )
            if result.returncode == 0:
                logger.info("Jenkins build re-triggered: %s", trigger_url)
                return trigger_url
            logger.warning("Jenkins re-trigger failed: %s", result.stderr[:200])
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("Failed to re-trigger Jenkins: %s", exc)
        return ""

    def _retrigger_github(self, build_id: str) -> str:
        """Re-run a GitHub Actions workflow."""
        if not build_id:
            return ""
        try:
            result = subprocess.run(
                ["gh", "run", "rerun", build_id, "--failed"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.cwd,
            )
            if result.returncode == 0:
                logger.info("GH Actions re-run triggered for %s", build_id)
                return build_id
            logger.warning("GH Actions re-run failed: %s", result.stderr[:200])
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("Failed to re-trigger GH Actions: %s", exc)
        return ""

    # ------------------------------------------------------------------
    # Wait for result
    # ------------------------------------------------------------------

    def _wait_for_result(
        self,
        retrigger_url: str,
        source: str,
        build_id: str,
        timeout: int = 300,
    ) -> bool:
        """Poll build status until complete or timeout. Returns True if passed."""
        logger.info("Waiting for build result (timeout=%ds)", timeout)
        start = time.time()
        poll_interval = 10

        while time.time() - start < timeout:
            status = self._check_build_status(source, build_id)
            if status == "success":
                return True
            elif status == "failure":
                return False
            elif status == "unknown":
                # Can't determine — assume still running
                pass
            time.sleep(poll_interval)

        logger.warning("Timed out waiting for build result after %ds", timeout)
        return False

    def _check_build_status(self, source: str, build_id: str) -> str:
        """Check current build status. Returns 'success', 'failure', 'running', or 'unknown'."""
        if source == "github" and build_id:
            try:
                result = subprocess.run(
                    ["gh", "run", "view", build_id, "--json", "status,conclusion"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=self.cwd,
                )
                if result.returncode == 0:
                    import json

                    data = json.loads(result.stdout)
                    status = data.get("status", "")
                    conclusion = data.get("conclusion", "")
                    if status == "completed":
                        return "success" if conclusion == "success" else "failure"
                    return "running"
            except Exception as exc:
                logger.debug("Status check failed: %s", exc)

        elif source == "jenkins":
            jenkins_url = os.environ.get("JENKINS_URL", "")
            jenkins_job = os.environ.get("JENKINS_JOB", "")
            if jenkins_url and jenkins_job:
                api_url = f"{jenkins_url}/job/{jenkins_job}/lastBuild/api/json"
                try:
                    result = subprocess.run(
                        ["curl", "-sS", "--max-time", "10", api_url],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        cwd=self.cwd,
                    )
                    if result.returncode == 0:
                        import json

                        data = json.loads(result.stdout)
                        if data.get("building", True):
                            return "running"
                        res = data.get("result", "")
                        if res == "SUCCESS":
                            return "success"
                        return "failure"
                except Exception as exc:
                    logger.debug("Jenkins status check failed: %s", exc)

        return "unknown"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _extract_affected_files(logs: str) -> list[str]:
    """Extract file paths mentioned in tracebacks / error output."""
    files: list[str] = []
    seen: set[str] = set()

    for pattern in [_FILE_PATTERN, _JS_FILE_PATTERN, _TS_FILE_PATTERN, _GENERIC_FILE_PATTERN]:
        for m in pattern.finditer(logs):
            fpath = m.group(1)
            # Filter out stdlib / site-packages / virtual env paths
            if any(skip in fpath for skip in ["site-packages", "/usr/lib", "node_modules", "<"]):
                continue
            if fpath not in seen:
                seen.add(fpath)
                files.append(fpath)

    return files[:20]  # Cap at 20 files


def _extract_error_snippet(logs: str, max_len: int = 500) -> str:
    """Extract a short error snippet from logs."""
    lines = logs.strip().splitlines()
    # Look for lines containing "error", "FAILED", "Error" etc.
    error_lines = []
    for line in lines:
        if re.search(r"error|FAILED|Exception|Traceback", line, re.IGNORECASE):
            error_lines.append(line.strip())
    if error_lines:
        return "\n".join(error_lines[:10])[:max_len]
    # Fallback: last 10 lines
    return "\n".join(lines[-10:])[:max_len]


def _suggest_fix(category: str, root_cause: str, affected_files: list[str]) -> str:
    """Generate a human-readable fix suggestion."""
    suggestions = {
        "lint": "Run auto-formatter (black, prettier, gofmt) to fix style issues",
        "dependency": "Install missing dependency",
        "compile": "Fix syntax error at reported location",
        "test": "Investigate failing test — may be flaky or need assertion update",
        "config": "Check CI environment configuration (connections, credentials, paths)",
        "timeout": "Investigate slow step — increase timeout or optimize",
    }
    return suggestions.get(category, "Manual investigation required")


def _compute_confidence(category: str, logs: str, match: re.Match) -> float:
    """Compute confidence score for a diagnosis."""
    base = {
        "lint": 0.9,
        "dependency": 0.85,
        "compile": 0.8,
        "test": 0.7,
        "config": 0.5,
        "timeout": 0.6,
    }.get(category, 0.3)

    # Boost confidence if multiple patterns match
    all_patterns = {
        "lint": _LINT_PATTERNS,
        "dependency": _DEPENDENCY_PATTERNS,
        "compile": _COMPILE_PATTERNS,
        "test": _TEST_PATTERNS,
        "config": _CONFIG_PATTERNS,
        "timeout": _TIMEOUT_PATTERNS,
    }
    patterns = all_patterns.get(category, [])
    match_count = sum(1 for p in patterns if p.search(logs))
    if match_count > 1:
        base = min(1.0, base + 0.05 * (match_count - 1))

    return round(base, 2)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_heal_result(result: HealResult) -> str:
    """Format a HealResult as a rich terminal panel."""
    width = 50
    line = "\u2500" * (width - 2)

    if result.healed:
        status_label = "FAILED \u2192 FIXED \u2713"
    elif result.final_status == "dry_run":
        status_label = "DRY RUN"
    else:
        status_label = f"FAILED ({result.final_status})"

    lines = [
        f"\u256d\u2500 CI Self-Healing {'─' * (width - 21)}\u256e",
        f"\u2502 Build: #{result.build_id} ({status_label}){' ' * max(0, width - 14 - len(result.build_id) - len(status_label))}\u2502",
        f"\u2502 Attempts: {result.total_attempts}/{len(result.attempts) if result.attempts else '?'}{' ' * max(0, width - 15 - len(str(result.total_attempts)))}\u2502",
        f"\u251c{line}\u2524",
    ]

    for att in result.attempts:
        d = att.diagnosis
        lines.append(
            f"\u2502 Attempt {att.attempt}: {d.category} error"
            f"{' ' * max(0, width - 17 - len(d.category) - len(str(att.attempt)))}\u2502"
        )
        # Root cause (truncated)
        rc = d.root_cause[:width - 10]
        lines.append(f"\u2502   Cause: {rc}{' ' * max(0, width - 12 - len(rc))}\u2502")
        # Fix
        fx = att.fix_applied[:width - 10]
        lines.append(f"\u2502   Fix: {fx}{' ' * max(0, width - 10 - len(fx))}\u2502")
        # Result
        if att.success:
            res = "\u2713 BUILD PASSED"
        elif att == result.attempts[-1] and result.healed:
            res = "\u2713 BUILD PASSED"
        else:
            res = "still failing"
        lines.append(f"\u2502   Result: {res}{' ' * max(0, width - 13 - len(res))}\u2502")

    lines.append(f"\u2570{'─' * (width - 2)}\u256f")
    return "\n".join(lines)
