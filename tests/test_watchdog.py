"""Tests for watchdog.py — post-deploy watchdog."""

from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.watchdog import (
    PostDeployWatchdog, WatchdogReport, WatchdogSnapshot,
    format_watchdog_report,
)


class TestPostDeployWatchdog:
    """Tests for PostDeployWatchdog."""

    def test_init(self):
        wd = PostDeployWatchdog(duration_minutes=10)
        assert wd.duration_minutes == 10

    def test_snapshot_dataclass(self):
        snap = WatchdogSnapshot(
            timestamp="2026-04-01T10:00:00",
            error_count=5, error_rate=1.2,
            p95_latency=250.0, pod_restarts=0,
        )
        assert snap.error_rate == 1.2

    def test_report_latest(self):
        report = WatchdogReport(snapshots=[
            WatchdogSnapshot(timestamp="t1", error_rate=1.0),
            WatchdogSnapshot(timestamp="t2", error_rate=2.0),
        ])
        assert report.latest.error_rate == 2.0

    def test_report_max_error_rate(self):
        report = WatchdogReport(snapshots=[
            WatchdogSnapshot(timestamp="t1", error_rate=1.0),
            WatchdogSnapshot(timestamp="t2", error_rate=5.0),
            WatchdogSnapshot(timestamp="t3", error_rate=3.0),
        ])
        assert report.max_error_rate == 5.0

    def test_report_empty(self):
        report = WatchdogReport()
        assert report.latest is None
        assert report.max_error_rate == 0.0

    def test_check_spike_no_baseline(self):
        wd = PostDeployWatchdog()
        snap = WatchdogSnapshot(timestamp="t1", error_rate=10.0)
        assert wd.check_spike(snap) is False

    def test_check_spike_detected(self):
        wd = PostDeployWatchdog()
        wd.report.baseline = WatchdogSnapshot(
            timestamp="t0", error_rate=2.0, pod_restarts=0,
        )
        snap = WatchdogSnapshot(timestamp="t1", error_rate=5.0, pod_restarts=0)
        assert wd.check_spike(snap) is True
        assert wd.report.spike_detected is True
        assert "spike" in wd.report.spike_message.lower()

    def test_check_spike_not_detected(self):
        wd = PostDeployWatchdog()
        wd.report.baseline = WatchdogSnapshot(
            timestamp="t0", error_rate=2.0, pod_restarts=0,
        )
        snap = WatchdogSnapshot(timestamp="t1", error_rate=3.0, pod_restarts=0)
        assert wd.check_spike(snap) is False

    def test_check_spike_pod_restarts(self):
        wd = PostDeployWatchdog()
        wd.report.baseline = WatchdogSnapshot(
            timestamp="t0", error_rate=1.0, pod_restarts=0,
        )
        snap = WatchdogSnapshot(timestamp="t1", error_rate=1.0, pod_restarts=5)
        assert wd.check_spike(snap) is True


class TestFormatWatchdogReport:
    """Tests for format_watchdog_report."""

    def test_format_healthy(self):
        report = WatchdogReport(
            baseline=WatchdogSnapshot(timestamp="t0", error_rate=1.0, pod_restarts=0),
            snapshots=[WatchdogSnapshot(timestamp="t1", error_rate=1.5, pod_restarts=0)],
        )
        output = format_watchdog_report(report)
        assert "Post-Deploy Watchdog" in output
        assert "[OK]" in output

    def test_format_spike(self):
        report = WatchdogReport(
            baseline=WatchdogSnapshot(timestamp="t0", error_rate=1.0),
            snapshots=[WatchdogSnapshot(timestamp="t1", error_rate=5.0)],
            spike_detected=True,
            spike_message="Error rate spike: 5.0%",
        )
        output = format_watchdog_report(report)
        assert "[ALERT]" in output
        assert "rollback" in output.lower()

    def test_format_empty(self):
        report = WatchdogReport()
        output = format_watchdog_report(report)
        assert "Post-Deploy Watchdog" in output


# ---------------------------------------------------------------------------
# Run loop (line 152)
# ---------------------------------------------------------------------------


class TestWatchdogRun:
    def test_run_short_duration_with_spike(self):
        """Spike detection should break the loop."""
        wd = PostDeployWatchdog(duration_minutes=10, poll_interval=1)
        wd.report.baseline = WatchdogSnapshot(
            timestamp="t0", error_rate=1.0, pod_restarts=0,
        )
        spike_snap = WatchdogSnapshot(timestamp="t1", error_rate=10.0, pod_restarts=0)
        call_count = [0]
        def mock_time():
            call_count[0] += 1
            if call_count[0] <= 2:
                return 0  # start
            return 0  # still in range
        with patch.object(wd, "collect_snapshot", return_value=spike_snap), \
             patch("time.time", side_effect=[0, 0, 0]):
            report = wd.run(duration_minutes=10)
        assert report.spike_detected is True
        assert len(report.snapshots) >= 1

    def test_collect_baseline(self):
        wd = PostDeployWatchdog()
        with patch.object(wd, "collect_snapshot", return_value=WatchdogSnapshot(
            timestamp="t0", error_rate=2.0, pod_restarts=1,
        )):
            baseline = wd.collect_baseline()
        assert baseline.error_rate == 2.0
        assert wd.report.baseline is baseline

    def test_run_collects_baseline_if_missing(self):
        """run() should call collect_baseline if none exists."""
        wd = PostDeployWatchdog(duration_minutes=1, poll_interval=1)
        snap = WatchdogSnapshot(timestamp="t", error_rate=0.5, pod_restarts=0)
        # Return spike to break out quickly
        spike_snap = WatchdogSnapshot(timestamp="t1", error_rate=100.0, pod_restarts=0)
        with patch.object(wd, "collect_snapshot", side_effect=[snap, spike_snap]), \
             patch("time.time", side_effect=[0, 0, 0, 0]):
            report = wd.run(duration_minutes=1)
        assert report.baseline is not None

    def test_run_else_break_on_poll_past_end(self):
        """When remaining time < poll_interval, the else branch breaks."""
        wd = PostDeployWatchdog(duration_minutes=1, poll_interval=120)
        wd.report.baseline = WatchdogSnapshot(
            timestamp="t0", error_rate=1.0, pod_restarts=0,
        )
        normal_snap = WatchdogSnapshot(timestamp="t1", error_rate=1.0, pod_restarts=0)
        # time sequence: start=0, end_time=60, loop check: 0<60=True, then time+120>60 -> else break
        with patch.object(wd, "collect_snapshot", return_value=normal_snap), \
             patch("time.time", side_effect=[0, 0, 50, 50]):
            report = wd.run(duration_minutes=1)
        assert len(report.snapshots) == 1
        assert report.spike_detected is False
