"""CLI handlers for high-impact features — benchmark, debug, review-fix, workspace, pipeline, share, join."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_features")


def cmd_debug(rest: list[str] | None = None):
    """Autonomous debug engine — reproduce, trace, root-cause, fix, verify."""
    from code_agents.observability.debug_engine import cmd_debug as _run
    _run(rest)


def cmd_review_fix(rest: list[str] | None = None):
    """AI code review with auto-fix — enhanced review with fix suggestions."""
    from code_agents.cli.cli_helpers import _load_env, _colors
    _load_env()
    bold, green, yellow, red, cyan, dim = _colors()

    rest = rest or []
    import os
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    # Parse flags
    fix = "--fix" in rest
    post = "--post" in rest
    json_output = "--json" in rest
    severity_filter = ""
    pr_id = ""
    base = "main"

    for i, a in enumerate(rest):
        if a == "--severity" and i + 1 < len(rest):
            severity_filter = rest[i + 1]
        if a == "--pr" and i + 1 < len(rest):
            pr_id = rest[i + 1]
        if a == "--base" and i + 1 < len(rest):
            base = rest[i + 1]

    print()
    print(bold(cyan("  AI Code Review + Auto-Fix")))
    print(dim(f"  Reviewing {base}...HEAD"))
    if fix:
        print(dim("  Auto-fix: ON"))
    print()

    from code_agents.reviews.review_autofix import ReviewAutoFixer, format_autofix_report

    fixer = ReviewAutoFixer(cwd=cwd)
    report = fixer.run(
        base=base, fix=fix,
        post_comments=post, pr_id=pr_id,
        severity_filter=severity_filter,
    )

    if json_output:
        import json
        from dataclasses import asdict
        print(json.dumps(asdict(report), indent=2))
    else:
        format_autofix_report(report)


def cmd_bench_compare(rest: list[str] | None = None):
    """Compare two benchmark runs for regressions."""
    from code_agents.cli.cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    baseline_id = rest[0] if len(rest) >= 1 else ""
    current_id = rest[1] if len(rest) >= 2 else ""

    if "--help" in rest:
        print()
        print("  Usage: code-agents bench-compare [baseline_id] [current_id]")
        print("  If no IDs given, compares the last two runs.")
        print()
        return

    print()
    print(bold(cyan("  Benchmark Regression Check")))
    print()

    from code_agents.testing.benchmark_regression import RegressionDetector, format_comparison
    detector = RegressionDetector()
    result = detector.compare(baseline_id, current_id)
    format_comparison(result)


def cmd_bench_trend(rest: list[str] | None = None):
    """Show benchmark quality trend over time."""
    from code_agents.cli.cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    n = 10
    if rest:
        try:
            n = int(rest[0])
        except ValueError:
            pass

    from code_agents.testing.benchmark_regression import RegressionDetector, format_trend

    print()
    print(bold(cyan("  Benchmark Quality Trend")))
    print()

    detector = RegressionDetector()
    trend_data = detector.trend(n)

    if not trend_data:
        print(dim("  No benchmark data. Run 'code-agents benchmark' first."))
        print()
        return

    format_trend(trend_data)

    # Export option
    if "--export" in rest:
        path = detector.export_csv()
        if path:
            print(f"  Exported to: {path}")
            print()


def cmd_benchmark(rest: list[str] | None = None):
    """Run agent benchmarks against backend/model combos."""
    from code_agents.testing.benchmark import cmd_benchmark as _run
    _run(rest)


def cmd_workspace(rest: list[str] | None = None):
    """Manage multi-repo workspace (add, remove, list, status)."""
    from code_agents.knowledge.workspace import cmd_workspace as _run
    _run(rest)


def cmd_pipeline_exec(rest: list[str] | None = None):
    """Manage and run agent pipelines (list, create, run, templates)."""
    from code_agents.devops.pipeline import cmd_pipeline_exec as _run
    _run(rest)


def cmd_share(rest: list[str] | None = None):
    """Start a live collaboration session."""
    from code_agents.domain.collaboration import cmd_share as _run
    _run(rest)


def cmd_join(rest: list[str] | None = None):
    """Join a live collaboration session by code."""
    from code_agents.domain.collaboration import cmd_join as _run
    _run(rest)
