"""Agent Benchmarking — run standard tasks against backend/model combos, measure latency + quality.

Runs a suite of benchmark tasks (code generation, review, explanation, etc.) against
configurable backend/model pairs. Uses an LLM judge to score quality 1-5.
Results saved to ~/.code-agents/benchmarks/ as JSON for comparison.

Usage:
    from code_agents.testing.benchmark import BenchmarkRunner
    runner = BenchmarkRunner(agents=["code-writer"], models=["claude-sonnet-4-20250514"])
    results = await runner.run()
    runner.print_report(results)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.benchmark")

BENCHMARKS_DIR = Path.home() / ".code-agents" / "benchmarks"

# ---------------------------------------------------------------------------
# Standard benchmark tasks
# ---------------------------------------------------------------------------

DEFAULT_TASKS = [
    {
        "id": "code_gen_fizzbuzz",
        "name": "Code Generation — FizzBuzz",
        "category": "generation",
        "prompt": "Write a Python function fizzbuzz(n) that returns a list of strings from 1 to n. For multiples of 3 use 'Fizz', multiples of 5 use 'Buzz', multiples of both use 'FizzBuzz', else the number as string.",
        "judge_criteria": "Correct implementation, clean code, handles edge cases (n=0, n=1). Must return list of strings.",
    },
    {
        "id": "code_gen_binary_search",
        "name": "Code Generation — Binary Search",
        "category": "generation",
        "prompt": "Implement a binary search function in Python: binary_search(arr, target) -> int. Return the index if found, -1 if not. The array is sorted in ascending order.",
        "judge_criteria": "Correct O(log n) implementation, handles empty array, handles not-found case. No off-by-one errors.",
    },
    {
        "id": "code_review_sql_injection",
        "name": "Code Review — Security",
        "category": "review",
        "prompt": 'Review this code for issues:\n\ndef get_user(username):\n    query = f"SELECT * FROM users WHERE name = \'{username}\'"\n    return db.execute(query)\n\ndef login(request):\n    user = get_user(request.form["username"])\n    if user and user.password == request.form["password"]:\n        session["user"] = user.id\n        return redirect("/dashboard")',
        "judge_criteria": "Must identify: SQL injection, plaintext password comparison, no CSRF protection. Bonus: suggests parameterized queries, password hashing.",
    },
    {
        "id": "explain_decorator",
        "name": "Explanation — Python Decorators",
        "category": "explanation",
        "prompt": "Explain how Python decorators work, with a practical example of a retry decorator that retries a function up to 3 times on exception.",
        "judge_criteria": "Clear explanation of decorator pattern, correct retry implementation with exponential backoff or delay, proper use of functools.wraps.",
    },
    {
        "id": "refactor_extract",
        "name": "Refactoring — Extract Method",
        "category": "refactoring",
        "prompt": "Refactor this function by extracting methods:\n\ndef process_order(order):\n    # validate\n    if not order.get('items'):\n        raise ValueError('No items')\n    if not order.get('customer_id'):\n        raise ValueError('No customer')\n    for item in order['items']:\n        if item.get('quantity', 0) <= 0:\n            raise ValueError(f'Invalid quantity for {item[\"name\"]}')\n    # calculate\n    subtotal = sum(i['price'] * i['quantity'] for i in order['items'])\n    tax = subtotal * 0.1\n    shipping = 5.99 if subtotal < 50 else 0\n    total = subtotal + tax + shipping\n    # save\n    order['subtotal'] = subtotal\n    order['tax'] = tax\n    order['shipping'] = shipping\n    order['total'] = total\n    order['status'] = 'processed'\n    return order",
        "judge_criteria": "Extracts validate_order, calculate_totals, and finalize_order (or similar). Each method has single responsibility. Original function reads as high-level steps.",
    },
    {
        "id": "debug_off_by_one",
        "name": "Debugging — Off-by-one",
        "category": "debugging",
        "prompt": "Find and fix the bug:\n\ndef merge_sorted(a, b):\n    result = []\n    i = j = 0\n    while i <= len(a) and j <= len(b):\n        if a[i] <= b[j]:\n            result.append(a[i])\n            i += 1\n        else:\n            result.append(b[j])\n            j += 1\n    result.extend(a[i:])\n    result.extend(b[j:])\n    return result",
        "judge_criteria": "Identifies the off-by-one error (should be < not <=). Explains why it causes IndexError. Provides corrected code.",
    },
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Result of a single benchmark task execution."""
    task_id: str
    task_name: str
    category: str
    agent: str
    backend: str
    model: str
    response: str = ""
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    quality_score: int = 0  # 1-5, from LLM judge
    quality_notes: str = ""
    error: str = ""
    timestamp: str = ""


@dataclass
class BenchmarkReport:
    """Aggregate report for a benchmark run."""
    run_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    results: list[BenchmarkResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Quality judge
# ---------------------------------------------------------------------------


def _build_judge_prompt(task: dict, response: str) -> str:
    """Build prompt for LLM judge to score quality 1-5."""
    return f"""You are an expert code quality judge. Rate the following AI response on a scale of 1-5.

## Task
{task['prompt']}

## Evaluation Criteria
{task['judge_criteria']}

## AI Response
{response}

## Scoring Guide
1 = Wrong/useless — major errors, doesn't address the task
2 = Poor — partially addresses task but has significant issues
3 = Adequate — addresses the task with minor issues
4 = Good — correct, clean, well-explained
5 = Excellent — correct, elegant, handles edge cases, well-structured

Respond with ONLY a JSON object:
{{"score": <1-5>, "notes": "<brief explanation of score>"}}"""


async def _judge_quality(task: dict, response: str, url: str) -> tuple[int, str]:
    """Use an LLM call to judge response quality. Returns (score, notes)."""
    try:
        import httpx

        judge_prompt = _build_judge_prompt(task, response)
        payload = {
            "model": "auto",
            "messages": [{"role": "user", "content": judge_prompt}],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{url}/v1/chat/completions",
                json=payload,
            )
            if resp.status_code != 200:
                return 0, f"Judge API error: {resp.status_code}"

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON from response
            import re
            match = re.search(r'\{[^}]+\}', content)
            if match:
                result = json.loads(match.group())
                return int(result.get("score", 0)), result.get("notes", "")
            return 0, "Could not parse judge response"

    except Exception as e:
        logger.warning("Quality judge failed: %s", e)
        return 0, f"Judge error: {e}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class BenchmarkRunner:
    """Runs benchmark tasks against agent/model combinations."""

    def __init__(
        self,
        agents: list[str] | None = None,
        models: list[str] | None = None,
        tasks: list[dict] | None = None,
        url: str = "",
        judge: bool = True,
    ):
        self.agents = agents or ["code-writer"]
        self.models = models or []  # empty = use agent default
        self.tasks = tasks or DEFAULT_TASKS
        self.url = url or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
        self.judge = judge
        self.run_id = str(uuid.uuid4())[:8]

    async def _run_single(
        self, task: dict, agent: str, model: str | None = None
    ) -> BenchmarkResult:
        """Run a single benchmark task against an agent."""
        result = BenchmarkResult(
            task_id=task["id"],
            task_name=task["name"],
            category=task["category"],
            agent=agent,
            backend="",
            model=model or "default",
            timestamp=datetime.now().isoformat(),
        )

        try:
            import httpx

            payload = {
                "model": model or "auto",
                "messages": [{"role": "user", "content": task["prompt"]}],
                "stream": False,
            }

            start = time.monotonic()
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.url}/v1/chat/completions",
                    json=payload,
                    headers={"X-Agent": agent},
                )

                result.latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code != 200:
                    result.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    return result

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                result.response = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                result.input_tokens = usage.get("prompt_tokens", 0)
                result.output_tokens = usage.get("completion_tokens", 0)
                result.backend = data.get("backend", "unknown")

        except Exception as e:
            result.error = str(e)
            return result

        # Quality judging
        if self.judge and not result.error:
            score, notes = await _judge_quality(task, result.response, self.url)
            result.quality_score = score
            result.quality_notes = notes

        return result

    async def run(self, progress_callback=None) -> BenchmarkReport:
        """Run all benchmark tasks. Returns a BenchmarkReport."""
        report = BenchmarkReport(
            run_id=self.run_id,
            started_at=datetime.now().isoformat(),
        )

        total = len(self.tasks) * len(self.agents) * max(len(self.models), 1)
        completed = 0

        for agent in self.agents:
            models = self.models if self.models else [None]
            for model in models:
                for task in self.tasks:
                    result = await self._run_single(task, agent, model)
                    report.results.append(result)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total, result)

        report.finished_at = datetime.now().isoformat()
        report.summary = self._summarize(report.results)
        return report

    def _summarize(self, results: list[BenchmarkResult]) -> dict:
        """Generate summary statistics from results."""
        if not results:
            return {}

        valid = [r for r in results if not r.error]
        errors = [r for r in results if r.error]

        summary = {
            "total_tasks": len(results),
            "successful": len(valid),
            "failed": len(errors),
        }

        if valid:
            summary["avg_latency_ms"] = int(sum(r.latency_ms for r in valid) / len(valid))
            summary["avg_quality"] = round(
                sum(r.quality_score for r in valid) / len(valid), 2
            )
            summary["total_tokens"] = sum(
                r.input_tokens + r.output_tokens for r in valid
            )

            # Per-agent breakdown
            agents = {}
            for r in valid:
                key = f"{r.agent}/{r.model}"
                if key not in agents:
                    agents[key] = {"scores": [], "latencies": [], "tokens": 0}
                agents[key]["scores"].append(r.quality_score)
                agents[key]["latencies"].append(r.latency_ms)
                agents[key]["tokens"] += r.input_tokens + r.output_tokens

            summary["per_agent"] = {
                k: {
                    "avg_quality": round(sum(v["scores"]) / len(v["scores"]), 2),
                    "avg_latency_ms": int(sum(v["latencies"]) / len(v["latencies"])),
                    "total_tokens": v["tokens"],
                    "tasks_run": len(v["scores"]),
                }
                for k, v in agents.items()
            }

            # Per-category breakdown
            cats = {}
            for r in valid:
                if r.category not in cats:
                    cats[r.category] = {"scores": [], "latencies": []}
                cats[r.category]["scores"].append(r.quality_score)
                cats[r.category]["latencies"].append(r.latency_ms)

            summary["per_category"] = {
                k: {
                    "avg_quality": round(sum(v["scores"]) / len(v["scores"]), 2),
                    "avg_latency_ms": int(sum(v["latencies"]) / len(v["latencies"])),
                }
                for k, v in cats.items()
            }

        return summary

    def save_report(self, report: BenchmarkReport) -> Path:
        """Save benchmark report to disk."""
        BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"benchmark_{report.run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = BENCHMARKS_DIR / filename

        data = {
            "run_id": report.run_id,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "summary": report.summary,
            "results": [asdict(r) for r in report.results],
        }

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Benchmark report saved: %s", path)
        return path

    @staticmethod
    def load_report(path: str | Path) -> dict:
        """Load a saved benchmark report."""
        return json.loads(Path(path).read_text())

    @staticmethod
    def list_reports() -> list[dict]:
        """List all saved benchmark reports (newest first)."""
        if not BENCHMARKS_DIR.exists():
            return []
        reports = []
        for f in sorted(BENCHMARKS_DIR.glob("benchmark_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                reports.append({
                    "file": str(f),
                    "run_id": data.get("run_id", ""),
                    "started_at": data.get("started_at", ""),
                    "summary": data.get("summary", {}),
                })
            except (json.JSONDecodeError, OSError):
                pass
        return reports

    @staticmethod
    def print_report(report: BenchmarkReport) -> None:
        """Pretty-print a benchmark report to terminal."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel

            console = Console()

            # Summary panel
            s = report.summary
            summary_text = (
                f"Tasks: {s.get('successful', 0)}/{s.get('total_tasks', 0)} passed  |  "
                f"Avg Quality: {s.get('avg_quality', 0)}/5  |  "
                f"Avg Latency: {s.get('avg_latency_ms', 0)}ms  |  "
                f"Total Tokens: {s.get('total_tokens', 0):,}"
            )
            console.print(Panel(summary_text, title=f"Benchmark {report.run_id}", border_style="cyan"))

            # Per-agent table
            if s.get("per_agent"):
                table = Table(title="Results by Agent/Model", show_lines=True)
                table.add_column("Agent / Model", style="bold")
                table.add_column("Quality", justify="center")
                table.add_column("Latency", justify="right")
                table.add_column("Tokens", justify="right")
                table.add_column("Tasks", justify="center")

                for key, v in s["per_agent"].items():
                    q = v["avg_quality"]
                    q_style = "green" if q >= 4 else "yellow" if q >= 3 else "red"
                    table.add_row(
                        key,
                        f"[{q_style}]{q}/5[/{q_style}]",
                        f"{v['avg_latency_ms']:,}ms",
                        f"{v['total_tokens']:,}",
                        str(v["tasks_run"]),
                    )
                console.print(table)

            # Per-category table
            if s.get("per_category"):
                table = Table(title="Results by Category")
                table.add_column("Category", style="bold")
                table.add_column("Avg Quality", justify="center")
                table.add_column("Avg Latency", justify="right")

                for cat, v in s["per_category"].items():
                    q = v["avg_quality"]
                    q_style = "green" if q >= 4 else "yellow" if q >= 3 else "red"
                    table.add_row(
                        cat,
                        f"[{q_style}]{q}/5[/{q_style}]",
                        f"{v['avg_latency_ms']:,}ms",
                    )
                console.print(table)

            # Detailed results
            table = Table(title="Detailed Results", show_lines=True)
            table.add_column("Task", style="bold", max_width=30)
            table.add_column("Agent", max_width=15)
            table.add_column("Score", justify="center")
            table.add_column("Latency", justify="right")
            table.add_column("Notes", max_width=40)

            for r in report.results:
                if r.error:
                    table.add_row(r.task_name, r.agent, "[red]ERR[/red]", "—", r.error[:40])
                else:
                    q = r.quality_score
                    q_style = "green" if q >= 4 else "yellow" if q >= 3 else "red"
                    table.add_row(
                        r.task_name,
                        r.agent,
                        f"[{q_style}]{q}/5[/{q_style}]",
                        f"{r.latency_ms:,}ms",
                        r.quality_notes[:40],
                    )
            console.print(table)

        except ImportError:
            # Fallback without rich
            print(f"\n=== Benchmark Report {report.run_id} ===")
            s = report.summary
            print(f"Tasks: {s.get('successful', 0)}/{s.get('total_tasks', 0)}")
            print(f"Avg Quality: {s.get('avg_quality', 0)}/5")
            print(f"Avg Latency: {s.get('avg_latency_ms', 0)}ms")
            print()
            for r in report.results:
                status = f"ERR: {r.error[:30]}" if r.error else f"{r.quality_score}/5"
                print(f"  {r.task_name:<35} {r.agent:<15} {status}")


# ---------------------------------------------------------------------------
# CLI / Slash entry points
# ---------------------------------------------------------------------------


def cmd_benchmark(args: list[str] | None = None):
    """CLI entry point for `code-agents benchmark`."""
    args = args or []

    if "list" in args or "--list" in args:
        reports = BenchmarkRunner.list_reports()
        if not reports:
            print("  No benchmark reports found.")
            return
        print("\n  Saved Benchmark Reports:")
        for r in reports[:10]:
            s = r["summary"]
            print(
                f"    {r['run_id']}  {r['started_at'][:19]}  "
                f"quality={s.get('avg_quality', '?')}/5  "
                f"latency={s.get('avg_latency_ms', '?')}ms"
            )
        print()
        return

    if "show" in args:
        # Show a specific report
        reports = BenchmarkRunner.list_reports()
        if not reports:
            print("  No reports found.")
            return
        # Find by run_id if provided
        target = None
        idx = args.index("show")
        if idx + 1 < len(args):
            run_id = args[idx + 1]
            target = next((r for r in reports if r["run_id"] == run_id), None)
        if not target:
            target = reports[0]  # latest
        data = BenchmarkRunner.load_report(target["file"])
        report = BenchmarkReport(
            run_id=data["run_id"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            summary=data["summary"],
            results=[BenchmarkResult(**r) for r in data["results"]],
        )
        BenchmarkRunner.print_report(report)
        return

    # Parse agent/model args
    agents = []
    models = []
    no_judge = "--no-judge" in args

    for i, a in enumerate(args):
        if a == "--agent" and i + 1 < len(args):
            agents.append(args[i + 1])
        elif a == "--model" and i + 1 < len(args):
            models.append(args[i + 1])

    if not agents:
        agents = ["code-writer"]

    from code_agents.cli.cli_helpers import _load_env, _server_url
    _load_env()
    url = _server_url()

    runner = BenchmarkRunner(
        agents=agents,
        models=models if models else [],
        url=url,
        judge=not no_judge,
    )

    print(f"\n  Running benchmark {runner.run_id}...")
    print(f"  Agents: {', '.join(agents)}")
    print(f"  Tasks:  {len(runner.tasks)}")
    if models:
        print(f"  Models: {', '.join(models)}")
    print()

    def progress(done, total, result):
        status = "ERR" if result.error else f"{result.quality_score}/5"
        print(f"  [{done}/{total}] {result.task_name:<35} {result.agent:<15} {status}  ({result.latency_ms}ms)")

    report = asyncio.run(runner.run(progress_callback=progress))
    path = runner.save_report(report)

    print()
    BenchmarkRunner.print_report(report)
    print(f"\n  Report saved: {path}\n")
