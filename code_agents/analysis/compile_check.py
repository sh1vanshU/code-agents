"""Compile Check — auto-verify code compiles after agent writes it.

Detects Java/Go/TypeScript code blocks in agent responses and runs
the appropriate compile command. Optional via CODE_AGENTS_AUTO_COMPILE env var.

Usage:
    checker = CompileChecker(cwd="/path/to/project")
    if checker.should_check(agent_response):
        result = checker.run_compile()
        print(checker.format_result(result))
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.compile_check")

# Compile timeout — generous for large projects
COMPILE_TIMEOUT = 120  # seconds


@dataclass
class CompileResult:
    """Result of a compile check."""

    success: bool
    language: str
    command: str
    elapsed: float = 0.0
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_auto_compile_enabled() -> bool:
    """Check if auto-compile is enabled via env var (default: false)."""
    return os.getenv("CODE_AGENTS_AUTO_COMPILE", "false").strip().lower() in (
        "1", "true", "yes",
    )


class CompileChecker:
    """Detect project language and run compile checks."""

    _UNSET = object()  # sentinel for "not yet detected"

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._language = CompileChecker._UNSET

    @property
    def language(self) -> Optional[str]:
        """Lazy-detect project language from build files."""
        if self._language is CompileChecker._UNSET:
            self._language = self._detect_language()
        return self._language

    def _detect_language(self) -> Optional[str]:
        """Detect project language from build files in cwd."""
        cwd = Path(self.cwd)

        # Java: Maven or Gradle
        if (cwd / "pom.xml").is_file():
            return "java-maven"
        if (cwd / "build.gradle").is_file() or (cwd / "build.gradle.kts").is_file():
            return "java-gradle"

        # Go
        if (cwd / "go.mod").is_file():
            return "go"

        # TypeScript
        if (cwd / "tsconfig.json").is_file():
            return "typescript"

        return None

    def _get_compile_command(self) -> Optional[str]:
        """Return the compile command for the detected language."""
        lang = self.language
        if not lang:
            return None

        cwd = Path(self.cwd)
        commands = {
            "java-maven": "mvn compile -q -DskipTests",
            "java-gradle": (
                "./gradlew compileJava -q"
                if (cwd / "gradlew").is_file()
                else "gradle compileJava -q"
            ),
            "go": "go build ./...",
            "typescript": "npx tsc --noEmit",
        }
        return commands.get(lang)

    def should_check(self, response: str) -> bool:
        """Check if response contains code blocks that should be compiled.

        Returns True if the response has ```java, ```go, or ```typescript
        code blocks AND the project has a matching build system.
        """
        if not response:
            return False

        # Map code block language tags to project language prefixes
        block_to_lang = {
            "```java": ("java-maven", "java-gradle"),
            "```go": ("go",),
            "```typescript": ("typescript",),
            "```ts": ("typescript",),
        }

        lang = self.language
        if not lang:
            return False

        for block_tag, lang_prefixes in block_to_lang.items():
            if block_tag in response and lang in lang_prefixes:
                return True

        return False

    def run_compile(self) -> CompileResult:
        """Run compile command and return result."""
        command = self._get_compile_command()
        if not command:
            return CompileResult(
                success=False,
                language=self.language or "unknown",
                command="",
                errors=["No compile command found for this project type."],
            )

        logger.info("Running compile check: %s (cwd=%s)", command, self.cwd)
        start = time.monotonic()

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT,
            )
            elapsed = time.monotonic() - start

            errors = _extract_errors(proc.stdout + proc.stderr, self.language or "")
            warnings = _extract_warnings(proc.stdout + proc.stderr, self.language or "")

            result = CompileResult(
                success=proc.returncode == 0,
                language=self.language or "unknown",
                command=command,
                elapsed=elapsed,
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode,
                errors=errors,
                warnings=warnings,
            )
            logger.info(
                "Compile check %s (%s, %.1fs, %d errors, %d warnings)",
                "passed" if result.success else "failed",
                result.language, elapsed, len(errors), len(warnings),
            )
            return result

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            logger.warning("Compile check timed out after %ds", COMPILE_TIMEOUT)
            return CompileResult(
                success=False,
                language=self.language or "unknown",
                command=command,
                elapsed=elapsed,
                errors=[f"Compile timed out after {COMPILE_TIMEOUT}s"],
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error("Compile check error: %s", e)
            return CompileResult(
                success=False,
                language=self.language or "unknown",
                command=command,
                elapsed=elapsed,
                errors=[f"Compile error: {e}"],
            )

    def format_result(self, result: CompileResult) -> str:
        """Format compile result for terminal display (plain text, no ANSI)."""
        if result.success:
            msg = f"Compilation successful ({result.elapsed:.1f}s)"
            if result.warnings:
                msg += f" with {len(result.warnings)} warning(s)"
            return msg

        lines = [f"Compilation failed ({result.elapsed:.1f}s)"]
        for err in result.errors[:10]:
            lines.append(f"  {err}")
        if len(result.errors) > 10:
            lines.append(f"  ... and {len(result.errors) - 10} more errors")
        return "\n".join(lines)


def _extract_errors(output: str, language: str) -> list[str]:
    """Extract error lines from compiler output."""
    errors = []
    for line in output.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Java errors: "src/Foo.java:45: error: ..."
        if language.startswith("java") and ": error:" in line_stripped:
            errors.append(line_stripped)
        # Go errors: "./main.go:10:5: ..."
        elif language == "go" and ".go:" in line_stripped and ":" in line_stripped:
            # Go compile errors typically have file:line:col: message
            parts = line_stripped.split(":")
            if len(parts) >= 4:
                errors.append(line_stripped)
        # TypeScript errors: "src/foo.ts(10,5): error TS..."
        elif language == "typescript" and "error TS" in line_stripped:
            errors.append(line_stripped)
        # Generic: lines containing "error" (case-insensitive) as fallback
        elif "error" in line_stripped.lower() and "warning" not in line_stripped.lower():
            # Skip lines that are just progress/info
            if any(skip in line_stripped.lower() for skip in ("downloading", "resolving", "info", "debug")):
                continue
            errors.append(line_stripped)
    return errors


def _extract_warnings(output: str, language: str) -> list[str]:
    """Extract warning lines from compiler output."""
    warnings = []
    for line in output.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if language.startswith("java") and ": warning:" in line_stripped:
            warnings.append(line_stripped)
        elif language == "go" and "warning" in line_stripped.lower():
            warnings.append(line_stripped)
        elif language == "typescript" and "warning" in line_stripped.lower():
            warnings.append(line_stripped)
    return warnings
