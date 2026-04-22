"""Tests for CI pipeline self-healing engine."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.devops.ci_self_heal import (
    CISelfHealer,
    Diagnosis,
    HealAttempt,
    HealResult,
    format_heal_result,
    _extract_affected_files,
    _extract_error_snippet,
    _suggest_fix,
    _compute_confidence,
)


# ---------------------------------------------------------------------------
# Sample log fragments
# ---------------------------------------------------------------------------

LINT_LOG = """\
Running black --check .
would reformat src/api.py
Oh no! 1 file would be reformatted.
error: black would reformat 1 file
"""

TEST_LOG = """\
============================= test session starts ==============================
collected 42 items
tests/test_api.py::test_create_user PASSED
tests/test_api.py::test_get_user FAILED
FAILED tests/test_api.py::test_get_user - AssertionError: assert 200 == 404
============================= 1 failed, 41 passed ==============================
"""

DEPENDENCY_LOG = """\
Traceback (most recent call last):
  File "src/app.py", line 3, in <module>
    import flask
ModuleNotFoundError: No module named 'flask'
"""

COMPILE_LOG = """\
src/main.ts(42,5): error TS2304: Cannot find name 'fooBar'.
src/utils.ts(10,1): error TS1005: ';' expected.
Build FAILED with 2 errors.
"""

CONFIG_LOG = """\
Step 5: Running integration tests...
urllib3.exceptions.MaxRetryError: HTTPConnectionPool(host='localhost', port=5432):
  Max retries exceeded (Caused by NewConnectionError: Connection refused)
ConnectionRefused: localhost:5432
"""

TIMEOUT_LOG = """\
Step 3: Running end-to-end tests...
Process timed out after 300 seconds.
Build timed out — aborting.
"""

UNKNOWN_LOG = """\
Some random output
Nothing useful here
Process exited with code 1
"""

PYTHON_TRACEBACK_LOG = """\
Traceback (most recent call last):
  File "src/api.py", line 45, in handler
    result = process(data)
  File "src/processor.py", line 12, in process
    return compute(data)
SyntaxError: invalid syntax
"""


# ---------------------------------------------------------------------------
# TestDiagnosis
# ---------------------------------------------------------------------------


class TestDiagnosis:
    """Test the diagnosis engine with sample logs."""

    def setup_method(self):
        self.healer = CISelfHealer(cwd="/tmp/test-repo")

    def test_diagnose_lint(self):
        d = self.healer._diagnose(LINT_LOG)
        assert d.category == "lint"
        assert d.confidence > 0.5
        assert "black" in d.root_cause.lower() or "reformat" in d.root_cause.lower()

    def test_diagnose_test_failure(self):
        d = self.healer._diagnose(TEST_LOG)
        assert d.category == "test"
        assert d.confidence > 0.5

    def test_diagnose_dependency(self):
        d = self.healer._diagnose(DEPENDENCY_LOG)
        assert d.category == "dependency"
        assert "flask" in d.root_cause.lower() or "module" in d.root_cause.lower()
        assert d.confidence > 0.5

    def test_diagnose_compile(self):
        d = self.healer._diagnose(COMPILE_LOG)
        assert d.category == "compile"
        assert d.confidence > 0.5

    def test_diagnose_config(self):
        d = self.healer._diagnose(CONFIG_LOG)
        assert d.category == "config"
        assert d.confidence > 0.3

    def test_diagnose_timeout(self):
        d = self.healer._diagnose(TIMEOUT_LOG)
        assert d.category == "timeout"
        assert d.confidence > 0.3

    def test_diagnose_unknown(self):
        d = self.healer._diagnose(UNKNOWN_LOG)
        assert d.category == "unknown"
        assert d.confidence == 0.0

    def test_affected_files_python_traceback(self):
        files = _extract_affected_files(PYTHON_TRACEBACK_LOG)
        assert "src/api.py" in files
        assert "src/processor.py" in files

    def test_affected_files_ts(self):
        files = _extract_affected_files(COMPILE_LOG)
        assert any("main.ts" in f for f in files)

    def test_affected_files_filters_stdlib(self):
        log = 'File "/usr/lib/python3.10/site-packages/foo.py", line 1\n'
        files = _extract_affected_files(log)
        assert len(files) == 0


# ---------------------------------------------------------------------------
# TestApplyFix
# ---------------------------------------------------------------------------


class TestApplyFix:
    """Test fix application with mocked subprocess calls."""

    def setup_method(self):
        self.healer = CISelfHealer(cwd="/tmp/test-repo")

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_fix_lint_runs_black(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        diag = Diagnosis(
            category="lint",
            root_cause="black would reformat",
            affected_files=["src/api.py"],
            suggested_fix="Run auto-formatter",
            confidence=0.9,
        )
        result = self.healer._apply_fix(diag)
        assert "black" in result.lower() or "format" in result.lower()
        assert mock_run.called

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    @patch("code_agents.devops.ci_self_heal.Path")
    def test_fix_dependency_python(self, mock_path, mock_run):
        # Mock Path().exists() checks
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.read_text.return_value = "requests\n"
        mock_path.return_value = mock_path_instance
        mock_path.side_effect = lambda *a, **kw: mock_path_instance

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        diag = Diagnosis(
            category="dependency",
            root_cause="ModuleNotFoundError: No module named 'flask'",
            affected_files=["src/app.py"],
            suggested_fix="Install missing dependency",
            confidence=0.85,
        )
        result = self.healer._fix_dependency(diag)
        # Should attempt to install flask
        assert "flask" in result.lower() or mock_run.called

    def test_fix_config_returns_empty(self):
        """Config issues can't be auto-fixed — should return empty string."""
        diag = Diagnosis(
            category="config",
            root_cause="ConnectionRefused",
            affected_files=[],
            suggested_fix="Check environment config",
            confidence=0.5,
        )
        result = self.healer._apply_fix(diag)
        assert result == ""

    def test_fix_timeout_returns_empty(self):
        """Timeout issues can't be auto-fixed."""
        diag = Diagnosis(
            category="timeout",
            root_cause="Build timed out",
            affected_files=[],
            suggested_fix="Increase timeout",
            confidence=0.6,
        )
        result = self.healer._apply_fix(diag)
        assert result == ""

    def test_dry_run_does_not_execute(self):
        """Dry run should describe the fix but not run anything."""
        healer = CISelfHealer(cwd="/tmp/test-repo", dry_run=True)
        diag = Diagnosis(
            category="lint",
            root_cause="black would reformat",
            affected_files=["src/api.py"],
            suggested_fix="Run auto-formatter",
            confidence=0.9,
        )
        result = healer._apply_fix(diag)
        assert "dry-run" in result.lower()


# ---------------------------------------------------------------------------
# TestHealLoop
# ---------------------------------------------------------------------------


class TestHealLoop:
    """Test the full heal loop with mocked internals."""

    def test_heal_loop_success_first_attempt(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")
        healer._fetch_logs = MagicMock(return_value=LINT_LOG)
        healer._apply_fix = MagicMock(return_value="Auto-formatted with black")
        healer._commit_fix = MagicMock(return_value="fix(ci): auto-heal lint")
        healer._retrigger = MagicMock(return_value="http://ci/build/2")
        healer._wait_for_result = MagicMock(return_value=True)

        result = healer.heal(build_id="100", source="jenkins", log_text=LINT_LOG)

        assert result.healed is True
        assert result.total_attempts == 1
        assert result.final_status == "healed"
        assert len(result.attempts) == 1
        assert result.attempts[0].success is True

    def test_heal_loop_success_second_attempt(self):
        healer = CISelfHealer(cwd="/tmp/test-repo", max_attempts=3)
        healer._fetch_logs = MagicMock(return_value=TEST_LOG)
        healer._apply_fix = MagicMock(return_value="Re-ran flaky test")
        healer._commit_fix = MagicMock(return_value="fix(ci): auto-heal test")
        healer._retrigger = MagicMock(return_value="http://ci/build/3")
        healer._wait_for_result = MagicMock(side_effect=[False, True])

        result = healer.heal(build_id="100", source="jenkins", log_text=TEST_LOG)

        assert result.healed is True
        assert result.total_attempts == 2

    def test_heal_loop_unknown_stops(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")

        result = healer.heal(build_id="100", source="jenkins", log_text=UNKNOWN_LOG)

        assert result.healed is False
        assert result.final_status == "undiagnosable"
        assert result.total_attempts == 1

    def test_heal_loop_unfixable_stops(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")

        result = healer.heal(build_id="100", source="jenkins", log_text=CONFIG_LOG)

        assert result.healed is False
        assert result.final_status == "unfixable"

    def test_heal_loop_no_logs(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")
        healer._fetch_logs = MagicMock(return_value="")

        result = healer.heal(build_id="100", source="jenkins")

        assert result.healed is False
        assert result.final_status == "no_logs"


# ---------------------------------------------------------------------------
# TestDryRun
# ---------------------------------------------------------------------------


class TestDryRun:
    """Test that dry-run mode makes no changes."""

    def test_dry_run_no_commit_no_retrigger(self):
        healer = CISelfHealer(cwd="/tmp/test-repo", dry_run=True)

        result = healer.heal(build_id="100", source="jenkins", log_text=LINT_LOG)

        assert result.final_status == "dry_run"
        assert result.healed is False
        assert result.total_attempts == 1
        # The fix_applied should indicate dry-run
        assert "dry-run" in result.attempts[0].fix_applied.lower()

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_dry_run_no_subprocess_for_git(self, mock_run):
        """Dry run should not invoke git commit or push."""
        healer = CISelfHealer(cwd="/tmp/test-repo", dry_run=True)

        result = healer.heal(build_id="100", source="jenkins", log_text=LINT_LOG)

        # No subprocess calls for git operations should be made
        for call in mock_run.call_args_list:
            cmd = call[0][0] if call[0] else call[1].get("args", [])
            if isinstance(cmd, list) and cmd:
                assert cmd[0] != "git", f"Git command should not be called in dry-run: {cmd}"


# ---------------------------------------------------------------------------
# TestMaxAttempts
# ---------------------------------------------------------------------------


class TestMaxAttempts:
    """Test that max attempts is respected."""

    def test_stops_after_max_attempts(self):
        healer = CISelfHealer(cwd="/tmp/test-repo", max_attempts=2)
        healer._fetch_logs = MagicMock(return_value=LINT_LOG)
        healer._apply_fix = MagicMock(return_value="Auto-formatted")
        healer._commit_fix = MagicMock(return_value="fix(ci): lint")
        healer._retrigger = MagicMock(return_value="url")
        healer._wait_for_result = MagicMock(return_value=False)

        result = healer.heal(build_id="100", source="jenkins", log_text=LINT_LOG)

        assert result.healed is False
        assert result.total_attempts == 2
        assert result.final_status == "max_attempts_reached"

    def test_max_attempts_one(self):
        healer = CISelfHealer(cwd="/tmp/test-repo", max_attempts=1)
        healer._fetch_logs = MagicMock(return_value=LINT_LOG)
        healer._apply_fix = MagicMock(return_value="Auto-formatted")
        healer._commit_fix = MagicMock(return_value="fix(ci): lint")
        healer._retrigger = MagicMock(return_value="url")
        healer._wait_for_result = MagicMock(return_value=False)

        result = healer.heal(build_id="100", source="jenkins", log_text=LINT_LOG)

        assert result.total_attempts == 1


# ---------------------------------------------------------------------------
# TestFormat
# ---------------------------------------------------------------------------


class TestFormat:
    """Test output formatting."""

    def test_format_healed(self):
        result = HealResult(
            build_id="1234",
            original_error="SyntaxError in api.py",
            attempts=[
                HealAttempt(
                    attempt=1,
                    diagnosis=Diagnosis(
                        category="lint",
                        root_cause="black would reformat src/api.py",
                        affected_files=["src/api.py"],
                        suggested_fix="Auto-format",
                        confidence=0.9,
                    ),
                    fix_applied="Auto-formatted with black",
                    success=True,
                ),
            ],
            healed=True,
            total_attempts=1,
            final_status="healed",
        )
        output = format_heal_result(result)
        assert "1234" in output
        assert "FIXED" in output
        assert "lint" in output
        assert "black" in output.lower()

    def test_format_failed(self):
        result = HealResult(
            build_id="5678",
            original_error="ConnectionRefused",
            attempts=[
                HealAttempt(
                    attempt=1,
                    diagnosis=Diagnosis(
                        category="config",
                        root_cause="ConnectionRefused",
                        affected_files=[],
                        suggested_fix="Check config",
                        confidence=0.5,
                    ),
                    fix_applied="none — fix not applicable",
                ),
            ],
            healed=False,
            total_attempts=1,
            final_status="unfixable",
        )
        output = format_heal_result(result)
        assert "5678" in output
        assert "FAILED" in output

    def test_format_dry_run(self):
        result = HealResult(
            build_id="999",
            original_error="lint error",
            attempts=[
                HealAttempt(
                    attempt=1,
                    diagnosis=Diagnosis(
                        category="lint",
                        root_cause="IndentationError",
                        affected_files=["src/foo.py"],
                        suggested_fix="Run formatter",
                        confidence=0.9,
                    ),
                    fix_applied="[dry-run] Would apply lint fix",
                ),
            ],
            healed=False,
            total_attempts=1,
            final_status="dry_run",
        )
        output = format_heal_result(result)
        assert "DRY RUN" in output

    def test_format_multiple_attempts(self):
        result = HealResult(
            build_id="42",
            original_error="multiple issues",
            attempts=[
                HealAttempt(
                    attempt=1,
                    diagnosis=Diagnosis(
                        category="lint",
                        root_cause="IndentationError",
                        affected_files=["src/a.py"],
                        suggested_fix="Format",
                        confidence=0.9,
                    ),
                    fix_applied="Auto-formatted with black",
                    success=False,
                ),
                HealAttempt(
                    attempt=2,
                    diagnosis=Diagnosis(
                        category="test",
                        root_cause="AssertionError in test_api",
                        affected_files=["tests/test_api.py"],
                        suggested_fix="Fix assertion",
                        confidence=0.7,
                    ),
                    fix_applied="Updated test assertion",
                    success=True,
                ),
            ],
            healed=True,
            total_attempts=2,
            final_status="healed",
        )
        output = format_heal_result(result)
        assert "Attempt 1" in output
        assert "Attempt 2" in output
        assert "FIXED" in output


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_extract_error_snippet(self):
        snippet = _extract_error_snippet(LINT_LOG)
        assert len(snippet) <= 500
        assert "error" in snippet.lower() or "reformat" in snippet.lower()

    def test_extract_error_snippet_fallback(self):
        snippet = _extract_error_snippet("line1\nline2\nline3\n")
        assert snippet  # Should return something from last lines

    def test_suggest_fix_lint(self):
        fix = _suggest_fix("lint", "IndentationError", ["foo.py"])
        assert "format" in fix.lower()

    def test_suggest_fix_dependency(self):
        fix = _suggest_fix("dependency", "ModuleNotFoundError", ["app.py"])
        assert "install" in fix.lower() or "dependency" in fix.lower()

    def test_suggest_fix_unknown(self):
        fix = _suggest_fix("unknown", "???", [])
        assert "manual" in fix.lower()

    def test_compute_confidence_lint(self):
        c = _compute_confidence("lint", LINT_LOG, None)
        assert 0.5 < c <= 1.0

    def test_compute_confidence_unknown(self):
        c = _compute_confidence("other", "", None)
        assert c == 0.3

    def test_affected_files_caps_at_20(self):
        log = "\n".join(f'  File "src/file_{i}.py", line {i}' for i in range(30))
        files = _extract_affected_files(log)
        assert len(files) <= 20


# ---------------------------------------------------------------------------
# TestFetchLogs
# ---------------------------------------------------------------------------


class TestFetchLogs:
    """Test log fetching from different sources."""

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_fetch_github_logs(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="FAILED test_foo", stderr="")
        healer = CISelfHealer(cwd="/tmp/test-repo")
        logs = healer._fetch_github_logs("12345")
        assert "FAILED" in logs
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "12345" in cmd

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_fetch_jenkins_logs_with_url(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Build failed", stderr="")
        healer = CISelfHealer(cwd="/tmp/test-repo")
        logs = healer._fetch_jenkins_logs("42", "http://jenkins/job/myapp/42")
        assert "Build failed" in logs

    def test_fetch_generic_from_file(self, tmp_path):
        log_file = tmp_path / "build.log"
        log_file.write_text("SyntaxError in foo.py")
        healer = CISelfHealer(cwd=str(tmp_path))
        logs = healer._fetch_generic_logs(str(log_file))
        assert "SyntaxError" in logs

    def test_fetch_generic_missing_file(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")
        logs = healer._fetch_generic_logs("/nonexistent/path")
        assert logs == ""


# ---------------------------------------------------------------------------
# TestRetrigger
# ---------------------------------------------------------------------------


class TestRetrigger:
    """Test build re-trigger logic."""

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_retrigger_github(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        healer = CISelfHealer(cwd="/tmp/test-repo")
        result = healer._retrigger_github("12345")
        assert result == "12345"
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "rerun" in cmd

    @patch("code_agents.devops.ci_self_heal.subprocess.run")
    def test_retrigger_jenkins(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        healer = CISelfHealer(cwd="/tmp/test-repo")
        result = healer._retrigger_jenkins("http://jenkins/job/app/42")
        assert result  # Should return the trigger URL

    def test_retrigger_github_no_build_id(self):
        healer = CISelfHealer(cwd="/tmp/test-repo")
        result = healer._retrigger_github("")
        assert result == ""
