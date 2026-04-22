"""CLI add-types command — scan and add type annotations to Python code."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("code_agents.cli.cli_type_adder")


def cmd_add_types():
    """Add type annotations to untyped Python functions.

    Usage:
      code-agents add-types                    # scan entire repo
      code-agents add-types --path src/        # scan specific directory
      code-agents add-types --dry-run          # preview without writing
      code-agents add-types --json             # output as JSON
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]
    path = ""
    dry_run = False
    scan_only = False
    as_json = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--path" and i + 1 < len(args):
            path = args[i + 1]
            i += 1
        elif a == "--dry-run":
            dry_run = True
        elif a == "--scan":
            scan_only = True
        elif a == "--json":
            as_json = True
        elif a in ("--help", "-h"):
            print(cmd_add_types.__doc__)
            return
        i += 1

    from code_agents.reviews.type_adder import TypeAdder, format_type_report

    repo_path = os.environ.get("TARGET_REPO_PATH", os.getcwd())
    print(dim(f"  Scanning {repo_path} for untyped functions..."))

    adder = TypeAdder(cwd=repo_path)

    if scan_only or as_json:
        untyped = adder.scan(path=path)
        if as_json:
            import json
            data = {
                "total_untyped": len(untyped),
                "functions": [
                    {
                        "file": f.file, "line": f.line, "name": f.name,
                        "params": f.params,
                        "inferred_return": f.inferred_return,
                        "inferred_params": f.inferred_params,
                    }
                    for f in untyped
                ],
            }
            print(json.dumps(data, indent=2))
        else:
            print(format_type_report(untyped))
    else:
        count = adder.add_types(path=path, dry_run=dry_run)
        mode = "preview" if dry_run else "applied"
        if count > 0:
            print(green(f"  Type annotations {mode} for {count} functions"))
        else:
            print(green("  All functions already have type annotations!"))
