"""
Acquirer Integration Health Monitor — monitors payment acquirer success rates,
latency, and error distributions via Grafana metrics or Elasticsearch logs.

Supports three data sources in priority order:
1. Grafana metrics (dashboards with acquirer panels)
2. Elasticsearch / Kibana log-based metrics
3. Local log file parsing (offline mode)
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("code_agents.domain.acquirer_health")

# ── Thresholds ──────────────────────────────────────────────────────────────

SUCCESS_RATE_WARN = 95.0  # below this = degraded
SUCCESS_RATE_CRIT = 90.0  # below this = down
LATENCY_WARN_MS = 2000.0  # above this = degraded
TIMEOUT_RATE_WARN = 2.0   # percent, above this = degraded

# Well-known acquirers (can be extended per project)
DEFAULT_ACQUIRERS = [
    "Visa", "Mastercard", "RuPay", "UPI-NPCI", "Acme-PG",
    "HDFC", "ICICI", "Axis", "SBI", "Amex",
]

# ── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class AcquirerMetrics:
    """Metrics for a single acquirer over a time window."""

    name: str
    success_rate: float
    avg_latency_ms: float
    error_count: int
    timeout_count: int
    volume: int
    top_errors: list[str] = field(default_factory=list)


@dataclass
class HealthReport:
    """Aggregated health report across all acquirers."""

    acquirers: list[AcquirerMetrics]
    overall_success_rate: float
    degraded: list[str]
    alerts: list[str]
    timestamp: str = ""
    env: str = "prod"
    window: str = "1h"


# ── Window Helpers ──────────────────────────────────────────────────────────


def _window_to_seconds(window: str) -> int:
    """Convert window string like '1h', '30m', '2d' to seconds."""
    m = re.match(r"^(\d+)([smhd])$", window.strip())
    if not m:
        return 3600
    value, unit = int(m.group(1)), m.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 3600)


def _format_volume(volume: int) -> str:
    """Format volume with K/M suffix for display."""
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f}M"
    if volume >= 1_000:
        return f"{volume / 1_000:.1f}K"
    return str(volume)


# ── Monitor Class ───────────────────────────────────────────────────────────


class AcquirerHealthMonitor:
    """Monitors payment acquirer health using Grafana or Elasticsearch data."""

    def __init__(self, cwd: str = ""):
        self.cwd = cwd or os.getcwd()
        self._grafana_client = None
        self._kibana_client = None

    def _get_grafana_client(self):
        """Lazy-load Grafana client."""
        if self._grafana_client is None:
            try:
                from code_agents.cicd.grafana_client import GrafanaClient

                url = os.environ.get("GRAFANA_URL", "")
                user = os.environ.get("GRAFANA_USERNAME", "")
                pw = os.environ.get("GRAFANA_PASSWORD", "")
                if url:
                    self._grafana_client = GrafanaClient(
                        grafana_url=url, username=user, password=pw
                    )
                    logger.info("Grafana client initialized: %s", url)
                else:
                    logger.debug("GRAFANA_URL not set, Grafana unavailable")
            except ImportError:
                logger.debug("Grafana client not available")
        return self._grafana_client

    def _get_kibana_client(self):
        """Lazy-load Kibana/ES client."""
        if self._kibana_client is None:
            try:
                from code_agents.cicd.kibana_client import KibanaClient

                url = os.environ.get("KIBANA_URL", "") or os.environ.get(
                    "ELASTICSEARCH_URL", ""
                )
                user = os.environ.get("KIBANA_USERNAME", "")
                pw = os.environ.get("KIBANA_PASSWORD", "")
                if url:
                    self._kibana_client = KibanaClient(
                        kibana_url=url, username=user, password=pw
                    )
                    logger.info("Kibana/ES client initialized: %s", url)
                else:
                    logger.debug("KIBANA_URL not set, ES unavailable")
            except ImportError:
                logger.debug("Kibana client not available")
        return self._kibana_client

    # ── Public API ──────────────────────────────────────────────────────

    def check(self, env: str = "prod", window: str = "1h") -> HealthReport:
        """Check acquirer health — tries Grafana first, falls back to ES."""
        logger.info("Checking acquirer health: env=%s, window=%s", env, window)
        metrics: list[AcquirerMetrics] = []

        # Strategy 1: Grafana metrics
        grafana = self._get_grafana_client()
        if grafana:
            logger.info("Attempting Grafana-based metrics collection")
            for acquirer in DEFAULT_ACQUIRERS:
                m = self._query_grafana(acquirer, window)
                if m is not None:
                    metrics.append(m)
            if metrics:
                logger.info(
                    "Collected metrics from Grafana for %d acquirers", len(metrics)
                )
                return self._build_report(metrics, env, window)

        # Strategy 2: Elasticsearch log-based metrics
        kibana = self._get_kibana_client()
        if kibana:
            logger.info("Attempting ES-based metrics collection")
            for acquirer in DEFAULT_ACQUIRERS:
                m = self._query_es(acquirer, window)
                if m is not None:
                    metrics.append(m)
            if metrics:
                logger.info(
                    "Collected metrics from ES for %d acquirers", len(metrics)
                )
                return self._build_report(metrics, env, window)

        # No data sources available
        logger.warning(
            "No data sources available. Configure GRAFANA_URL or KIBANA_URL."
        )
        return HealthReport(
            acquirers=[],
            overall_success_rate=0.0,
            degraded=[],
            alerts=["No data sources configured. Set GRAFANA_URL or KIBANA_URL/ELASTICSEARCH_URL."],
            timestamp=datetime.now(timezone.utc).isoformat(),
            env=env,
            window=window,
        )

    def check_from_logs(
        self, log_dir: str = "", pattern: str = ""
    ) -> HealthReport:
        """Parse local log files for acquirer metrics (offline mode).

        Looks for JSON log lines with fields: acquirer, status, latency_ms, error.
        """
        log_dir = log_dir or os.path.join(self.cwd, "logs")
        logger.info("Checking acquirer health from logs: dir=%s", log_dir)

        metrics = self._parse_log_files(log_dir, pattern)
        return self._build_report(metrics, env="local", window="logs")

    # ── Grafana Query ───────────────────────────────────────────────────

    def _query_grafana(
        self, acquirer: str, window: str
    ) -> AcquirerMetrics | None:
        """Query Grafana for acquirer metrics. Returns None if unavailable."""
        try:
            import asyncio

            grafana = self._get_grafana_client()
            if not grafana:
                return None

            # Search for acquirer dashboard
            loop = asyncio.new_event_loop()
            try:
                dashboards = loop.run_until_complete(
                    grafana.search_dashboards(query=f"acquirer {acquirer}")
                )
            finally:
                loop.close()

            if not dashboards:
                logger.debug("No Grafana dashboard found for %s", acquirer)
                return None

            # Build metrics from dashboard data (simplified — real impl would
            # query specific panels for success_rate, latency, volume)
            logger.debug("Found Grafana dashboard for %s", acquirer)
            return AcquirerMetrics(
                name=acquirer,
                success_rate=0.0,
                avg_latency_ms=0.0,
                error_count=0,
                timeout_count=0,
                volume=0,
            )
        except Exception as exc:
            logger.warning("Grafana query failed for %s: %s", acquirer, exc)
            return None

    # ── Elasticsearch Query ─────────────────────────────────────────────

    def _query_es(
        self, acquirer: str, window: str
    ) -> AcquirerMetrics | None:
        """Query Elasticsearch for acquirer metrics via Kibana client."""
        try:
            import asyncio

            kibana = self._get_kibana_client()
            if not kibana:
                return None

            loop = asyncio.new_event_loop()
            try:
                results = loop.run_until_complete(
                    kibana.search_logs(
                        query=f"acquirer:{acquirer} AND type:payment",
                        index="payments-*",
                        size=0,
                    )
                )
            finally:
                loop.close()

            if not results:
                logger.debug("No ES data found for %s", acquirer)
                return None

            # Parse aggregated results (simplified)
            total = results.get("total", 0)
            if total == 0:
                return None

            return AcquirerMetrics(
                name=acquirer,
                success_rate=0.0,
                avg_latency_ms=0.0,
                error_count=0,
                timeout_count=0,
                volume=total,
            )
        except Exception as exc:
            logger.warning("ES query failed for %s: %s", acquirer, exc)
            return None

    # ── Log File Parser ─────────────────────────────────────────────────

    def _parse_log_files(
        self, log_dir: str, pattern: str = ""
    ) -> list[AcquirerMetrics]:
        """Parse local log files for acquirer transaction metrics.

        Expected log format (JSON lines):
            {"acquirer": "Visa", "status": "success", "latency_ms": 145, "error": ""}
            {"acquirer": "RuPay", "status": "failed", "latency_ms": 2100, "error": "timeout"}
        """
        file_pattern = pattern or "*.log"
        log_path = os.path.join(log_dir, file_pattern)
        files = glob.glob(log_path)

        if not files:
            logger.warning("No log files found at %s", log_path)
            return []

        # Aggregate per acquirer
        acq_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total": 0,
                "success": 0,
                "latencies": [],
                "errors": [],
                "timeouts": 0,
            }
        )

        lines_parsed = 0
        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        acq_name = entry.get("acquirer", "")
                        if not acq_name:
                            continue

                        data = acq_data[acq_name]
                        data["total"] += 1
                        lines_parsed += 1

                        status = entry.get("status", "").lower()
                        if status in ("success", "ok", "captured"):
                            data["success"] += 1

                        latency = entry.get("latency_ms", 0)
                        if latency:
                            data["latencies"].append(float(latency))

                        error = entry.get("error", "")
                        if error:
                            data["errors"].append(error)
                            if "timeout" in error.lower():
                                data["timeouts"] += 1
            except OSError as exc:
                logger.warning("Failed to read %s: %s", filepath, exc)

        logger.info(
            "Parsed %d lines from %d files, found %d acquirers",
            lines_parsed,
            len(files),
            len(acq_data),
        )

        metrics: list[AcquirerMetrics] = []
        for name, data in sorted(acq_data.items()):
            total = data["total"]
            success = data["success"]
            latencies = data["latencies"]
            errors = data["errors"]

            success_rate = (success / total * 100) if total > 0 else 0.0
            avg_latency = (
                sum(latencies) / len(latencies) if latencies else 0.0
            )

            # Top 5 error messages
            error_counts = Counter(errors)
            top_errors = [msg for msg, _ in error_counts.most_common(5)]

            metrics.append(
                AcquirerMetrics(
                    name=name,
                    success_rate=round(success_rate, 2),
                    avg_latency_ms=round(avg_latency, 1),
                    error_count=len(errors),
                    timeout_count=data["timeouts"],
                    volume=total,
                    top_errors=top_errors,
                )
            )

        return metrics

    # ── Degradation Detection ───────────────────────────────────────────

    def _detect_degradation(
        self, metrics: list[AcquirerMetrics]
    ) -> list[str]:
        """Flag acquirers with degraded health.

        Criteria:
        - success_rate < 95%
        - avg_latency > 2000ms
        - timeout_rate > 2%
        """
        degraded: list[str] = []
        for m in metrics:
            reasons: list[str] = []
            if m.success_rate < SUCCESS_RATE_WARN:
                reasons.append(f"success_rate={m.success_rate:.1f}%")
            if m.avg_latency_ms > LATENCY_WARN_MS:
                reasons.append(f"latency={m.avg_latency_ms:.0f}ms")
            if m.volume > 0:
                timeout_rate = m.timeout_count / m.volume * 100
                if timeout_rate > TIMEOUT_RATE_WARN:
                    reasons.append(f"timeout_rate={timeout_rate:.1f}%")
            if reasons:
                degraded.append(f"{m.name}: {', '.join(reasons)}")
        return degraded

    # ── Alert Generation ────────────────────────────────────────────────

    def _generate_alerts(
        self, metrics: list[AcquirerMetrics]
    ) -> list[str]:
        """Generate alert messages for critical acquirer issues."""
        alerts: list[str] = []
        for m in metrics:
            if m.success_rate < SUCCESS_RATE_CRIT:
                alerts.append(
                    f"CRITICAL: {m.name} success rate {m.success_rate:.1f}% "
                    f"(below {SUCCESS_RATE_CRIT}% threshold)"
                )
            if m.avg_latency_ms > LATENCY_WARN_MS * 1.5:
                alerts.append(
                    f"HIGH LATENCY: {m.name} avg latency {m.avg_latency_ms:.0f}ms "
                    f"(>{LATENCY_WARN_MS * 1.5:.0f}ms)"
                )
            if m.volume > 0:
                timeout_rate = m.timeout_count / m.volume * 100
                if timeout_rate > TIMEOUT_RATE_WARN * 2:
                    alerts.append(
                        f"TIMEOUT SPIKE: {m.name} timeout rate {timeout_rate:.1f}% "
                        f"(>{TIMEOUT_RATE_WARN * 2:.0f}%)"
                    )
            if m.volume == 0:
                alerts.append(f"NO TRAFFIC: {m.name} has zero volume — possible outage")
        return alerts

    # ── Report Builder ──────────────────────────────────────────────────

    def _build_report(
        self, metrics: list[AcquirerMetrics], env: str, window: str
    ) -> HealthReport:
        """Build a HealthReport from collected metrics."""
        total_vol = sum(m.volume for m in metrics)
        total_success = sum(
            m.volume * m.success_rate / 100 for m in metrics
        )
        overall = (total_success / total_vol * 100) if total_vol > 0 else 0.0

        degraded = self._detect_degradation(metrics)
        alerts = self._generate_alerts(metrics)

        return HealthReport(
            acquirers=metrics,
            overall_success_rate=round(overall, 2),
            degraded=degraded,
            alerts=alerts,
            timestamp=datetime.now(timezone.utc).isoformat(),
            env=env,
            window=window,
        )


# ── Dashboard Formatter ─────────────────────────────────────────────────────


def _status_label(m: AcquirerMetrics) -> str:
    """Return status label for an acquirer."""
    if m.success_rate < SUCCESS_RATE_CRIT:
        return "\033[91m DOWN \033[0m"
    if m.success_rate < SUCCESS_RATE_WARN:
        return "\033[93m DEGRADE\033[0m"
    if m.avg_latency_ms > LATENCY_WARN_MS:
        return "\033[93m SLOW  \033[0m"
    return "\033[92m OK   \033[0m"


def format_health_dashboard(report: HealthReport) -> str:
    """Format HealthReport as a rich terminal dashboard table."""
    lines: list[str] = []

    header = f"Acquirer Health ({report.env}, last {report.window})"
    border_len = 62
    lines.append(f"\033[1;36m{'=' * border_len}\033[0m")
    lines.append(f"\033[1;37m {header:^{border_len - 2}} \033[0m")
    lines.append(f"\033[1;36m{'=' * border_len}\033[0m")

    if not report.acquirers:
        lines.append("  No acquirer data available.")
        if report.alerts:
            lines.append("")
            for alert in report.alerts:
                lines.append(f"  \033[93m{alert}\033[0m")
        return "\n".join(lines)

    # Table header
    lines.append(
        f"  {'Acquirer':<14} {'Success':>8} {'Latency':>9} {'Volume':>8} {'Status':>10}"
    )
    lines.append(f"  {'-' * 14} {'-' * 8} {'-' * 9} {'-' * 8} {'-' * 10}")

    # Sort: worst success rate first
    sorted_acq = sorted(report.acquirers, key=lambda m: m.success_rate)
    for m in sorted_acq:
        vol_str = _format_volume(m.volume)
        status = _status_label(m)
        lines.append(
            f"  {m.name:<14} {m.success_rate:>7.1f}% {m.avg_latency_ms:>7.0f}ms {vol_str:>8} {status}"
        )

    lines.append(f"\033[1;36m{'-' * border_len}\033[0m")
    lines.append(
        f"  Overall success rate: \033[1m{report.overall_success_rate:.1f}%\033[0m"
    )

    # Degraded acquirers
    if report.degraded:
        lines.append("")
        lines.append("  \033[93mDegraded:\033[0m")
        for d in report.degraded:
            lines.append(f"    - {d}")

    # Alerts
    if report.alerts:
        lines.append("")
        lines.append("  \033[91mAlerts:\033[0m")
        for a in report.alerts:
            lines.append(f"    - {a}")

    lines.append(f"\033[1;36m{'=' * border_len}\033[0m")
    lines.append(f"  \033[90mTimestamp: {report.timestamp}\033[0m")

    return "\n".join(lines)


def report_to_dict(report: HealthReport) -> dict:
    """Serialize HealthReport to a JSON-safe dict."""
    return {
        "acquirers": [
            {
                "name": m.name,
                "success_rate": m.success_rate,
                "avg_latency_ms": m.avg_latency_ms,
                "error_count": m.error_count,
                "timeout_count": m.timeout_count,
                "volume": m.volume,
                "top_errors": m.top_errors,
            }
            for m in report.acquirers
        ],
        "overall_success_rate": report.overall_success_rate,
        "degraded": report.degraded,
        "alerts": report.alerts,
        "timestamp": report.timestamp,
        "env": report.env,
        "window": report.window,
    }
