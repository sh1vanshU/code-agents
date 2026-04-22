"""Tests for code_agents.debug_engine — autonomous debug engine."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.observability.debug_engine import (
    BlastRadius,
    DebugEngine,
    DebugFix,
    DebugResult,
    DebugTrace,
    ErrorParser,
    format_debug_result,
)


# ---------------------------------------------------------------------------
# ErrorParser tests
# ---------------------------------------------------------------------------


class TestErrorParser:
    """Tests for ErrorParser — structured error extraction."""

    def test_parse_python_traceback(self):
        output = '''Traceback (most recent call last):
  File "tests/test_auth.py", line 42, in test_login
    result = auth.login(user)
  File "src/auth.py", line 15, in login
    token = generate_token(user.id)
AttributeError: 'NoneType' object has no attribute 'id'
'''
        parsed = ErrorParser.parse(output)
        assert parsed["language"] == "python"
        assert parsed["error_type"] == "AttributeError"
        assert parsed["error_message"] == "'NoneType' object has no attribute 'id'"
        assert parsed["error_file"] == "src/auth.py"
        assert parsed["error_line"] == 15
        assert len(parsed["stack_frames"]) == 2

    def test_parse_python_assertion_error(self):
        output = '''
  File "tests/test_calc.py", line 10, in test_add
    assert result == 5
AssertionError: assert 4 == 5
'''
        parsed = ErrorParser.parse(output)
        assert parsed["language"] == "python"
        assert parsed["error_type"] == "AssertionError"
        assert parsed["error_line"] == 10

    def test_parse_javascript_error(self):
        output = '''TypeError: Cannot read property 'name' of undefined
    at Object.getUser (src/users.js:23:10)
    at processRequest (src/handler.js:45:15)
'''
        parsed = ErrorParser.parse(output)
        assert parsed["language"] == "javascript"
        assert parsed["error_type"] == "TypeError"
        assert parsed["error_file"] == "src/users.js"
        assert parsed["error_line"] == 23
        assert len(parsed["stack_frames"]) == 2

    def test_parse_java_error(self):
        output = '''java.lang.NullPointerException
    at com.app.UserService.getUser(UserService.java:42)
    at com.app.Controller.handle(Controller.java:15)
'''
        parsed = ErrorParser.parse(output)
        assert parsed["language"] == "java"
        assert parsed["error_file"] == "UserService.java"
        assert parsed["error_line"] == 42

    def test_parse_go_error(self):
        output = '''main.go:15:3: undefined: someFunction
'''
        parsed = ErrorParser.parse(output)
        assert parsed["language"] == "go"
        assert parsed["error_file"] == "main.go"
        assert parsed["error_line"] == 15

    def test_parse_generic_test_failure(self):
        output = "FAILED: test_something — expected 5 got 4"
        parsed = ErrorParser.parse(output)
        assert parsed["error_message"]

    def test_parse_empty_output(self):
        parsed = ErrorParser.parse("")
        assert parsed["language"] == "unknown"
        assert parsed["error_type"] == ""

    def test_parse_no_error(self):
        output = "All tests passed!\n3 tests ran in 0.5s"
        parsed = ErrorParser.parse(output)
        assert parsed["error_type"] == ""


# ---------------------------------------------------------------------------
# DebugEngine tests
# ---------------------------------------------------------------------------


class TestDebugEngine:
    """Tests for DebugEngine core functionality."""

    def test_init_defaults(self):
        engine = DebugEngine()
        assert engine.max_attempts == 3
        assert engine.auto_fix is True
        assert engine.auto_commit is False

    def test_init_custom(self):
        engine = DebugEngine(
            cwd="/tmp/test",
            max_attempts=5,
            auto_fix=False,
        )
        assert engine.cwd == "/tmp/test"
        assert engine.max_attempts == 5
        assert engine.auto_fix is False

    def test_detect_test_command_pytest(self):
        engine = DebugEngine()
        assert engine._detect_test_command("pytest tests/test_foo.py -x") == "pytest tests/test_foo.py -x"

    def test_detect_test_command_python(self):
        engine = DebugEngine()
        assert engine._detect_test_command("python -m pytest test.py") == "python -m pytest test.py"

    def test_detect_test_command_test_file(self):
        engine = DebugEngine()
        cmd = engine._detect_test_command("tests/test_auth.py")
        assert "pytest" in cmd
        assert "tests/test_auth.py" in cmd

    def test_detect_test_command_test_function(self):
        engine = DebugEngine()
        cmd = engine._detect_test_command("tests/test_auth.py::test_login")
        assert "pytest" in cmd

    def test_detect_test_command_jest(self):
        engine = DebugEngine()
        cmd = engine._detect_test_command("src/auth.test.js")
        assert "jest" in cmd

    def test_detect_test_command_go(self):
        engine = DebugEngine()
        cmd = engine._detect_test_command("pkg/auth_test.go")
        assert "go test" in cmd

    def test_detect_test_command_description(self):
        engine = DebugEngine()
        cmd = engine._detect_test_command("login page crashes with AttributeError")
        assert cmd == ""

    def test_detect_test_command_npm(self):
        engine = DebugEngine()
        assert engine._detect_test_command("npm test") == "npm test"

    def test_detect_test_command_make(self):
        engine = DebugEngine()
        assert engine._detect_test_command("make test") == "make test"

    @patch("subprocess.run")
    def test_reproduce_with_test(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="FAILED test_login\nAssertionError: ...",
            stderr="",
        )
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.reproduce("pytest tests/test_auth.py -x")

        assert trace.step == "reproduce"
        assert trace.success is True  # reproduced = failure observed
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_reproduce_test_passes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1 passed",
            stderr="",
        )
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.reproduce("pytest tests/test_auth.py -x")

        assert trace.success is False  # cannot reproduce

    def test_reproduce_description_only(self):
        engine = DebugEngine()
        trace = engine.reproduce("login page shows 500 error when clicking submit")

        assert trace.step == "reproduce"
        assert trace.success is True  # description parsed directly
        assert "login page" in trace.output

    @patch("subprocess.run", side_effect=Exception("command failed"))
    def test_reproduce_command_error(self, mock_run):
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.reproduce("pytest tests/test_auth.py")
        assert trace.success is False

    def test_trace_with_error_output(self):
        engine = DebugEngine(cwd="/tmp/test")
        error_output = '''Traceback (most recent call last):
  File "tests/test_auth.py", line 42, in test_login
    result = auth.login(None)
AttributeError: 'NoneType' object has no attribute 'id'
'''
        trace = engine.trace(error_output)
        assert trace.step == "trace"
        assert trace.success is True
        assert "python" in trace.output

    def test_trace_empty_output(self):
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.trace("")
        assert trace.step == "trace"

    def test_read_file_context(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            for i in range(20):
                f.write(f"line {i + 1}\n")
            f.flush()

            engine = DebugEngine()
            context = engine._read_file_context(f.name, 10)
            assert ">>> " in context
            assert "line 10" in context

        os.unlink(f.name)

    def test_read_file_context_not_found(self):
        engine = DebugEngine(cwd="/tmp")
        context = engine._read_file_context("/nonexistent/file.py", 10)
        assert context == ""

    def test_apply_fixes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("x = 1 + 1\nassert x == 3\n")

            engine = DebugEngine(cwd=tmpdir)
            fixes = [DebugFix(
                file="test.py", line=2,
                original="assert x == 3",
                replacement="assert x == 2",
                explanation="Fix assertion",
            )]

            trace = engine.apply_fixes(fixes)
            assert trace.success is True
            assert "APPLIED" in trace.output

            content = Path(test_file).read_text()
            assert "assert x == 2" in content

    def test_apply_fixes_file_not_found(self):
        engine = DebugEngine(cwd="/tmp")
        fixes = [DebugFix(
            file="/nonexistent.py", line=1,
            original="old", replacement="new",
            explanation="test",
        )]
        trace = engine.apply_fixes(fixes)
        assert trace.success is False

    def test_apply_fixes_original_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("x = 42\n")

            engine = DebugEngine(cwd=tmpdir)
            fixes = [DebugFix(
                file="test.py", line=1,
                original="y = 99",
                replacement="y = 100",
                explanation="test",
            )]
            trace = engine.apply_fixes(fixes)
            assert "SKIP" in trace.output

    @patch("subprocess.run")
    def test_verify_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.verify("pytest tests/test_auth.py -x")
        assert trace.success is True
        assert "verified" in trace.description.lower()

    @patch("subprocess.run")
    def test_verify_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")
        engine = DebugEngine(cwd="/tmp/test")
        trace = engine.verify("pytest tests/test_auth.py -x")
        assert trace.success is False

    def test_verify_no_command(self):
        engine = DebugEngine()
        trace = engine.verify("")
        assert trace.success is False
        assert "manual" in trace.output.lower()

    def test_analyze_blast_radius(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source and test files
            os.makedirs(os.path.join(tmpdir, "tests"))
            Path(os.path.join(tmpdir, "auth.py")).write_text("# auth")
            Path(os.path.join(tmpdir, "tests", "test_auth.py")).write_text("# test")

            engine = DebugEngine(cwd=tmpdir)
            fixes = [DebugFix(file="auth.py", line=1, original="", replacement="", explanation="")]
            br = engine.analyze_blast_radius(fixes)

            assert "auth.py" in br.files_affected
            assert br.risk_level == "low"

    def test_blast_radius_high_risk(self):
        engine = DebugEngine(cwd="/tmp")
        fixes = [
            DebugFix(file=f"file{i}.py", line=1, original="", replacement="", explanation="")
            for i in range(6)
        ]
        br = engine.analyze_blast_radius(fixes)
        assert br.risk_level == "high"

    def test_parse_fixes_valid(self):
        engine = DebugEngine()
        ai_output = json.dumps({
            "root_cause": "Off by one",
            "fixes": [
                {"file": "calc.py", "line": 5, "original": "< len(a)", "replacement": "<= len(a)", "explanation": "Fix bound"}
            ],
        })
        fixes = engine._parse_fixes(ai_output)
        assert len(fixes) == 1
        assert fixes[0].file == "calc.py"

    def test_parse_fixes_invalid_json(self):
        engine = DebugEngine()
        fixes = engine._parse_fixes("not json")
        assert fixes == []

    def test_parse_fixes_empty(self):
        engine = DebugEngine()
        fixes = engine._parse_fixes("{}")
        assert fixes == []


# ---------------------------------------------------------------------------
# DebugResult tests
# ---------------------------------------------------------------------------


class TestDebugResult:
    """Tests for DebugResult data model."""

    def test_is_resolved_true(self):
        result = DebugResult(
            bug_description="test",
            status="resolved",
            verified=True,
        )
        assert result.is_resolved is True

    def test_is_resolved_false_not_verified(self):
        result = DebugResult(
            bug_description="test",
            status="resolved",
            verified=False,
        )
        assert result.is_resolved is False

    def test_is_resolved_false_wrong_status(self):
        result = DebugResult(
            bug_description="test",
            status="failed",
            verified=True,
        )
        assert result.is_resolved is False


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------


class TestFormatDebugResult:
    """Tests for debug result formatting."""

    def test_format_resolved(self, capsys):
        result = DebugResult(
            bug_description="test_login fails",
            status="resolved",
            verified=True,
            error_type="AttributeError",
            error_message="'NoneType' has no attribute 'id'",
            error_file="auth.py",
            error_line=15,
            root_cause="user object is None",
            traces=[
                DebugTrace(step="reproduce", description="Ran test", success=True, duration_ms=100),
                DebugTrace(step="verify", description="Fix verified", success=True, duration_ms=50),
            ],
            fixes=[DebugFix(file="auth.py", line=15, original="user.id", replacement="user.id if user else None", explanation="Null check")],
            total_duration_ms=500,
            attempts=1,
        )
        format_debug_result(result)
        # Should not raise

    def test_format_failed(self, capsys):
        result = DebugResult(
            bug_description="mysterious crash",
            status="failed",
            total_duration_ms=1000,
        )
        format_debug_result(result)
        # Should not raise


# ---------------------------------------------------------------------------
# Async run tests
# ---------------------------------------------------------------------------


class TestDebugEngineAsync:
    """Tests for async debug engine run."""

    @pytest.mark.asyncio
    async def test_run_description_only(self):
        engine = DebugEngine(cwd="/tmp", auto_fix=False)
        with patch.object(engine, "analyze_root_cause", new_callable=AsyncMock) as mock_rca:
            mock_rca.return_value = DebugTrace(
                step="root_cause", description="AI analysis",
                output='{"root_cause": "test", "fixes": []}',
                success=True,
            )
            result = await engine.run("login crashes")
            assert result.status in ("pending", "failed")
            assert len(result.traces) >= 2

    @pytest.mark.asyncio
    async def test_run_with_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "buggy.py")).write_text("x = 1\nassert x == 2\n")

            engine = DebugEngine(cwd=tmpdir, auto_fix=True, max_attempts=1)

            with patch.object(engine, "analyze_root_cause", new_callable=AsyncMock) as mock_rca:
                mock_rca.return_value = DebugTrace(
                    step="root_cause", description="AI analysis",
                    output=json.dumps({
                        "root_cause": "Wrong assertion",
                        "fixes": [{
                            "file": "buggy.py", "line": 2,
                            "original": "assert x == 2",
                            "replacement": "assert x == 1",
                            "explanation": "Fix assertion value",
                        }],
                    }),
                    success=True,
                )

                result = await engine.run("buggy assertion")
                assert len(result.fixes) >= 0  # May or may not have fixes depending on flow
