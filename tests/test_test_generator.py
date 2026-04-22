"""Tests for code_agents.tools.test_generator — AI-powered test generation pipeline."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

from code_agents.tools.test_generator import (
    FileAnalysis,
    GenerationResult,
    GenTestsReport,
    TestGenerator,
    format_gen_tests_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python project structure."""
    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")

    # Source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calculator.py").write_text(
        'def add(a, b):\n    """Add two numbers."""\n    return a + b\n\n'
        'def subtract(a, b):\n    """Subtract b from a."""\n    return a - b\n\n'
        'def _private():\n    pass\n'
    )
    (src / "auth.py").write_text(
        'class AuthService:\n    def login(self, user, pwd):\n        pass\n\n'
        '    def logout(self, token):\n        pass\n'
    )

    # Test directory with one existing test
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text(
        'def test_add():\n    from src.calculator import add\n    assert add(1, 2) == 3\n'
    )

    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """Create a minimal JS project structure."""
    (tmp_path / "package.json").write_text('{"name": "demo"}')
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.js").write_text(
        'function greet(name) { return `Hello ${name}`; }\nmodule.exports = { greet };\n'
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------


class TestStackDetection:
    def test_detect_python(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        assert gen.language == "python"
        assert gen.test_framework == "pytest"

    def test_detect_javascript(self, js_repo):
        gen = TestGenerator(repo_path=str(js_repo))
        assert gen.language == "javascript"
        assert gen.test_framework == "jest"

    def test_detect_java(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        gen = TestGenerator(repo_path=str(tmp_path))
        assert gen.language == "java"
        assert gen.test_framework == "junit"

    def test_detect_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/demo")
        gen = TestGenerator(repo_path=str(tmp_path))
        assert gen.language == "go"
        assert gen.test_framework == "go test"

    def test_detect_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        gen = TestGenerator(repo_path=str(tmp_path))
        assert gen.language == "java"

    def test_no_stack(self, tmp_path):
        gen = TestGenerator(repo_path=str(tmp_path))
        assert gen.language == ""


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


class TestDiscoverFiles:
    def test_discover_python_files(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        files = gen.discover_files()
        names = [os.path.basename(f) for f in files]
        assert "calculator.py" in names
        assert "auth.py" in names
        # Should skip __init__.py
        assert "__init__.py" not in names

    def test_discover_single_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo), target_path="src/calculator.py")
        files = gen.discover_files()
        assert len(files) == 1
        assert files[0].endswith("calculator.py")

    def test_discover_skips_test_dirs(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        files = gen.discover_files()
        for f in files:
            assert "/tests/" not in f and "/test/" not in f


# ---------------------------------------------------------------------------
# File analysis
# ---------------------------------------------------------------------------


class TestAnalyzeFile:
    def test_analyze_python_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/calculator.py")

        assert analysis.language == "python"
        assert analysis.loc > 0
        func_names = [f["name"] for f in analysis.functions]
        assert "add" in func_names
        assert "subtract" in func_names

    def test_finds_existing_test_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/calculator.py")
        assert analysis.existing_test_file == "tests/test_calculator.py"

    def test_identifies_missing_tests(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/calculator.py")
        assert "subtract" in analysis.missing_tests

    def test_skips_private_functions(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/calculator.py")
        assert "_private" not in analysis.missing_tests

    def test_risk_scoring_critical(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/auth.py")
        assert analysis.risk == "critical"  # "auth" in path

    def test_no_existing_test_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = gen.analyze_file("src/auth.py")
        assert analysis.existing_test_file == ""


class TestAnalyzeAll:
    def test_analyze_all_finds_gaps(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analyses = gen.analyze_all()
        assert len(analyses) >= 1
        assert gen.report.files_analyzed >= 2

    def test_respects_max_files(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo), max_files=1)
        analyses = gen.analyze_all()
        assert len(analyses) <= 1

    def test_sorts_by_risk(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analyses = gen.analyze_all()
        if len(analyses) >= 2:
            risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for i in range(len(analyses) - 1):
                assert risk_order.get(analyses[i].risk, 99) <= risk_order.get(analyses[i + 1].risk, 99)


# ---------------------------------------------------------------------------
# Test path generation
# ---------------------------------------------------------------------------


class TestGetTestPath:
    def test_python_test_path(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(file_path="src/utils.py", abs_path="", language="python")
        path = gen._get_test_path(analysis)
        assert path == "tests/test_utils.py"

    def test_uses_existing_test_path(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(
            file_path="src/calc.py", abs_path="",
            language="python", existing_test_file="tests/test_calc.py",
        )
        path = gen._get_test_path(analysis)
        assert path == "tests/test_calc.py"

    def test_js_test_path(self, js_repo):
        gen = TestGenerator(repo_path=str(js_repo))
        analysis = FileAnalysis(file_path="src/utils.js", abs_path="", language="javascript")
        path = gen._get_test_path(analysis)
        assert path == "src/utils.test.js"

    def test_go_test_path(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x")
        gen = TestGenerator(repo_path=str(tmp_path))
        analysis = FileAnalysis(file_path="pkg/handler.go", abs_path="", language="go")
        path = gen._get_test_path(analysis)
        assert path == "pkg/handler_test.go"

    def test_java_test_path(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        gen = TestGenerator(repo_path=str(tmp_path))
        analysis = FileAnalysis(
            file_path="src/main/java/com/example/Service.java",
            abs_path="", language="java",
        )
        path = gen._get_test_path(analysis)
        assert path == "src/test/java/com/example/ServiceTest.java"


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


class TestExtractCode:
    def test_extract_from_python_fence(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        response = "Here are the tests:\n```python\nimport pytest\n\ndef test_foo():\n    assert True\n```\nDone."
        code = gen._extract_code(response)
        assert "import pytest" in code
        assert "def test_foo" in code
        assert "Here are" not in code

    def test_extract_from_generic_fence(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        response = "```\nimport os\ndef test_bar():\n    pass\n```"
        code = gen._extract_code(response)
        assert "import os" in code

    def test_extract_raw_code(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        response = "import pytest\n\ndef test_one():\n    assert 1 == 1\n"
        code = gen._extract_code(response)
        assert "import pytest" in code

    def test_extract_longest_code_block(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        response = (
            "```python\nshort\n```\n\n"
            "```python\nimport pytest\ndef test_a():\n    pass\ndef test_b():\n    pass\n```"
        )
        code = gen._extract_code(response)
        assert "test_b" in code


# ---------------------------------------------------------------------------
# Test pattern scanning
# ---------------------------------------------------------------------------


class TestScanTestPatterns:
    def test_scans_existing_tests(self, python_repo):
        # Ensure the test file is long enough (>100 chars) to be picked up
        test_content = (
            'import pytest\n\n'
            'class TestCalculator:\n'
            '    def test_add(self):\n'
            '        assert 1 + 2 == 3\n\n'
            '    def test_subtract(self):\n'
            '        assert 5 - 3 == 2\n\n'
            '    def test_multiply(self):\n'
            '        assert 2 * 3 == 6\n'
        )
        (python_repo / "tests" / "test_calculator.py").write_text(test_content)
        gen = TestGenerator(repo_path=str(python_repo))
        style = gen.scan_test_patterns()
        assert "def test_add" in style

    def test_no_test_dir(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        gen = TestGenerator(repo_path=str(tmp_path))
        style = gen.scan_test_patterns()
        assert style == ""


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_prompt_includes_source(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(
            file_path="src/calculator.py",
            abs_path=str(python_repo / "src" / "calculator.py"),
            language="python",
            functions=[{"name": "add", "signature": "def add(a, b)", "line": 1, "docstring": "Add two numbers."}],
            missing_tests=["subtract"],
        )
        prompt = gen._build_generation_prompt(analysis, "def add(a, b): return a + b", "", "")
        assert "src/calculator.py" in prompt
        assert "subtract" in prompt
        assert "def add(a, b)" in prompt

    def test_prompt_includes_existing_tests(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(
            file_path="src/calc.py",
            abs_path=str(python_repo / "src" / "calculator.py"),
            language="python",
            existing_test_file="tests/test_calc.py",
            existing_test_methods=["test_add", "test_subtract"],
            missing_tests=["multiply"],
        )
        prompt = gen._build_generation_prompt(analysis, "code", "", "")
        assert "DO NOT duplicate" in prompt
        assert "test_add" in prompt


# ---------------------------------------------------------------------------
# Write & verify
# ---------------------------------------------------------------------------


class TestWriteTestFile:
    def test_writes_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        ok = gen._write_test_file("tests/test_new.py", "def test_x():\n    pass\n")
        assert ok
        assert (python_repo / "tests" / "test_new.py").exists()

    def test_creates_directories(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        ok = gen._write_test_file("new_dir/test_deep.py", "pass")
        assert ok
        assert (python_repo / "new_dir" / "test_deep.py").exists()


class TestRunTestFile:
    def test_run_python_tests(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        test_path = "tests/test_simple.py"
        gen._write_test_file(test_path, "def test_pass():\n    assert True\n")
        result = gen._run_test_file(test_path)
        assert result["passed"] is True
        assert result["passed_count"] >= 1

    def test_run_failing_test(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        test_path = "tests/test_fail.py"
        gen._write_test_file(test_path, "def test_fail():\n    assert False\n")
        result = gen._run_test_file(test_path)
        assert result["passed"] is False
        assert result["failed_count"] >= 1


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_basic_report(self):
        report = GenTestsReport(
            repo_path="/tmp/demo",
            target_path="src/",
            files_analyzed=10,
            files_with_gaps=3,
            files_generated=2,
            total_tests_written=15,
            results=[
                GenerationResult(
                    source_file="src/a.py",
                    test_file="tests/test_a.py",
                    tests_written=8,
                ),
                GenerationResult(
                    source_file="src/b.py",
                    test_file="tests/test_b.py",
                    tests_written=7,
                    error="timeout",
                ),
            ],
        )
        output = format_gen_tests_report(report)
        assert "AI TEST GENERATOR" in output
        assert "src/a.py" in output
        assert "timeout" in output
        assert "15 tests" in output

    def test_format_empty_report(self):
        report = GenTestsReport(repo_path="/tmp", target_path="")
        output = format_gen_tests_report(report)
        assert "AI TEST GENERATOR" in output

    def test_format_with_verify_info(self):
        report = GenTestsReport(
            repo_path="/tmp",
            target_path="",
            files_generated=1,
            total_tests_written=5,
            total_tests_passed=4,
            total_tests_failed=1,
            results=[
                GenerationResult(
                    source_file="src/x.py",
                    test_file="tests/test_x.py",
                    tests_written=5,
                    tests_passed=4,
                    tests_failed=1,
                    retries=2,
                ),
            ],
        )
        output = format_gen_tests_report(report)
        assert "4 passed" in output
        assert "2 retries" in output


# ---------------------------------------------------------------------------
# Full pipeline (mocked delegation)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_dry_run(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo), dry_run=True)
        report = await gen.run()
        assert report.files_analyzed >= 2
        assert report.files_with_gaps >= 1
        assert report.files_generated >= 1
        for r in report.results:
            assert r.test_code == ""

    @pytest.mark.asyncio
    async def test_pipeline_with_mocked_agent(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo), max_files=1)

        mock_response = (
            "import pytest\n\n"
            "def test_subtract():\n"
            "    from src.calculator import subtract\n"
            "    assert subtract(5, 3) == 2\n\n"
            "def test_subtract_negative():\n"
            "    from src.calculator import subtract\n"
            "    assert subtract(1, 5) == -4\n"
        )

        with patch.object(gen, "_delegate_to_agent", return_value=mock_response):
            report = await gen.run()

        assert report.files_generated >= 1
        assert report.total_tests_written >= 1

    @pytest.mark.asyncio
    async def test_progress_callback(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo), dry_run=True)
        steps = []

        def on_progress(step, detail):
            steps.append(step)

        await gen.run(on_progress=on_progress)
        assert "analyze" in steps
        assert "done" in steps


# ---------------------------------------------------------------------------
# Dependency context (mocked knowledge graph)
# ---------------------------------------------------------------------------


class TestDependencyContext:
    def test_returns_empty_when_kg_unavailable(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(file_path="src/calc.py", abs_path="", language="python")
        ctx = gen.get_dependency_context(analysis)
        assert ctx == ""

    def test_returns_context_when_kg_available(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        analysis = FileAnalysis(file_path="src/calc.py", abs_path="", language="python")

        mock_kg = MagicMock()
        mock_kg.is_built.return_value = True
        mock_kg.query.return_value = [
            {"file": "src/utils.py", "name": "helper", "kind": "function"},
        ]

        with patch("code_agents.knowledge.knowledge_graph.KnowledgeGraph", return_value=mock_kg):
            ctx = gen.get_dependency_context(analysis)
            assert "utils.py" in ctx


# ---------------------------------------------------------------------------
# Extract test methods from existing files
# ---------------------------------------------------------------------------


class TestExtractTestMethods:
    def test_python_methods(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        methods = gen._extract_test_methods("tests/test_calculator.py")
        assert "test_add" in methods

    def test_nonexistent_file(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        methods = gen._extract_test_methods("tests/test_nonexistent.py")
        assert methods == []


# ---------------------------------------------------------------------------
# Find test file
# ---------------------------------------------------------------------------


class TestFindTestFile:
    def test_finds_python_test(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        result = gen._find_test_file("src/calculator.py")
        assert result == "tests/test_calculator.py"

    def test_no_match(self, python_repo):
        gen = TestGenerator(repo_path=str(python_repo))
        result = gen._find_test_file("src/auth.py")
        assert result == ""
