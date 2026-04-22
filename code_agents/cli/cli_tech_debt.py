"""CLI tech-debt command — deep tech debt scan with scoring and trends."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_tech_debt")


def cmd_tech_debt(rest: list[str] | None = None):
    """Deep tech debt scan — TODOs, complexity, test gaps, outdated deps, dead code.

    Usage:
      code-agents tech-debt              # full scan with score
      code-agents tech-debt --json       # JSON output
      code-agents tech-debt --save       # save snapshot for trend tracking
      code-agents tech-debt --trend      # show trend vs last snapshot
    """
    import json as _json
    import os
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    json_output = "--json" in rest
    save_snapshot = "--save" in rest

    print()
    print(bold(cyan("  Tech Debt Tracker")))
    print(dim(f"  Scanning {cwd}..."))
    print()

    from code_agents.reviews.tech_debt import TechDebtTracker, format_debt_report

    tracker = TechDebtTracker(cwd=cwd)
    report = tracker.scan()

    if json_output:
        import dataclasses
        print(_json.dumps(dataclasses.asdict(report), indent=2))
    else:
        print(format_debt_report(report))
        print()

    if save_snapshot:
        tracker.save_snapshot(report)
        print(green("  Snapshot saved for trend tracking."))
        print()
