"""Code Health Dashboard — terminal dashboard showing project health metrics.

Collects test results, coverage, complexity hotspots, and open PRs into a
single Rich panel display.  Each metric is collected independently so one
failure never blocks the others.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("code_agents.observability.health_dashboard")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TestMetrics:
    total: int
    passed: int
    failed: int
    skipped: int
    duration: float = 0.0


@dataclass
class CoverageMetrics:
    total_lines: int
    covered_lines: int
    percentage: float


@dataclass
class ComplexityInfo:
    file: str
    function: str
    score: int
    grade: str  # A-F


@dataclass
class PRInfo:
    number: int
    title: str
    author: str
    age_days: int
    status: str


@dataclass
class DashboardData:
    tests: TestMetrics | None
    coverage: CoverageMetrics | None
    complexity_hotspots: list[ComplexityInfo]
    open_prs: list[PRInfo]
    timestamp: str


# ---------------------------------------------------------------------------
# Complexity grading
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (5, "A"),
    (10, "B"),
    (15, "C"),
    (20, "D"),
    (25, "E"),
]


def _complexity_grade(score: int) -> str:
    """Return A-F grade based on cyclomatic complexity score."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score <= threshold:
            return grade
    return "F"


# ---------------------------------------------------------------------------
# AST-based complexity calculator (no radon dependency)
# ---------------------------------------------------------------------------

_BRANCH_KEYWORDS = {"If", "For", "While", "ExceptHandler", "BoolOp"}


class _ComplexityVisitor(ast.NodeVisitor):
    """Walk a Python AST and compute per-function complexity scores.

    Complexity = 1 (base) + number of branches (if/for/while/except/and/or).
    """

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.results: list[ComplexityInfo] = []
        self._stack: list[tuple[str, int]] = []  # (name, score)

    # -- helpers -----------------------------------------------------------

    def _push(self, name: str) -> None:
        self._stack.append((name, 1))  # base complexity

    def _pop(self) -> tuple[str, int]:
        return self._stack.pop()

    def _incr(self, amount: int = 1) -> None:
        if self._stack:
            name, score = self._stack[-1]
            self._stack[-1] = (name, score + amount)

    # -- node visitors -----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._push(node.name)
        self.generic_visit(node)
        name, score = self._pop()
        self.results.append(
            ComplexityInfo(
                file=self.filepath,
                function=name,
                score=score,
                grade=_complexity_grade(score),
            )
        )

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self._incr()
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        self._incr()
        self.generic_visit(node)

    visit_AsyncFor = visit_For  # noqa: N815

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        self._incr()
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        self._incr()
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        # Each `and`/`or` adds len(values)-1 branch paths
        self._incr(len(node.values) - 1)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:  # noqa: N802
        self._incr()
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802
        self._incr(len(node.generators))
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802
        self._incr(len(node.generators))
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802
        self._incr(len(node.generators))
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802
        self._incr(len(node.generators))
        self.generic_visit(node)


def _analyze_file_complexity(filepath: str) -> list[ComplexityInfo]:
    """Parse a single Python file and return per-function complexity."""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        logger.debug("Skipping %s: %s", filepath, exc)
        return []

    visitor = _ComplexityVisitor(filepath)
    visitor.visit(tree)
    return visitor.results


# ---------------------------------------------------------------------------
# HealthDashboard
# ---------------------------------------------------------------------------


class HealthDashboard:
    """Collect and render project health metrics."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self.root = Path(cwd)

    # -- public API --------------------------------------------------------

    def collect_metrics(self) -> DashboardData:
        """Collect all metrics.  Each collector may fail independently."""
        tests = self._safe(self._test_status)
        coverage = self._safe(self._coverage_status)
        complexity = self._safe(self._complexity_hotspots) or []
        prs = self._safe(self._open_prs) or []

        return DashboardData(
            tests=tests,
            coverage=coverage,
            complexity_hotspots=complexity,
            open_prs=prs,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    # -- metric collectors -------------------------------------------------

    def _test_status(self) -> TestMetrics | None:
        """Count tests via ``pytest --co -q`` (collection-only, fast)."""
        try:
            proc = subprocess.run(
                ["pytest", "--co", "-q"],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=60,
            )
            # Last meaningful line is like "120 tests collected"
            output = proc.stdout.strip()
            for line in reversed(output.splitlines()):
                line = line.strip()
                if "test" in line and "collected" in line:
                    parts = line.split()
                    total = int(parts[0])
                    return TestMetrics(
                        total=total, passed=total, failed=0, skipped=0
                    )
            # Fallback: count lines that look like test ids
            test_lines = [
                ln for ln in output.splitlines()
                if "::" in ln and ln.strip()
            ]
            if test_lines:
                return TestMetrics(
                    total=len(test_lines), passed=len(test_lines),
                    failed=0, skipped=0,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("Test collection failed: %s", exc)
        return None

    def _coverage_status(self) -> CoverageMetrics | None:
        """Parse ``coverage.json`` or ``.coverage`` if present."""
        # Try coverage.json first (generated by coverage json)
        cov_json = self.root / "coverage.json"
        if cov_json.is_file():
            try:
                data = json.loads(cov_json.read_text(encoding="utf-8"))
                totals = data.get("totals", {})
                total_lines = totals.get("num_statements", 0)
                covered = totals.get("covered_lines", 0)
                pct = totals.get("percent_covered", 0.0)
                return CoverageMetrics(
                    total_lines=total_lines,
                    covered_lines=covered,
                    percentage=round(pct, 1),
                )
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                logger.debug("Failed to parse coverage.json: %s", exc)

        # Try htmlcov/status.json (generated by coverage html)
        htmlcov_status = self.root / "htmlcov" / "status.json"
        if htmlcov_status.is_file():
            try:
                data = json.loads(htmlcov_status.read_text(encoding="utf-8"))
                totals = data.get("totals", {})
                pct = totals.get("percent_covered", 0.0)
                total_lines = totals.get("num_statements", 0)
                covered = totals.get("covered_lines", 0)
                return CoverageMetrics(
                    total_lines=total_lines,
                    covered_lines=covered,
                    percentage=round(pct, 1),
                )
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                logger.debug("Failed to parse htmlcov/status.json: %s", exc)

        return None

    def _complexity_hotspots(self, top_n: int = 10) -> list[ComplexityInfo]:
        """Scan Python files and return the top-N most complex functions."""
        all_results: list[ComplexityInfo] = []

        for py_file in self.root.rglob("*.py"):
            # Skip common non-project dirs
            rel = str(py_file.relative_to(self.root))
            if any(
                part.startswith(".")
                or part in ("node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build")
                for part in py_file.parts
            ):
                continue
            all_results.extend(_analyze_file_complexity(str(py_file)))

        # Sort by score descending, take top N
        all_results.sort(key=lambda c: c.score, reverse=True)
        return all_results[:top_n]

    def _open_prs(self) -> list[PRInfo]:
        """Fetch open PRs via ``gh pr list``."""
        try:
            proc = subprocess.run(
                [
                    "gh", "pr", "list",
                    "--json", "number,title,author,createdAt",
                    "--limit", "10",
                ],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.debug("gh pr list failed: %s", proc.stderr.strip())
                return []
            items = json.loads(proc.stdout)
            now = datetime.now(timezone.utc)
            prs: list[PRInfo] = []
            for item in items:
                created = item.get("createdAt", "")
                age_days = 0
                if created:
                    try:
                        created_dt = datetime.fromisoformat(
                            created.replace("Z", "+00:00")
                        )
                        age_days = (now - created_dt).days
                    except (ValueError, TypeError):
                        pass
                author = item.get("author", {})
                author_login = author.get("login", "") if isinstance(author, dict) else str(author)
                prs.append(
                    PRInfo(
                        number=item.get("number", 0),
                        title=item.get("title", ""),
                        author=author_login,
                        age_days=age_days,
                        status="open",
                    )
                )
            return prs
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            logger.debug("PR fetch failed: %s", exc)
            return []

    # -- rendering ---------------------------------------------------------

    def render_terminal(self, data: DashboardData) -> str:
        """Render a Rich static dashboard to string."""
        try:
            from rich.console import Console
            from rich.columns import Columns
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text
            from io import StringIO

            buf = StringIO()
            console = Console(file=buf, force_terminal=True, width=120)

            top_panels: list[Any] = []

            # -- Tests panel -----------------------------------------------
            if data.tests is not None:
                t = data.tests
                lines = []
                lines.append(f"[bold green]{t.passed}[/bold green] passed")
                if t.failed:
                    lines.append(f"[bold red]{t.failed}[/bold red] failed")
                if t.skipped:
                    lines.append(f"[yellow]{t.skipped}[/yellow] skipped")
                lines.append(f"[dim]{t.total} total[/dim]")
                if t.duration:
                    lines.append(f"[dim]{t.duration:.1f}s[/dim]")
                top_panels.append(
                    Panel("\n".join(lines), title="Tests", border_style="green", width=25)
                )
            else:
                top_panels.append(
                    Panel("[dim]No test data[/dim]", title="Tests", border_style="dim", width=25)
                )

            # -- Coverage panel --------------------------------------------
            if data.coverage is not None:
                c = data.coverage
                pct = c.percentage
                filled = int(pct / 10)
                bar = f"[green]{'█' * filled}[/green][dim]{'░' * (10 - filled)}[/dim]"
                color = "green" if pct >= 80 else "yellow" if pct >= 60 else "red"
                body = f"[bold {color}]{pct:.1f}%[/bold {color}]\n{bar}\n[dim]{c.covered_lines}/{c.total_lines} lines[/dim]"
                top_panels.append(
                    Panel(body, title="Coverage", border_style=color, width=25)
                )
            else:
                top_panels.append(
                    Panel("[dim]No coverage data[/dim]", title="Coverage", border_style="dim", width=25)
                )

            # -- Complexity panel ------------------------------------------
            if data.complexity_hotspots:
                table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
                table.add_column("File", style="dim", max_width=30)
                table.add_column("Function", max_width=20)
                table.add_column("Grade", justify="center")
                table.add_column("Score", justify="right")
                for ci in data.complexity_hotspots[:5]:
                    grade_color = {
                        "A": "green", "B": "green", "C": "yellow",
                        "D": "red", "E": "red", "F": "bold red",
                    }.get(ci.grade, "white")
                    short_file = ci.file
                    try:
                        short_file = str(Path(ci.file).relative_to(self.root))
                    except ValueError:
                        pass
                    table.add_row(
                        short_file, ci.function,
                        f"[{grade_color}]{ci.grade}[/{grade_color}]",
                        str(ci.score),
                    )
                top_panels.append(
                    Panel(table, title="Complexity Hotspots", border_style="yellow", width=65)
                )
            else:
                top_panels.append(
                    Panel("[dim]No complexity data[/dim]", title="Complexity", border_style="dim", width=25)
                )

            console.print(Columns(top_panels, padding=(0, 1)))

            # -- PRs panel -------------------------------------------------
            if data.open_prs:
                pr_lines: list[str] = []
                for pr in data.open_prs:
                    age_color = "green" if pr.age_days <= 3 else "yellow" if pr.age_days <= 7 else "red"
                    title_short = pr.title[:60] + ("..." if len(pr.title) > 60 else "")
                    pr_lines.append(
                        f"[cyan]#{pr.number}[/cyan] {title_short} "
                        f"[{age_color}]({pr.age_days}d)[/{age_color}] "
                        f"[dim]-- {pr.author}[/dim]"
                    )
                console.print(
                    Panel(
                        "\n".join(pr_lines),
                        title=f"Open PRs ({len(data.open_prs)})",
                        border_style="cyan",
                    )
                )
            else:
                console.print(
                    Panel("[dim]No open PRs[/dim]", title="Open PRs", border_style="dim")
                )

            console.print(f"\n[dim]Dashboard generated at {data.timestamp}[/dim]")
            return buf.getvalue()

        except ImportError:
            return self._render_plain(data)

    def _render_plain(self, data: DashboardData) -> str:
        """Fallback plain-text rendering when Rich is not available."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  Code Health Dashboard")
        lines.append("=" * 60)

        if data.tests:
            t = data.tests
            lines.append(f"\n  Tests: {t.passed} passed, {t.failed} failed, {t.skipped} skipped ({t.total} total)")
        else:
            lines.append("\n  Tests: No data")

        if data.coverage:
            c = data.coverage
            lines.append(f"  Coverage: {c.percentage:.1f}% ({c.covered_lines}/{c.total_lines} lines)")
        else:
            lines.append("  Coverage: No data")

        if data.complexity_hotspots:
            lines.append("\n  Complexity Hotspots:")
            for ci in data.complexity_hotspots[:10]:
                lines.append(f"    {ci.grade} ({ci.score:2d})  {ci.file}:{ci.function}")
        else:
            lines.append("\n  Complexity: No data")

        if data.open_prs:
            lines.append(f"\n  Open PRs ({len(data.open_prs)}):")
            for pr in data.open_prs:
                lines.append(f"    #{pr.number} {pr.title[:50]} ({pr.age_days}d) -- {pr.author}")
        else:
            lines.append("\n  Open PRs: None")

        lines.append(f"\n  Generated at {data.timestamp}")
        lines.append("")
        return "\n".join(lines)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _safe(fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a collector, returning None on any exception."""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("Metric collection failed (%s): %s", getattr(fn, "__name__", str(fn)), exc)
            return None


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def format_dashboard_json(data: DashboardData) -> str:
    """Serialize DashboardData to a JSON string."""
    payload: dict[str, Any] = {
        "timestamp": data.timestamp,
        "tests": None,
        "coverage": None,
        "complexity_hotspots": [],
        "open_prs": [],
    }

    if data.tests:
        t = data.tests
        payload["tests"] = {
            "total": t.total,
            "passed": t.passed,
            "failed": t.failed,
            "skipped": t.skipped,
            "duration": t.duration,
        }

    if data.coverage:
        c = data.coverage
        payload["coverage"] = {
            "total_lines": c.total_lines,
            "covered_lines": c.covered_lines,
            "percentage": c.percentage,
        }

    for ci in data.complexity_hotspots:
        payload["complexity_hotspots"].append({
            "file": ci.file,
            "function": ci.function,
            "score": ci.score,
            "grade": ci.grade,
        })

    for pr in data.open_prs:
        payload["open_prs"].append({
            "number": pr.number,
            "title": pr.title,
            "author": pr.author,
            "age_days": pr.age_days,
            "status": pr.status,
        })

    return json.dumps(payload, indent=2)
