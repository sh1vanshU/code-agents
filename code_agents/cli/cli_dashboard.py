"""CLI health dashboard — terminal view of project health metrics."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_dashboard")


def cmd_dashboard():
    """Show project health dashboard.

    Usage:
      code-agents dashboard              # full dashboard (default)
      code-agents dashboard --json       # JSON output
      code-agents dashboard --no-prs     # skip PR fetch
      code-agents dashboard --no-tests   # skip test collection
    """
    args = sys.argv[2:]

    fmt = "text"
    skip_prs = False
    skip_tests = False

    for a in args:
        if a == "--json":
            fmt = "json"
        elif a == "--no-prs":
            skip_prs = True
        elif a == "--no-tests":
            skip_tests = True
        elif a in ("--help", "-h"):
            print(cmd_dashboard.__doc__)
            return

    import os
    from code_agents.observability.health_dashboard import HealthDashboard, format_dashboard_json

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    dash = HealthDashboard(cwd)
    data = dash.collect_metrics()

    # Honour skip flags by clearing sections
    if skip_prs:
        data.open_prs = []
    if skip_tests:
        data.tests = None

    if fmt == "json":
        print(format_dashboard_json(data))
    else:
        print(dash.render_terminal(data))
