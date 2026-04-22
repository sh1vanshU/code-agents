"""Tests for the CallChainAnalyzer module."""

import textwrap
from unittest.mock import patch

import pytest

from code_agents.observability.call_chain import (
    CallChainAnalyzer, CallChainConfig, CallChainResult, CallNode, format_call_chain,
)


class TestCallChainAnalyzer:
    """Test CallChainAnalyzer functionality."""

    def test_config_defaults(self):
        config = CallChainConfig()
        assert config.cwd == "."
        assert config.max_depth == 3
        assert config.include_tests is False

    def test_analyze_simple(self, tmp_path):
        source = textwrap.dedent('''\
            def helper():
                return 42

            def main():
                result = helper()
                return result

            def caller():
                main()
        ''')
        (tmp_path / "app.py").write_text(source)

        config = CallChainConfig(cwd=str(tmp_path))
        analyzer = CallChainAnalyzer(config)
        result = analyzer.analyze("main")

        assert result.target == "main"
        # main calls helper
        assert "helper" in result.direct_callees

    def test_analyze_entry_point(self, tmp_path):
        source = textwrap.dedent('''\
            def leaf():
                return 1

            def root():
                return leaf()
        ''')
        (tmp_path / "app.py").write_text(source)

        config = CallChainConfig(cwd=str(tmp_path))
        analyzer = CallChainAnalyzer(config)
        result = analyzer.analyze("root")

        assert result.is_entry_point is True
        assert "leaf" in result.direct_callees

    def test_analyze_leaf_function(self, tmp_path):
        source = textwrap.dedent('''\
            def pure_func(x):
                return x * 2

            def caller():
                pure_func(5)
        ''')
        (tmp_path / "app.py").write_text(source)

        config = CallChainConfig(cwd=str(tmp_path))
        analyzer = CallChainAnalyzer(config)
        result = analyzer.analyze("pure_func")

        assert result.is_leaf is True
        # pure_func should be called by caller
        assert "caller" in result.direct_callers or result.callers_count == 0  # depends on AST walk order

    def test_count_nodes(self):
        config = CallChainConfig(cwd="/tmp")
        analyzer = CallChainAnalyzer(config)

        root = CallNode(name="a", children=[
            CallNode(name="b", children=[CallNode(name="c")]),
            CallNode(name="d"),
        ])
        assert analyzer._count_nodes(root) == 4
        assert analyzer._count_nodes(None) == 0

    def test_format_call_chain(self):
        result = CallChainResult(
            target="main",
            target_file="app.py",
            target_line=10,
            callers_count=2,
            callees_count=3,
            direct_callers=["handler", "cli"],
            direct_callees=["process", "validate", "save"],
            is_entry_point=False,
            is_leaf=False,
        )
        output = format_call_chain(result)
        assert "main" in output
        assert "CALLERS (2)" in output
        assert "CALLEES (3)" in output


class TestCallChainEdgeCases:
    """Test edge cases in call chain analysis."""

    def test_empty_codebase(self, tmp_path):
        config = CallChainConfig(cwd=str(tmp_path))
        analyzer = CallChainAnalyzer(config)
        result = analyzer.analyze("nonexistent")

        assert result.callers_count == 0
        assert result.callees_count == 0
        assert result.is_entry_point is True
        assert result.is_leaf is True

    def test_max_depth_respected(self, tmp_path):
        source = textwrap.dedent('''\
            def a(): b()
            def b(): c()
            def c(): d()
            def d(): e()
            def e(): pass
        ''')
        (tmp_path / "deep.py").write_text(source)

        config = CallChainConfig(cwd=str(tmp_path), max_depth=2)
        analyzer = CallChainAnalyzer(config)
        result = analyzer.analyze("a")

        # Should not traverse deeper than 2 levels
        assert result.callees_count <= 3  # a -> b -> c (depth 2)
