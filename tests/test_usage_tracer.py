"""Tests for the UsageTracer module."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.domain.usage_tracer import UsageTracer, UsageTraceConfig, UsageTraceResult, format_usage


class TestUsageTracer:
    """Test UsageTracer functionality."""

    def test_config_defaults(self):
        config = UsageTraceConfig()
        assert config.cwd == "."
        assert config.include_tests is True
        assert config.max_results == 100

    @patch("code_agents.tools._pattern_matchers.find_usage_sites")
    def test_trace_basic(self, mock_find):
        from code_agents.tools._pattern_matchers import UsageSite

        mock_find.return_value = [
            UsageSite(file="a.py", line=1, usage_type="import", content="from x import build_prompt"),
            UsageSite(file="b.py", line=10, usage_type="call", content="result = build_prompt(data)"),
            UsageSite(file="test_x.py", line=5, usage_type="test", content="assert build_prompt()"),
        ]

        config = UsageTraceConfig(cwd="/tmp")
        result = UsageTracer(config).trace("build_prompt")

        assert result.symbol == "build_prompt"
        assert result.total_usages == 3
        assert result.import_count == 1
        assert result.call_count == 1
        assert result.test_count == 1
        assert len(result.files_affected) == 3

    @patch("code_agents.tools._pattern_matchers.find_usage_sites")
    def test_trace_excludes_tests(self, mock_find):
        from code_agents.tools._pattern_matchers import UsageSite

        mock_find.return_value = [
            UsageSite(file="a.py", line=1, usage_type="import", content="import x"),
            UsageSite(file="test_a.py", line=5, usage_type="test", content="test x"),
        ]

        config = UsageTraceConfig(cwd="/tmp", include_tests=False)
        result = UsageTracer(config).trace("x")

        assert result.total_usages == 1
        assert result.test_count == 0

    @patch("code_agents.tools._pattern_matchers.find_usage_sites")
    def test_trace_empty_results(self, mock_find):
        mock_find.return_value = []
        config = UsageTraceConfig(cwd="/tmp")
        result = UsageTracer(config).trace("nonexistent_symbol")
        assert result.total_usages == 0
        assert result.files_affected == []

    def test_format_usage(self):
        result = UsageTraceResult(
            symbol="test_func",
            total_usages=5,
            import_count=2,
            call_count=3,
            files_affected=["a.py", "b.py"],
        )
        output = format_usage(result)
        assert "test_func" in output
        assert "5 usages" in output
