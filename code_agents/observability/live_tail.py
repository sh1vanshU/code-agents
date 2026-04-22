"""Live Tail Mode — real-time log streaming with anomaly detection.

Stream logs from Elasticsearch with colorized output, anomaly detection,
and error rate alerting. Gracefully degrades when ES is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger("code_agents.observability.live_tail")


@dataclass
class TailConfig:
    """Configuration for live tail streaming."""

    service: str
    env: str = "dev"
    index: str = "logs-*"
    log_level: str = ""
    poll_interval: float = 5.0
    window_size: int = 100
    alert_threshold: float = 5.0  # error rate %


@dataclass
class AnomalyAlert:
    """Anomaly detection alert when error rate exceeds threshold."""

    timestamp: str
    severity: str
    message: str
    error_rate: float
    sample_logs: list[str]
    analysis: str = ""


class LiveTailStream:
    """Polls Elasticsearch for new log entries and streams them via callback.

    Uses asyncio.Event for graceful shutdown. Falls back gracefully when
    the elasticsearch client is not installed or ES is unreachable.
    """

    def __init__(self, config: TailConfig) -> None:
        self.config = config
        self._stop_event = asyncio.Event()
        self._last_timestamp: str = datetime.now(timezone.utc).isoformat()
        self._es_client: Any = None
        self._init_es_client()

    def _init_es_client(self) -> None:
        """Lazily initialise the Elasticsearch client."""
        try:
            from elasticsearch import Elasticsearch  # type: ignore[import-untyped]

            import os

            es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
            self._es_client = Elasticsearch([es_url], request_timeout=10)
            logger.info("Elasticsearch client initialised: %s", es_url)
        except ImportError:
            logger.warning(
                "elasticsearch package not installed — running in demo mode"
            )
            self._es_client = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to connect to Elasticsearch: %s", exc)
            self._es_client = None

    def _build_query(self, since: str) -> dict:
        """Build an Elasticsearch query DSL dict for new logs since *since*."""
        must_clauses: list[dict] = [
            {"range": {"@timestamp": {"gt": since}}},
            {"term": {"service.keyword": self.config.service}},
        ]
        if self.config.env:
            must_clauses.append({"term": {"environment.keyword": self.config.env}})
        if self.config.log_level:
            must_clauses.append(
                {"term": {"level.keyword": self.config.log_level.upper()}}
            )

        return {
            "size": self.config.window_size,
            "sort": [{"@timestamp": {"order": "asc"}}],
            "query": {"bool": {"must": must_clauses}},
        }

    def _query_logs(self, since: str) -> list[dict]:
        """Execute the ES query and return log entries.

        Returns an empty list when ES is unavailable.
        """
        if self._es_client is None:
            return []

        query = self._build_query(since)
        try:
            resp = self._es_client.search(index=self.config.index, body=query)
            hits = resp.get("hits", {}).get("hits", [])
            return [h["_source"] for h in hits]
        except Exception as exc:  # noqa: BLE001
            logger.debug("ES query failed: %s", exc)
            return []

    async def start(
        self,
        callback: Callable[[list[dict]], Coroutine[Any, Any, None] | None],
    ) -> None:
        """Start the polling loop.

        Calls *callback(new_entries)* for every non-empty batch.
        Runs until :meth:`stop` is called.
        """
        logger.info(
            "Starting live tail for service=%s env=%s (interval=%.1fs)",
            self.config.service,
            self.config.env,
            self.config.poll_interval,
        )

        while not self._stop_event.is_set():
            entries = self._query_logs(self._last_timestamp)
            if entries:
                # Advance watermark
                last_ts = entries[-1].get("@timestamp")
                if last_ts:
                    self._last_timestamp = last_ts

                result = callback(entries)
                if asyncio.iscoroutine(result):
                    await result

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.config.poll_interval
                )
                # Event was set — break out
                break
            except asyncio.TimeoutError:
                continue

        logger.info("Live tail stopped.")

    def stop(self) -> None:
        """Signal the polling loop to stop gracefully."""
        self._stop_event.set()


class AnomalyDetector:
    """Detects anomalous error rates in batches of log entries."""

    ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}

    def __init__(self, config: TailConfig) -> None:
        self.config = config
        self._total_seen: int = 0
        self._total_errors: int = 0

    @property
    def total_seen(self) -> int:
        return self._total_seen

    @property
    def total_errors(self) -> int:
        return self._total_errors

    def _compute_error_rate(self, logs: list[dict]) -> float:
        """Return the error rate (0-100) for a batch of logs."""
        if not logs:
            return 0.0
        error_count = sum(
            1
            for log in logs
            if str(log.get("level", "")).upper() in self.ERROR_LEVELS
        )
        return (error_count / len(logs)) * 100.0

    def _extract_errors(self, logs: list[dict]) -> list[str]:
        """Return error-level messages from the batch."""
        errors: list[str] = []
        for log in logs:
            if str(log.get("level", "")).upper() in self.ERROR_LEVELS:
                msg = log.get("message", str(log))
                errors.append(msg[:200])  # truncate long messages
        return errors

    def analyze_batch(self, logs: list[dict]) -> AnomalyAlert | None:
        """Analyze a batch and return an alert if the error rate exceeds the threshold."""
        self._total_seen += len(logs)
        error_rate = self._compute_error_rate(logs)
        errors = self._extract_errors(logs)
        self._total_errors += len(errors)

        if error_rate < self.config.alert_threshold:
            return None

        severity = "CRITICAL" if error_rate > 50 else "HIGH" if error_rate > 20 else "WARNING"

        return AnomalyAlert(
            timestamp=datetime.now(timezone.utc).isoformat(),
            severity=severity,
            message=(
                f"Error rate {error_rate:.1f}% exceeds threshold "
                f"{self.config.alert_threshold}% for {self.config.service}"
            ),
            error_rate=error_rate,
            sample_logs=errors[:5],
            analysis=(
                f"Detected {len(errors)} errors in batch of {len(logs)} logs. "
                f"Cumulative: {self._total_errors}/{self._total_seen} total."
            ),
        )


class TailRenderer:
    """Renders log lines and alerts with Rich-style ANSI colors."""

    LEVEL_COLORS: dict[str, str] = {
        "ERROR": "\033[91m",    # red
        "FATAL": "\033[91m",
        "CRITICAL": "\033[91m",
        "WARN": "\033[93m",     # yellow
        "WARNING": "\033[93m",
        "INFO": "\033[92m",     # green
        "DEBUG": "\033[2m",     # dim
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED_BG = "\033[41m\033[97m"  # red background, white text

    def render_log_line(self, entry: dict) -> str:
        """Return a colorized single-line representation of a log entry."""
        ts = entry.get("@timestamp", entry.get("timestamp", ""))
        level = str(entry.get("level", "INFO")).upper()
        service = entry.get("service", entry.get("service.name", ""))
        message = entry.get("message", "")

        color = self.LEVEL_COLORS.get(level, "")
        reset = self.RESET if color else ""

        return f"{color}{ts}  {level:<8} [{service}] {message}{reset}"

    def render_alert(self, alert: AnomalyAlert) -> str:
        """Render an anomaly alert as a prominent red box."""
        border = "=" * 60
        lines = [
            "",
            f"{self.RED_BG} {'ANOMALY ALERT':^58} {self.RESET}",
            f"{self.BOLD}{border}{self.RESET}",
            f"  Severity:   {alert.severity}",
            f"  Timestamp:  {alert.timestamp}",
            f"  Error Rate: {alert.error_rate:.1f}%",
            f"  Message:    {alert.message}",
        ]
        if alert.sample_logs:
            lines.append("  Sample errors:")
            for err in alert.sample_logs[:5]:
                lines.append(f"    - {err}")
        if alert.analysis:
            lines.append(f"  Analysis:   {alert.analysis}")
        lines.append(f"{self.BOLD}{border}{self.RESET}")
        lines.append("")
        return "\n".join(lines)

    def render_stats_bar(self, total: int, errors: int, uptime: float) -> str:
        """Render a compact stats bar showing totals and uptime."""
        error_rate = (errors / total * 100) if total > 0 else 0.0
        minutes = uptime / 60.0

        color = "\033[92m"  # green
        if error_rate > 5:
            color = "\033[93m"  # yellow
        if error_rate > 20:
            color = "\033[91m"  # red

        return (
            f"{color}[TAIL] "
            f"logs={total}  errors={errors}  "
            f"rate={error_rate:.1f}%  "
            f"uptime={minutes:.1f}m"
            f"{self.RESET}"
        )


async def run_tail(config: TailConfig) -> None:
    """Orchestrate live tail: stream + anomaly detector + renderer.

    Wires the components together and runs until interrupted.
    """
    stream = LiveTailStream(config)
    detector = AnomalyDetector(config)
    renderer = TailRenderer()
    start_time = time.monotonic()

    print(
        f"\n\033[1mLive Tail\033[0m — {config.service} / {config.env} "
        f"(index={config.index}, interval={config.poll_interval}s)\n"
        f"Press Ctrl+C to stop.\n"
    )

    def on_batch(entries: list[dict]) -> None:
        for entry in entries:
            print(renderer.render_log_line(entry))

        alert = detector.analyze_batch(entries)
        if alert:
            print(renderer.render_alert(alert))

        uptime = time.monotonic() - start_time
        print(
            renderer.render_stats_bar(
                detector.total_seen, detector.total_errors, uptime
            )
        )

    try:
        await stream.start(on_batch)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        uptime = time.monotonic() - start_time
        print(
            f"\n\033[1mTail ended.\033[0m  "
            f"Total logs: {detector.total_seen}, "
            f"errors: {detector.total_errors}, "
            f"uptime: {uptime / 60:.1f}m"
        )
