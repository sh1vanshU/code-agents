"""Performance Profiler & Baseline — endpoint latency measurement and comparison."""

import logging
import os
import json
import time
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger("code_agents.observability.performance")

BASELINE_PATH = Path.home() / ".code-agents" / "perf_baseline.json"


@dataclass
class EndpointResult:
    url: str
    method: str = "GET"
    iterations: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    status_codes: dict = field(default_factory=dict)  # code -> count

    # Calculated
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    avg: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class BaselineEntry:
    url: str
    method: str = "GET"
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    avg: float = 0.0
    recorded_at: str = ""


@dataclass
class ProfileReport:
    results: list[EndpointResult] = field(default_factory=list)
    baseline_comparison: list[dict] = field(default_factory=list)  # url, metric, baseline, current, change_pct
    total_requests: int = 0
    total_errors: int = 0
    duration_s: float = 0.0


class PerformanceProfiler:
    """Profile endpoint latency and compare with baselines."""

    def __init__(self):
        self.baselines: dict[str, BaselineEntry] = {}
        self._load_baselines()

    def _load_baselines(self):
        if BASELINE_PATH.exists():
            try:
                with open(BASELINE_PATH) as f:
                    data = json.load(f)
                for entry in data.get("baselines", []):
                    key = f"{entry.get('method', 'GET')} {entry['url']}"
                    self.baselines[key] = BaselineEntry(**entry)
            except Exception:
                pass

    def _save_baselines(self):
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "baselines": [vars(b) for b in self.baselines.values()],
            "updated": datetime.now().isoformat(),
        }
        with open(BASELINE_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def profile_endpoint(self, url: str, method: str = "GET",
                         iterations: int = 20, timeout: float = 10.0,
                         headers: dict = None, body: str = None) -> EndpointResult:
        """Hit an endpoint N times and measure latency."""
        result = EndpointResult(url=url, method=method.upper(), iterations=iterations)

        for i in range(iterations):
            start = time.monotonic()
            try:
                req = Request(url, method=method.upper())
                if headers:
                    for k, v in headers.items():
                        req.add_header(k, v)
                if body:
                    req.data = body.encode()

                with urlopen(req, timeout=timeout) as resp:
                    _ = resp.read()
                    elapsed = (time.monotonic() - start) * 1000  # ms

                    result.latencies_ms.append(elapsed)
                    code = resp.status
                    result.status_codes[code] = result.status_codes.get(code, 0) + 1
            except URLError:
                result.errors += 1
                # Still measure time for timeouts
                elapsed = (time.monotonic() - start) * 1000
                result.latencies_ms.append(elapsed)
            except Exception:
                result.errors += 1
                elapsed = (time.monotonic() - start) * 1000
                result.latencies_ms.append(elapsed)

        # Calculate percentiles
        if result.latencies_ms:
            sorted_lat = sorted(result.latencies_ms)
            n = len(sorted_lat)
            result.avg = statistics.mean(sorted_lat)
            result.min_ms = sorted_lat[0]
            result.max_ms = sorted_lat[-1]
            result.p50 = sorted_lat[int(n * 0.5)]
            result.p95 = sorted_lat[min(int(n * 0.95), n - 1)]
            result.p99 = sorted_lat[min(int(n * 0.99), n - 1)]

        return result

    def profile_multiple(self, endpoints: list[dict], iterations: int = 20) -> ProfileReport:
        """Profile multiple endpoints."""
        report = ProfileReport()
        start = time.monotonic()

        for ep in endpoints:
            url = ep.get("url", "")
            method = ep.get("method", "GET")
            if not url:
                continue

            result = self.profile_endpoint(url, method, iterations)
            report.results.append(result)
            report.total_requests += iterations
            report.total_errors += result.errors

        report.duration_s = time.monotonic() - start

        # Compare with baselines
        for result in report.results:
            key = f"{result.method} {result.url}"
            baseline = self.baselines.get(key)
            if baseline:
                for metric in ["p50", "p95", "p99", "avg"]:
                    base_val = getattr(baseline, metric, 0)
                    curr_val = getattr(result, metric, 0)
                    if base_val > 0:
                        change_pct = ((curr_val - base_val) / base_val) * 100
                        report.baseline_comparison.append({
                            "url": result.url,
                            "method": result.method,
                            "metric": metric,
                            "baseline": base_val,
                            "current": curr_val,
                            "change_pct": round(change_pct, 1),
                            "regression": change_pct > 20,  # >20% slower = regression
                        })

        return report

    def save_as_baseline(self, results: list[EndpointResult]):
        """Save current results as the new baseline."""
        for result in results:
            key = f"{result.method} {result.url}"
            self.baselines[key] = BaselineEntry(
                url=result.url,
                method=result.method,
                p50=round(result.p50, 1),
                p95=round(result.p95, 1),
                p99=round(result.p99, 1),
                avg=round(result.avg, 1),
                recorded_at=datetime.now().isoformat(),
            )
        self._save_baselines()
        return len(results)

    def discover_endpoints(self, cwd: str) -> list[dict]:
        """Discover endpoints from the repo for profiling."""
        # Try to load from endpoint scanner
        try:
            from code_agents.cicd.endpoint_scanner import scan_endpoints
            endpoints = scan_endpoints(cwd)
            base_url = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
            return [{"url": f"{base_url}{ep.get('path', '')}", "method": ep.get("method", "GET")}
                    for ep in endpoints[:20]]
        except Exception:
            pass

        # Fallback: common health/actuator endpoints
        base_url = os.getenv("CODE_AGENTS_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        return [
            {"url": f"{base_url}/health", "method": "GET"},
            {"url": f"{base_url}/actuator/health", "method": "GET"},
        ]


def format_profile_report(report: ProfileReport) -> str:
    """Format for terminal display."""
    lines = []
    lines.append("  ╔══ PERFORMANCE PROFILE ══╗")
    lines.append(f"  ║ Requests: {report.total_requests} | Errors: {report.total_errors}")
    lines.append(f"  ║ Duration: {report.duration_s:.1f}s")
    lines.append("  ╚═════════════════════════╝")

    for result in report.results:
        lines.append(f"\n  {result.method} {result.url}")
        if not result.latencies_ms:
            lines.append("    (no data)")
            continue

        # Latency bar
        bar_width = 30
        max_val = max(result.p99, 1)
        p50_bar = int(result.p50 / max_val * bar_width)
        p95_bar = int(result.p95 / max_val * bar_width) - p50_bar
        p99_bar = bar_width - p50_bar - p95_bar

        lines.append(f"    p50: {result.p50:7.1f}ms  [{'█' * p50_bar}{'▓' * p95_bar}{'░' * p99_bar}]")
        lines.append(f"    p95: {result.p95:7.1f}ms")
        lines.append(f"    p99: {result.p99:7.1f}ms")
        lines.append(f"    avg: {result.avg:7.1f}ms  (min: {result.min_ms:.1f}, max: {result.max_ms:.1f})")

        if result.errors:
            lines.append(f"    Errors: {result.errors}/{result.iterations}")

        status_str = ", ".join(f"{code}: {count}" for code, count in sorted(result.status_codes.items()))
        if status_str:
            lines.append(f"    Status: {status_str}")

    # Baseline comparisons
    regressions = [c for c in report.baseline_comparison if c.get("regression")]
    improvements = [c for c in report.baseline_comparison if c.get("change_pct", 0) < -10]

    if regressions:
        lines.append(f"\n  Regressions ({len(regressions)}):")
        for r in regressions:
            lines.append(f"    REGR {r['method']} {r['url']} -- {r['metric']}: "
                         f"{r['baseline']:.1f}ms -> {r['current']:.1f}ms (+{r['change_pct']}%)")

    if improvements:
        lines.append(f"\n  Improvements ({len(improvements)}):")
        for r in improvements:
            lines.append(f"    IMPR {r['method']} {r['url']} -- {r['metric']}: "
                         f"{r['baseline']:.1f}ms -> {r['current']:.1f}ms ({r['change_pct']}%)")

    if not regressions and report.baseline_comparison:
        lines.append(f"\n  No performance regressions detected")

    return "\n".join(lines)
