"""CLI pr-respond command — respond to PR review comments autonomously."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_pr_respond")


def cmd_pr_respond():
    """Respond to PR review comments — address feedback, push fixes, reply in-thread.

    Usage:
      code-agents pr-respond --pr 123                # respond to all actionable comments
      code-agents pr-respond --pr 123 --auto-fix     # auto-fix + reply (default)
      code-agents pr-respond --pr 123 --no-fix       # reply only, no code changes
      code-agents pr-respond --pr 123 --dry-run      # preview without committing or replying
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    pr_number: int | None = None
    auto_fix = True
    dry_run = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--pr" and i + 1 < len(args):
            try:
                pr_number = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid PR number: {args[i + 1]}"))
                return
            i += 2
            continue
        elif a == "--auto-fix":
            auto_fix = True
        elif a == "--no-fix":
            auto_fix = False
        elif a == "--dry-run":
            dry_run = True
        elif a in ("--help", "-h"):
            print(cmd_pr_respond.__doc__)
            return
        i += 1

    if pr_number is None:
        print(red("  Missing required flag: --pr <number>"))
        print(dim("  Usage: code-agents pr-respond --pr 123 [--no-fix] [--dry-run]"))
        return

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    print()
    print(bold(f"  PR Review Responder — PR #{pr_number}"))
    print(dim(f"  auto-fix={auto_fix}, dry-run={dry_run}"))
    print()

    from code_agents.git_ops.pr_thread_agent import PRThreadAgent, format_thread_responses

    agent = PRThreadAgent(cwd=cwd)

    try:
        responses = agent.respond_to_reviews(
            pr_number=pr_number,
            auto_fix=auto_fix,
            dry_run=dry_run,
        )
    except Exception as exc:
        print(red(f"  Error: {exc}"))
        return

    output = format_thread_responses(responses)
    print(output)

    if dry_run:
        print()
        print(dim("  [dry-run] No commits or replies were made."))

    print()
