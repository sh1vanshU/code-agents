"""CLI command for mutation testing — inject mutations, verify tests catch them."""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_mutate")


def cmd_mutate_test():
    """Run mutation testing to find weak spots in your test suite.

    Usage:
      code-agents mutate-test                        # auto-detect target & tests
      code-agents mutate-test --target src/api.py    # mutate specific file
      code-agents mutate-test --max 100              # test up to 100 mutations
      code-agents mutate-test --timeout 60           # 60s per mutation test run
      code-agents mutate-test --format json          # JSON output
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    target = ""
    max_mutations = 50
    timeout = 30
    fmt = "text"

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--target" and i + 1 < len(args):
            target = args[i + 1]
            i += 1
        elif a == "--max" and i + 1 < len(args):
            try:
                max_mutations = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid --max value: {args[i + 1]}"))
                return
            i += 1
        elif a == "--timeout" and i + 1 < len(args):
            try:
                timeout = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid --timeout value: {args[i + 1]}"))
                return
            i += 1
        elif a == "--format" and i + 1 < len(args):
            fmt = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_mutate_test.__doc__)
            return
        i += 1

    import os
    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    print(cyan(f"\n  Mutation Testing — {target or 'auto-detect'} (max {max_mutations} mutations)\n"))

    from code_agents.testing.mutation_testing import MutationTester, format_mutation_report, format_mutation_report_json

    tester = MutationTester(cwd=cwd)
    try:
        report = tester.run(target=target, max_mutations=max_mutations)
    finally:
        tester.cleanup()

    if fmt == "json":
        print(json.dumps(format_mutation_report_json(report), indent=2))
    else:
        print(format_mutation_report(report))

    # Exit code: non-zero if score is below 80%
    if report.score < 0.8 and report.total_mutations > 0:
        print(yellow(f"  Mutation score {report.score * 100:.0f}% is below 80% threshold."))
        sys.exit(1)
