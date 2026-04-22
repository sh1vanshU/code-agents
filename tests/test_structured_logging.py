"""Tests for structured logging — JSONFormatter, PlainFormatter, trace context injection."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest


class TestJSONFormatter:
    """Tests for the JSONFormatter."""

    def test_json_output(self):
        from code_agents.core.logging_config import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "code_agents.test"
        assert data["message"] == "test message"
        assert data["line"] == 42
        assert "timestamp" in data

    def test_json_with_request_id(self):
        from code_agents.core.logging_config import JSONFormatter
        from code_agents.observability.otel import generate_request_id
        rid = generate_request_id()
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data.get("request_id") == rid

    def test_json_with_exception(self):
        from code_agents.core.logging_config import JSONFormatter
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=None,
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["exception"]["type"] == "ValueError"
        assert "test error" in data["exception"]["message"]

    def test_json_extra_fields(self):
        from code_agents.core.logging_config import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="agent call",
            args=None,
            exc_info=None,
        )
        record.agent = "code-writer"
        record.tokens = 1500
        record.duration_ms = 245.3
        output = formatter.format(record)
        data = json.loads(output)
        assert data["agent"] == "code-writer"
        assert data["tokens"] == 1500
        assert data["duration_ms"] == 245.3


class TestPlainFormatter:
    """Tests for PlainFormatter with request_id injection."""

    def test_plain_with_request_id(self):
        from code_agents.core.logging_config import PlainFormatter
        from code_agents.observability.otel import generate_request_id
        rid = generate_request_id()
        formatter = PlainFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert f"[req={rid}]" in output
        assert "test message" in output

    def test_plain_without_request_id(self):
        from code_agents.core.logging_config import PlainFormatter
        from code_agents.observability.otel import request_id_var
        token = request_id_var.set("")
        formatter = PlainFormatter(
            "%(levelname)s %(message)s",
            datefmt="%Y-%m-%d",
        )
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[req=" not in output
        assert "test message" in output
        request_id_var.reset(token)


class TestColoredFormatter:
    """Tests for ColoredFormatter with request_id."""

    def test_colored_format(self):
        from code_agents.core.logging_config import ColoredFormatter
        formatter = ColoredFormatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        record = logging.LogRecord(
            name="code_agents.core.stream",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="streaming data",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "\033[" in output
        assert "streaming data" in output

    def test_colored_with_request_id(self):
        from code_agents.core.logging_config import ColoredFormatter
        from code_agents.observability.otel import generate_request_id
        rid = generate_request_id()
        formatter = ColoredFormatter(
            "%(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        record = logging.LogRecord(
            name="code_agents.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert f"req={rid}" in output
