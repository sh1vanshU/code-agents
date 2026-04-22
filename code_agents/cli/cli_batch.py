"""CLI batch command — process multiple files in parallel with a single instruction."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_batch")


def cmd_batch():
    """Batch operations — apply a single instruction across many files.

    Usage:
      code-agents batch --instruction "add error handling"
      code-agents batch --instruction "add docstrings" --pattern "src/**/*.py"
      code-agents batch --instruction "remove print statements" --files a.py b.py
      code-agents batch --instruction "add logging" --dry-run --parallel 8
    """
    import os
    import sys

    args = sys.argv[2:]
    instruction = ""
    files: list[str] = []
    pattern = ""
    dry_run = False
    parallel = 4

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--instruction" and i + 1 < len(args):
            instruction = args[i + 1]
            i += 1
        elif a == "--files":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                files.append(args[i])
                i += 1
            continue  # don't double-increment
        elif a == "--pattern" and i + 1 < len(args):
            pattern = args[i + 1]
            i += 1
        elif a == "--dry-run":
            dry_run = True
        elif a == "--parallel" and i + 1 < len(args):
            try:
                parallel = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        i += 1

    if not instruction:
        print("Usage: code-agents batch --instruction \"...\" [--files f1 f2] [--pattern '*.py'] [--dry-run] [--parallel N]")
        return

    from code_agents.devops.batch_ops import BatchOperator, format_batch_result

    cwd = os.getenv("TARGET_REPO_PATH", os.getcwd())
    operator = BatchOperator(cwd=cwd)
    result = operator.run(
        instruction=instruction,
        files=files or None,
        pattern=pattern,
        max_parallel=parallel,
        dry_run=dry_run,
    )
    print(format_batch_result(result))
