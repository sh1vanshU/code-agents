"""Test Generator — AI-powered test generation for source files."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.generators.test_generator")


class TestGenerator:
    """Generates test code by analyzing source files."""

    def __init__(self, source_file: str, cwd: str):
        self.source_file = source_file
        self.cwd = cwd
        self.language = self._detect_language()
        self.framework = self._detect_test_framework()

    def _detect_language(self) -> str:
        """Detect language from file extension."""
        ext = Path(self.source_file).suffix.lower()
        return {
            ".py": "python",
            ".java": "java",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rb": "ruby",
            ".kt": "kotlin",
            ".scala": "scala",
        }.get(ext, "unknown")

    def _detect_test_framework(self) -> str:
        """Detect test framework from project files."""
        if self.language == "python":
            if os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
                return "pytest"
            return "unittest"
        elif self.language == "java":
            pom = os.path.join(self.cwd, "pom.xml")
            if os.path.exists(pom):
                try:
                    with open(pom) as f:
                        content = f.read()
                        if "junit-jupiter" in content or "junit5" in content:
                            return "junit5"
                        return "junit4"
                except OSError:
                    pass
            return "junit5"
        elif self.language in ("javascript", "typescript"):
            pkg = os.path.join(self.cwd, "package.json")
            if os.path.exists(pkg):
                try:
                    import json

                    with open(pkg) as f:
                        data = json.load(f)
                        deps = {
                            **data.get("devDependencies", {}),
                            **data.get("dependencies", {}),
                        }
                        if "jest" in deps:
                            return "jest"
                        if "mocha" in deps:
                            return "mocha"
                        if "vitest" in deps:
                            return "vitest"
                except (OSError, ValueError):
                    pass
            return "jest"
        elif self.language == "go":
            return "testing"
        return "unknown"

    def analyze_source(self) -> dict:
        """Analyze source file to extract testable units."""
        path = self.source_file
        if not os.path.isabs(path):
            path = os.path.join(self.cwd, path)

        with open(path) as f:
            content = f.read()

        analysis = {
            "file": self.source_file,
            "language": self.language,
            "framework": self.framework,
            "classes": [],
            "functions": [],
            "imports": [],
            "dependencies": [],  # external deps that need mocking
            "lines": len(content.split("\n")),
        }

        if self.language == "python":
            analysis["classes"] = re.findall(
                r"^class\s+(\w+)", content, re.MULTILINE
            )
            analysis["functions"] = re.findall(
                r"^def\s+(\w+)\s*\(", content, re.MULTILINE
            )
            analysis["imports"] = re.findall(
                r"^(?:from\s+\S+\s+)?import\s+(.+)$", content, re.MULTILINE
            )
            # Detect external deps (requests, subprocess, urllib, etc.)
            if "requests." in content or "import requests" in content:
                analysis["dependencies"].append("requests")
            if "subprocess." in content:
                analysis["dependencies"].append("subprocess")
            if "urllib" in content:
                analysis["dependencies"].append("urllib")
            if "open(" in content:
                analysis["dependencies"].append("filesystem")

        elif self.language == "java":
            analysis["classes"] = re.findall(r"class\s+(\w+)", content)
            analysis["functions"] = re.findall(
                r"(?:public|private|protected)\s+\w+\s+(\w+)\s*\(", content
            )
            if "@Autowired" in content or "@Inject" in content:
                analysis["dependencies"].append("spring-di")
            if "Repository" in content or "JpaRepository" in content:
                analysis["dependencies"].append("database")
            if "RestTemplate" in content or "WebClient" in content:
                analysis["dependencies"].append("http-client")

        elif self.language in ("javascript", "typescript"):
            analysis["functions"] = re.findall(
                r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", content
            )
            # Also match arrow functions: const name = ...=>
            analysis["functions"] += re.findall(
                r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
                content,
            )
            analysis["classes"] = re.findall(
                r"class\s+(\w+)", content
            )
            if "fetch(" in content:
                analysis["dependencies"].append("fetch")
            if "axios" in content:
                analysis["dependencies"].append("axios")
            if "fs." in content or "readFile" in content:
                analysis["dependencies"].append("filesystem")

        elif self.language == "go":
            analysis["functions"] = re.findall(
                r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\(", content, re.MULTILINE
            )
            if "http." in content:
                analysis["dependencies"].append("net/http")
            if "sql." in content:
                analysis["dependencies"].append("database/sql")
            if "os." in content:
                analysis["dependencies"].append("os")

        return analysis

    def generate_test_path(self) -> str:
        """Generate the test file path following project conventions."""
        src = Path(self.source_file)
        if self.language == "python":
            return f"tests/test_{src.stem}.py"
        elif self.language == "java":
            path_str = str(src).replace("src/main/java", "src/test/java")
            return path_str.replace(src.stem, f"{src.stem}Test")
        elif self.language in ("javascript", "typescript"):
            ext = ".test" + src.suffix
            return str(src.with_suffix(ext))
        elif self.language == "go":
            return str(src.with_suffix("")) + "_test.go"
        return f"tests/test_{src.stem}{src.suffix}"

    def build_prompt(self, analysis: dict) -> str:
        """Build the prompt for the AI agent to generate tests."""
        source_path = self.source_file
        if not os.path.isabs(source_path):
            source_path = os.path.join(self.cwd, source_path)

        with open(source_path) as f:
            source_code = f.read()

        mock_instructions = ""
        if analysis["dependencies"]:
            mock_lib = {
                "python": "unittest.mock / pytest-mock",
                "java": "Mockito",
                "javascript": "jest.mock",
                "typescript": "jest.mock",
                "go": "gomock",
            }.get(self.language, "mock framework")
            mock_instructions = (
                "\nMock these external dependencies:\n"
                + "\n".join(f"- {dep}" for dep in analysis["dependencies"])
                + f"\nUse appropriate mocking library ({mock_lib})."
            )

        return (
            f"Generate comprehensive tests for this {self.language} file.\n\n"
            f"**Source file:** `{self.source_file}`\n"
            f"**Test framework:** {self.framework}\n"
            f"**Test file path:** `{self.generate_test_path()}`\n\n"
            f"**Source code:**\n```{self.language}\n{source_code}\n```\n\n"
            f"**Analysis:**\n"
            f"- Classes: {', '.join(analysis['classes']) or 'none'}\n"
            f"- Functions: {', '.join(analysis['functions']) or 'none'}\n"
            f"- External dependencies to mock: {', '.join(analysis['dependencies']) or 'none'}\n"
            f"{mock_instructions}\n\n"
            f"**Requirements:**\n"
            f"1. Generate unit tests for EVERY public function/method\n"
            f"2. Include edge cases: null/None inputs, empty collections, boundary values\n"
            f"3. Include error cases: exceptions, invalid input, timeout scenarios\n"
            f"4. Mock all external dependencies (network, filesystem, database)\n"
            f"5. Use descriptive test names that explain the scenario\n"
            f"6. Include setup/teardown where needed\n"
            f"7. Add integration test class/describe block for key workflows\n"
            f"8. Target 80%+ code coverage\n"
            f"9. Follow {self.framework} best practices and conventions\n\n"
            f"Output ONLY the test code, no explanations."
        )


def format_analysis(analysis: dict) -> str:
    """Format analysis for terminal display."""
    lines = []
    lines.append(f"  File: {analysis['file']}")
    lines.append(
        f"  Language: {analysis['language']} | Framework: {analysis['framework']} | Lines: {analysis['lines']}"
    )
    if analysis["classes"]:
        lines.append(f"  Classes: {', '.join(analysis['classes'])}")
    if analysis["functions"]:
        funcs = analysis["functions"]
        if len(funcs) > 10:
            lines.append(f"  Functions ({len(funcs)}): {', '.join(funcs[:10])}...")
        else:
            lines.append(f"  Functions: {', '.join(funcs)}")
    if analysis["dependencies"]:
        lines.append(f"  Dependencies to mock: {', '.join(analysis['dependencies'])}")
    return "\n".join(lines)
