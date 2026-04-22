"""CLI load-test command — generate load test scripts (k6, Locust, JMeter)."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_load_test")


def cmd_load_test():
    """Generate load test scenarios from detected API endpoints.

    Usage:
      code-agents load-test                              # k6 peak scenario (default)
      code-agents load-test --format locust              # Locust format
      code-agents load-test --format jmeter              # JMeter XML
      code-agents load-test --scenario smoke             # smoke test
      code-agents load-test --scenario stress --output stress_test.js
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    fmt = "k6"
    scenario = "peak"
    output_path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            fmt = args[i + 1].lower()
            i += 1
        elif a == "--scenario" and i + 1 < len(args):
            scenario = args[i + 1].lower()
            i += 1
        elif a == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_load_test.__doc__)
            return
        i += 1

    if fmt not in ("k6", "locust", "jmeter"):
        print(red(f"  Unknown format: {fmt}"))
        print(dim("  Supported: k6, locust, jmeter"))
        return

    if scenario not in ("smoke", "peak", "stress", "soak"):
        print(red(f"  Unknown scenario: {scenario}"))
        print(dim("  Supported: smoke, peak, stress, soak"))
        return

    # Lazy import
    from code_agents.domain.load_test_gen import LoadTestGenerator, format_scenario_summary

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning endpoints in {repo_path}..."))

    try:
        gen = LoadTestGenerator(cwd=repo_path)
        script = gen.generate(scenario=scenario, format=fmt)
    except ValueError as exc:
        print(red(f"  Error: {exc}"))
        return

    # Show summary
    endpoints = gen._scan_endpoints()
    from code_agents.domain.load_test_gen import Scenario, _SCENARIO_PRESETS

    preset = _SCENARIO_PRESETS[scenario]
    spec = Scenario(
        name=scenario,
        description=preset["description"],
        endpoints=endpoints,
        rps=preset["rps"],
        duration=preset["duration"],
        ramp_up=preset["ramp_up"],
        think_time=preset["think_time"],
    )
    print()
    print(bold(f"  Load Test — {scenario.upper()} scenario ({fmt})"))
    print(format_scenario_summary(spec))
    print()

    if output_path:
        from pathlib import Path

        out = Path(output_path).resolve()
        out.write_text(script, encoding="utf-8")
        print(green(f"  Written to {out}"))
    else:
        print(script)
