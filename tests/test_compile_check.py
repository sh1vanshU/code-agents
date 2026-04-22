"""Tests for compile_check.py — compile verification after code generation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.analysis.compile_check import (
    CompileChecker,
    CompileResult,
    is_auto_compile_enabled,
    COMPILE_TIMEOUT,
)
from code_agents.analysis.compile_check import (
    _extract_errors,
    _extract_warnings,
)


# ---------------------------------------------------------------------------
# is_auto_compile_enabled
# ---------------------------------------------------------------------------


class TestAutoCompileEnabled:
    """Test CODE_AGENTS_AUTO_COMPILE env var detection."""

    def test_default_is_false(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENTS_AUTO_COMPILE", raising=False)
        assert is_auto_compile_enabled() is False

    def test_explicit_false(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "false")
        assert is_auto_compile_enabled() is False

    def test_explicit_true(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "true")
        assert is_auto_compile_enabled() is True

    def test_numeric_true(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "1")
        assert is_auto_compile_enabled() is True

    def test_yes_true(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "yes")
        assert is_auto_compile_enabled() is True

    def test_random_string_false(self, monkeypatch):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", "banana")
        assert is_auto_compile_enabled() is False


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    """Test project language detection from build files."""

    def test_maven_project(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "java-maven"

    def test_gradle_project(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "java-gradle"

    def test_gradle_kts_project(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { java }")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "java-gradle"

    def test_go_project(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "go"

    def test_typescript_project(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "typescript"

    def test_no_build_system(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language is None

    def test_maven_takes_priority_over_gradle(self, tmp_path):
        """If both pom.xml and build.gradle exist, Maven wins."""
        (tmp_path / "pom.xml").write_text("<project/>")
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.language == "java-maven"

    def test_language_is_lazy(self, tmp_path):
        """Language detection is lazy — only runs on first access."""
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._language is CompileChecker._UNSET  # not yet detected
        _ = checker.language
        assert checker._language is not CompileChecker._UNSET  # now detected (even if None result)


# ---------------------------------------------------------------------------
# should_check
# ---------------------------------------------------------------------------


class TestShouldCheck:
    """Test response scanning for compilable code blocks."""

    def test_java_block_with_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("Here is the code:\n```java\npublic class Foo {}\n```") is True

    def test_java_block_without_build_system(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```java\npublic class Foo {}\n```") is False

    def test_go_block_with_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module foo")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```go\npackage main\n```") is True

    def test_typescript_block_with_tsconfig(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```typescript\nconst x: number = 1;\n```") is True

    def test_ts_shorthand_block(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```ts\nconst x: number = 1;\n```") is True

    def test_python_block_not_checked(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```python\nprint('hello')\n```") is False

    def test_empty_response(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("") is False

    def test_no_code_blocks(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("Just some explanation text.") is False

    def test_mismatched_language(self, tmp_path):
        """Go code block in a Java project should not trigger."""
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker.should_check("```go\npackage main\n```") is False


# ---------------------------------------------------------------------------
# Compile command selection
# ---------------------------------------------------------------------------


class TestGetCompileCommand:
    """Test compile command selection per language."""

    def test_maven_command(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() == "mvn compile -q -DskipTests"

    def test_gradle_with_wrapper(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        (tmp_path / "gradlew").write_text("#!/bin/sh")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() == "./gradlew compileJava -q"

    def test_gradle_without_wrapper(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() == "gradle compileJava -q"

    def test_go_command(self, tmp_path):
        (tmp_path / "go.mod").write_text("module foo")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() == "go build ./..."

    def test_typescript_command(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() == "npx tsc --noEmit"

    def test_no_language_returns_none(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        assert checker._get_compile_command() is None


# ---------------------------------------------------------------------------
# run_compile
# ---------------------------------------------------------------------------


class TestRunCompile:
    """Test compile execution with mocked subprocess."""

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_successful_compile(self, mock_run, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        mock_run.return_value = MagicMock(
            returncode=0, stdout="BUILD SUCCESS", stderr=""
        )
        checker = CompileChecker(cwd=str(tmp_path))
        result = checker.run_compile()
        assert result.success is True
        assert result.language == "java-maven"
        assert result.return_code == 0
        mock_run.assert_called_once()
        # Verify timeout is set
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == COMPILE_TIMEOUT

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_failed_compile(self, mock_run, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="src/Foo.java:10: error: cannot find symbol\n",
        )
        checker = CompileChecker(cwd=str(tmp_path))
        result = checker.run_compile()
        assert result.success is False
        assert result.return_code == 1
        assert len(result.errors) > 0

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_timeout(self, mock_run, tmp_path):
        (tmp_path / "go.mod").write_text("module foo")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="go build", timeout=120)
        checker = CompileChecker(cwd=str(tmp_path))
        result = checker.run_compile()
        assert result.success is False
        assert "timed out" in result.errors[0].lower()

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_exception(self, mock_run, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        mock_run.side_effect = OSError("command not found")
        checker = CompileChecker(cwd=str(tmp_path))
        result = checker.run_compile()
        assert result.success is False
        assert "error" in result.errors[0].lower()

    def test_no_language_returns_failure(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        result = checker.run_compile()
        assert result.success is False
        assert "No compile command" in result.errors[0]


# ---------------------------------------------------------------------------
# Error/warning extraction
# ---------------------------------------------------------------------------


class TestExtractErrors:
    """Test error line extraction from compiler output."""

    def test_java_error(self):
        output = "src/PaymentService.java:45: error: cannot find symbol"
        errors = _extract_errors(output, "java-maven")
        assert len(errors) == 1
        assert "cannot find symbol" in errors[0]

    def test_go_error(self):
        output = "./main.go:10:5: undefined: fmt.Printlnx"
        errors = _extract_errors(output, "go")
        assert len(errors) == 1
        assert "undefined" in errors[0]

    def test_typescript_error(self):
        output = "src/app.ts(10,5): error TS2304: Cannot find name 'foo'"
        errors = _extract_errors(output, "typescript")
        assert len(errors) == 1
        assert "TS2304" in errors[0]

    def test_skips_download_lines(self):
        output = "Downloading https://repo.maven.apache.org/error-prone/1.0.jar"
        errors = _extract_errors(output, "java-maven")
        assert len(errors) == 0

    def test_empty_output(self):
        assert _extract_errors("", "java-maven") == []

    def test_multiple_errors(self):
        output = (
            "src/A.java:1: error: missing ;\n"
            "src/B.java:2: error: type mismatch\n"
        )
        errors = _extract_errors(output, "java-maven")
        assert len(errors) == 2


class TestExtractWarnings:
    """Test warning line extraction from compiler output."""

    def test_java_warning(self):
        output = "src/Foo.java:10: warning: [deprecation] method is deprecated"
        warnings = _extract_warnings(output, "java-maven")
        assert len(warnings) == 1

    def test_no_warnings(self):
        output = "BUILD SUCCESS"
        warnings = _extract_warnings(output, "java-maven")
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# format_result
# ---------------------------------------------------------------------------


class TestFormatResult:
    """Test result formatting."""

    def test_success_format(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checker = CompileChecker(cwd=str(tmp_path))
        result = CompileResult(
            success=True, language="java-maven", command="mvn compile", elapsed=2.3
        )
        formatted = checker.format_result(result)
        assert "successful" in formatted.lower()
        assert "2.3s" in formatted

    def test_success_with_warnings(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        result = CompileResult(
            success=True, language="java-maven", command="mvn compile",
            elapsed=1.5, warnings=["deprecation warning"]
        )
        formatted = checker.format_result(result)
        assert "1 warning" in formatted

    def test_failure_format(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        result = CompileResult(
            success=False, language="java-maven", command="mvn compile",
            elapsed=3.1, errors=["src/Foo.java:10: error: missing ;"]
        )
        formatted = checker.format_result(result)
        assert "failed" in formatted.lower()
        assert "missing ;" in formatted

    def test_many_errors_truncated(self, tmp_path):
        checker = CompileChecker(cwd=str(tmp_path))
        errors = [f"error {i}" for i in range(20)]
        result = CompileResult(
            success=False, language="go", command="go build",
            elapsed=1.0, errors=errors
        )
        formatted = checker.format_result(result)
        assert "10 more errors" in formatted


# ---------------------------------------------------------------------------
# CompileResult dataclass
# ---------------------------------------------------------------------------


class TestCompileResult:
    """Test CompileResult defaults."""

    def test_defaults(self):
        r = CompileResult(success=True, language="go", command="go build")
        assert r.elapsed == 0.0
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.return_code == 0
        assert r.errors == []
        assert r.warnings == []

    def test_custom_fields(self):
        r = CompileResult(
            success=False, language="typescript", command="npx tsc",
            elapsed=5.5, return_code=1,
            errors=["err1"], warnings=["warn1"],
        )
        assert r.elapsed == 5.5
        assert r.return_code == 1
        assert len(r.errors) == 1
        assert len(r.warnings) == 1
