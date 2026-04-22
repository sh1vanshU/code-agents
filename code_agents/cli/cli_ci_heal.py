"""CLI command for CI pipeline self-healing."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_ci_heal")


def cmd_ci_heal():
    """CI pipeline self-healing — diagnose failures, apply fixes, re-trigger.

    Usage:
      code-agents ci-heal                           # auto-detect from env
      code-agents ci-heal --build 1234              # heal specific build
      code-agents ci-heal --source github           # use GitHub Actions
      code-agents ci-heal --source jenkins          # use Jenkins (default)
      code-agents ci-heal --max-attempts 5          # up to 5 attempts
      code-agents ci-heal --dry-run                 # diagnose only, no changes
      code-agents ci-heal --log-file /tmp/build.log # diagnose from log file
    """
    from .cli_helpers import _colors

    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]

    build_id = ""
    source = "jenkins"
    max_attempts = 3
    dry_run = False
    log_file = ""
    build_url = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--build", "-b") and i + 1 < len(args):
            build_id = args[i + 1]
            i += 2
        elif a in ("--source", "-s") and i + 1 < len(args):
            source = args[i + 1]
            i += 2
        elif a in ("--max-attempts", "-m") and i + 1 < len(args):
            try:
                max_attempts = int(args[i + 1])
            except ValueError:
                print(red(f"  Invalid --max-attempts value: {args[i + 1]}"))
                return
            i += 2
        elif a == "--dry-run":
            dry_run = True
            i += 1
        elif a in ("--log-file", "-f") and i + 1 < len(args):
            log_file = args[i + 1]
            i += 2
        elif a in ("--url", "-u") and i + 1 < len(args):
            build_url = args[i + 1]
            i += 2
        elif a in ("--help", "-h"):
            print(cmd_ci_heal.__doc__)
            return
        else:
            i += 1

    import os

    cwd = os.environ.get("TARGET_REPO_PATH", os.getcwd())

    # Load log text from file if specified
    log_text = ""
    if log_file:
        try:
            with open(log_file) as f:
                log_text = f.read()
            source = "generic"
        except OSError as exc:
            print(red(f"  Cannot read log file: {exc}"))
            return

    from code_agents.devops.ci_self_heal import CISelfHealer, format_heal_result

    print()
    mode = dim("[dry-run] ") if dry_run else ""
    print(bold(f"  {mode}CI Self-Healing"))
    print(dim(f"  Source: {source} | Build: {build_id or 'auto'} | Max attempts: {max_attempts}"))
    print()

    healer = CISelfHealer(cwd=cwd, max_attempts=max_attempts, dry_run=dry_run)
    result = healer.heal(
        build_url=build_url,
        build_id=build_id,
        source=source,
        log_text=log_text,
    )

    print(format_heal_result(result))
    print()

    if result.healed:
        print(green(f"  Build healed after {result.total_attempts} attempt(s)"))
    elif result.final_status == "dry_run":
        print(yellow("  Dry run complete — no changes made"))
    else:
        print(red(f"  Could not heal build: {result.final_status}"))
    print()
