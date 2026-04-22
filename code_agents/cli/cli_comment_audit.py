"""CLI comment-audit command — analyze comment quality in the codebase."""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_comment_audit")


def cmd_comment_audit():
    """Audit code comments for quality issues.

    Usage:
      code-agents comment-audit                    # text report
      code-agents comment-audit --json             # JSON output
      code-agents comment-audit --target src/      # scan specific path
      code-agents comment-audit --category obvious # filter by category
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    fmt = "text"
    target = ""
    category_filter = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            fmt = "json"
        elif a == "--target" and i + 1 < len(args):
            target = args[i + 1]
            i += 1
        elif a == "--category" and i + 1 < len(args):
            category_filter = args[i + 1].lower()
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_comment_audit.__doc__)
            return
        elif not a.startswith("-"):
            target = a
        i += 1

    from code_agents.reviews.comment_audit import (
        CommentAuditor,
        format_comment_report,
        comment_report_to_json,
    )

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Auditing comments in {repo_path}..."))

    auditor = CommentAuditor(cwd=repo_path)
    report = auditor.audit(target=target)

    if category_filter:
        report.findings = [
            f for f in report.findings if f.category == category_filter
        ]

    if fmt == "json":
        print(json.dumps(comment_report_to_json(report), indent=2))
    else:
        print(format_comment_report(report))
