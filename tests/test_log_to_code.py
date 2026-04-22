"""Tests for log_to_code.py — production log to execution path reconstruction."""

import pytest

from code_agents.observability.log_to_code import (
    LogToCodeMapper,
    LogToCodeReport,
    LogEntry,
    ExecutionPath,
    format_report,
)


@pytest.fixture
def mapper(tmp_path):
    return LogToCodeMapper(str(tmp_path))


class TestParseLogLine:
    def test_python_log_format(self, mapper):
        entry = mapper._parse_line(
            "2024-01-15 10:30:00,123 - auth.service - INFO - User login successful"
        )
        assert entry is not None
        assert entry.level == "INFO"
        assert "login" in entry.message

    def test_generic_log_format(self, mapper):
        entry = mapper._parse_line("[ERROR] Connection refused to database")
        assert entry is not None
        assert entry.level == "ERROR"

    def test_empty_line(self, mapper):
        entry = mapper._parse_line("")
        assert entry is not None
        assert entry.message == ""

    def test_variable_extraction(self, mapper):
        entry = mapper._parse_line("2024-01-15 10:30:00 - app - INFO - userId=42 status=active")
        assert entry is not None
        assert "userId" in entry.variables or "status" in entry.variables

    def test_unstructured_line(self, mapper):
        entry = mapper._parse_line("Just some random text")
        assert entry is not None
        assert entry.message == "Just some random text"


class TestGroupByRequest:
    def test_groups_by_request_id(self, mapper):
        entries = [
            LogEntry(message="request_id=abc123 start"),
            LogEntry(message="request_id=abc123 processing"),
            LogEntry(message="request_id=def456 other"),
        ]
        groups = mapper._group_by_request(entries)
        assert "abc123" in groups
        assert len(groups["abc123"]) == 2

    def test_untagged_entries(self, mapper):
        entries = [LogEntry(message="no id here"), LogEntry(message="also no id")]
        groups = mapper._group_by_request(entries)
        assert len(groups) >= 1

    def test_empty_entries(self, mapper):
        groups = mapper._group_by_request([])
        assert groups == {}


class TestAnalyze:
    def test_basic_analysis(self, mapper):
        log_content = """2024-01-15 10:30:00 - auth - INFO - request_id=r1 login started
2024-01-15 10:30:01 - auth - INFO - request_id=r1 login completed
2024-01-15 10:30:02 - auth - ERROR - request_id=r2 login failed"""
        report = mapper.analyze(log_content)
        assert isinstance(report, LogToCodeReport)
        assert len(report.paths) >= 1

    def test_empty_log(self, mapper):
        report = mapper.analyze("")
        assert isinstance(report, LogToCodeReport)
        assert len(report.paths) == 0

    def test_format_report(self, mapper):
        report = mapper.analyze("[INFO] test message\n[ERROR] bad thing")
        text = format_report(report)
        assert "Log-to-Code" in text
