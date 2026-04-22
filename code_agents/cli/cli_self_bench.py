"""CLI handler for Self-Benchmarking.

Usage:
  code-agents self-bench
  code-agents self-bench --tasks review,test,bug
  code-agents self-bench --json
  code-agents self-bench --trend
  code-agents self-bench --save
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_self_bench")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_self_bench(rest: list[str] | None = None):
    """Run agent self-benchmarks."""
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    tasks: list[str] | None = None
    json_mode = False
    show_trend = False
    save = False

    # Parse args
    i = 0
    while i < len(rest):
        if rest[i] in ("--tasks", "-t") and i + 1 < len(rest):
            tasks = [t.strip() for t in rest[i + 1].split(",") if t.strip()]
            i += 2
            continue
        elif rest[i] == "--json":
            json_mode = True
        elif rest[i] == "--trend":
            show_trend = True
        elif rest[i] == "--save":
            save = True
        i += 1

    cwd = _user_cwd()

    from code_agents.testing.self_benchmark import (
        SelfBenchmark, format_report_rich, format_trend_rich,
    )

    bench = SelfBenchmark(cwd=cwd)

    # Trend mode
    if show_trend:
        trend_data = bench.trend()
        if json_mode:
            import json
            print(json.dumps(trend_data, indent=2))
        else:
            print(format_trend_rich(trend_data))
        return

    # Run benchmarks
    if not json_mode:
        task_list = ", ".join(tasks) if tasks else "all"
        print(f"\n  {bold('Self-Benchmark')}")
        print(f"  {dim(f'Tasks: {task_list}')}\n")
        print(f"  {dim('Running benchmarks...')}")

    report = bench.run(tasks=tasks)

    if save:
        filepath = bench.save_result(report)
        if not json_mode:
            print(f"  {green(f'Saved to {filepath}')}")

    if json_mode:
        import json
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_rich(report))
