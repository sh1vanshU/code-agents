"""CLI command for dead code elimination — scan and optionally remove unused code."""

from __future__ import annotations

import logging
import os

from .cli_helpers import _colors

logger = logging.getLogger("code_agents.cli.cli_dead_code")


def cmd_dead_code_eliminate(rest: list[str] | None = None):
    """Scan for dead code and optionally remove it.

    Usage:
      code-agents dead-code-eliminate              # scan only
      code-agents dead-code-eliminate --apply      # scan + remove safe items
      code-agents dead-code-eliminate --dry-run    # preview what --apply would do
      code-agents dead-code-eliminate --json       # JSON output
    """
    import json as _json
    import dataclasses
    from code_agents.reviews.dead_code_eliminator import (
        DeadCodeEliminator, format_dead_code_report,
    )

    bold, green, yellow, red, cyan, dim = _colors()
    rest = rest or []

    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    apply_mode = "--apply" in rest
    dry_run = "--dry-run" in rest
    json_output = "--json" in rest

    if not json_output:
        print()
        print(bold(cyan("  Dead Code Eliminator")))
        print(dim(f"  Scanning {cwd}..."))
        print()

    eliminator = DeadCodeEliminator(cwd=cwd)
    report = eliminator.scan()

    if json_output:
        data = {
            "findings": [dataclasses.asdict(f) for f in report.findings],
            "total_dead_lines": report.total_dead_lines,
            "by_kind": report.by_kind,
            "safe_to_remove": [dataclasses.asdict(f) for f in report.safe_to_remove],
        }
        print(_json.dumps(data, indent=2))
        return

    print(format_dead_code_report(report))
    print()

    if dry_run:
        if report.safe_to_remove:
            print(bold(yellow("  [dry-run] Would remove:")))
            for f in report.safe_to_remove:
                print(f"    - {f.file}:{f.line} ({f.kind}: {f.name})")
            print()
        else:
            print(dim("  [dry-run] Nothing safe to auto-remove."))
            print()
    elif apply_mode:
        if report.safe_to_remove:
            count = eliminator.apply(report.safe_to_remove)
            print(bold(green(f"  Removed {count} dead code items.")))
            print(dim("  Backups saved as *.deadcode.bak"))
            print()
        else:
            print(dim("  Nothing safe to auto-remove."))
            print()
