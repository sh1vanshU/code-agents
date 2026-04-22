"""Tests for complexity.py — code complexity analyzer."""

import os
import tempfile
from pathlib import Path

import pytest

from code_agents.analysis.complexity import (
    ComplexityAnalyzer, ComplexityReport, FunctionComplexity,
    FileComplexity, format_complexity_report,
)


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python repo with functions of varying complexity."""
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")

    (tmp_path / "simple.py").write_text(
        "def hello():\n"
        "    return 'world'\n"
    )

    (tmp_path / "complex.py").write_text(
        "def process(data):\n"
        "    if data is None:\n"
        "        return\n"
        "    for item in data:\n"
        "        if item > 0:\n"
        "            if item > 100:\n"
        "                print('big')\n"
        "            elif item > 50:\n"
        "                print('medium')\n"
        "            else:\n"
        "                print('small')\n"
        "        else:\n"
        "            print('negative')\n"
    )

    (tmp_path / "boolops.py").write_text(
        "def check(a, b, c):\n"
        "    if a and b or c:\n"
        "        return True\n"
        "    return False\n"
    )

    return tmp_path


@pytest.fixture
def java_repo(tmp_path):
    """Create a minimal Java repo."""
    (tmp_path / "pom.xml").write_text("<project></project>")
    src = tmp_path / "src"
    src.mkdir()
    (src / "Main.java").write_text(
        "public class Main {\n"
        "    public void simple() {\n"
        "        System.out.println(\"hello\");\n"
        "    }\n"
        "    public int calculate(int x) {\n"
        "        if (x > 0) {\n"
        "            for (int i = 0; i < x; i++) {\n"
        "                if (i % 2 == 0) {\n"
        "                    return i;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        return -1;\n"
        "    }\n"
        "}\n"
    )
    return tmp_path


class TestComplexityAnalyzer:
    """Tests for ComplexityAnalyzer."""

    def test_detect_python(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        assert analyzer.language == "python"

    def test_detect_java(self, java_repo):
        analyzer = ComplexityAnalyzer(cwd=str(java_repo))
        assert analyzer.language == "java"

    def test_python_simple_function(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        report = analyzer.analyze()
        # Find the hello() function
        all_funcs = [f for fc in report.files for f in fc.functions]
        hello = [f for f in all_funcs if f.name == "hello"]
        assert len(hello) == 1
        assert hello[0].cyclomatic == 1  # no branching
        assert hello[0].rating == "A"

    def test_python_complex_function(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        report = analyzer.analyze()
        all_funcs = [f for fc in report.files for f in fc.functions]
        process = [f for f in all_funcs if f.name == "process"]
        assert len(process) == 1
        # if + for + if + if(elif) + else branches
        assert process[0].cyclomatic > 3
        assert process[0].nesting_depth >= 2

    def test_python_boolops(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        report = analyzer.analyze()
        all_funcs = [f for fc in report.files for f in fc.functions]
        check = [f for f in all_funcs if f.name == "check"]
        assert len(check) == 1
        # 1 base + 1 if + 2 bool ops (and, or)
        assert check[0].cyclomatic >= 3

    def test_java_analysis(self, java_repo):
        analyzer = ComplexityAnalyzer(cwd=str(java_repo))
        report = analyzer.analyze()
        assert report.language == "java"
        assert report.total_functions >= 1

    def test_report_totals(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        report = analyzer.analyze()
        assert report.total_functions >= 3
        assert report.total_complexity > 0
        assert report.avg_complexity > 0

    def test_empty_repo(self, tmp_path):
        analyzer = ComplexityAnalyzer(cwd=str(tmp_path), language="python")
        report = analyzer.analyze()
        assert report.total_functions == 0


class TestFunctionComplexity:
    """Tests for FunctionComplexity rating."""

    def test_rating_a(self):
        fc = FunctionComplexity(file="x.py", name="f", line=1, cyclomatic=3, nesting_depth=1)
        assert fc.rating == "A"

    def test_rating_b(self):
        fc = FunctionComplexity(file="x.py", name="f", line=1, cyclomatic=8, nesting_depth=2)
        assert fc.rating == "B"

    def test_rating_c(self):
        fc = FunctionComplexity(file="x.py", name="f", line=1, cyclomatic=15, nesting_depth=3)
        assert fc.rating == "C"

    def test_rating_f(self):
        fc = FunctionComplexity(file="x.py", name="f", line=1, cyclomatic=55, nesting_depth=5)
        assert fc.rating == "F"


class TestFormatReport:
    """Tests for format_complexity_report."""

    def test_format_with_data(self, python_repo):
        analyzer = ComplexityAnalyzer(cwd=str(python_repo))
        report = analyzer.analyze()
        output = format_complexity_report(report)
        assert "Complexity Report" in output
        assert "Total functions" in output

    def test_format_empty(self):
        report = ComplexityReport(repo_path="/tmp", language="python")
        output = format_complexity_report(report)
        assert "No functions found" in output
