"""Test Style Matching — detect and match project test conventions.

Analyzes existing tests to profile the style (AAA vs BDD, assertion style,
fixture style, naming convention) and generates new tests matching the detected style.

Usage::

    from code_agents.testing.test_style import TestStyleAnalyzer

    analyzer = TestStyleAnalyzer("/path/to/repo")
    profile = analyzer.analyze()
    print(profile.pattern)   # "pytest-fixtures"
    test_code = analyzer.generate_matching("src/api.py")
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.testing.test_style")


# ---------------------------------------------------------------------------
# TestStyleProfile
# ---------------------------------------------------------------------------

@dataclass
class TestStyleProfile:
    """Describes the testing style used in a project."""

    pattern: str = "AAA"  # "AAA"|"BDD"|"pytest-fixtures"|"unittest-class"
    assertion_style: str = "assert"  # "assert"|"assertEqual"|"expect"
    fixture_style: str = "@pytest.fixture"  # "setUp"|"@pytest.fixture"|"beforeEach"
    naming: str = "test_X_when_Y"  # "test_should_X"|"test_X_when_Y"|"it_does_X"
    imports: list[str] = field(default_factory=list)  # common test imports
    avg_test_length: int = 10  # average lines per test
    uses_classes: bool = False  # whether tests are organized in classes
    mock_style: str = "unittest.mock"  # "unittest.mock"|"pytest-mock"|"monkeypatch"

    def summary(self) -> str:
        """Human-readable summary of the detected style."""
        lines = [
            f"Pattern:     {self.pattern}",
            f"Assertions:  {self.assertion_style}",
            f"Fixtures:    {self.fixture_style}",
            f"Naming:      {self.naming}",
            f"Classes:     {'Yes' if self.uses_classes else 'No'}",
            f"Mock style:  {self.mock_style}",
            f"Avg length:  ~{self.avg_test_length} lines",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TestStyleAnalyzer
# ---------------------------------------------------------------------------

class TestStyleAnalyzer:
    """Analyze test files to detect project style and generate matching tests."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._profile: TestStyleProfile | None = None
        logger.debug("TestStyleAnalyzer initialized for %s", cwd)

    def analyze(self) -> TestStyleProfile:
        """Analyze all test files and return detected style profile."""
        test_files = self._find_test_files()
        if not test_files:
            logger.info("No test files found in %s", self.cwd)
            return TestStyleProfile()

        logger.info("Analyzing %d test files", len(test_files))

        all_content: list[str] = []
        for tf in test_files[:50]:  # cap to avoid scanning huge repos
            try:
                content = Path(tf).read_text(encoding="utf-8", errors="ignore")
                all_content.append(content)
            except OSError:
                continue

        if not all_content:
            return TestStyleProfile()

        profile = TestStyleProfile(
            pattern=self._detect_pattern(all_content),
            assertion_style=self._detect_assertion_style(all_content),
            fixture_style=self._detect_fixture_style(all_content),
            naming=self._detect_naming(all_content),
            imports=self._detect_imports(all_content),
            avg_test_length=self._detect_avg_length(all_content),
            uses_classes=self._detect_uses_classes(all_content),
            mock_style=self._detect_mock_style(all_content),
        )

        self._profile = profile
        logger.info("Detected style: pattern=%s, assertions=%s, naming=%s",
                     profile.pattern, profile.assertion_style, profile.naming)
        return profile

    def generate_matching(self, source_file: str) -> str:
        """Generate test code matching the detected style for a source file.

        Args:
            source_file: Path to the source file to generate tests for.

        Returns:
            Generated test code matching the detected project style.
        """
        profile = self._profile or self.analyze()
        abs_path = self._resolve(source_file)

        if not os.path.isfile(abs_path):
            return f"# Error: file not found: {abs_path}"

        source = Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        functions = self._extract_functions(source)

        if not functions:
            return f"# No functions found in {source_file}"

        module_path = self._file_to_module(source_file)

        lines: list[str] = []
        lines.append(f'"""Tests for {source_file} — generated matching project style."""')
        lines.append("")

        # Imports matching style
        if profile.assertion_style == "assert":
            lines.append("import pytest")
        elif profile.assertion_style == "assertEqual":
            lines.append("import unittest")
        lines.append("")

        if profile.mock_style == "pytest-mock":
            lines.append("# Uses pytest-mock (mocker fixture)")
        elif profile.mock_style == "monkeypatch":
            lines.append("# Uses monkeypatch fixture")
        else:
            lines.append("from unittest.mock import patch, MagicMock")
        lines.append("")

        if module_path:
            func_names = ", ".join(f["name"] for f in functions if not f.get("is_method"))
            if func_names:
                lines.append(f"from {module_path} import {func_names}")
                lines.append("")

        # Generate tests
        if profile.uses_classes and profile.pattern == "unittest-class":
            lines.extend(self._gen_unittest_class(functions, profile))
        elif profile.uses_classes:
            lines.extend(self._gen_pytest_class(functions, profile))
        else:
            lines.extend(self._gen_pytest_functions(functions, profile))

        return "\n".join(lines)

    # --- Detection methods ---

    def _detect_pattern(self, contents: list[str]) -> str:
        """Detect test pattern: AAA, BDD, pytest-fixtures, unittest-class."""
        counts: Counter[str] = Counter()
        for c in contents:
            if "unittest.TestCase" in c or "self.assert" in c:
                counts["unittest-class"] += 3
            if "@pytest.fixture" in c:
                counts["pytest-fixtures"] += 2
            if re.search(r"\b(given|when|then)\b", c, re.IGNORECASE):
                counts["BDD"] += 1
            # AAA pattern: Arrange / Act / Assert comments or structure
            if "# arrange" in c.lower() or "# act" in c.lower() or "# assert" in c.lower():
                counts["AAA"] += 2
            # Default pytest with plain assert
            if "\nassert " in c or "\n    assert " in c:
                counts["AAA"] += 1

        if not counts:
            return "AAA"
        return counts.most_common(1)[0][0]

    def _detect_assertion_style(self, contents: list[str]) -> str:
        """Detect assertion style: assert, assertEqual, expect."""
        counts: Counter[str] = Counter()
        for c in contents:
            counts["assert"] += len(re.findall(r"^\s+assert\s", c, re.MULTILINE))
            counts["assertEqual"] += len(re.findall(r"self\.assert\w+\(", c))
            counts["expect"] += len(re.findall(r"\bexpect\(", c))
        if not counts:
            return "assert"
        return counts.most_common(1)[0][0]

    def _detect_fixture_style(self, contents: list[str]) -> str:
        """Detect fixture style."""
        counts: Counter[str] = Counter()
        for c in contents:
            counts["@pytest.fixture"] += c.count("@pytest.fixture")
            counts["setUp"] += c.count("def setUp(")
            counts["beforeEach"] += c.count("beforeEach")
        if not counts:
            return "@pytest.fixture"
        return counts.most_common(1)[0][0]

    def _detect_naming(self, contents: list[str]) -> str:
        """Detect test naming convention."""
        patterns: Counter[str] = Counter()
        for c in contents:
            # test_should_X
            patterns["test_should_X"] += len(re.findall(r"def test_should_\w+", c))
            # test_X_when_Y
            patterns["test_X_when_Y"] += len(re.findall(r"def test_\w+_when_\w+", c))
            # it_does_X (BDD style)
            patterns["it_does_X"] += len(re.findall(r"def it_\w+", c))
            # plain test_X
            patterns["test_X"] += len(re.findall(r"def test_\w+", c))

        # test_X is superset — subtract specific patterns
        patterns["test_X"] -= (patterns["test_should_X"] + patterns["test_X_when_Y"])
        if patterns["test_X"] < 0:
            patterns["test_X"] = 0

        if not patterns or max(patterns.values()) == 0:
            return "test_X_when_Y"

        winner = patterns.most_common(1)[0][0]
        # If plain test_X dominates, check if they have _when_ pattern
        return winner

    def _detect_imports(self, contents: list[str]) -> list[str]:
        """Detect common test imports."""
        import_counter: Counter[str] = Counter()
        for c in contents:
            for m in re.finditer(r"^(?:from|import)\s+([\w.]+)", c, re.MULTILINE):
                import_counter[m.group(1)] += 1
        # Return top imports
        return [imp for imp, _ in import_counter.most_common(10)]

    def _detect_avg_length(self, contents: list[str]) -> int:
        """Detect average test function length in lines."""
        lengths: list[int] = []
        for c in contents:
            in_test = False
            count = 0
            for line in c.splitlines():
                if re.match(r"\s+def test_", line) or re.match(r"def test_", line):
                    if in_test and count > 0:
                        lengths.append(count)
                    in_test = True
                    count = 0
                elif in_test:
                    if line.strip():
                        count += 1
                    elif count > 0 and not line.strip():
                        # Blank line may end test
                        pass
            if in_test and count > 0:
                lengths.append(count)
        return int(sum(lengths) / max(len(lengths), 1)) if lengths else 10

    def _detect_uses_classes(self, contents: list[str]) -> bool:
        """Detect whether tests are organized in classes."""
        class_count = 0
        func_count = 0
        for c in contents:
            class_count += len(re.findall(r"^class Test\w+", c, re.MULTILINE))
            func_count += len(re.findall(r"^def test_\w+", c, re.MULTILINE))
        return class_count > func_count * 0.3  # >30% ratio => classes

    def _detect_mock_style(self, contents: list[str]) -> str:
        """Detect mocking style."""
        counts: Counter[str] = Counter()
        for c in contents:
            counts["unittest.mock"] += c.count("from unittest.mock") + c.count("@patch")
            counts["pytest-mock"] += c.count("mocker.") + c.count("mocker,")
            counts["monkeypatch"] += c.count("monkeypatch.")
        if not counts:
            return "unittest.mock"
        return counts.most_common(1)[0][0]

    # --- Generation helpers ---

    def _gen_pytest_functions(self, functions: list[dict], profile: TestStyleProfile) -> list[str]:
        """Generate standalone pytest function tests."""
        lines: list[str] = []
        for f in functions:
            if f.get("is_method"):
                continue
            name = f["name"]
            params_str = ", ".join(f["params"]) if f["params"] else ""
            test_name = self._make_test_name(name, profile.naming)

            lines.append(f"def {test_name}():")
            lines.append(f'    """Test {name} with valid input."""')
            if params_str:
                lines.append(f"    # Arrange")
                for p in f["params"]:
                    lines.append(f"    {p} = None  # TODO: provide test value")
                lines.append(f"    # Act")
                lines.append(f"    result = {name}({params_str})")
            else:
                lines.append(f"    result = {name}()")
            lines.append(f"    # Assert")
            lines.append(f"    assert result is not None")
            lines.append("")
        return lines

    def _gen_pytest_class(self, functions: list[dict], profile: TestStyleProfile) -> list[str]:
        """Generate pytest-style class tests."""
        lines: list[str] = []
        class_name = "TestGenerated"
        lines.append(f"class {class_name}:")
        lines.append(f'    """Generated tests matching project style."""')
        lines.append("")

        for f in functions:
            if f.get("is_method"):
                continue
            name = f["name"]
            params_str = ", ".join(f["params"]) if f["params"] else ""
            test_name = self._make_test_name(name, profile.naming)

            lines.append(f"    def {test_name}(self):")
            lines.append(f'        """Test {name}."""')
            if params_str:
                for p in f["params"]:
                    lines.append(f"        {p} = None  # TODO")
                lines.append(f"        result = {name}({params_str})")
            else:
                lines.append(f"        result = {name}()")
            lines.append(f"        assert result is not None")
            lines.append("")
        return lines

    def _gen_unittest_class(self, functions: list[dict], profile: TestStyleProfile) -> list[str]:
        """Generate unittest-style class tests."""
        lines: list[str] = []
        lines.append("class TestGenerated(unittest.TestCase):")
        lines.append(f'    """Generated tests matching project style."""')
        lines.append("")

        for f in functions:
            if f.get("is_method"):
                continue
            name = f["name"]
            params_str = ", ".join(f["params"]) if f["params"] else ""
            test_name = self._make_test_name(name, profile.naming)

            lines.append(f"    def {test_name}(self):")
            lines.append(f'        """Test {name}."""')
            if params_str:
                for p in f["params"]:
                    lines.append(f"        {p} = None  # TODO")
                lines.append(f"        result = {name}({params_str})")
            else:
                lines.append(f"        result = {name}()")
            lines.append(f"        self.assertIsNotNone(result)")
            lines.append("")
        return lines

    def _make_test_name(self, func_name: str, naming: str) -> str:
        """Generate test function name matching naming convention."""
        if naming == "test_should_X":
            return f"test_should_{func_name}"
        elif naming == "it_does_X":
            return f"it_{func_name}_works"
        elif naming == "test_X_when_Y":
            return f"test_{func_name}_when_valid_input"
        else:
            return f"test_{func_name}"

    # --- Source parsing ---

    def _extract_functions(self, source: str) -> list[dict]:
        """Extract function names and params from source."""
        import ast as _ast
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return []

        functions: list[dict] = []
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
            is_method = any(a.arg == "self" for a in node.args.args)
            functions.append({"name": node.name, "params": params, "is_method": is_method})
        return functions

    # --- Utilities ---

    def _find_test_files(self) -> list[str]:
        """Find test files in the project."""
        test_files: list[str] = []
        for root, dirs, files in os.walk(self.cwd):
            # Skip hidden/venv directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".venv", "__pycache__")]
            for f in files:
                if f.startswith("test_") and f.endswith(".py"):
                    test_files.append(os.path.join(root, f))
                elif f.endswith("_test.py"):
                    test_files.append(os.path.join(root, f))
        return sorted(test_files)[:100]

    def _resolve(self, file_path: str) -> str:
        """Resolve file path."""
        if os.path.isabs(file_path):
            return file_path
        return os.path.join(self.cwd, file_path)

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module path."""
        p = file_path.replace(".py", "").replace("/", ".").replace("\\", ".").lstrip(".")
        if p.startswith("src."):
            p = p[4:]
        return p
