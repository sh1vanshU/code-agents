"""CLI secret-rotation command — track secret staleness and generate runbooks."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_secret_rotation")


def cmd_secret_rotation():
    """Track secret rotation status and generate rotation runbooks.

    Usage:
      code-agents secret-rotation                  # text report (90-day default)
      code-agents secret-rotation --max-age 60     # custom max age in days
      code-agents secret-rotation --json            # JSON output
      code-agents secret-rotation --runbook         # show only the runbook
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    max_age = 90
    fmt = "text"
    runbook_only = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--max-age" and i + 1 < len(args):
            try:
                max_age = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid max-age: {args[i + 1]}"))
                return
            i += 1
        elif a == "--json":
            fmt = "json"
        elif a == "--runbook":
            runbook_only = True
        elif a in ("--help", "-h"):
            print(cmd_secret_rotation.__doc__)
            return
        i += 1

    from code_agents.security.secret_rotation import (
        SecretRotationTracker,
        format_rotation_report,
        rotation_report_to_json,
    )

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for secrets (max age: {max_age} days)..."))

    tracker = SecretRotationTracker(cwd=repo_path)
    report = tracker.scan(max_age=max_age)

    if runbook_only:
        print(report.runbook)
    elif fmt == "json":
        print(json.dumps(rotation_report_to_json(report), indent=2))
    else:
        print(format_rotation_report(report))
