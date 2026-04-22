"""CLI subcommand: code-agents pr-split [--base main] [--json]."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_pr_split")


def cmd_pr_split(rest: list[str] | None = None):
    """Analyze branch diff and suggest how to split into smaller PRs.

    Usage:
      code-agents pr-split                  # default base=main
      code-agents pr-split --base develop   # custom base branch
      code-agents pr-split --json           # JSON output
    """
    rest = rest or sys.argv[2:]
    base = "main"
    as_json = False

    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--base" and i + 1 < len(rest):
            base = rest[i + 1]
            i += 2
            continue
        elif arg == "--json":
            as_json = True
        elif arg in ("--help", "-h"):
            print(cmd_pr_split.__doc__)
            return
        i += 1

    from code_agents.git_ops.pr_split import PRSplitter, format_split_report

    cwd = os.environ.get("TARGET_REPO_PATH") or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    splitter = PRSplitter(cwd=cwd)
    groups = splitter.analyze(base=base)

    if as_json:
        import json
        data = [
            {
                "name": g.name,
                "files": g.files,
                "description": g.description,
                "risk": g.risk,
                "estimated_review_min": g.estimated_review_min,
            }
            for g in groups
        ]
        print(json.dumps(data, indent=2))
    else:
        print(format_split_report(groups))
