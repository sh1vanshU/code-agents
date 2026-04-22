"""Tests for code_agents.otel — OpenTelemetry setup and utilities."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import os

import pytest


class TestRequestId:
    """Tests for request ID generation and context."""

    def test_generate_request_id(self):
        from code_agents.observability.otel import generate_request_id, get_request_id
        rid = generate_request_id()
        assert len(rid) == 16
        assert rid == get_request_id()

    def test_request_id_default_empty(self):
        from code_agents.observability.otel import request_id_var
        # Reset to default
        token = request_id_var.set("")
        from code_agents.observability.otel import get_request_id
        assert get_request_id() == ""
        request_id_var.reset(token)

    def test_unique_ids(self):
        from code_agents.observability.otel import generate_request_id
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # All unique


class TestTraceContext:
    """Tests for trace context extraction."""

    def test_trace_context_without_otel(self):
        from code_agents.observability.otel import get_trace_context, generate_request_id
        rid = generate_request_id()
        ctx = get_trace_context()
        assert ctx["request_id"] == rid
        # Without OTel enabled, no trace_id/span_id
        assert "trace_id" not in ctx or ctx.get("trace_id") is None


class TestIsEnabled:
    """Tests for OTEL_ENABLED flag."""

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OTEL_ENABLED", None)
            from code_agents.observability.otel import is_enabled
            assert not is_enabled()

    def test_enabled_true(self):
        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            from code_agents.observability.otel import is_enabled
            assert is_enabled()

    def test_enabled_1(self):
        with patch.dict(os.environ, {"OTEL_ENABLED": "1"}):
            from code_agents.observability.otel import is_enabled
            assert is_enabled()


class TestNoOpFallbacks:
    """Tests for no-op tracer/meter when OTel is not installed."""

    def test_noop_tracer(self):
        from code_agents.observability.otel import _NoOpTracer
        tracer = _NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            span.set_attribute("key", "value")
            span.add_event("event")

    def test_noop_meter(self):
        from code_agents.observability.otel import _NoOpMeter
        meter = _NoOpMeter()
        counter = meter.create_counter("test")
        counter.add(1, {"label": "value"})
        histogram = meter.create_histogram("test")
        histogram.record(42.0)


class TestInstrumentation:
    """Tests for instrumentation functions."""

    @patch.dict(os.environ, {"OTEL_ENABLED": "false"})
    def test_instrument_fastapi_disabled(self):
        """Should no-op when OTel is disabled."""
        from code_agents.observability.otel import instrument_fastapi
        mock_app = MagicMock()
        instrument_fastapi(mock_app)
        # Should not have called any instrumentor

    @patch.dict(os.environ, {"OTEL_ENABLED": "false"})
    def test_instrument_httpx_disabled(self):
        """Should no-op when OTel is disabled."""
        from code_agents.observability.otel import instrument_httpx
        instrument_httpx()  # Should not raise


class TestGetTracerMeter:
    """Tests for get_tracer/get_meter fallbacks."""

    def test_get_tracer_returns_noop(self):
        """Without OTel init, should return a usable tracer."""
        from code_agents.observability.otel import get_tracer
        tracer = get_tracer()
        # Should be usable (no-op or real)
        assert tracer is not None

    def test_get_meter_returns_noop(self):
        """Without OTel init, should return a usable meter."""
        from code_agents.observability.otel import get_meter
        meter = get_meter()
        assert meter is not None


class TestMetricsHelpers:
    """Tests for pre-built metrics."""

    def test_token_counter(self):
        from code_agents.observability.otel import get_token_counter
        counter = get_token_counter()
        counter.add(100, {"agent": "auto-pilot", "model": "gpt-4", "direction": "input"})

    def test_request_histogram(self):
        from code_agents.observability.otel import get_request_duration_histogram
        hist = get_request_duration_histogram()
        hist.record(42.5, {"method": "POST", "path": "/v1/chat/completions", "status": "200"})

    def test_agent_call_counter(self):
        from code_agents.observability.otel import get_agent_call_counter
        counter = get_agent_call_counter()
        counter.add(1, {"agent": "code-writer", "backend": "claude"})
