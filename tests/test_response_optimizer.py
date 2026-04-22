"""Tests for code_agents.response_optimizer."""

import pytest
from code_agents.core.response_optimizer import ResponseOptimizer, ResponseOptimizerConfig, ResponseOptimizeResult, format_response_report


class TestResponseOptimizer:
    def test_config_defaults(self):
        config = ResponseOptimizerConfig()
        assert config.cwd == "."
        assert config.max_files == 200

    def test_scan_empty_codebase(self, tmp_path):
        result = ResponseOptimizer(ResponseOptimizerConfig(cwd=str(tmp_path))).scan()
        assert result.endpoints_found == 0
        assert len(result.findings) == 0

    def test_format_output(self):
        result = ResponseOptimizeResult(summary="5 endpoints, 2 issues")
        output = format_response_report(result)
        assert "Response Optimizer" in output

    def test_format_no_findings(self):
        result = ResponseOptimizeResult(summary="0 endpoints")
        output = format_response_report(result)
        assert "No optimization" in output
