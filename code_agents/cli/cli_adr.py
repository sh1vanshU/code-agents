"""CLI adr command — generate and manage Architecture Decision Records."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_adr")


def cmd_adr():
    """Generate and manage Architecture Decision Records (ADRs).

    Usage:
      code-agents adr --decision "Use PostgreSQL for persistence"
      code-agents adr --decision "..." --context "..." --alternatives "Redis, DynamoDB"
      code-agents adr list                  # list existing ADRs
      code-agents adr --decision "..." --status accepted
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    decision = ""
    context = ""
    alternatives = ""
    status = "proposed"
    do_list = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--decision" and i + 1 < len(args):
            decision = args[i + 1]
            i += 2
        elif a == "--context" and i + 1 < len(args):
            context = args[i + 1]
            i += 2
        elif a == "--alternatives" and i + 1 < len(args):
            alternatives = args[i + 1]
            i += 2
        elif a == "--status" and i + 1 < len(args):
            status = args[i + 1]
            i += 2
        elif a == "list":
            do_list = True
            i += 1
        elif a in ("--help", "-h"):
            print(cmd_adr.__doc__)
            return
        else:
            i += 1

    from code_agents.knowledge.adr_generator import ADRGenerator, format_adr_table

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    generator = ADRGenerator(cwd=repo_path)

    if do_list:
        adrs = generator.list_adrs()
        print(format_adr_table(adrs))
        return

    if not decision:
        print(red("  --decision is required. Use --help for usage."))
        return

    print(dim(f"  Generating ADR in {repo_path}..."))
    adr = generator.generate(
        decision=decision, context=context,
        alternatives=alternatives, status=status,
    )
    filepath = generator.save(adr)

    print(green(f"  ADR-{adr.id:04d} created: {adr.title}"))
    print(dim(f"  Saved to: {filepath}"))
