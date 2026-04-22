"""Post-Deploy Watchdog — monitor error rate after deployment."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.tools.watchdog")


@dataclass
class WatchdogSnapshot:
    """A single monitoring snapshot."""

    timestamp: str
    error_count: int = 0
    error_rate: float = 0.0
    p95_latency: float = 0.0
    pod_restarts: int = 0


@dataclass
class WatchdogReport:
    """Full watchdog monitoring report."""

    baseline: Optional[WatchdogSnapshot] = None
    snapshots: list[WatchdogSnapshot] = field(default_factory=list)
    spike_detected: bool = False
    spike_message: str = ""
    duration_minutes: int = 15

    @property
    def latest(self) -> Optional[WatchdogSnapshot]:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def max_error_rate(self) -> float:
        if not self.snapshots:
            return 0.0
        return max(s.error_rate for s in self.snapshots)


class PostDeployWatchdog:
    """Monitors service health after deployment, alerts on spikes."""

    def __init__(self, duration_minutes: int = 15, poll_interval: int = 60):
        self.duration_minutes = duration_minutes
        self.poll_interval = poll_interval
        self.server_url = os.getenv(
            "CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        )
        self.report = WatchdogReport(duration_minutes=duration_minutes)
        logger.info("PostDeployWatchdog initialized — duration=%dm", duration_minutes)

    def _api_get(self, path: str, timeout: int = 10) -> Optional[dict]:
        url = f"{self.server_url}{path}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.debug("API GET %s failed: %s", path, e)
            return None

    def collect_snapshot(self) -> WatchdogSnapshot:
        """Collect current metrics snapshot."""
        snap = WatchdogSnapshot(timestamp=datetime.now().isoformat())

        # Kibana error rate
        data = self._api_get("/kibana/error-rate?minutes=5")
        if data:
            snap.error_count = data.get("error_count", 0)
            snap.error_rate = data.get("error_rate", 0.0)

        # Pod restarts via ArgoCD
        app_name = os.getenv("ARGOCD_APP_NAME", "")
        if app_name:
            data = self._api_get(f"/argocd/apps/{app_name}/pods")
            if data:
                restarts = sum(p.get("restarts", 0) for p in data.get("pods", []))
                snap.pod_restarts = restarts

        return snap

    def collect_baseline(self) -> WatchdogSnapshot:
        """Collect pre-deploy baseline metrics."""
        baseline = self.collect_snapshot()
        self.report.baseline = baseline
        logger.info("Baseline collected — error_rate=%.1f%%", baseline.error_rate)
        return baseline

    def check_spike(self, snapshot: WatchdogSnapshot) -> bool:
        """Check if current snapshot shows a spike vs baseline."""
        if not self.report.baseline:
            return False

        baseline_rate = max(self.report.baseline.error_rate, 0.1)  # avoid div by zero
        if snapshot.error_rate > baseline_rate * 2:
            self.report.spike_detected = True
            self.report.spike_message = (
                f"Error rate spike: {snapshot.error_rate:.1f}% "
                f"(baseline: {self.report.baseline.error_rate:.1f}%, "
                f"{snapshot.error_rate / baseline_rate:.1f}x increase)"
            )
            return True

        # Check pod restarts
        baseline_restarts = self.report.baseline.pod_restarts
        if snapshot.pod_restarts > baseline_restarts + 3:
            self.report.spike_detected = True
            self.report.spike_message = (
                f"Pod restart spike: {snapshot.pod_restarts} "
                f"(baseline: {baseline_restarts})"
            )
            return True

        return False

    def run(self, duration_minutes: Optional[int] = None) -> WatchdogReport:
        """Run monitoring loop for specified duration."""
        minutes = duration_minutes or self.duration_minutes
        self.report.duration_minutes = minutes
        end_time = time.time() + (minutes * 60)

        # Collect baseline first
        if not self.report.baseline:
            self.collect_baseline()

        logger.info("Starting watchdog monitoring for %d minutes", minutes)

        while time.time() < end_time:
            snapshot = self.collect_snapshot()
            self.report.snapshots.append(snapshot)

            if self.check_spike(snapshot):
                logger.warning("Spike detected: %s", self.report.spike_message)
                break

            remaining = int((end_time - time.time()) / 60)
            logger.info(
                "Watchdog check — error_rate=%.1f%%, restarts=%d, %dm remaining",
                snapshot.error_rate, snapshot.pod_restarts, remaining,
            )

            if time.time() + self.poll_interval < end_time:
                time.sleep(self.poll_interval)
            else:
                break

        return self.report


def format_watchdog_report(report: WatchdogReport) -> str:
    """Format watchdog report for terminal display."""
    lines: list[str] = []
    lines.append("")
    lines.append("  Post-Deploy Watchdog Report")
    lines.append("  " + "=" * 50)
    lines.append(f"  Duration: {report.duration_minutes} minutes")
    lines.append("")

    if report.baseline:
        lines.append(f"  Baseline:")
        lines.append(f"    Error rate: {report.baseline.error_rate:.1f}%")
        lines.append(f"    Error count: {report.baseline.error_count}")
        lines.append(f"    Pod restarts: {report.baseline.pod_restarts}")
        lines.append("")

    if report.snapshots:
        lines.append(f"  Snapshots collected: {len(report.snapshots)}")
        lines.append(f"  Max error rate: {report.max_error_rate:.1f}%")
        latest = report.latest
        if latest:
            lines.append(f"  Latest error rate: {latest.error_rate:.1f}%")
            lines.append(f"  Latest pod restarts: {latest.pod_restarts}")
        lines.append("")

    if report.spike_detected:
        lines.append(f"  [ALERT] {report.spike_message}")
        lines.append(f"  Consider rollback: code-agents pipeline rollback <id>")
    else:
        lines.append(f"  [OK] No spikes detected — deployment looks healthy")

    lines.append("")
    return "\n".join(lines)
