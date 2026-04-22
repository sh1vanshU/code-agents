"""
OpenTelemetry setup for Code Agents.

Initializes tracing, metrics, and log bridging. Controlled via env vars:

  OTEL_ENABLED=true                     — master switch (default: false)
  OTEL_SERVICE_NAME=code-agents         — service name (default: code-agents)
  OTEL_EXPORTER_OTLP_ENDPOINT           — OTLP collector (default: http://localhost:4317)
  OTEL_TRACES_EXPORTER=otlp|console     — trace export target
  OTEL_METRICS_EXPORTER=otlp|console    — metrics export target

When OTEL_ENABLED is false, all tracing operations are no-ops (zero overhead).
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger("code_agents.observability.otel")

# Context variable for per-request ID (used even without OTel)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_initialized = False
_tracer = None
_meter = None


def is_enabled() -> bool:
    """Check if OpenTelemetry is enabled."""
    return os.getenv("OTEL_ENABLED", "false").lower() in ("true", "1", "yes")


def init_telemetry() -> None:
    """Initialize OpenTelemetry providers. Safe to call multiple times."""
    global _initialized, _tracer, _meter
    if _initialized:
        return
    _initialized = True

    if not is_enabled():
        logger.info("OpenTelemetry disabled (set OTEL_ENABLED=true to enable)")
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        service_name = os.getenv("OTEL_SERVICE_NAME", "code-agents")
        resource = Resource.create({SERVICE_NAME: service_name})

        # --- Tracer ---
        tracer_provider = TracerProvider(resource=resource)

        traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "otlp")
        if traces_exporter == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer("code_agents", "0.3.0")

        # --- Meter ---
        metrics_exporter = os.getenv("OTEL_METRICS_EXPORTER", "otlp")
        if metrics_exporter == "console":
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
            reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter("code_agents", "0.3.0")

        logger.info(
            "OpenTelemetry initialized: service=%s, traces=%s, metrics=%s",
            service_name, traces_exporter, metrics_exporter,
        )

    except ImportError as e:
        logger.warning("OpenTelemetry packages not installed: %s", e)
    except Exception as e:
        logger.error("OpenTelemetry init failed: %s", e)


def get_tracer():
    """Get the application tracer. Returns a no-op tracer if OTel is disabled."""
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace
        return trace.get_tracer("code_agents")
    except ImportError:
        return _NoOpTracer()


def get_meter():
    """Get the application meter. Returns a no-op meter if OTel is disabled."""
    if _meter is not None:
        return _meter
    try:
        from opentelemetry import metrics
        return metrics.get_meter("code_agents")
    except ImportError:
        return _NoOpMeter()


def generate_request_id() -> str:
    """Generate a new request ID and set it in context."""
    rid = uuid4().hex[:16]
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_var.get("")


def get_trace_context() -> dict[str, str]:
    """Get current trace context as a dict for log injection."""
    ctx: dict[str, str] = {"request_id": get_request_id()}
    if not is_enabled():
        return ctx
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx and span_ctx.is_valid:
            ctx["trace_id"] = format(span_ctx.trace_id, "032x")
            ctx["span_id"] = format(span_ctx.span_id, "016x")
    except Exception:
        pass
    return ctx


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app with OpenTelemetry auto-instrumentation."""
    if not is_enabled():
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI auto-instrumented with OpenTelemetry")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi not installed, skipping")
    except Exception as e:
        logger.warning("FastAPI OTel instrumentation failed: %s", e)


def instrument_httpx() -> None:
    """Instrument httpx globally for automatic span propagation to external calls."""
    if not is_enabled():
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("httpx auto-instrumented with OpenTelemetry")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-httpx not installed, skipping")
    except Exception as e:
        logger.warning("httpx OTel instrumentation failed: %s", e)


# ---------------------------------------------------------------------------
# Metrics helpers — pre-built counters/histograms for common operations
# ---------------------------------------------------------------------------

def get_token_counter():
    """Counter for token usage: labels = agent, model, direction (input/output)."""
    meter = get_meter()
    return meter.create_counter(
        "code_agents.tokens",
        unit="tokens",
        description="Token usage by agent and model",
    )


def get_request_duration_histogram():
    """Histogram for request durations: labels = method, path, status."""
    meter = get_meter()
    return meter.create_histogram(
        "code_agents.request.duration",
        unit="ms",
        description="HTTP request duration",
    )


def get_agent_call_counter():
    """Counter for agent invocations: labels = agent, backend."""
    meter = get_meter()
    return meter.create_counter(
        "code_agents.agent.calls",
        unit="calls",
        description="Agent invocation count",
    )


# ---------------------------------------------------------------------------
# No-op fallbacks when OTel is not installed
# ---------------------------------------------------------------------------

class _NoOpSpan:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def set_attribute(self, *a): pass
    def add_event(self, *a): pass
    def set_status(self, *a): pass

class _NoOpTracer:
    def start_as_current_span(self, *a, **kw): return _NoOpSpan()
    def start_span(self, *a, **kw): return _NoOpSpan()

class _NoOpCounter:
    def add(self, *a, **kw): pass

class _NoOpHistogram:
    def record(self, *a, **kw): pass

class _NoOpMeter:
    def create_counter(self, *a, **kw): return _NoOpCounter()
    def create_histogram(self, *a, **kw): return _NoOpHistogram()
    def create_up_down_counter(self, *a, **kw): return _NoOpCounter()
