"""CLI command for headless/CI mode — run agent tasks non-interactively."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_ci_run")


def cmd_ci_run():
    """Run agent tasks non-interactively in CI pipelines.

    Usage:
      code-agents ci-run fix-lint gen-tests review security-scan
      code-agents ci-run fix-lint --json
      code-agents ci-run audit --fail-on warning
      code-agents ci-run --list

    Tasks: fix-lint, gen-tests, update-docs, review, security-scan,
           pci-scan, dead-code, audit

    Flags:
      --json              Output JSON instead of terminal text
      --fail-on LEVEL     Fail on 'warning' (any finding) or 'critical' (errors only)
      --list              List available tasks
      -h, --help          Show this help
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]

    # Parse flags
    output_json = False
    fail_on = "critical"
    tasks: list[str] = []

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--help", "-h"):
            print(cmd_ci_run.__doc__)
            return
        elif a == "--json":
            output_json = True
            i += 1
        elif a == "--fail-on" and i + 1 < len(args):
            fail_on = args[i + 1]
            if fail_on not in ("warning", "critical"):
                print(red(f"  Invalid --fail-on value: {fail_on}. Use 'warning' or 'critical'."))
                return
            i += 2
        elif a == "--list":
            from code_agents.devops.headless_mode import HeadlessRunner

            print(bold("\n  Available CI tasks:\n"))
            for task_name in HeadlessRunner.KNOWN_TASKS:
                print(f"    {cyan(task_name)}")
            print()
            return
        elif a.startswith("-"):
            print(red(f"  Unknown flag: {a}"))
            print(dim("  Run 'code-agents ci-run --help' for usage."))
            return
        else:
            tasks.append(a)
            i += 1

    if not tasks:
        print(red("\n  No tasks specified."))
        print(dim("  Usage: code-agents ci-run fix-lint gen-tests review"))
        print(dim("  Run 'code-agents ci-run --list' to see available tasks.\n"))
        return

    # Run tasks
    from code_agents.devops.headless_mode import HeadlessRunner, format_headless_json, format_headless_report

    runner = HeadlessRunner()
    report = runner.run(tasks)

    # Output
    if output_json:
        print(format_headless_json(report))
    else:
        print(format_headless_report(report))

    # Determine exit behavior based on --fail-on
    if fail_on == "warning" and report.exit_code >= 1:
        sys.exit(report.exit_code)
    elif fail_on == "critical" and report.exit_code >= 2:
        sys.exit(report.exit_code)
    elif report.exit_code == 2:
        # Always exit non-zero on errors
        sys.exit(2)
