"""CLI command: code-agents review — AI code review with inline terminal diff."""

from __future__ import annotations

import json
import logging
import os
import sys

from .cli_helpers import _colors, _load_env, _user_cwd

logger = logging.getLogger("code_agents.cli.cli_review")


def cmd_review(args: list[str]):
    """AI code review with inline annotated diff.

    Flags:
      --base <branch>       Base branch (default: main)
      --files <f1,f2,...>   Restrict to specific files
      --fix                 Auto-fix accepted/fixable findings
      --category <cat>      Filter: security,performance,correctness,style (default: all)
      --json                Output as JSON instead of ANSI diff
    """
    from code_agents.reviews.code_review import (
        InlineCodeReview,
        format_annotated_diff,
        interactive_review,
        apply_fixes,
        to_json,
    )

    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = "main"
    files = None
    fix = False
    category = "all"
    output_json = False

    i = 0
    while i < len(args):
        if args[i] == "--base" and i + 1 < len(args):
            base = args[i + 1]
            i += 1
        elif args[i] == "--files" and i + 1 < len(args):
            files = [f.strip() for f in args[i + 1].split(",")]
            i += 1
        elif args[i] == "--fix":
            fix = True
        elif args[i] == "--category" and i + 1 < len(args):
            category = args[i + 1]
            i += 1
        elif args[i] == "--json":
            output_json = True
        i += 1

    cwd = _user_cwd()
    print(dim(f"  Reviewing {base}...HEAD in {os.path.basename(cwd)}"))

    reviewer = InlineCodeReview(cwd=cwd, base=base, files=files, category_filter=category)
    result = reviewer.run()

    if output_json:
        print(json.dumps(to_json(result), indent=2))
        return

    print(format_annotated_diff(result))

    if fix and result.findings:
        count = apply_fixes(result, cwd)
        if count:
            print(green(f"  Applied {count} fix(es)"))
        else:
            print(dim("  No auto-fixable issues found"))
        print()
