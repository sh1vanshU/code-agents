"""Benchmark Regression Detection — compare runs, detect quality drops, threshold alerts.

Compares benchmark runs to detect:
- Quality score regressions (per agent, per category)
- Latency regressions
- Token usage changes
- Custom threshold violations

Also supports:
- Custom benchmark task definitions via YAML
- Export to CSV/JSON for CI integration
- Historical trend analysis

Usage:
    from code_agents.testing.benchmark_regression import RegressionDetector
    detector = RegressionDetector()
    result = detector.compare("run1", "run2")
    alerts = detector.check_thresholds(result)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.benchmark_regression")

BENCHMARKS_DIR = Path.home() / ".code-agents" / "benchmarks"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RegressionAlert:
    """A single regression alert."""
    metric: str  # quality, latency, tokens
    agent: str
    category: str
    baseline_value: float
    current_value: float
    delta: float
    delta_pct: float
    severity: str  # info, warning, critical
    message: str


@dataclass
class ComparisonResult:
    """Result of comparing two benchmark runs."""
    baseline_id: str
    current_id: str
    baseline_date: str = ""
    current_date: str = ""
    alerts: list[RegressionAlert] = field(default_factory=list)
    per_agent: dict = field(default_factory=dict)
    per_category: dict = field(default_factory=dict)
    overall: dict = field(default_factory=dict)
    passed: bool = True

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == "warning")


@dataclass
class Threshold:
    """A quality threshold for regression detection."""
    metric: str  # min_quality, max_latency, max_tokens
    value: float
    agent: str = ""  # empty = global
    category: str = ""
    severity: str = "warning"  # warning or critical


DEFAULT_THRESHOLDS = [
    Threshold(metric="min_quality", value=3.0, severity="critical"),
    Threshold(metric="min_quality", value=4.0, severity="warning"),
    Threshold(metric="max_latency_ms", value=30000, severity="warning"),
    Threshold(metric="max_latency_ms", value=60000, severity="critical"),
    Threshold(metric="quality_drop_pct", value=10.0, severity="warning"),
    Threshold(metric="quality_drop_pct", value=20.0, severity="critical"),
    Threshold(metric="latency_increase_pct", value=50.0, severity="warning"),
    Threshold(metric="latency_increase_pct", value=100.0, severity="critical"),
]


# ---------------------------------------------------------------------------
# Custom task loader
# ---------------------------------------------------------------------------


def load_custom_tasks(yaml_path: str = "") -> list[dict]:
    """Load custom benchmark tasks from a YAML file.

    Expected format:
    ```yaml
    tasks:
      - id: my_task
        name: My Custom Task
        category: generation
        prompt: "Write a function that..."
        judge_criteria: "Should correctly..."
    ```
    """
    if not yaml_path:
        # Look for .code-agents/benchmarks.yaml in the repo
        cwd = os.getenv("TARGET_REPO_PATH", os.getcwd())
        yaml_path = os.path.join(cwd, ".code-agents", "benchmarks.yaml")

    if not os.path.isfile(yaml_path):
        return []

    try:
        import yaml  # type: ignore
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        tasks = data.get("tasks", [])
        logger.info("Loaded %d custom benchmark tasks from %s", len(tasks), yaml_path)
        return tasks
    except ImportError:
        # Fallback: try JSON
        json_path = yaml_path.replace(".yaml", ".json").replace(".yml", ".json")
        if os.path.isfile(json_path):
            with open(json_path) as f:
                data = json.loads(f.read())
            return data.get("tasks", [])
    except Exception as e:
        logger.warning("Failed to load custom tasks: %s", e)

    return []


# ---------------------------------------------------------------------------
# Regression detector
# ---------------------------------------------------------------------------


class RegressionDetector:
    """Detect quality regressions between benchmark runs."""

    def __init__(self, thresholds: list[Threshold] | None = None):
        self.thresholds = thresholds or DEFAULT_THRESHOLDS

    def _load_report(self, run_id: str) -> dict:
        """Load a benchmark report by run ID."""
        if not BENCHMARKS_DIR.exists():
            return {}

        for f in BENCHMARKS_DIR.glob("benchmark_*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("run_id") == run_id:
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        # Try loading by filename
        path = Path(run_id)
        if path.is_file():
            return json.loads(path.read_text())

        return {}

    def _latest_reports(self, n: int = 2) -> list[dict]:
        """Get the N most recent benchmark reports."""
        if not BENCHMARKS_DIR.exists():
            return []

        reports = []
        for f in sorted(BENCHMARKS_DIR.glob("benchmark_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                reports.append(data)
                if len(reports) >= n:
                    break
            except (json.JSONDecodeError, OSError):
                pass
        return reports

    def compare(
        self,
        baseline_id: str = "",
        current_id: str = "",
    ) -> ComparisonResult:
        """Compare two benchmark runs for regressions."""
        # Load reports
        if baseline_id and current_id:
            baseline = self._load_report(baseline_id)
            current = self._load_report(current_id)
        else:
            # Auto: compare last two runs
            reports = self._latest_reports(2)
            if len(reports) < 2:
                return ComparisonResult(
                    baseline_id="", current_id="",
                    alerts=[RegressionAlert(
                        metric="error", agent="", category="",
                        baseline_value=0, current_value=0,
                        delta=0, delta_pct=0, severity="info",
                        message="Need at least 2 benchmark runs to compare",
                    )],
                )
            current, baseline = reports[0], reports[1]

        if not baseline or not current:
            return ComparisonResult(
                baseline_id=baseline_id, current_id=current_id,
                alerts=[RegressionAlert(
                    metric="error", agent="", category="",
                    baseline_value=0, current_value=0,
                    delta=0, delta_pct=0, severity="critical",
                    message="Could not load one or both benchmark reports",
                )],
            )

        result = ComparisonResult(
            baseline_id=baseline.get("run_id", ""),
            current_id=current.get("run_id", ""),
            baseline_date=baseline.get("started_at", ""),
            current_date=current.get("started_at", ""),
        )

        b_summary = baseline.get("summary", {})
        c_summary = current.get("summary", {})

        # Overall comparison
        result.overall = self._compare_metrics(
            b_summary.get("avg_quality", 0),
            c_summary.get("avg_quality", 0),
            b_summary.get("avg_latency_ms", 0),
            c_summary.get("avg_latency_ms", 0),
            b_summary.get("total_tokens", 0),
            c_summary.get("total_tokens", 0),
        )

        # Per-agent comparison
        b_agents = b_summary.get("per_agent", {})
        c_agents = c_summary.get("per_agent", {})
        all_agents = set(list(b_agents.keys()) + list(c_agents.keys()))

        for agent in all_agents:
            b = b_agents.get(agent, {})
            c = c_agents.get(agent, {})

            b_quality = b.get("avg_quality", 0)
            c_quality = c.get("avg_quality", 0)
            b_latency = b.get("avg_latency_ms", 0)
            c_latency = c.get("avg_latency_ms", 0)

            result.per_agent[agent] = self._compare_metrics(
                b_quality, c_quality, b_latency, c_latency,
                b.get("total_tokens", 0), c.get("total_tokens", 0),
            )

            # Check for regressions
            if b_quality > 0 and c_quality < b_quality:
                drop_pct = ((b_quality - c_quality) / b_quality) * 100
                result.alerts.append(RegressionAlert(
                    metric="quality_drop",
                    agent=agent, category="",
                    baseline_value=b_quality, current_value=c_quality,
                    delta=c_quality - b_quality, delta_pct=-drop_pct,
                    severity="critical" if drop_pct > 20 else "warning",
                    message=f"Quality dropped {drop_pct:.1f}% for {agent}",
                ))

            if b_latency > 0 and c_latency > b_latency:
                increase_pct = ((c_latency - b_latency) / b_latency) * 100
                if increase_pct > 50:
                    result.alerts.append(RegressionAlert(
                        metric="latency_increase",
                        agent=agent, category="",
                        baseline_value=b_latency, current_value=c_latency,
                        delta=c_latency - b_latency, delta_pct=increase_pct,
                        severity="critical" if increase_pct > 100 else "warning",
                        message=f"Latency increased {increase_pct:.1f}% for {agent}",
                    ))

        # Per-category comparison
        b_cats = b_summary.get("per_category", {})
        c_cats = c_summary.get("per_category", {})
        all_cats = set(list(b_cats.keys()) + list(c_cats.keys()))

        for cat in all_cats:
            b = b_cats.get(cat, {})
            c = c_cats.get(cat, {})
            result.per_category[cat] = self._compare_metrics(
                b.get("avg_quality", 0), c.get("avg_quality", 0),
                b.get("avg_latency_ms", 0), c.get("avg_latency_ms", 0),
            )

        # Check thresholds
        result.alerts.extend(self._check_thresholds(c_summary))

        result.passed = result.critical_count == 0
        return result

    def _compare_metrics(
        self,
        b_quality: float = 0,
        c_quality: float = 0,
        b_latency: float = 0,
        c_latency: float = 0,
        b_tokens: float = 0,
        c_tokens: float = 0,
    ) -> dict:
        """Compare a pair of metrics and compute deltas."""
        def _delta_pct(old, new):
            if old == 0:
                return 0
            return round(((new - old) / old) * 100, 1)

        return {
            "quality": {
                "baseline": b_quality, "current": c_quality,
                "delta": round(c_quality - b_quality, 2),
                "delta_pct": _delta_pct(b_quality, c_quality),
            },
            "latency_ms": {
                "baseline": b_latency, "current": c_latency,
                "delta": round(c_latency - b_latency),
                "delta_pct": _delta_pct(b_latency, c_latency),
            },
            "tokens": {
                "baseline": b_tokens, "current": c_tokens,
                "delta": round(c_tokens - b_tokens),
                "delta_pct": _delta_pct(b_tokens, c_tokens),
            },
        }

    def _check_thresholds(self, summary: dict) -> list[RegressionAlert]:
        """Check current run against configured thresholds."""
        alerts = []

        avg_quality = summary.get("avg_quality", 0)
        avg_latency = summary.get("avg_latency_ms", 0)

        for t in self.thresholds:
            if t.metric == "min_quality" and avg_quality < t.value:
                alerts.append(RegressionAlert(
                    metric="min_quality", agent=t.agent, category=t.category,
                    baseline_value=t.value, current_value=avg_quality,
                    delta=avg_quality - t.value, delta_pct=0,
                    severity=t.severity,
                    message=f"Quality {avg_quality:.1f} below threshold {t.value}",
                ))
            elif t.metric == "max_latency_ms" and avg_latency > t.value:
                alerts.append(RegressionAlert(
                    metric="max_latency_ms", agent=t.agent, category=t.category,
                    baseline_value=t.value, current_value=avg_latency,
                    delta=avg_latency - t.value, delta_pct=0,
                    severity=t.severity,
                    message=f"Latency {avg_latency:.0f}ms exceeds threshold {t.value:.0f}ms",
                ))

        return alerts

    def trend(self, n: int = 10) -> list[dict]:
        """Get quality trend over the last N runs."""
        reports = self._latest_reports(n)
        trend_data = []

        for r in reversed(reports):
            s = r.get("summary", {})
            trend_data.append({
                "run_id": r.get("run_id", ""),
                "date": r.get("started_at", "")[:19],
                "avg_quality": s.get("avg_quality", 0),
                "avg_latency_ms": s.get("avg_latency_ms", 0),
                "total_tokens": s.get("total_tokens", 0),
                "tasks": s.get("total_tasks", 0),
                "success_rate": (
                    round(s.get("successful", 0) / max(s.get("total_tasks", 1), 1) * 100, 1)
                ),
            })

        return trend_data

    def export_csv(self, output_path: str = "") -> str:
        """Export benchmark history to CSV."""
        if not output_path:
            output_path = str(BENCHMARKS_DIR / "benchmark_history.csv")

        trend_data = self.trend(100)
        if not trend_data:
            return ""

        headers = list(trend_data[0].keys())
        lines = [",".join(headers)]
        for row in trend_data:
            lines.append(",".join(str(row.get(h, "")) for h in headers))

        Path(output_path).write_text("\n".join(lines))
        return output_path


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_comparison(result: ComparisonResult) -> str:
    """Format comparison result for terminal display."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        # Status
        status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
        console.print(Panel(
            f"Baseline: {result.baseline_id} ({result.baseline_date[:19]})  |  "
            f"Current: {result.current_id} ({result.current_date[:19]})  |  "
            f"Status: {status}",
            title="Benchmark Regression Check",
            border_style="green" if result.passed else "red",
        ))

        # Overall metrics
        if result.overall:
            console.print()
            table = Table(title="Overall Metrics")
            table.add_column("Metric", style="bold")
            table.add_column("Baseline", justify="right")
            table.add_column("Current", justify="right")
            table.add_column("Delta", justify="right")

            for metric_name in ("quality", "latency_ms", "tokens"):
                m = result.overall.get(metric_name, {})
                delta = m.get("delta", 0)
                delta_pct = m.get("delta_pct", 0)

                # Color based on direction
                if metric_name == "quality":
                    delta_color = "green" if delta >= 0 else "red"
                else:
                    delta_color = "red" if delta > 0 else "green"

                delta_str = f"[{delta_color}]{delta:+.1f} ({delta_pct:+.1f}%)[/{delta_color}]"

                table.add_row(
                    metric_name.replace("_", " ").title(),
                    str(m.get("baseline", "")),
                    str(m.get("current", "")),
                    delta_str,
                )
            console.print(table)

        # Per-agent comparison
        if result.per_agent:
            console.print()
            table = Table(title="Per Agent", show_lines=True)
            table.add_column("Agent", style="bold")
            table.add_column("Quality", justify="center")
            table.add_column("Latency", justify="center")
            table.add_column("Status", justify="center")

            for agent, metrics in result.per_agent.items():
                q = metrics.get("quality", {})
                l = metrics.get("latency_ms", {})

                q_delta = q.get("delta", 0)
                q_color = "green" if q_delta >= 0 else "red"
                l_delta = l.get("delta", 0)
                l_color = "green" if l_delta <= 0 else "red"

                status = "[green]OK[/green]"
                for a in result.alerts:
                    if a.agent == agent and a.severity == "critical":
                        status = "[red]FAIL[/red]"
                        break
                    elif a.agent == agent and a.severity == "warning":
                        status = "[yellow]WARN[/yellow]"

                table.add_row(
                    agent,
                    f"{q.get('current', 0)}/5 [{q_color}]({q_delta:+.1f})[/{q_color}]",
                    f"{l.get('current', 0)}ms [{l_color}]({l_delta:+.0f})[/{l_color}]",
                    status,
                )
            console.print(table)

        # Alerts
        if result.alerts:
            console.print()
            table = Table(title=f"Alerts ({len(result.alerts)})", show_lines=True)
            table.add_column("Severity", justify="center")
            table.add_column("Metric")
            table.add_column("Agent")
            table.add_column("Message", max_width=50)

            sev_colors = {"critical": "red bold", "warning": "yellow", "info": "dim"}
            for a in result.alerts:
                style = sev_colors.get(a.severity, "white")
                table.add_row(
                    f"[{style}]{a.severity.upper()}[/{style}]",
                    a.metric, a.agent or "global", a.message,
                )
            console.print(table)

        console.print()

    except ImportError:
        lines = []
        lines.append(f"\n  Benchmark Regression: {'PASSED' if result.passed else 'FAILED'}")
        lines.append(f"  Baseline: {result.baseline_id} | Current: {result.current_id}")

        if result.alerts:
            lines.append(f"\n  Alerts ({len(result.alerts)}):")
            for a in result.alerts:
                lines.append(f"    [{a.severity.upper()}] {a.message}")

        lines.append("")
        print("\n".join(lines))

    return ""


def format_trend(trend_data: list[dict]) -> str:
    """Format trend data for terminal display."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Benchmark Trend (last {len(trend_data)} runs)")
        table.add_column("Run ID", style="bold")
        table.add_column("Date")
        table.add_column("Quality", justify="center")
        table.add_column("Latency", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Success", justify="center")

        for row in trend_data:
            q = row.get("avg_quality", 0)
            q_color = "green" if q >= 4 else "yellow" if q >= 3 else "red"
            table.add_row(
                row.get("run_id", ""),
                row.get("date", ""),
                f"[{q_color}]{q}/5[/{q_color}]",
                f"{row.get('avg_latency_ms', 0):,}ms",
                f"{row.get('total_tokens', 0):,}",
                f"{row.get('success_rate', 0)}%",
            )
        console.print(table)
        console.print()

    except ImportError:
        print(f"\n  Benchmark Trend ({len(trend_data)} runs):")
        for row in trend_data:
            print(
                f"    {row.get('run_id', ''):<10} "
                f"q={row.get('avg_quality', 0)}/5  "
                f"lat={row.get('avg_latency_ms', 0)}ms  "
                f"success={row.get('success_rate', 0)}%"
            )

    return ""
