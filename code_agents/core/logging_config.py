"""
Centralized logging configuration for Code Agents.

Set LOG_LEVEL env var to control verbosity:
  LOG_LEVEL=DEBUG   — full request/response bodies, backend calls, tool activity
  LOG_LEVEL=INFO    — startup, requests, agent routing
  LOG_LEVEL=WARNING — only problems

Log modes (controlled by CODE_AGENTS_LOG_FORMAT):
  text    — human-readable colored output (default for TTY)
  json    — structured JSON lines (default for non-TTY / production)

Logs are written to both stderr (colored/json) and logs/code-agents.log (plain).
The current log file contains only the last hour of data.
Every hour, the file is rotated to a timestamped backup:
  logs/code-agents.log.2026-03-21_14  (kept for 7 days = 168 hourly files)

Structured logging via structlog adds:
  - request_id: per-request correlation ID
  - trace_id / span_id: OpenTelemetry trace context (when OTEL_ENABLED=true)
"""

from __future__ import annotations

import json as _json
import logging
import logging.handlers
import os
import sys
from pathlib import Path


def _ensure_log_dir() -> Path:
    """Create the logs directory relative to the project root and return the log file path."""
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "code-agents.log"


# ---------------------------------------------------------------------------
# Colored console formatter (text mode)
# ---------------------------------------------------------------------------

_LEVEL_COLORS = {
    "DEBUG":    "\033[36m",     # cyan
    "INFO":     "\033[32m",     # green
    "WARNING":  "\033[33m",     # yellow
    "ERROR":    "\033[31m",     # red
    "CRITICAL": "\033[1;31m",   # bold red
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"

# Logger name colors — specific loggers get distinct colors
_LOGGER_COLORS = {
    "code_agents.core.stream":       "\033[34m",     # blue — streaming
    "code_agents.core.backend":      "\033[35m",     # magenta — backend calls
    "code_agents.chat":         "\033[36m",     # cyan — chat
    "code_agents.agent_response": "\033[1;33m", # bold yellow — agent responses
    "code_agents.observability.otel":         "\033[34m",     # blue — telemetry
}


class ColoredFormatter(logging.Formatter):
    """Log formatter with ANSI colors for terminal output."""

    def __init__(self, fmt: str, datefmt: str):
        super().__init__(fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # Inject request_id if available
        from code_agents.observability.otel import get_request_id
        rid = get_request_id()
        rid_str = f" req={rid}" if rid else ""

        # Color the level name
        level_color = _LEVEL_COLORS.get(record.levelname, "")
        colored_level = f"{level_color}{record.levelname:<8}{_RESET}" if level_color else record.levelname

        # Color the logger name
        logger_color = ""
        for prefix, color in _LOGGER_COLORS.items():
            if record.name.startswith(prefix):
                logger_color = color
                break

        # Color timestamp dim
        original_levelname = record.levelname
        record.levelname = colored_level
        original_name = record.name
        if logger_color:
            record.name = f"{logger_color}{record.name}{_RESET}"

        # Append request_id to message
        original_msg = record.msg
        if rid_str:
            record.msg = f"{record.msg}{_DIM}{rid_str}{_RESET}"

        result = super().format(record)

        # Restore original values
        record.levelname = original_levelname
        record.name = original_name
        record.msg = original_msg

        return result


# ---------------------------------------------------------------------------
# JSON formatter (structured logging for production / log aggregation)
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter with trace context injection."""

    def format(self, record: logging.LogRecord) -> str:
        from code_agents.observability.otel import get_trace_context
        ctx = get_trace_context()

        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add trace context
        if ctx.get("request_id"):
            log_entry["request_id"] = ctx["request_id"]
        if ctx.get("trace_id"):
            log_entry["trace_id"] = ctx["trace_id"]
        if ctx.get("span_id"):
            log_entry["span_id"] = ctx["span_id"]

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "",
                "message": str(record.exc_info[1]),
            }

        # Add extra fields (structured logging)
        for key in ("agent", "backend", "model", "tokens", "duration_ms", "status_code", "method", "path"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return _json.dumps(log_entry, default=str)


# ---------------------------------------------------------------------------
# Plain text formatter with request_id (for file handler)
# ---------------------------------------------------------------------------

class PlainFormatter(logging.Formatter):
    """Plain text formatter with request_id injection for log files."""

    def format(self, record: logging.LogRecord) -> str:
        from code_agents.observability.otel import get_request_id
        rid = get_request_id()
        if rid:
            original_msg = record.msg
            record.msg = f"[req={rid}] {record.msg}"
            result = super().format(record)
            record.msg = original_msg
            return result
        return super().format(record)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_logging_initialized = False


def setup_logging() -> None:
    """Configure logging for the entire application. Safe to call multiple times."""
    global _logging_initialized
    if _logging_initialized:
        return
    _logging_initialized = True

    level_name = os.getenv("LOG_LEVEL", os.getenv("CODE_AGENTS_LOG_LEVEL", "DEBUG")).upper()
    level = getattr(logging, level_name, logging.INFO)

    # Determine log format: text (human) or json (structured)
    log_format = os.getenv("CODE_AGENTS_LOG_FORMAT", "").lower()
    if not log_format:
        log_format = "text" if sys.stderr.isatty() else "json"

    # Format strings for text mode
    fmt = "%(asctime)s.%(msecs)03d %(levelname)-8s [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Reset any existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    elif sys.stderr.isatty():
        console_handler.setFormatter(ColoredFormatter(fmt, datefmt))
    else:
        console_handler.setFormatter(PlainFormatter(fmt, datefmt=datefmt))
    root.addHandler(console_handler)

    # File handler — hourly rotation (plain text with request_id, no colors)
    try:
        log_file = _ensure_log_dir()
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when="H",
            interval=1,
            backupCount=168,    # 7 days of hourly backups
            encoding="utf-8",
            utc=False,
        )
        file_handler.suffix = "%Y-%m-%d_%H"
        file_handler.setFormatter(PlainFormatter(fmt, datefmt=datefmt))
        root.addHandler(file_handler)
    except OSError as e:
        root.warning("Could not set up file logging at logs/code-agents.log: %s", e)

    root.setLevel(level)

    # Quiet down noisy third-party loggers unless we're at DEBUG
    if level > logging.DEBUG:
        for name in ("uvicorn.access", "httpx", "httpcore", "urllib3", "elasticsearch",
                      "opentelemetry", "grpc"):
            logging.getLogger(name).setLevel(logging.WARNING)

    # Uvicorn's own loggers
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)

    # Log the logging config itself
    startup_logger = logging.getLogger("code_agents.logging")
    startup_logger.info(
        "Logging initialized: level=%s, format=%s, file=%s, rotation=hourly, backups=168",
        level_name, log_format, _ensure_log_dir(),
    )


# ---------------------------------------------------------------------------
# Agent response logger — distinct logger for agent outputs
# ---------------------------------------------------------------------------

_agent_logger = logging.getLogger("code_agents.agent_response")


def log_agent_response(agent_name: str, response_text: str, tokens: int = 0) -> None:
    """Log an agent's response. Preview to console, full text to file."""
    preview = response_text[:200].replace("\n", " ").strip()
    if len(response_text) > 200:
        preview += "..."
    _agent_logger.info(
        "[%s] response (%d chars, %d tokens): %s",
        agent_name, len(response_text), tokens, preview,
    )
    _agent_logger.debug(
        "[%s] full response:\n%s", agent_name, response_text,
    )
