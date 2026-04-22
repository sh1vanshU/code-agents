"""Tests for the LogAnalyzer module."""

import pytest
from code_agents.observability.log_analyzer import LogAnalyzer, LogAnalysisResult, format_log_analysis


class TestLogAnalyzer:
    def test_parse_json_logs(self):
        logs = '{"timestamp":"2024-01-15T10:00:00","level":"ERROR","service":"api","message":"Connection failed"}\n'
        result = LogAnalyzer().analyze(logs)
        assert result.error_count == 1
        assert "api" in result.services_seen

    def test_parse_plain_logs(self):
        logs = """2024-01-15 10:00:00 ERROR api - Connection failed
2024-01-15 10:00:01 INFO api - Retrying connection
2024-01-15 10:00:02 WARN api - Slow query detected
"""
        result = LogAnalyzer().analyze(logs)
        assert result.total_lines == 3
        assert result.parsed_lines == 3
        assert result.error_count == 1
        assert result.warn_count == 1

    def test_root_cause_is_first_error(self):
        logs = """2024-01-15 10:00:00 INFO api - Starting
2024-01-15 10:00:01 ERROR api - DB connection lost
2024-01-15 10:00:02 ERROR api - Query failed
"""
        result = LogAnalyzer().analyze(logs)
        assert result.root_cause is not None
        assert "DB connection lost" in result.root_cause.message

    def test_correlation_grouping(self):
        logs = '''{"timestamp":"t1","level":"INFO","message":"start","trace_id":"abc123"}
{"timestamp":"t2","level":"ERROR","message":"fail","trace_id":"abc123"}
{"timestamp":"t3","level":"INFO","message":"other","trace_id":"def456"}
'''
        result = LogAnalyzer().analyze(logs)
        assert len(result.timelines) == 2
        abc_timeline = next(t for t in result.timelines if t.correlation_id == "abc123")
        assert abc_timeline.has_error is True
        assert len(abc_timeline.entries) == 2

    def test_empty_logs(self):
        result = LogAnalyzer().analyze("")
        assert result.total_lines == 0
        assert result.error_count == 0

    def test_level_distribution(self):
        logs = """2024-01-15 10:00:00 INFO msg1
2024-01-15 10:00:01 INFO msg2
2024-01-15 10:00:02 ERROR msg3
"""
        result = LogAnalyzer().analyze(logs)
        assert result.level_distribution.get("INFO", 0) == 2
        assert result.level_distribution.get("ERROR", 0) == 1

    def test_format_output(self):
        result = LogAnalysisResult(summary="5 lines | 1 error", error_count=1)
        output = format_log_analysis(result)
        assert "Log Analysis" in output
        assert "1 error" in output
