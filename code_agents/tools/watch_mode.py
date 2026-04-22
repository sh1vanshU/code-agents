"""Watch Mode — file watcher with auto-lint, auto-test, and auto-fix via agent delegation.

Watches source files for changes, runs lint and tests on affected files,
and auto-delegates failures to code-writer/code-tester agents for fixing.

Usage:
    code-agents watch                    # watch cwd, auto-detect everything
    code-agents watch src/               # watch specific directory
    code-agents watch --lint-only        # only lint, no tests
    code-agents watch --test-only        # only tests, no lint
    code-agents watch --no-fix           # report failures, don't auto-fix
    code-agents watch --interval 5       # poll every 5s (default: 3s)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.watch_mode")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FileChange:
    """A detected file change."""
    file: str           # relative path
    change_type: str    # "modified", "created"
    timestamp: float = 0.0


@dataclass
class LintResult:
    """Result of linting a file."""
    file: str
    passed: bool
    tool: str = ""          # ruff, flake8, eslint, etc.
    errors: list[str] = field(default_factory=list)
    auto_fixed: bool = False


@dataclass
class TestResult:
    """Result of running tests for a file."""
    file: str
    test_file: str = ""
    passed: bool = False
    output: str = ""
    passed_count: int = 0
    failed_count: int = 0
    auto_fixed: bool = False


@dataclass
class WatchCycle:
    """Results from one watch cycle (one set of changes processed)."""
    timestamp: float = 0.0
    files_changed: list[str] = field(default_factory=list)
    lint_results: list[LintResult] = field(default_factory=list)
    test_results: list[TestResult] = field(default_factory=list)
    fixes_attempted: int = 0
    fixes_succeeded: int = 0


@dataclass
class WatchStats:
    """Cumulative stats for the watch session."""
    started_at: float = 0.0
    cycles: int = 0
    files_changed: int = 0
    lint_errors_found: int = 0
    lint_errors_fixed: int = 0
    test_failures_found: int = 0
    test_failures_fixed: int = 0


# ---------------------------------------------------------------------------
# Skip patterns
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".idea", ".vscode", ".next", "coverage",
}

_DEFAULT_PATTERNS = ["*.py", "*.java", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.kt"]


# ---------------------------------------------------------------------------
# WatchMode — the core engine
# ---------------------------------------------------------------------------


class WatchMode:
    """File watcher with auto-lint, auto-test, and auto-fix."""

    def __init__(
        self,
        repo_path: str,
        watch_path: str = "",
        *,
        interval: float = 3.0,
        lint_only: bool = False,
        test_only: bool = False,
        no_fix: bool = False,
        watch_patterns: list[str] | None = None,
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.watch_path = watch_path
        self.interval = max(1.0, interval)
        self.lint_only = lint_only
        self.test_only = test_only
        self.no_fix = no_fix
        self.watch_patterns = watch_patterns or _DEFAULT_PATTERNS
        self.active = False
        self.language = ""
        self.test_framework = ""
        self.lint_tool = ""
        self.stats = WatchStats()

        self._file_hashes: dict[str, str] = {}
        self._debounce_until: float = 0.0
        self._debounce_delay: float = 1.0  # wait 1s after last change

        self._detect_stack()

    # ------------------------------------------------------------------
    # Stack detection
    # ------------------------------------------------------------------

    def _detect_stack(self):
        """Detect language, lint tool, and test framework."""
        if os.path.exists(os.path.join(self.repo_path, "pyproject.toml")) or \
           os.path.exists(os.path.join(self.repo_path, "setup.py")):
            self.language = "python"
            self.test_framework = "pytest"
            self.lint_tool = "ruff" if shutil.which("ruff") else ("flake8" if shutil.which("flake8") else "")
        elif os.path.exists(os.path.join(self.repo_path, "package.json")):
            self.language = "javascript"
            self.test_framework = "jest"
            self.lint_tool = "eslint"
        elif os.path.exists(os.path.join(self.repo_path, "pom.xml")) or \
             os.path.exists(os.path.join(self.repo_path, "build.gradle")):
            self.language = "java"
            self.test_framework = "junit"
            self.lint_tool = ""
        elif os.path.exists(os.path.join(self.repo_path, "go.mod")):
            self.language = "go"
            self.test_framework = "go test"
            self.lint_tool = "golint" if shutil.which("golint") else ("golangci-lint" if shutil.which("golangci-lint") else "")

        logger.info("Stack: %s / lint=%s / test=%s", self.language, self.lint_tool, self.test_framework)

    # ------------------------------------------------------------------
    # File watching
    # ------------------------------------------------------------------

    def _get_watch_root(self) -> str:
        """Get the directory to watch."""
        if self.watch_path:
            from pathlib import Path
            resolved = str(Path(os.path.join(self.repo_path, self.watch_path)).resolve())
            repo_resolved = str(Path(self.repo_path).resolve())
            if not resolved.startswith(repo_resolved):
                logger.warning("watch_path escapes repo: %s", self.watch_path)
                return self.repo_path
            return resolved
        return self.repo_path

    def _match_pattern(self, filename: str) -> bool:
        """Check if filename matches any watch pattern."""
        for pattern in self.watch_patterns:
            if pattern.startswith("*."):
                if filename.endswith(pattern[1:]):
                    return True
            elif filename == pattern:
                return True
        return False

    def _get_watched_files(self) -> list[str]:
        """Get all files matching watch patterns."""
        root = self._get_watch_root()
        if not os.path.isdir(root):
            return []

        files = []
        for dirpath, dirs, filenames in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in filenames:
                if self._match_pattern(f):
                    files.append(os.path.join(dirpath, f))
        return files

    def _hash_file(self, filepath: str) -> str:
        """Get MD5 hash of file content."""
        try:
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except (OSError, PermissionError) as e:
            logger.debug("Cannot hash file %s: %s", filepath, e)
            return ""

    def snapshot(self):
        """Take initial snapshot of all watched files."""
        self._file_hashes.clear()
        for fpath in self._get_watched_files():
            h = self._hash_file(fpath)
            if h:
                self._file_hashes[fpath] = h
        logger.info("Snapshot: %d files", len(self._file_hashes))

    def detect_changes(self) -> list[FileChange]:
        """Detect file changes since last snapshot."""
        changes = []
        now = time.time()
        current_files = set()

        for fpath in self._get_watched_files():
            current_files.add(fpath)
            new_hash = self._hash_file(fpath)
            if not new_hash:
                continue

            old_hash = self._file_hashes.get(fpath)
            if old_hash is None:
                changes.append(FileChange(
                    file=os.path.relpath(fpath, self.repo_path),
                    change_type="created",
                    timestamp=now,
                ))
                self._file_hashes[fpath] = new_hash
            elif old_hash != new_hash:
                changes.append(FileChange(
                    file=os.path.relpath(fpath, self.repo_path),
                    change_type="modified",
                    timestamp=now,
                ))
                self._file_hashes[fpath] = new_hash

        return changes

    # ------------------------------------------------------------------
    # Lint
    # ------------------------------------------------------------------

    def run_lint(self, files: list[str]) -> list[LintResult]:
        """Run lint on changed files."""
        if not self.lint_tool or self.test_only:
            return []

        results = []
        for rel_path in files:
            abs_path = os.path.join(self.repo_path, rel_path)
            result = self._lint_file(rel_path, abs_path)
            results.append(result)
            if not result.passed:
                self.stats.lint_errors_found += 1

        return results

    def _lint_file(self, rel_path: str, abs_path: str) -> LintResult:
        """Lint a single file."""
        if self.lint_tool == "ruff":
            cmd = ["ruff", "check", abs_path, "--output-format=text"]
        elif self.lint_tool == "flake8":
            cmd = ["flake8", "--max-line-length=120", abs_path]
        elif self.lint_tool == "eslint":
            cmd = ["npx", "eslint", abs_path, "--no-error-on-unmatched-pattern"]
        elif self.lint_tool in ("golint", "golangci-lint"):
            cmd = [self.lint_tool, "run", abs_path] if self.lint_tool == "golangci-lint" else [self.lint_tool, abs_path]
        else:
            return LintResult(file=rel_path, passed=True, tool="none")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=self.repo_path,
            )
            errors = []
            if result.returncode != 0:
                output = (result.stdout or "") + (result.stderr or "")
                errors = [line.strip() for line in output.strip().splitlines() if line.strip()][:20]

            return LintResult(
                file=rel_path,
                passed=result.returncode == 0,
                tool=self.lint_tool,
                errors=errors,
            )
        except subprocess.TimeoutExpired:
            return LintResult(file=rel_path, passed=False, tool=self.lint_tool, errors=["Lint timed out (30s)"])
        except FileNotFoundError:
            return LintResult(file=rel_path, passed=True, tool="none", errors=[f"{self.lint_tool} not found"])
        except Exception as e:
            return LintResult(file=rel_path, passed=False, tool=self.lint_tool, errors=[str(e)])

    def auto_fix_lint(self, lint_result: LintResult) -> bool:
        """Try auto-fix with the lint tool's built-in fixer."""
        abs_path = os.path.join(self.repo_path, lint_result.file)

        if self.lint_tool == "ruff":
            cmd = ["ruff", "check", "--fix", abs_path]
        elif self.lint_tool == "eslint":
            cmd = ["npx", "eslint", "--fix", abs_path]
        else:
            return False

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=self.repo_path,
            )
            # Re-check after fix
            recheck = self._lint_file(lint_result.file, abs_path)
            if recheck.passed:
                # Update hash after auto-fix
                self._file_hashes[abs_path] = self._hash_file(abs_path)
                return True
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Test running
    # ------------------------------------------------------------------

    def find_test_file(self, rel_path: str) -> str:
        """Map a source file to its test file."""
        basename = os.path.basename(rel_path)
        name_no_ext = os.path.splitext(basename)[0]
        ext = os.path.splitext(basename)[1]

        candidates = []
        if self.language == "python":
            candidates = [
                f"tests/test_{basename}",
                f"test/test_{basename}",
                os.path.join(os.path.dirname(rel_path), f"test_{basename}"),
            ]
        elif self.language in ("javascript", "typescript"):
            candidates = [
                os.path.join(os.path.dirname(rel_path), f"{name_no_ext}.test{ext}"),
                os.path.join(os.path.dirname(rel_path), f"{name_no_ext}.spec{ext}"),
                f"__tests__/{name_no_ext}.test{ext}",
            ]
        elif self.language == "go":
            candidates = [rel_path.replace(".go", "_test.go")]
        elif self.language == "java":
            candidates = [
                rel_path.replace("src/main/java", "src/test/java").replace(".java", "Test.java"),
            ]

        for c in candidates:
            if os.path.exists(os.path.join(self.repo_path, c)):
                return c
        return ""

    def run_tests(self, files: list[str]) -> list[TestResult]:
        """Run tests for changed files."""
        if self.lint_only:
            return []

        results = []
        tested_files = set()

        for rel_path in files:
            test_file = self.find_test_file(rel_path)
            if not test_file or test_file in tested_files:
                continue
            tested_files.add(test_file)

            result = self._run_test_file(rel_path, test_file)
            results.append(result)
            if not result.passed:
                self.stats.test_failures_found += 1

        return results

    def _run_test_file(self, source_file: str, test_file: str) -> TestResult:
        """Run a single test file."""
        abs_test = os.path.join(self.repo_path, test_file)

        if self.language == "python":
            cmd = ["python", "-m", "pytest", abs_test, "-x", "-q", "--tb=short", "--no-header"]
        elif self.language in ("javascript", "typescript"):
            cmd = ["npx", "jest", abs_test, "--no-coverage", "--bail"]
        elif self.language == "go":
            pkg = os.path.dirname(test_file)
            cmd = ["go", "test", f"./{pkg}/...", "-v", "-count=1"]
        elif self.language == "java":
            test_class = os.path.basename(test_file).replace(".java", "")
            cmd = ["mvn", "test", f"-Dtest={test_class}", "-pl", "."]
        else:
            return TestResult(file=source_file, test_file=test_file, passed=True, output="No test framework")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd=self.repo_path,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")

            passed_count = 0
            failed_count = 0
            if self.language == "python":
                m = re.search(r'(\d+) passed', output)
                if m:
                    passed_count = int(m.group(1))
                m = re.search(r'(\d+) failed', output)
                if m:
                    failed_count = int(m.group(1))

            return TestResult(
                file=source_file,
                test_file=test_file,
                passed=result.returncode == 0,
                output=output[-2000:],
                passed_count=passed_count,
                failed_count=failed_count,
            )
        except subprocess.TimeoutExpired:
            return TestResult(file=source_file, test_file=test_file, passed=False, output="Test timed out (120s)")
        except Exception as e:
            return TestResult(file=source_file, test_file=test_file, passed=False, output=str(e))

    # ------------------------------------------------------------------
    # Agent delegation for auto-fix
    # ------------------------------------------------------------------

    async def _delegate_fix(self, prompt: str, agent_name: str = "code-writer") -> str:
        """Delegate a fix to an agent via the backend dispatcher."""
        from code_agents.core.config import agent_loader
        from code_agents.core.backend import run_agent
        from code_agents.core.stream import _inject_context

        if not agent_loader.list_agents():
            agent_loader.load()

        agent = agent_loader.get(agent_name)
        if not agent:
            logger.warning("Agent %s not found", agent_name)
            return ""

        agent = _inject_context(agent, self.repo_path)

        response_parts = []
        async for message in run_agent(agent, prompt, cwd_override=self.repo_path):
            msg_type = type(message).__name__
            if msg_type == "AssistantMessage":
                for block in (message.content or []):
                    if hasattr(block, "text") and block.text:
                        response_parts.append(block.text)

        return "".join(response_parts)

    async def auto_fix_lint_via_agent(self, lint_result: LintResult) -> bool:
        """Fix lint errors by delegating to code-writer agent."""
        abs_path = os.path.join(self.repo_path, lint_result.file)
        try:
            with open(abs_path) as f:
                source = f.read()
        except Exception:
            return False

        prompt = (
            f"Fix these lint errors in {lint_result.file}. Output ONLY the corrected file — no explanations.\n\n"
            f"## Lint Errors ({lint_result.tool})\n"
            + "\n".join(f"  - {e}" for e in lint_result.errors[:15])
            + f"\n\n## Source Code\n```{self.language}\n{source[:8000]}\n```\n\n"
            "Output ONLY the corrected code. No markdown fences."
        )

        response = await self._delegate_fix(prompt, "code-writer")
        if not response or len(response) < 20:
            return False

        # Extract code
        code = self._extract_code(response)
        if not code:
            return False

        try:
            # Atomic write: backup original, write new, restore on failure
            import shutil, tempfile
            backup = abs_path + ".bak"
            shutil.copy2(abs_path, backup)
            with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(abs_path),
                                              delete=False, suffix=".tmp") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            os.replace(tmp_path, abs_path)
            # Update hash
            self._file_hashes[abs_path] = self._hash_file(abs_path)
            # Re-check
            recheck = self._lint_file(lint_result.file, abs_path)
            if recheck.passed:
                os.remove(backup)
                return True
            else:
                # Restore original on failed lint
                shutil.copy2(backup, abs_path)
                os.remove(backup)
                return False
        except Exception as e:
            logger.warning("Auto-fix write failed for %s: %s", abs_path, e)
            # Restore backup if it exists
            if os.path.exists(backup):
                shutil.copy2(backup, abs_path)
                os.remove(backup)
            return False

    async def auto_fix_test_via_agent(self, test_result: TestResult) -> bool:
        """Fix test failures by delegating to code-tester agent."""
        abs_source = os.path.join(self.repo_path, test_result.file)
        abs_test = os.path.join(self.repo_path, test_result.test_file)

        source_code = ""
        test_code = ""
        try:
            with open(abs_source) as f:
                source_code = f.read()
            with open(abs_test) as f:
                test_code = f.read()
        except Exception:
            return False

        prompt = (
            f"Tests for {test_result.file} are FAILING after a code change. Fix the source code.\n\n"
            f"## Test Output\n```\n{test_result.output[-2000:]}\n```\n\n"
            f"## Source Code ({test_result.file})\n```{self.language}\n{source_code[:6000]}\n```\n\n"
            f"## Test Code ({test_result.test_file})\n```{self.language}\n{test_code[:4000]}\n```\n\n"
            f"Fix the source code so the tests pass. Output ONLY the corrected source file code.\n"
            "No markdown fences, no explanations."
        )

        response = await self._delegate_fix(prompt, "code-tester")
        if not response or len(response) < 20:
            return False

        code = self._extract_code(response)
        if not code:
            return False

        try:
            # Atomic write with backup — restore if tests still fail
            import shutil, tempfile
            backup = abs_source + ".bak"
            shutil.copy2(abs_source, backup)
            with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(abs_source),
                                              delete=False, suffix=".tmp") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            os.replace(tmp_path, abs_source)
            self._file_hashes[abs_source] = self._hash_file(abs_source)
            # Re-run test
            recheck = self._run_test_file(test_result.file, test_result.test_file)
            if recheck.passed:
                os.remove(backup)
                return True
            else:
                # Restore original on failed test
                shutil.copy2(backup, abs_source)
                os.remove(backup)
                return False
        except Exception as e:
            logger.warning("Auto-fix write failed for %s: %s", abs_source, e)
            if os.path.exists(backup):
                shutil.copy2(backup, abs_source)
                os.remove(backup)
            return False

    def _extract_code(self, response: str) -> str:
        """Extract code from agent response."""
        patterns = [
            r'```(?:python|java|javascript|typescript|go|jsx|tsx)\n(.*?)```',
            r'```\n(.*?)```',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                return max(matches, key=len).strip()

        lines = response.strip().splitlines()
        code_lines = []
        in_code = False
        for line in lines:
            if not in_code:
                if re.match(r'^(import |from |package |const |var |func |class |def |describe\(|#!)', line):
                    in_code = True
            if in_code:
                code_lines.append(line)

        return "\n".join(code_lines) if code_lines else response.strip()

    # ------------------------------------------------------------------
    # Single watch cycle
    # ------------------------------------------------------------------

    async def process_changes(self, changes: list[FileChange], on_event=None) -> WatchCycle:
        """Process a batch of file changes: lint → test → auto-fix."""
        cycle = WatchCycle(
            timestamp=time.time(),
            files_changed=[c.file for c in changes],
        )

        changed_files = [c.file for c in changes]

        # Step 1: Lint
        if not self.test_only:
            lint_results = self.run_lint(changed_files)
            cycle.lint_results = lint_results

            for lr in lint_results:
                if not lr.passed and not self.no_fix:
                    if on_event:
                        on_event("lint_fail", f"{lr.file}: {len(lr.errors)} errors ({lr.tool})")

                    # Try tool's built-in fix first
                    fixed = self.auto_fix_lint(lr)
                    if fixed:
                        lr.auto_fixed = True
                        self.stats.lint_errors_fixed += 1
                        cycle.fixes_succeeded += 1
                        if on_event:
                            on_event("lint_fixed", f"{lr.file}: auto-fixed by {lr.tool}")
                    else:
                        # Delegate to agent
                        cycle.fixes_attempted += 1
                        if on_event:
                            on_event("lint_delegating", f"{lr.file}: delegating to code-writer...")
                        agent_fixed = await self.auto_fix_lint_via_agent(lr)
                        if agent_fixed:
                            lr.auto_fixed = True
                            self.stats.lint_errors_fixed += 1
                            cycle.fixes_succeeded += 1
                            if on_event:
                                on_event("lint_fixed", f"{lr.file}: fixed by code-writer agent")
                        else:
                            if on_event:
                                on_event("lint_unfixed", f"{lr.file}: could not auto-fix")
                elif lr.passed and on_event:
                    on_event("lint_ok", f"{lr.file}: clean")

        # Step 2: Tests
        if not self.lint_only:
            test_results = self.run_tests(changed_files)
            cycle.test_results = test_results

            for tr in test_results:
                if not tr.passed and not self.no_fix:
                    if on_event:
                        on_event("test_fail", f"{tr.file} ({tr.test_file}): {tr.failed_count} failed")

                    cycle.fixes_attempted += 1
                    if on_event:
                        on_event("test_delegating", f"{tr.file}: delegating to code-tester...")
                    agent_fixed = await self.auto_fix_test_via_agent(tr)
                    if agent_fixed:
                        tr.auto_fixed = True
                        self.stats.test_failures_fixed += 1
                        cycle.fixes_succeeded += 1
                        if on_event:
                            on_event("test_fixed", f"{tr.file}: fixed by code-tester agent")
                    else:
                        if on_event:
                            on_event("test_unfixed", f"{tr.file}: could not auto-fix")
                elif tr.passed and on_event:
                    on_event("test_ok", f"{tr.file}: {tr.passed_count} tests passed")

        self.stats.cycles += 1
        self.stats.files_changed += len(changed_files)
        return cycle

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self, on_event=None):
        """Run the watch loop. Blocks until interrupted.

        Args:
            on_event: Optional callback(event_type: str, detail: str) for UI updates.
        """
        self.active = True
        self.stats.started_at = time.time()
        self.snapshot()

        if on_event:
            on_event("started", f"Watching {len(self._file_hashes)} files ({self.language}/{self.lint_tool}/{self.test_framework})")

        try:
            while self.active:
                await asyncio.sleep(self.interval)

                changes = self.detect_changes()
                if not changes:
                    continue

                # Debounce: wait for rapid saves to settle
                self._debounce_until = time.time() + self._debounce_delay
                while time.time() < self._debounce_until:
                    await asyncio.sleep(0.5)
                    more_changes = self.detect_changes()
                    if more_changes:
                        changes.extend(more_changes)
                        self._debounce_until = time.time() + self._debounce_delay

                if on_event:
                    file_list = ", ".join(c.file for c in changes[:5])
                    extra = f" +{len(changes) - 5} more" if len(changes) > 5 else ""
                    on_event("changes", f"{len(changes)} files changed: {file_list}{extra}")

                cycle = await self.process_changes(changes, on_event=on_event)

                if on_event:
                    summary_parts = []
                    lint_ok = sum(1 for r in cycle.lint_results if r.passed)
                    lint_fail = sum(1 for r in cycle.lint_results if not r.passed)
                    test_ok = sum(1 for r in cycle.test_results if r.passed)
                    test_fail = sum(1 for r in cycle.test_results if not r.passed)
                    fixed = cycle.fixes_succeeded

                    if cycle.lint_results:
                        summary_parts.append(f"lint: {lint_ok} ok, {lint_fail} fail")
                    if cycle.test_results:
                        summary_parts.append(f"tests: {test_ok} ok, {test_fail} fail")
                    if fixed:
                        summary_parts.append(f"{fixed} auto-fixed")

                    on_event("cycle_done", " | ".join(summary_parts) if summary_parts else "no checks ran")

        except asyncio.CancelledError:
            pass
        finally:
            self.active = False
            if on_event:
                on_event("stopped", format_watch_stats(self.stats))

    def stop(self):
        """Stop the watch loop."""
        self.active = False

    def run_in_background(self, on_event=None):
        """Start the watch loop in a daemon thread. Non-blocking.

        Returns the thread so caller can check status.
        """
        import threading

        def _thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run(on_event=on_event))
            except Exception as e:
                logger.error("Watch background thread error: %s", e)
            finally:
                loop.close()

        t = threading.Thread(target=_thread_target, daemon=True, name="watch-mode")
        t.start()
        return t


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def format_watch_stats(stats: WatchStats) -> str:
    """Format cumulative stats for display."""
    elapsed = time.time() - stats.started_at if stats.started_at else 0
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    lines = []
    lines.append(f"  Watch session: {mins}m {secs}s, {stats.cycles} cycles")
    lines.append(f"  Files changed: {stats.files_changed}")
    if stats.lint_errors_found or stats.lint_errors_fixed:
        lines.append(f"  Lint errors: {stats.lint_errors_found} found, {stats.lint_errors_fixed} auto-fixed")
    if stats.test_failures_found or stats.test_failures_fixed:
        lines.append(f"  Test failures: {stats.test_failures_found} found, {stats.test_failures_fixed} auto-fixed")
    return "\n".join(lines)


def format_watch_event(event_type: str, detail: str) -> str:
    """Format a single watch event for terminal output."""
    icons = {
        "started": f"  {_GREEN}>>>{_RESET}",
        "stopped": f"  {_RED}<<<{_RESET}",
        "changes": f"  {_CYAN}---{_RESET}",
        "lint_ok": f"  {_GREEN} + {_RESET}",
        "lint_fail": f"  {_RED} x {_RESET}",
        "lint_fixed": f"  {_GREEN} ~ {_RESET}",
        "lint_delegating": f"  {_YELLOW} > {_RESET}",
        "lint_unfixed": f"  {_RED} ! {_RESET}",
        "test_ok": f"  {_GREEN} + {_RESET}",
        "test_fail": f"  {_RED} x {_RESET}",
        "test_fixed": f"  {_GREEN} ~ {_RESET}",
        "test_delegating": f"  {_YELLOW} > {_RESET}",
        "test_unfixed": f"  {_RED} ! {_RESET}",
        "cycle_done": f"  {_DIM}---{_RESET}",
    }
    icon = icons.get(event_type, "  ...")
    return f"{icon} {detail}"
