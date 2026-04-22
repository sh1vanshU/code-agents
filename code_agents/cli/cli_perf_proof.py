"""CLI handler for Performance Profiling with Proof.

Usage:
  code-agents perf-proof --command "pytest test.py" --iterations 5
  code-agents perf-proof --command "python app.py --dry-run"
  code-agents perf-proof --command "make build" --iterations 10 --json
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_perf_proof")


def _user_cwd() -> str:
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def cmd_perf_proof(rest: list[str] | None = None):
    """Benchmark a command with statistical proof."""
    from .cli_helpers import _colors, _load_env

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    rest = rest or []
    command = ""
    iterations = 3
    json_mode = False

    # Parse args
    i = 0
    while i < len(rest):
        if rest[i] in ("--command", "-c") and i + 1 < len(rest):
            command = rest[i + 1]
            i += 2
            continue
        elif rest[i] in ("--iterations", "-n") and i + 1 < len(rest):
            try:
                iterations = int(rest[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        elif rest[i] == "--json":
            json_mode = True
            i += 1
            continue
        elif not command:
            # Bare argument treated as command
            command = rest[i]
        i += 1

    if not command:
        print(f"\n  {red('Usage: code-agents perf-proof --command \"<cmd>\" [--iterations N] [--json]')}")
        print(f"  {dim('Examples:')}")
        print(f"    code-agents perf-proof --command \"pytest tests/\" --iterations 5")
        print(f"    code-agents perf-proof --command \"python -c 'import app'\" --json")
        print(f"    code-agents perf-proof --command \"make build\"")
        return

    cwd = _user_cwd()

    from code_agents.testing.perf_proof import PerfProver, format_benchmark_rich

    prover = PerfProver(cwd=cwd)

    if not json_mode:
        print(f"\n  {bold('Performance Benchmark')}")
        print(f"  {dim(f'Command: {command} | Iterations: {iterations}')}\n")
        print(f"  {dim('Running...')}")

    result = prover.benchmark(command=command, iterations=iterations)

    if json_mode:
        import json
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_benchmark_rich(result))
