"""Tests for the CodeExplainer module."""

import os
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from code_agents.knowledge.explain_code import CodeExplainer, ExplainConfig, CodeExplanation, format_explanation


class TestCodeExplainer:
    """Test CodeExplainer functionality."""

    def test_config_defaults(self):
        config = ExplainConfig()
        assert config.cwd == "."
        assert config.include_edge_cases is True
        assert config.max_depth == 2

    def test_parse_target_with_symbol(self):
        config = ExplainConfig(cwd="/tmp")
        explainer = CodeExplainer(config)
        file_path, symbol = explainer._parse_target("code_agents/stream.py:build_prompt")
        assert file_path == "code_agents/stream.py"
        assert symbol == "build_prompt"

    def test_parse_target_without_symbol(self):
        config = ExplainConfig(cwd="/tmp")
        explainer = CodeExplainer(config)
        file_path, symbol = explainer._parse_target("code_agents/stream.py")
        assert file_path == "code_agents/stream.py"
        assert symbol == ""

    def test_explain_missing_file(self):
        config = ExplainConfig(cwd="/nonexistent")
        explainer = CodeExplainer(config)
        result = explainer.explain("nonexistent.py:foo")
        assert "not found" in result.summary.lower() or "not found" in result.detailed.lower()

    def test_explain_python_function(self, tmp_path):
        source = textwrap.dedent('''\
            """A test module."""

            def add_numbers(a: int, b: int) -> int:
                """Add two numbers."""
                return a + b

            def multiply(x, y):
                result = x * y
                return result
        ''')
        test_file = tmp_path / "sample.py"
        test_file.write_text(source)

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        result = explainer.explain("sample.py:add_numbers")

        assert result.target_type == "function"
        assert result.target == "sample.py:add_numbers"
        assert "int" in result.signature
        assert result.docstring == "Add two numbers."

    def test_explain_python_class(self, tmp_path):
        source = textwrap.dedent('''\
            class Calculator:
                """A simple calculator."""

                def add(self, a, b):
                    return a + b

                def subtract(self, a, b):
                    return a - b
        ''')
        test_file = tmp_path / "calc.py"
        test_file.write_text(source)

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        result = explainer.explain("calc.py:Calculator")

        assert result.target_type == "class"
        assert "Calculator" in result.signature

    def test_explain_module(self, tmp_path):
        source = textwrap.dedent('''\
            """Module for processing data."""

            import os

            def process():
                pass

            class DataHandler:
                pass
        ''')
        test_file = tmp_path / "module.py"
        test_file.write_text(source)

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        result = explainer.explain("module.py")

        assert result.target_type == "module"
        assert "1 functions" in result.summary or "function" in result.summary.lower()

    def test_explain_symbol_not_found(self, tmp_path):
        test_file = tmp_path / "empty.py"
        test_file.write_text("x = 1\n")

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        result = explainer.explain("empty.py:nonexistent")

        assert "not found" in result.summary.lower()

    def test_format_explanation(self):
        result = CodeExplanation(
            target="file.py:func",
            target_type="function",
            summary="Does something",
            detailed="This function does something important.",
            signature="def func(x: int) -> str",
            docstring="",
            source_lines=10,
            complexity=3,
            edge_cases=["None input"],
            side_effects=["writes data"],
        )
        output = format_explanation(result)
        assert "file.py:func" in output
        assert "Does something" in output
        assert "None input" in output
        assert "writes data" in output


class TestEdgeCaseDetection:
    """Test edge case detection heuristics."""

    def test_detect_edge_cases(self, tmp_path):
        source = textwrap.dedent('''\
            def process(data):
                if data is None:
                    return []
                try:
                    result = len(data)
                except Exception:
                    return -1
                return result
        ''')
        test_file = tmp_path / "test.py"
        test_file.write_text(source)

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        edges = explainer._detect_edge_cases(str(test_file), 1, 8)

        assert any("None" in e for e in edges)
        assert any("Exception" in e for e in edges)


class TestSideEffectDetection:
    """Test side effect detection heuristics."""

    def test_detect_side_effects(self, tmp_path):
        source = textwrap.dedent('''\
            import subprocess
            import logging

            logger = logging.getLogger(__name__)

            def run_command(cmd):
                subprocess.run(cmd)
                logger.info("ran command")
        ''')
        test_file = tmp_path / "cmd.py"
        test_file.write_text(source)

        config = ExplainConfig(cwd=str(tmp_path))
        explainer = CodeExplainer(config)
        effects = explainer._detect_side_effects(str(test_file), 6, 8)

        assert any("shell" in e for e in effects)
        assert any("logging" in e for e in effects)
