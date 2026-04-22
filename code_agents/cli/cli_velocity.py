"""CLI velocity predict command — predict sprint capacity from git history."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_velocity")


def cmd_velocity_predict():
    """Predict sprint velocity and capacity from git history.

    Usage:
      code-agents velocity-predict                  # show velocity prediction
      code-agents velocity-predict --committed 30   # check if 30 points is overcommitted
      code-agents velocity-predict --json           # JSON output
    """
    from .cli_helpers import _colors, _user_cwd
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]  # after 'velocity-predict'
    if args and args[0] in ("--help", "-h"):
        print(cmd_velocity_predict.__doc__)
        return

    committed = 0
    if "--committed" in args:
        idx = args.index("--committed")
        if idx + 1 < len(args):
            try:
                committed = int(args[idx + 1])
            except ValueError:
                print(red(f"  Invalid number: {args[idx + 1]}"))
                return

    json_output = "--json" in args

    from code_agents.domain.velocity_predict import VelocityPredictor
    predictor = VelocityPredictor(cwd=_user_cwd())

    print(f"\n  {dim('Analyzing git history...')}")
    report = predictor.predict(committed_points=committed)

    if json_output:
        import json
        print(json.dumps({
            "avg_velocity": report.avg_velocity,
            "predicted_capacity": report.predicted_capacity,
            "committed": report.committed,
            "overcommit": report.overcommit,
            "trend": report.trend,
            "confidence": report.confidence,
            "avg_complexity": report.avg_complexity,
            "weekly_velocities": report.weekly_velocities,
        }, indent=2))
        return

    print()
    print(bold("  Sprint Velocity Prediction"))
    print()

    if report.avg_velocity == 0 and report.predicted_capacity == 0:
        print(yellow("  Insufficient git history for prediction."))
        print(dim("  Need at least a few weeks of commit history."))
        print()
        return

    print(f"  {bold('Avg weekly velocity:')}  {cyan(str(report.avg_velocity))}")
    print(f"  {bold('Predicted capacity:')}   {cyan(str(report.predicted_capacity))} points (2-week sprint)")
    print(f"  {bold('Trend:')}                {report.trend}")
    print(f"  {bold('Confidence:')}           {_confidence_bar(report.confidence)}")
    print(f"  {bold('Avg complexity:')}       {report.avg_complexity}")

    if committed > 0:
        print()
        if report.overcommit:
            print(f"  {red('⚠ OVERCOMMITTED')}: {committed} committed > {report.predicted_capacity} capacity")
            overage = committed - report.predicted_capacity
            print(f"    Consider reducing scope by ~{overage} points")
        else:
            headroom = report.predicted_capacity - committed
            print(f"  {green('✓')} Committed {committed} is within capacity ({headroom} points headroom)")

    if report.weekly_velocities:
        print()
        print(f"  {bold('Weekly velocity (last {len(report.weekly_velocities)} weeks):')}")
        max_v = max(report.weekly_velocities) if report.weekly_velocities else 1
        for i, v in enumerate(report.weekly_velocities):
            bar_len = int((v / max_v) * 30) if max_v > 0 else 0
            bar = "█" * bar_len
            print(f"    W{i+1:>2}: {dim(f'{v:>6.1f}')} {cyan(bar)}")

    print()


def _confidence_bar(confidence: float) -> str:
    """Render confidence as a simple bar."""
    filled = int(confidence * 10)
    empty = 10 - filled
    return f"[{'█' * filled}{'░' * empty}] {confidence:.0%}"
