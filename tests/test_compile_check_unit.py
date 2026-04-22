"""Unit tests for code_agents/analysis/compile_check.py."""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from code_agents.analysis.compile_check import (
    CompileChecker,
    CompileResult,
    _extract_errors,
    _extract_warnings,
    is_auto_compile_enabled,
)


# ---------------------------------------------------------------------------
# CompileResult dataclass
# ---------------------------------------------------------------------------

class TestCompileResult:
    def test_defaults(self):
        r = CompileResult(success=True, language="go", command="go build ./...")
        assert r.success is True
        assert r.elapsed == 0.0
        assert r.errors == []
        assert r.warnings == []
        assert r.return_code == 0


# ---------------------------------------------------------------------------
# is_auto_compile_enabled
# ---------------------------------------------------------------------------

class TestAutoCompileEnabled:
    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENTS_AUTO_COMPILE", raising=False)
        assert is_auto_compile_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "True", " true "])
    def test_enabled(self, monkeypatch, val):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", val)
        assert is_auto_compile_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off"])
    def test_disabled(self, monkeypatch, val):
        monkeypatch.setenv("CODE_AGENTS_AUTO_COMPILE", val)
        assert is_auto_compile_enabled() is False


# ---------------------------------------------------------------------------
# CompileChecker._detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_java_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        cc = CompileChecker(str(tmp_path))
        assert cc.language == "java-maven"

    def test_java_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        cc = CompileChecker(str(tmp_path))
        assert cc.language == "java-gradle"

    def test_java_gradle_kts(self, tmp_path):
        (tmp_path / "build.gradle.kts").write_text("plugins { java }")
        cc = CompileChecker(str(tmp_path))
        assert cc.language == "java-gradle"

    def test_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo")
        cc = CompileChecker(str(tmp_path))
        assert cc.language == "go"

    def test_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        cc = CompileChecker(str(tmp_path))
        assert cc.language == "typescript"

    def test_none(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        assert cc.language is None

    def test_language_cached(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        cc = CompileChecker(str(tmp_path))
        _ = cc.language
        # Access again — should return cached value
        assert cc.language == "go"


# ---------------------------------------------------------------------------
# _get_compile_command
# ---------------------------------------------------------------------------

class TestGetCompileCommand:
    def test_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        cc = CompileChecker(str(tmp_path))
        assert cc._get_compile_command() == "mvn compile -q -DskipTests"

    def test_gradle_with_wrapper(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        (tmp_path / "gradlew").write_text("#!/bin/sh")
        cc = CompileChecker(str(tmp_path))
        assert "./gradlew" in cc._get_compile_command()

    def test_gradle_without_wrapper(self, tmp_path):
        (tmp_path / "build.gradle").write_text("")
        cc = CompileChecker(str(tmp_path))
        assert cc._get_compile_command().startswith("gradle ")

    def test_go_command(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        cc = CompileChecker(str(tmp_path))
        assert cc._get_compile_command() == "go build ./..."

    def test_typescript_command(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        cc = CompileChecker(str(tmp_path))
        assert cc._get_compile_command() == "npx tsc --noEmit"

    def test_none_language(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        assert cc._get_compile_command() is None


# ---------------------------------------------------------------------------
# should_check
# ---------------------------------------------------------------------------

class TestShouldCheck:
    def test_empty_response(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("") is False

    def test_no_language(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("```go\nfmt.Println()\n```") is False

    def test_matching_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("Here is code:\n```go\nfmt.Println()\n```") is True

    def test_matching_java(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("```java\nSystem.out.println();\n```") is True

    def test_matching_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("```typescript\nconst x = 1;\n```") is True

    def test_matching_ts_shorthand(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        cc = CompileChecker(str(tmp_path))
        assert cc.should_check("```ts\nconst x = 1;\n```") is True

    def test_non_matching_language(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        cc = CompileChecker(str(tmp_path))
        # Go project but java code block
        assert cc.should_check("```java\nSystem.out.println();\n```") is False


# ---------------------------------------------------------------------------
# run_compile
# ---------------------------------------------------------------------------

class TestRunCompile:
    def test_no_command(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        result = cc.run_compile()
        assert result.success is False
        assert "No compile command" in result.errors[0]

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_successful_compile(self, mock_run, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        cc = CompileChecker(str(tmp_path))
        result = cc.run_compile()
        assert result.success is True
        assert result.language == "go"

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_failed_compile(self, mock_run, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="./main.go:10:5: undefined: foo",
        )
        cc = CompileChecker(str(tmp_path))
        result = cc.run_compile()
        assert result.success is False
        assert result.return_code == 1

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_timeout(self, mock_run, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        mock_run.side_effect = subprocess.TimeoutExpired("go build", 120)
        cc = CompileChecker(str(tmp_path))
        result = cc.run_compile()
        assert result.success is False
        assert "timed out" in result.errors[0].lower()

    @patch("code_agents.analysis.compile_check.subprocess.run")
    def test_generic_exception(self, mock_run, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        mock_run.side_effect = OSError("no such command")
        cc = CompileChecker(str(tmp_path))
        result = cc.run_compile()
        assert result.success is False
        assert "error" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# format_result
# ---------------------------------------------------------------------------

class TestFormatResult:
    def test_success_no_warnings(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        r = CompileResult(success=True, language="go", command="go build", elapsed=1.23)
        out = cc.format_result(r)
        assert "successful" in out.lower()
        assert "1.2s" in out

    def test_success_with_warnings(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        r = CompileResult(success=True, language="go", command="go build", elapsed=0.5, warnings=["w1", "w2"])
        out = cc.format_result(r)
        assert "2 warning" in out

    def test_failure(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        r = CompileResult(
            success=False, language="go", command="go build", elapsed=2.0,
            errors=["err1", "err2"],
        )
        out = cc.format_result(r)
        assert "failed" in out.lower()
        assert "err1" in out

    def test_failure_many_errors(self, tmp_path):
        cc = CompileChecker(str(tmp_path))
        errors = [f"error{i}" for i in range(15)]
        r = CompileResult(success=False, language="java-maven", command="mvn", elapsed=3.0, errors=errors)
        out = cc.format_result(r)
        assert "5 more errors" in out


# ---------------------------------------------------------------------------
# _extract_errors
# ---------------------------------------------------------------------------

class TestExtractErrors:
    def test_java_errors(self):
        output = "src/Foo.java:45: error: cannot find symbol\nBUILD SUCCESS"
        errors = _extract_errors(output, "java-maven")
        assert any("cannot find symbol" in e for e in errors)

    def test_go_errors(self):
        output = "./main.go:10:5: undefined: foo\nsome info line"
        errors = _extract_errors(output, "go")
        assert any("undefined" in e for e in errors)

    def test_typescript_errors(self):
        output = "src/foo.ts(10,5): error TS2304: Cannot find name 'x'"
        errors = _extract_errors(output, "typescript")
        assert len(errors) >= 1

    def test_generic_fallback(self):
        output = "FATAL error: something broke"
        errors = _extract_errors(output, "unknown")
        assert len(errors) >= 1

    def test_skip_downloading_info_lines(self):
        output = "Downloading dependency...\nResolving plugins..."
        errors = _extract_errors(output, "java-maven")
        assert len(errors) == 0

    def test_empty_lines_skipped(self):
        output = "\n\n   \n"
        errors = _extract_errors(output, "go")
        assert errors == []


# ---------------------------------------------------------------------------
# _extract_warnings
# ---------------------------------------------------------------------------

class TestExtractWarnings:
    def test_java_warnings(self):
        output = "src/Foo.java:10: warning: unchecked cast"
        warnings = _extract_warnings(output, "java-maven")
        assert len(warnings) == 1

    def test_go_warnings(self):
        output = "WARNING: something\ninfo line"
        warnings = _extract_warnings(output, "go")
        assert len(warnings) == 1

    def test_typescript_warnings(self):
        output = "WARNING: experimental feature"
        warnings = _extract_warnings(output, "typescript")
        assert len(warnings) == 1

    def test_no_warnings(self):
        output = "BUILD SUCCESS"
        warnings = _extract_warnings(output, "java-maven")
        assert warnings == []

    def test_empty_lines_skipped(self):
        output = "\n  \n"
        warnings = _extract_warnings(output, "go")
        assert warnings == []
